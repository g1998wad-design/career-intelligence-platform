# Career Intelligence Platform — Handoff Doc for ChatGPT

Paste this whole document into a new ChatGPT conversation before asking it to continue work on
this project. It captures the architecture, conventions, past bugs/fixes, and open issues that
were built up over many sessions with Claude Code — without this, ChatGPT will re-discover (or
re-break) things that have already been solved.

Repo root: `/Users/gurkiratsingh/JS_BASICS` (git repo, branch `main`).

---

## 1. What this project is

A personal, end-to-end AI-powered job search pipeline for Gurkirat Singh Wadhawan (Analytics
Engineer background — Snowflake, SQL, Python, dbt, ERP reporting, AI automation, ~5.5 years
experience, MS Information Systems from University of Maryland). It:

1. Scrapes job postings (LinkedIn, Indeed, Google) daily/on-demand.
2. Scores each posting against his resume/skills using an LLM (0-100 match score).
3. For strong matches, auto-generates a **tailored, truthful, one-page PDF resume** per job
   (reordered/reworded bullets pulled from a fixed pool of real accomplishments — never
   fabricated).
4. Renders a browsable `resumes/index.html` table of all tailored jobs, sorted by score.
5. Optionally auto-fills (and for very clean forms, auto-submits) ATS application forms via
   Playwright.

This has grown into a small full product concept ("Career Intelligence Platform") with an MCP
server, GTM/outreach tooling, etc. — but the core daily-use loop is steps 1-4 above.

---

## 2. Core pipeline flow

```
job_fetcher.py  →  job_fetcher.db (SQLite)  →  analyze_jobs.py  →  generate_resumes.py
   (scrape)          jobs / job_analysis         (score + tailor)      (render PDFs + index)
```

- **`job_fetcher.py`** (1115 lines) — scrapes LinkedIn/Indeed/Google via the `python-jobspy`
  library, normalizes/dedupes records, pre-filters by keyword relevance, writes to `jobs` table.
  No CLI flags/argparse at all — running it with any argument (including `--help`) is silently
  ignored and it just runs the real live scrape. Config lives entirely in
  `job_fetcher_config.json` (search terms, location, `hours_old` lookback, `minimum_preliminary_score`,
  etc.), not CLI flags. Prompts interactively for a lookback window (5h/1 day/2 days/1 week) only
  when run from a real terminal (`sys.stdin.isatty()`); non-interactive invocations silently use
  the config default. Run manually, on demand (`python3 job_fetcher.py`, prefixed with
  `caffeinate -i` to stop the Mac sleeping mid-scrape) — **no scheduled/background scraping is
  currently active** (a LaunchAgent and a Claude scheduled task both existed at various points and
  were both disabled per the user's explicit preference for manual control).

- **`analyze_jobs.py`** (698 lines) — reads jobs with `status='discovered'`, calls the Anthropic
  API directly (own `ANTHROPIC_API_KEY`, not tied to any Claude subscription) in batches of 8:
  - **Scoring**: `claude-haiku-4-5-20251001`, cheap, scores every job 0-100 plus a pitch/tech
    stack/missing-skills summary.
  - **Tailoring**: `claude-sonnet-4-6`, only for jobs scoring ≥70 (`SCORE_THRESHOLD_TAILOR`) OR
    belonging to a fixed `PRIORITY_COMPANIES` list (mckinsey, bain, bcg, deloitte, accenture, pwc,
    kpmg, ey, google, amazon, meta, apple, netflix, microsoft, capital one, t. rowe price) that
    still get tailored even below 70 as long as they clear the 40-point KEEP floor
    (`SCORE_THRESHOLD_KEEP`). Below 40 = dropped/archived. 40-69 = score+pitch saved, no resume.
  - Writes results to `job_analysis` via `save_analysis()`.
  - Interleaves scoring+tailoring per-batch (not score-everything-then-tailor-everything) and
    auto-refreshes `resumes/index.html` after any batch that produces a new tailored resume, so
    the user can start applying mid-run.
  - `python3 analyze_jobs.py` runs all pending jobs; there's also a `--job-id` single-job path.

- **`generate_resumes.py`** (604 lines) — reads `job_analysis` rows with non-empty
  `tailored_resume_bullets`, renders a one-page PDF per job via ReportLab (auto-shrinks
  font/spacing/margins to force one page, down to a `MIN_SCALE` floor), and rebuilds
  `resumes/index.html` (plain static HTML table — no JS/checkboxes currently). Key CLI flags:
  ```
  python generate_resumes.py                  # all analyzed jobs ≥ default filters
  python generate_resumes.py --min-score 70    # only jobs scoring ≥70
  python generate_resumes.py --job-id abc123   # force-build one specific job's PDF
  python generate_resumes.py --max-bullets 13  # bullet cap (default 13)
  python generate_resumes.py --show-applied    # include already-applied jobs (excluded by default)
  python generate_resumes.py --since 2026-09-13  # only jobs tailored on/after this date
  ```
  **Gotcha**: with zero jobs is matches, `main()` prints a message and returns *without* touching
  `index.html` — to force-rebuild an empty/near-empty index, import the module directly and call
  `build_index([])` (or the equivalent row list) yourself.

- **`master_resume.json`** — the single source of truth for all resume content. Structure:
  - `contact`: name/location/phone/email/linkedin.
  - `core_positioning`: one paragraph bio blurb.
  - `summary_variants`: named 1-liner summaries per role family (analytics_engineering,
    data_analytics, business_intelligence, finance_systems, ai_solutions,
    technical_business_analysis, product_analytics, data_engineering).
  - `skills_keyword_bank`: 5 categories (data_warehousing, bi_reporting, programming_automation,
    ai_llm, enterprise_systems) of real, verified keywords the model is allowed to draw from.
  - `experience`: 4 entries — **Allegis Group** (current, Business Analyst II Treasury, Feb
    2024-present, 14 bullets, Employee of the Year), **Career Intelligence Platform** (this
    project itself, personal project, 7 bullets), **KPMG** (Analyst IT Consulting, Mumbai,
    2021-2022, 7 bullets), **Thrivent Federal Credit Union** (intern, 2023, 2 bullets). Each
    bullet has a `tags` list of role families it's strongest for.
  - `education`: MS Info Systems (UMD) + BE Electronics (Mumbai University).
  - Every bullet is a **real, true accomplishment** — tailoring means reordering/selecting/
    lightly rewording for keyword match, never inventing content. (One past employer, BYJU'S,
    was deliberately removed entirely per explicit user request — never re-add it.)

---

## 3. Database (`job_fetcher.db`, SQLite)

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, url TEXT, apply_url TEXT,
  title TEXT, company TEXT, location TEXT, description TEXT,
  source TEXT, company_url TEXT, company_domain TEXT, date_posted TEXT,
  job_type TEXT, remote_status TEXT, location_compatibility TEXT,
  salary_min REAL, salary_max REAL, salary_interval TEXT, currency TEXT,
  sponsorship_status TEXT, clearance_status TEXT, role_family TEXT,
  seniority TEXT, description_quality TEXT, preliminary_score INTEGER,
  search_term TEXT, search_priority INTEGER, status TEXT,
  processing_attempts INTEGER DEFAULT 0, first_seen_at TEXT,
  last_seen_at TEXT, sent_at TEXT, last_error TEXT,
  n8n_response TEXT, raw_record_json TEXT,
  applied INTEGER DEFAULT 0, applied_at TEXT, applicant_count INTEGER
);

CREATE TABLE job_analysis (
  job_id TEXT PRIMARY KEY, match_score INTEGER, tech_stack TEXT, missing_skills TEXT,
  pitch TEXT, tailored_summary TEXT, tailored_skills TEXT, tailored_resume_bullets TEXT,
  cover_letter TEXT, processed_at TEXT, lead_with_projects INTEGER DEFAULT 0
);

CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT, statistics_json TEXT);
```

`job_id` format: `{normalized_company[:20]}_{normalized_title[:30]}_{fingerprint[:10]}`
(`company_name()`/`job_title()` in `job_fetcher.py` strip legal suffixes, generic words like
remote/hybrid/contract, punctuation, casing). `fingerprint` = sha256 of
`company|title|location|year-month`, used to dedupe reposts within the scraper itself.

`jobs.status` values seen in practice: `discovered`, `analyzed`, `archived_low_match_score`,
`archived_low_relevance`, `archived_too_senior`, `archived_<clearance-reason>`, `failed`.

`tech_stack`/`missing_skills`/`tailored_skills`/`tailored_resume_bullets` are all JSON-encoded
strings stored in TEXT columns (parse with `json.loads`, guard with a `safe_json()` helper —
already exists in `generate_resumes.py`).

---

## 4. Resume rendering standards (deliberately tuned, don't casually change)

These were converged on after multiple rounds of the user reviewing actual rendered PDFs:

- **Strict one-page resumes, no exceptions.** `MIN_SCALE = 0.78` in `generate_resumes.py` (0.62
  was tried and was unreadably small; 0.88 caused most resumes to spill to a sparse 2nd page).
  `--max-bullets` default 13.
- **Per-employer bullet floors** (`MINIMUM_BULLETS_BY_COMPANY`, set identically in both
  `generate_resumes.py` and the `analyze_jobs.py` tailoring prompt): Allegis Group ≥5, KPMG ≥3,
  Career Intelligence Platform ≥3, Thrivent ≥1. That's 12 of the 13-bullet budget committed; at
  most 1 bullet of headroom goes to whichever employer is most relevant to a given job.
  Within each employer, bullets should be ordered most-to-least relevant to the specific JD.
- **No automatic bold formatting** in bullets (was built, then explicitly removed — "the bold
  point is not working properly so remove it altogether").
- **Skills list hard-capped at 15** entries, selected (not just reordered) for relevance to the
  specific job — enforced both in the prompt ("SELECT the 12-15 most relevant entries") and as a
  render-time backstop slice `tailored_skills[:15]`.
- **Summary is a hard-enforced ~170-190 char, 2-line target** — enforced unconditionally at
  render time via `_shorten_summary()` (cuts at the last comma before the limit, strips a trailing
  conjunction, never truncates mid-clause), not just left to prompt compliance.
- **Section order (Projects-first vs. Experience-first) is model-judged per job**, not a fixed
  keyword list — the tailoring prompt returns `lead_with_projects: true|false`
  (`job_analysis.lead_with_projects` column), true only when the Career Intelligence Platform
  project bullets are genuinely stronger evidence than Allegis Group's treasury/finance work for
  that specific job (e.g. AI/ML/agent-building, forward-deployed, GTM/solutions-engineering roles).
- **Transferable-tools framing is allowed, direct-experience claims are not.** If a job names a
  tool that's a close functional analog to something actually used (Power BI vs. the candidate's
  real Tableau experience; Redshift/BigQuery vs. real Snowflake; Looker vs. Tableau), the resume
  may name-check the job's tool explicitly as a transferable parallel — e.g. "BI dashboard
  development (Tableau, directly transferable to Power BI-style platforms)" — but must never read
  as if it were hands-on experience with the tool itself.
- **Hard rules, never crossed**: never change/invent/round a quantified metric; never claim
  hands-on experience with a tool never used; never introduce a claim, employer, title, or scope
  of ownership not present in the source bullet or `skills_keyword_bank`.

---

## 5. Scoring standards (`analyze_jobs.py`'s scoring prompt)

- Anchors: 90-100 exceptional, 75-89 strong, 60-74 good, 45-59 reasonable (most jobs land here),
  30-44 weak, <30 poor.
- A **deterministic, code-level years-of-experience penalty** (`infer_required_years`,
  `experience_penalty`, `apply_penalty`) is applied *after* the LLM's raw score — the LLM is
  explicitly told NOT to self-apply any years-gap deduction, to avoid double-penalizing (this was
  a real bug, found and fixed: one job's score jumped 68→82 after removing the double penalty).
- **Domain fit matters more than raw keyword overlap** (added after user feedback: "you left out a
  job yesterday because it had excel and ppt. do you really think i would not know that?"). The
  prompt now explicitly instructs: never treat ubiquitous baseline office tools (Excel, PowerPoint,
  Word, Outlook, Google Sheets/Slides) as a missing skill; only flag genuine, non-trivial capability
  gaps; when the underlying *work* is a strong match, don't let incidental unfamiliar tool names in
  the posting drag the score down.
- FAVOR: Business Analysis, Analytics Engineering, Snowflake, SQL, Data Modeling, Tableau, AI
  Automation, Product Analytics, Process Improvement, Solutions Engineering, Forward Deployed,
  Implementation Engineering. REDUCE: heavy software/backend engineering, DevOps/infra,
  manufacturing automation, PLC, embedded systems, non-data technical roles.

---

## 6. Cost control (this is genuinely important — real money was burned)

Two real cost bugs were found and fixed the same day the user flagged "it literally consumed
$6.17. cant afford that for a daily run":

1. **No prompt caching.** `tailor_resume()` was re-sending the full ~5000-token `master_resume.json`
   + instructions in every single Sonnet call. Fixed via Anthropic prompt caching: the static
   block is now sent once as a `system` parameter with `cache_control: {"type": "ephemeral"}`
   (5-minute cache lifetime, refreshes on each hit) — turns ~150 full-price resends into one cache
   write + ~150 ~90%-off cache reads.
2. **Duplicate postings independently re-tailored.** The scraper intentionally keeps the same
   employer req as separate rows per city (so the user can pick which city to apply to via
   `location_compatibility`), but this meant identical resume content was being generated and
   billed dozens of times for mass multi-city postings (one PwC req was tailored 25 separate
   times; 152/582 = 26% of all-time tailored jobs were exact company+title duplicates). Fixed with
   a dedup reuse cache in `analyze_jobs.py`'s `main()`, keyed by normalized
   `(company_name(company), job_title(title))` tuples (the same normalization functions the
   scraper uses for its own fingerprinting) — a cache hit reuses the already-tailored content with
   zero additional API cost, printed as `resume↻ (reused, same req/city-repost)`.

**Known current blocker**: as of the most recent session, the `ANTHROPIC_API_KEY` account has
**$0 credit balance** — every real API call returns `Error code: 400 ... 'Your credit balance is
too low to access the Anthropic API'`. Until the user tops up at console.anthropic.com,
`analyze_jobs.py` cannot run for real, and any one-off "tailor this job" request has to be done by
hand (see §8).

**API key location**: `/Users/gurkiratsingh/JS_BASICS/.env` (gitignored, `chmod 600`), single line
`ANTHROPIC_API_KEY=sk-ant-...`, read by `_load_api_key()`. Deliberately NOT in `~/.zshrc` or any
shell profile.

**Rejected approach, worth remembering**: don't use the `claude_agent_sdk` package (which
authenticates via a Claude Code subscription login) for batch/automation scripts that make many
calls — it shares usage pool with the interactive Claude Code session itself and will exhaust the
session's limit after a few hundred calls. Use a real `ANTHROPIC_API_KEY` with the `anthropic`
package instead; real per-token cost for this workload is small (Haiku scoring: fractions of a
cent/job; Sonnet tailoring: ~$0.02-0.04/job, only for the ~10-15% of jobs that clear the tailoring
bar).

---

## 7. Two confirmed LLM fabrication patterns to watch for

Found while hand-reviewing tailored output for large skill/domain-mismatch jobs — not
hypothetical, both actually happened in generated resumes:

1. **Fabricating years of experience or ownership under pressure.** When tailoring for a job
   requiring "7+ years" against a candidate with ~5.5 years total, the model wrote "Full-stack AI
   product builder with **7+ years**..." — a direct fabrication despite explicit hard rules
   against it. Also seen: reassigning the candidate's *total* professional years to a narrow
   specialized claim the JD wanted (e.g. "5+ years building production-grade AI/ML solutions" when
   real hands-on AI/ML experience is closer to 1-2 years), and reframing genuinely non-technical
   past work (a KPMG research report, a training-session bullet) as if it involved literal ML
   model selection/evaluation work that never happened.
2. **Inventing contact info.** `write_cover_letter()`'s prompt never included the candidate's real
   email/phone, so the model would invent a plausible-but-fake email in the closing line (3
   different fabricated variants were found across sent cover letters). Fixed by explicitly
   feeding the real contact block into the prompt with a "use exactly, never invent" instruction.
   **General lesson**: any prompt that lets a model reference supposedly-fixed real-world facts
   (contact info, dates, employer names) needs those facts explicitly fed in — omitting them
   doesn't make the model omit the reference, it makes it invent one.

**Standing practice for any large-mismatch, high-stakes single-job tailoring request**: don't
trust `tailor_resume()`'s raw output blindly even with good prompt rules — read the generated
summary and every bullet against its real `master_resume.json` source before sending anything out.
If it's fabricated, discard it and hand-write the tailored content directly from verified bullets
rather than re-prompting and hoping for a better result.

---

## 8. Manual/hand-tailoring workflow (used when the API is down, or for one-off high-stakes jobs)

This is the exact procedure used successfully multiple times this session and previous ones:

1. If the job isn't already in `job_fetcher.db`, insert it:
   ```python
   import job_fetcher as jf
   raw = {
       'title': '...', 'company': '...', 'location': '...',
       'job_url': '...', 'job_url_direct': '',  # real ATS link if known, else blank
       'description': '...',  # full JD text
       'date_posted': 'YYYY-MM-DD', 'site': 'manual', 'is_remote': True/False,
   }
   cfg = jf.load_config()
   rec = jf.normalize_record(raw, 'Manual Entry', 1, cfg)
   jf.save_job(rec)
   print(rec['job_id'])  # note this for the next step
   ```
2. Hand-write `tailored_summary` (~170-190 chars), `tailored_skills` (12-15 items from
   `skills_keyword_bank`), and `tailored_resume_bullets` (a list of
   `{"company": ..., "bullets": [...]}` dicts, respecting the per-employer floors and ordering
   rules in §4) by pulling real bullets from `master_resume.json` — reorder/lightly reword, never
   invent. Decide `lead_with_projects` per the rule in §4.
3. Save via `analyze_jobs.py`'s `save_analysis()`:
   ```python
   import json, analyze_jobs as aj
   aj.save_analysis(
       job_id, match_score, tech_stack_list, missing_skills_list, pitch_str,
       tailored_summary=summary_str,
       tailored_skills=json.dumps(skills_list),
       tailored_resume_bullets=json.dumps(bullets_list),
       cover_letter="",
       lead_with_projects=True/False,
   )
   ```
4. Generate the PDF (no API call required, works even with $0 credit):
   ```
   python3 generate_resumes.py --job-id <job_id>
   ```
5. Verify it's actually one page:
   ```python
   from pypdf import PdfReader
   print(len(PdfReader('resumes/<filename>.pdf').pages))
   ```

---

## 9. Other scripts in the repo (lighter-touch, less frequently discussed)

- **`mark_applied.py`** — marks jobs `applied=1` in the DB, individually or via `--all` (marks
  every job with non-null `tailored_resume_bullets` and no existing applied flag). Applied jobs
  are excluded from `generate_resumes.py`'s default output and index.
- **`ats_autofill.py`** (742 lines) — Playwright-based ATS form autofill. Reads
  `selected_batch.json` + `autofill_profile.json`. Detects ATS by domain (Greenhouse/Workday/
  iCIMS/Lever/Ashby/SmartRecruiters/Taleo/SuccessFactors). Fills name/email/phone/address/
  LinkedIn/website + uploads resume/cover-letter PDFs. **Never** auto-fills sensitive fields
  (sponsorship, visa, work auth, EEO race/gender/veteran/disability, salary, clearance, DOB/SSN)
  or select/radio/checkbox groups *unless* a confident match exists in `autofill_profile.json`'s
  `standard_answers` block (work authorization, sponsorship, relocation, EEO demographics, notice
  period, background-check) — those get filled only on exact text match, otherwise flagged. Opens
  all batch jobs' tabs concurrently and leaves them open for manual review/submit, **except**:
  `--auto-submit-clean` flag will click real Submit, but only for a job that filled 100% clean
  (zero flagged fields) on a single-page ATS in `AUTO_SUBMIT_ALLOWED_ATS` (greenhouse/ashby/lever/
  smartrecruiters — Workday/iCIMS/Taleo/SuccessFactors excluded as multi-step/untested). Never
  touches an authenticated LinkedIn/Indeed session — bare linkedin.com/indeed.com hosts are
  skipped with an "apply manually" message (deliberate boundary, see §10).
- **`job_pipeline_mcp.py`** — an MCP server exposing job-search/scoring/application data as
  callable tools (list_jobs, get_job, search_jobs, mark_applied, pipeline_stats) for any
  MCP-compatible AI client.
- **`export_resume_data.py`**, **`generate_master_resume.py`**, **`generate_generic_resume.py`**,
  **`backfill_cover_letters.py`**, **`apply_to_job.py`**, **`tailor_clipboard_job.py`**,
  **`resume_send.py`**, **`apply_experience_penalty.py`**, **`search_jobs.py`** — various
  one-off/utility scripts, some superseded by the current `analyze_jobs.py`/`generate_resumes.py`
  pipeline. Not central to the daily workflow.
- **`resume-site/`** — a separate Next.js-based resume/portfolio site (not part of the job pipeline
  itself).
- **`My_workflow_*.json`** files — old n8n workflow exports. **n8n/Gemini are fully retired** as of
  2026-09-14; `analyze_jobs.py` calling the Anthropic API directly replaced them entirely. Root
  cause of the old n8n "(empty response body)" bug that plagued the pipeline for a long time: the
  Gemini HTTP node was configured with a hallucinated/nonexistent model ID
  (`models/gemini-3.5-flash`).

---

## 10. Explicit boundaries / things NOT to automate

- **Never script/automate LinkedIn profile scraping or unattended actions on an authenticated
  LinkedIn session** (job posting scraping via JobSpy is fine; interactive public-post browsing is
  fine; anything scripted/unattended against the logged-in session — Easy Apply automation,
  profile scraping — is declined). This was an explicit, repeated user boundary.
- **Never fully-automate LinkedIn Easy Apply** — real account-ban risk plus per-posting screening
  questions (comp, work auth, EEO) need real answers, not guesses.
- **Never auto-submit** an ATS form with any flagged/ambiguous field, or on a multi-step
  ATS outside the allowed set.
- **Resume content is never fabricated** — every bullet, metric, tool claim must trace back to a
  real `master_resume.json` source. This is the single most important standing rule in this whole
  project.

---

## 11. Current known issues / open items (as of the end of the last Claude Code session)

- **Anthropic API credit balance is $0** — blocks all real `analyze_jobs.py` runs. Top up at
  console.anthropic.com to resume normal automated scoring/tailoring.
- A recently-fixed bug in `generate_resumes.py`: single-job `--job-id` regens without an explicit
  `--min-score` were rebuilding the *entire* index from every tailored job regardless of score,
  pulling in dead links to jobs whose PDF was never actually built (e.g. sub-70 priority-company
  jobs). Fixed by only linking an already-tailored-but-not-rebuilt job into the index if its PDF
  file genuinely exists on disk. Always still pass `--min-score` on single-job calls as a
  defensive habit.
- The interactive checkbox/"Export Selected" UI that `resumes/index.html` used to have (referenced
  in an older archived version, `resumes_archive_2026-09-07/index.html`) was lost before the
  repo's initial git commit and has not been rebuilt — the current index is a plain static HTML
  table. `selected_batch.json` for `ats_autofill.py` must currently be built by hand/script.
  Rebuilding this UI is a known "nice to have" that hasn't been prioritized.
- Under Armour-class ATS sites (careers.underarmour.com) never reach a real application form in
  `ats_autofill.py` even after fixing page-load-wait, apply-button-regex, and new-tab-follow bugs
  — root cause undiagnosed, explicitly stopped debugging rather than iterate indefinitely.
- Workday is treated as low-confidence/multi-step in `ats_autofill.py` — best-effort fill only,
  flagged for extra scrutiny, never auto-submitted.

---

## 12. How to talk to this user about this project

- Prefers **concise, direct answers** — no filler, no restating what was asked.
- Wants **root-cause fixes**, not surface patches — has explicitly pushed back when a first fix
  addressed only part of a class of problem ("this keeps happening where we find loopholes...
  think about what more we might have missed").
- Cares a lot about **truthfulness in resume content** — has given pointed, blunt feedback when
  something looked fabricated or when a scoring/tailoring decision seemed to miss obvious context
  ("do you really think i would not know that?" re: Excel/PowerPoint being flagged as a skill
  gap). Take this kind of feedback as a signal of a systemic prompt/logic flaw, not a one-off.
  Deep-domain-fit judgment is valued much more than keyword-matching literalism.
- Runs a real, high-volume daily job-application workflow off this pipeline — treat requests to
  tailor/generate a specific resume as time-sensitive and practical, not hypothetical.
