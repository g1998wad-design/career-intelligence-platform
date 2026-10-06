# Build-Your-Own Career Intelligence Platform — Handoff for a New User

Paste this entire document into a new Claude Code conversation (running in an empty project
folder) and say "build this for me." It describes, end-to-end, a personal job-search pipeline:
scrape postings every 2 hours → score them against your real resume → auto-generate a tailored,
truthful one-page PDF resume for strong matches → (optionally) help you apply. It was built over
many sessions for one person; this doc strips that out so a friend can rebuild the same system for
themselves from scratch.

**Read §0 first.** It's the one section you (the human) must act on yourself before Claude writes
anything — everything else, Claude can build.

---

## 0. What YOU have to supply (Claude cannot invent this)

This is the single most important section. The system is only as good as the real facts you feed
it, and the standing hard rule across the whole build is: **never let the model fabricate
experience.** Have these ready before you start:

1. **Your real resume content**, broken into discrete, true, reusable bullets — not a finished
   resume, a *bank* of accomplishments the model will later mix-and-match per job. For each job
   you've held: company, title, dates, location, and 5-15 bullet points, each with a real number if
   one exists (time saved, $ impact, % improvement, volume handled). You'll paste these into a
   `master_resume.json` file (template in §2).
2. **Your target roles** — the job titles you want scraped (e.g. "Data Analyst", "Business
   Intelligence Analyst", "Forward Deployed Engineer" — whatever matches what you actually do).
3. **Your target locations** and whether you want remote-only, a specific country, or multiple
   cities.
4. **Your real contact info** — email, phone, LinkedIn URL, portfolio/GitHub if any. (The model
   will invent a plausible-looking fake one if you don't feed it the real one explicitly — this
   happened in the original build and is now an explicit guardrail; see §4.)
5. **A decision on scoring/tailoring cost** (see §3): pay a small amount via a real Anthropic API
   key, or use your own Claude subscription (free, but a human/agent has to be "on" to do the
   work — either you interactively, or Claude Code scheduled tasks).
6. **If you want auto-apply later (§6, optional/advanced)**: your work-authorization status,
   sponsorship needs, and answers to common EEO/screening questions. Never let any tool guess these
   — wrong answers here have real consequences.

Nothing else in this doc requires your judgment calls up front — Claude can write all the code.

---

## 1. Architecture

```
job_fetcher.py  →  jobs.db (SQLite)  →  analyze/tailor step  →  generate_resumes.py
   (scrape)         jobs / job_analysis    (score + tailor)      (PDFs + index.html)
                                                                         │
                                                       (optional, §6)    ▼
                                              review_app.py  →  application_worker.py
                                              (approve on phone)   (autofill + submit)
```

Two independent schedules drive it, offset so the second always has fresh input from the first:

- **Scrape, every 2 hours** (OS-level cron/LaunchAgent — cheap, no LLM involved, just HTTP scraping
  via the `python-jobspy` library). Runs continuously, 9am–7pm or whatever window you want.
- **Score + tailor, every 2 hours, ~35 min after each scrape** (a **Claude Code scheduled task** —
  this is the part that needs judgment, so either the Anthropic API or an agent session does it).

---

## 2. Step 1 — The resume data file

Create `master_resume.json`. This is the single source of truth; every generated resume pulls only
from here, never invents new content. Template:

```json
{
  "_note": "Every bullet below must be TRUE. Tailoring = reordering/selecting/rewording for keyword match, never inventing content.",
  "contact": {
    "name": "Your Name",
    "location": "City, ST",
    "phone": "555-555-5555",
    "email": "you@example.com",
    "linkedin": "linkedin.com/in/yourhandle",
    "github": "github.com/yourhandle"
  },
  "core_positioning": "One paragraph: who you are, what you do, what you're targeting next.",
  "summary_variants": {
    "role_family_1": "A punchy 1-2 line summary tuned for this type of role.",
    "role_family_2": "..."
  },
  "skills_keyword_bank": {
    "category_1": ["Real tool", "Real tool", "..."],
    "category_2": ["..."]
  },
  "experience": [
    {
      "company": "Employer Name",
      "title": "Your real title",
      "dates": "Mon YYYY - Present",
      "location": "City, ST",
      "context": "One-line context if useful (e.g. team/product area)",
      "bullets": [
        {
          "text": "Cut [metric] by [X%/$/time] by doing [specific real method/tool].",
          "tags": ["role_family_1", "role_family_2"]
        }
      ]
    }
  ],
  "education": [
    {"degree": "Your degree", "school": "Your school", "dates": "YYYY-YYYY"}
  ]
}
```

**Bullet format standard** (ask Claude to enforce this everywhere it generates/tailors bullets):

- **XYZ format**: "Accomplished [X, the result] as measured by [Y, the number] by doing [Z, the
  method]." Lead with the outcome, not the task.
- **No inline bold/markup** in bullet text — bold is reserved for job title/company/dates in the
  PDF layout only.
- **Every bullet needs a real number** if the underlying fact has one. Never invent one.
- **Vary opening verbs** across the whole resume (Cut, Increased, Delivered, Reduced, Built,
  Drove...) — never repeat the same opening verb twice.
- **Tag each bullet** with the role families it's strongest for — the tailoring step uses these
  tags to pick which bullets to surface for a given job posting.
- Set a **per-employer minimum bullet count** so no job (current, past, or a personal project) gets
  starved when the tailoring step is deciding what to include.

**Hard rule, never relaxed**: no fabricated metric, tool, employer, title, or scope of ownership.
Truthful reframing/reordering/rewording is encouraged and can be aggressive — invention is not.

---

## 3. Step 2 — Scrape jobs every 2 hours

Have Claude write `job_fetcher.py` using the `python-jobspy` PyPI package (`pip install
python-jobspy`), which scrapes Indeed/LinkedIn/Google/Glassdoor/ZipRecruiter without needing your
own LinkedIn login. Config lives in `job_fetcher_config.json`:

```json
{
  "search_terms": ["Your Target Title 1", "Your Target Title 2"],
  "location": "United States",
  "sites": ["indeed", "google", "linkedin"],
  "results_per_search": 100,
  "hours_old": 24,
  "minimum_preliminary_score": 35,
  "allow_security_clearance_jobs": false
}
```

Design points worth telling Claude up front (these were all learned the hard way in the original
build, so bake them in rather than rediscovering them):

- **Dedupe by a fingerprint**, e.g. `sha256(company|title|location|year-month)`, so reposts across
  scrape runs don't pile up.
- **Don't dedupe away different-city copies of the same req** — keep them as separate rows (you may
  want to pick which city to apply to) but tag them so the scoring step can treat them as "the same
  job" and reuse one score/tailor pass instead of re-paying for each city.
- Store everything in one SQLite file, two core tables: `jobs` (raw scraped postings, `status`
  column: `discovered` → `analyzed` → `archived_*`) and `job_analysis` (score, tech_stack,
  missing_skills, pitch, tailored_summary, tailored_skills, tailored_resume_bullets, cover_letter —
  one row per job_id once scored).
- No API/LLM calls happen in this script at all — it's pure scraping, so it's free and safe to run
  unattended on a tight schedule.

---

## 4. Step 3 — Score and tailor (pick ONE path)

This is the only part of the pipeline that costs money or Claude-usage, because it needs
judgment. Two options — tell Claude which one you want:

### Option A — Pay-per-use Anthropic API (simplest, ~$0.02-0.05/job tailored)

Get an API key at console.anthropic.com, put it in a gitignored `.env` file
(`ANTHROPIC_API_KEY=sk-ant-...`, `chmod 600`). Have Claude write `analyze_jobs.py`:

- **Scoring**: cheapest/fastest model, batches of ~8 jobs, 0-100 score + a short pitch + tech-stack
  match + missing-skills list. Anchor bands: 90-100 exceptional, 75-89 strong, 60-74 good, 45-59
  reasonable, 30-44 weak, <30 poor. Drop anything under ~40.
- **Tailoring**: a stronger model, only for jobs scoring above your bar (e.g. ≥70), writes
  `tailored_summary`, `tailored_skills` (12-15 items, selected not just reordered), and
  `tailored_resume_bullets` pulled from `master_resume.json`.
- **Cost controls that matter**: (1) use prompt caching — the `master_resume.json` content doesn't
  change between calls, so send it once with `cache_control: {"type": "ephemeral"}` instead of
  re-sending it in full on every call (cuts cost by ~90% on repeat calls); (2) cache scores for
  exact-duplicate postings (same normalized company+title) so multi-city reposts of one req aren't
  independently re-tailored and re-billed.
- **Feed the real contact block into every prompt explicitly** ("use exactly, never invent") — an
  LLM asked to write a cover letter closing line *will* invent a plausible-looking fake email/phone
  if the real one isn't in its context. This actually happened in testing; don't skip this.
- **Never let the model apply a years-of-experience penalty itself and also have your code apply
  one** — pick one place to do it (code-level is more reliable/deterministic) and tell the prompt
  explicitly not to self-penalize, or you'll double-penalize candidates.

### Option B — No API cost: your own Claude Code session does the scoring (what the original build
switched to after burning real money)

Have Claude write `manual_analyze.py` as a companion script with two modes:
- `--dump-pending`: dumps not-yet-scored jobs as JSON.
- `--save results.json`: reads a JSON array of `{job_id, match_score, tech_stack, missing_skills,
  pitch, tailored_summary, tailored_skills, tailored_resume_bullets, cover_letter,
  lead_with_projects}` objects and writes them into `job_analysis`.

Then the **scoring/tailoring itself is done by a Claude Code scheduled task** (see §5) reading
`master_resume.json` and the job dump directly, applying the same rubric as Option A by hand/judgment,
and calling `--save`. This costs $0 in API fees — it uses your Claude subscription's usage instead
of a separate billed key. Tradeoff: it only runs when you have an active Claude Code
session/scheduled task slot, and large batches should be delegated to a sub-agent (via the Agent
tool) rather than done token-by-token in the main scheduled-task context.

---

## 5. Step 4 — Render tailored PDF resumes

Have Claude write `generate_resumes.py` using ReportLab:

- Reads `job_analysis` rows with non-empty `tailored_resume_bullets`.
- Renders **one page only, no exceptions** — auto-shrink font/margins/spacing within a sane floor
  (don't go below ~0.78x scale, it becomes unreadable; don't allow up to 0.88x+, it spills to a
  near-empty 2nd page).
- Hard-cap total bullets (e.g. 13) and skills list (e.g. 15), both selected for relevance to the
  specific job, not just reordered.
- Build a plain static `resumes/index.html` table sorted by match score so you can browse results
  without opening every PDF.
- Support a `--job-id` flag to force-rebuild one resume without needing an API call (useful for
  hand-tailored one-offs).

---

## 6. Step 5 — Wire up the every-2-hours schedule

Two layers, intentionally separate so a stuck scraper never blocks scoring and vice versa:

**A. OS-level cron for scraping** (macOS LaunchAgent example — adapt for Linux `cron`/`systemd
timer` or Windows Task Scheduler):

```xml
<!-- ~/Library/LaunchAgents/com.yourname.jobscraper.plist -->
<key>Label</key><string>com.yourname.jobscraper</string>
<key>ProgramArguments</key><array><string>/bin/zsh</string><string>/path/to/run_scraper.sh</string></array>
<key>StartInterval</key><integer>7200</integer>  <!-- 2 hours -->
<key>StandardOutPath</key><string>/path/to/scraper.log</string>
```
`run_scraper.sh` just does `cd` + `exec python3 job_fetcher.py` (optionally `--hours-old 3` so each
run only looks slightly further back than the interval, avoiding gaps/overlap). Use a file lock
(`fcntl.flock`) in a wrapper script so overlapping runs don't double-scrape if one run is slow.

**B. A Claude Code scheduled task for scoring/tailoring**, offset ~30-35 minutes after the scrape,
same 2-hour cadence, during your waking hours (e.g. 9am-7pm). Use Claude Code's own scheduled-task
feature (ask Claude Code itself: "create a scheduled task that runs every 2 hours from 9am-7pm").
The task's instructions should tell it to: dump pending jobs via `manual_analyze.py --dump-pending
--since-hours 3`, read `master_resume.json` and the scoring rubric, delegate to a sub-agent if the
batch is large, save via `--save`, then run `generate_resumes.py` and report a short summary (jobs
scraped, scored, tailored, dropped). If zero pending jobs, it should just stop — no wasted work.

If you went with Option A (paid API) instead, the scheduled task is much simpler: it just runs
`job_fetcher.py` then `analyze_jobs.py` then `generate_resumes.py` in sequence and reports the
counts — no agent judgment needed since the API does the scoring itself.

---

## 7. Step 6 — Optional/advanced: review + auto-apply layer

Not required for the core "find and tailor" loop, but if you want to go further:

- **A tiny local review web app** (FastAPI/Flask) on `127.0.0.1`, behind HTTP basic auth with a
  password you store only in your gitignored `.env`. Lets you browse today's tailored jobs and tap
  "prepare application" from your phone.
- **Tailscale** (not a public tunnel) to reach that local review page from your phone off your home
  network — `tailscale serve --bg http://127.0.0.1:<port>`, never Tailscale Funnel/public exposure.
- **An application worker** using Playwright that opens the employer's real ATS form (Greenhouse,
  Lever, Ashby, Workday, etc.), fills known fields (name/email/phone/address/LinkedIn) and uploads
  the tailored PDF, then **stops and waits for your explicit approval** before ever clicking
  Submit. Auto-submit (if you build it at all) should be gated to only single-page, fully-clean
  forms on a short allow-list of simple ATS platforms you've verified work reliably — never
  multi-step ATS, never a form with any ambiguous/flagged field.
- **Never auto-fill or guess**: work authorization/sponsorship, visa status, EEO
  race/gender/veteran/disability questions, salary expectations, clearance status, DOB/SSN. Only
  fill these from an explicit `standard_answers` file you write yourself, and only on an exact text
  match to a question you've pre-answered — otherwise flag it for you to answer by hand.
- **Never let any script touch your authenticated LinkedIn session** — no Easy Apply automation, no
  profile scraping. See §8 for why, and what's fine instead.

---

## 8. How LinkedIn lead-finding (outreach) actually works here — read this carefully

This is a **separate, interactive-only workflow**, not a script, and that distinction is
deliberate and non-negotiable. Three tiers, in order of what's actually acceptable:

1. **Scraping public job postings** (§3's `job_fetcher.py`, via JobSpy) — public, unauthenticated
   pages, no login session involved, impersonal factual listings. Lowest risk, fine as an
   unattended script running every 2 hours.
2. **Scraping LinkedIn profiles / harvesting personal data about individuals at scale** — **do not
   build this**, scripted or interactive. It means automating your own authenticated session to
   compile personal data about identifiable people, which is both a LinkedIn ToS problem and a
   privacy problem regardless of how it's technically implemented (even "just reading," if looped
   and scaled, is the problem).
3. **Finding people who are *publicly, voluntarily* announcing "I'm hiring"** — this is the one
   that's fine, but only done interactively, at human pace, through Claude in Chrome (or you,
   manually): screenshot the page → read what's visible → scroll → repeat. Never turned into a
   loop/script, even though the content itself is public — the risk isn't the content, it's
   *automating your authenticated account at scale*.

**The actual method, step by step** (do this yourself, or ask Claude-in-Chrome to do it
interactively, one search at a time):

1. Build a LinkedIn Content Search URL with a specific phrase likely to appear in a genuine
   hiring-manager post, sorted by recency:
   `https://www.linkedin.com/search/results/content/?keywords=%22<phrase>%22&sortBy=%22date_posted%22`
   Example phrases that surface real hiring posts (rotate through several — LinkedIn's ranking
   shifts per exact phrase, so no single query exhausts the pool): `"we are hiring" "data
   analyst"`, `"my team is hiring" "business analyst"`, `"looking to hire" "analytics"`, `"growing
   my team" "analyst"`, `"add to my team" "analyst"`.
2. For each result, read the actual post text and apply a qualification checklist before touching
   Connect:
   - Is it a genuine individual (hiring manager/founder) post, not a company page, staffing
     agency, recruiter-for-hire, or job-board aggregator repost?
   - Is the role/location one you'd actually take (right country, right seniority — e.g. skip
     people-manager roles if you want an IC role, skip roles clearly outside your target domain)?
   - Are you not already a 1st-degree connection, and not already "Pending" from a prior session?
   - Is the post recent, not stale (a 3-month-old "hiring" post is probably filled)?
   - Skip recruiters/Talent Acquisition titles even when the role itself looks like a good fit —
     they're not the hiring manager and the signal is weaker.
3. If it qualifies: open their **full profile page** (not an inline feed button — it can skip the
   note dialog), find "Connect" (sometimes direct next to Message/Follow, sometimes inside the
   "..." / More menu), always choose **"Add a note"** (never send blank), write a short (<300
   char — LinkedIn's free-tier cap) note referencing their specific post/role and your relevant
   background, then Send. Confirm via the button changing to "Pending" or a toast notification.
4. Expect heavy noise — many query rotations will return mostly recruiter/staffing spam. That's
   normal; keep rotating phrases or stop, don't force low-quality sends to hit a number.

**Why this split matters, in one sentence**: the deciding factor is never "is this public" or
"what platform is it," it's whether you're *systematically automating an authenticated session at
scale* — bounded, human-paced, interactive browsing of public content is fine; looping/scripting
the same thing, or touching private/profile data at all, is not.

---

## 9. Standing hard rules (apply to the whole system, always)

- Resume/cover-letter content is **never fabricated** — every claim traces back to a real bullet in
  your own `master_resume.json`. Truthful reframing can be aggressive; invention is a hard no.
- Any prompt that references "fixed" real-world facts (your contact info, dates, employer names)
  must have those facts **explicitly fed in** — omitting them doesn't make a model omit the
  reference, it makes it invent a plausible-sounding fake.
- Never auto-submit an application with any ambiguous/flagged field, or on an ATS you haven't
  verified end-to-end.
- Never script actions against an authenticated LinkedIn (or similar) session, even "read-only"
  ones, at scale.
- Keep API keys in a gitignored, `chmod 600` `.env` file — never in shell profiles, never
  committed.

---

## Appendix A — working `job_fetcher.py` (paste as-is, then edit the marked sections)

This is the actual scraper script, not a description of one. It's generic enough to run for any
target roles — the only parts you need to edit are flagged `>>> EDIT FOR YOUR TARGET ROLES <<<`
below: the `search_terms`/`search_term_priorities` in `DEFAULT_CONFIG`, the `POSITIVE` keyword
weights, the `NEGATIVE_TITLE` penalties, and `TITLE_RESCUE_PATTERN`. Everything else (dedup,
sponsorship/clearance detection, retry/rate-limit handling, SQLite schema) is domain-agnostic.

Requires: `pip install python-jobspy requests beautifulsoup4`.

```python
#!/usr/bin/env python3
"""JobSpy -> SQLite job scraper. Scrapes Indeed/LinkedIn/Google on a schedule,
normalizes/dedupes records, pre-filters by keyword relevance, writes eligible
postings to a local SQLite DB (status='discovered') for a separate
scoring/tailoring step to pick up. No LLM calls in this script -- pure
scraping, safe to run unattended on a tight schedule (e.g. every 2 hours).
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from jobspy import scrape_jobs

# --- Optional: LinkedIn applicant-count patch -----------------------------
# JobSpy's JobPost model has no applicant-count field, but the same
# job-detail page fetch JobSpy already makes (when linkedin_fetch_description
# is on) contains it in the HTML. This replaces LinkedIn._get_job_details with
# a copy of the original plus one extra parse step. Safe to delete this whole
# block if you don't care about applicant counts.
_LINKEDIN_APPLICANT_COUNTS: Dict[str, int] = {}


def _patch_jobspy_linkedin_applicant_count() -> None:
    try:
        from bs4 import BeautifulSoup
        from jobspy.linkedin import LinkedIn as _LinkedIn
        from jobspy.linkedin.util import (
            parse_job_level, parse_company_industry, parse_job_type,
        )
        from jobspy.model import DescriptionFormat
        from jobspy.util import remove_attributes, markdown_converter
    except ImportError:
        return  # jobspy internals changed shape; skip patch, rest still works

    def _get_job_details_with_applicants(self, job_id: str) -> dict:
        try:
            response = self.session.get(f"{self.base_url}/jobs/view/{job_id}", timeout=5)
            response.raise_for_status()
        except Exception:
            return {}
        if "linkedin.com/signup" in response.url:
            return {}

        soup = BeautifulSoup(response.text, "html.parser")
        div_content = soup.find(
            "div", class_=lambda x: x and "show-more-less-html__markup" in x
        )
        description = None
        if div_content is not None:
            div_content = remove_attributes(div_content)
            description = div_content.prettify(formatter="html")
            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
                description = markdown_converter(description)

        h3_tag = soup.find(
            "h3", string=lambda text: text and "Job function" in text.strip()
        )
        job_function = None
        if h3_tag:
            job_function_span = h3_tag.find_next(
                "span", class_="description__job-criteria-text"
            )
            if job_function_span:
                job_function = job_function_span.text.strip()

        company_logo = (
            logo_image.get("data-delayed-url")
            if (logo_image := soup.find("img", {"class": "artdeco-entity-image"}))
            else None
        )

        caption = soup.find("figcaption", class_="num-applicants__caption")
        if caption:
            m = re.search(r"[\d,]+", caption.get_text(strip=True))
            if m:
                _LINKEDIN_APPLICANT_COUNTS[job_id] = int(m.group().replace(",", ""))

        return {
            "description": description,
            "job_level": parse_job_level(soup),
            "company_industry": parse_company_industry(soup),
            "job_type": parse_job_type(soup),
            "job_url_direct": self._parse_job_url_direct(soup),
            "company_logo": company_logo,
            "job_function": job_function,
        }

    _LinkedIn._get_job_details = _get_job_details_with_applicants


_patch_jobspy_linkedin_applicant_count()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "job_fetcher_config.json"
MASTER_RESUME_PATH = BASE_DIR / "master_resume.json"
DB_PATH = BASE_DIR / "job_fetcher.db"
LOG_DIR = BASE_DIR / "job_fetcher_logs"
RAW_DIR = BASE_DIR / "raw_jobs"
LOG_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)

# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# search_terms: the literal queries sent to each job site. Keep this to
# 10-25 close variants of what you actually want -- too few misses postings
# that use slightly different phrasing, too many just slows the scrape down.
# search_term_priorities: 1 = your ideal title (gets a small score boost),
# 2/3 = still relevant but secondary.
DEFAULT_CONFIG = {
    "search_terms": [
        "Your Primary Target Title",
        "A Close Variant Title",
        "Another Adjacent Title",
    ],
    "search_term_priorities": {
        "Your Primary Target Title": 1,
    },
    "location": "United States",
    "country_indeed": "USA",
    "sites": ["indeed", "google", "linkedin"],
    "results_per_search": 100,
    "hours_old": 168,
    "fetch_linkedin_description": True,
    "batch_size": 1,
    "batch_delay_seconds": 20,
    "use_n8n": False,
    "maximum_description_characters": 30000,
    "request_timeout_seconds": 300,
    "maximum_request_attempts": 3,
    "retry_delays_seconds": [10, 30, 60],
    "test_mode": True,
    "test_mode_maximum_jobs": 3,
    "minimum_preliminary_score": 35,
    "allow_explicit_no_sponsorship": True,
    "allow_security_clearance_jobs": False,
    "minimum_salary": None,
    "store_raw_records": True,
    "save_run_logs": True,
    "skip_already_analyzed": True,
    "max_consecutive_failures": 3
}

# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# Cheap keyword-weighted pre-filter so junk never reaches the (expensive,
# judgment-requiring) scoring step. Add/remove keywords for YOUR domain --
# these examples are for a data/analytics job search.
POSITIVE = {
    "sql": 8, "python": 6, "tableau": 8, "data modeling": 8,
    "dashboard": 4, "stakeholder": 3, "kpi": 5,
    # add more keywords specific to your target roles here
}
NEGATIVE_TITLE = {
    # title keywords that should hard-penalize a posting as off-target,
    # e.g. for a data/analytics search:
    "plc": -45, "embedded": -40, "electrical engineer": -35,
}
NO_SPONSOR = [
    r"\bno (?:visa )?sponsorship\b", r"\bwill not sponsor\b",
    r"\bdoes not sponsor\b", r"\bunable to sponsor\b", r"\bcannot sponsor\b",
    r"\bwithout (?:current or future )?sponsorship\b",
    r"\bmust be authorized to work.*without sponsorship\b",
    r"\bus citizens? only\b", r"\bu\.s\. citizens? only\b",
    r"\bgreen card holders? only\b"
]
YES_SPONSOR = [r"\bvisa sponsorship (?:is )?available\b", r"\bwe sponsor\b",
               r"\bh-?1b sponsorship\b", r"\bimmigration sponsorship\b",
               r"\bvisa transfer\b"]

# Hard-reject ONLY these two categories -- everything else (no sponsorship
# mentioned, sponsorship unclear, "must be authorized to work in the US") is
# kept for review rather than silently discarded.
US_CITIZEN_ONLY = [
    r"\bus citizens? only\b", r"\bu\.s\. citizens? only\b",
    r"\bmust be a u\.s\. citizen\b", r"\bcitizenship required\b",
]
CLEARANCE_REQUIRED = [
    r"\bactive clearance\b", r"\bactive secret clearance\b",
    r"\bcurrent clearance\b", r"\btop secret\b", r"\bts/sci\b",
    r"\bsecret clearance required\b",
]

US_MARKERS = [
    "united states", "remote", "alabama", "alaska", "arizona", "arkansas",
    "california", "colorado", "connecticut", "delaware", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina", "north dakota",
    "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia"
]


@dataclass
class Stats:
    run_id: str
    started_at: str
    completed_at: str = ""
    raw_found: int = 0
    normalized: int = 0
    url_duplicates: int = 0
    fingerprint_duplicates: int = 0
    filtered_relevance: int = 0
    rescued_by_title: int = 0
    filtered_clearance: int = 0
    filtered_salary: int = 0
    filtered_seniority: int = 0
    cached_skipped: int = 0
    previously_failed_skipped: int = 0
    eligible: int = 0
    sent: int = 0
    failed: int = 0
    consecutive_failures: int = 0
    recent_failure_companies: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe(v: Any, default: Any = "") -> Any:
    if v is None:
        return default
    try:
        if isinstance(v, float) and math.isnan(v):
            return default
    except Exception:
        pass
    return v


def text(v: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(safe(v, "")))).strip()


def clean(v: Any) -> str:
    return re.sub(r"<[^>]+>", " ", text(v)).strip()


def norm(v: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", clean(v).lower())).strip()


def number(v: Any) -> Optional[float]:
    try:
        n = float(safe(v, ""))
        return None if math.isnan(n) else n
    except (TypeError, ValueError):
        return None


def digest(v: str, length: int = 16) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()[:length]


def normalize_url(url: str) -> str:
    url = text(url)
    if not url:
        return ""
    try:
        p = urlparse(url)
        ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "trk", "trackingid", "ref", "source", "src"}
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in ignored]
        return urlunparse((p.scheme or "https", (p.hostname or "").lower(),
                           p.path.rstrip("/"), "", urlencode(sorted(query)), ""))
    except Exception:
        return url


def company_name(v: str) -> str:
    value = norm(v)
    value = re.sub(r"\b(llc|inc|incorporated|corporation|corp|ltd|limited|plc|company|co)\b$", "", value).strip()
    for marker in (" via ", " on behalf of ", " through "):
        if marker in value:
            value = value.split(marker, 1)[0].strip()
    return value


def job_title(v: str) -> str:
    value = norm(v)
    for word in ("remote", "hybrid", "united states", "usa", "contract", "full time", "part time"):
        value = re.sub(rf"\b{re.escape(word)}\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def is_direct_apply_url(url: str) -> bool:
    host = domain(url)
    if not host:
        return False
    aggregators = ("linkedin.com", "indeed.com", "google.com")
    return not any(host == root or host.endswith("." + root) for root in aggregators)


def merge_direct_apply_link(job: Dict[str, Any]) -> bool:
    candidate = job.get("apply_url") or ""
    if not is_direct_apply_url(candidate):
        return False
    with db() as con:
        row = con.execute(
            "SELECT apply_url FROM jobs WHERE fingerprint=? ORDER BY last_seen_at DESC LIMIT 1",
            (job["fingerprint"],),
        ).fetchone()
        if row is None or is_direct_apply_url(row["apply_url"] or ""):
            return False
        con.execute(
            "UPDATE jobs SET apply_url=?, last_seen_at=? WHERE fingerprint=?",
            (candidate, now(), job["fingerprint"]),
        )
    return True


def year_month(date_str: str) -> str:
    v = clean(date_str)
    match = re.search(r"(\d{4})-(\d{2})", v)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return datetime.now(timezone.utc).strftime("%Y-%m")


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return cfg


LOOKBACK_CHOICES = {"1": 5, "2": 24, "3": 48, "4": 168}


def prompt_lookback_hours(default_hours: int) -> int:
    """Only prompts when run directly in a terminal by a human -- a
    scheduled/cron invocation has no attached tty, so it silently keeps the
    config default instead of hanging forever waiting for input."""
    if not sys.stdin.isatty():
        return default_hours
    print("\nHow far back should this scrape look for postings?")
    print("  1) 5 hours\n  2) 1 day\n  3) 2 days\n  4) 1 week (default)")
    choice = input("Choice [1-4, Enter for default]: ").strip()
    return LOOKBACK_CHOICES.get(choice, default_hours)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
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
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT,
          statistics_json TEXT
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS job_analysis (
          job_id TEXT PRIMARY KEY, match_score INTEGER, tech_stack TEXT,
          missing_skills TEXT, pitch TEXT, tailored_summary TEXT,
          tailored_skills TEXT, tailored_resume_bullets TEXT, cover_letter TEXT,
          processed_at TEXT, lead_with_projects INTEGER DEFAULT 0
        )""")


def seen(field: str, value: str) -> bool:
    """A job only counts as permanently "seen" once it's reached a genuinely
    terminal state: successfully analyzed, or deliberately archived. A job
    stuck at "discovered" or "failed" is retried on the next run instead of
    silently disappearing forever."""
    if not value:
        return False
    if field not in {"url", "fingerprint"}:
        raise ValueError("Invalid deduplication field")
    with db() as con:
        row = con.execute(
            f"SELECT status FROM jobs WHERE {field}=? ORDER BY last_seen_at DESC LIMIT 1",
            (value,)
        ).fetchone()
        if row is None:
            return False
        status = row["status"] or ""
        return status == "analyzed" or status.startswith("archived_")


def already_analyzed(job_id: str) -> bool:
    with db() as con:
        return con.execute(
            "SELECT 1 FROM job_analysis WHERE job_id=? LIMIT 1", (job_id,)
        ).fetchone() is not None


def save_job(j: Dict[str, Any]) -> None:
    timestamp = now()
    cols = [
        "job_id", "fingerprint", "url", "apply_url", "title", "company", "location", "description",
        "source", "company_url", "company_domain", "date_posted", "job_type",
        "remote_status", "location_compatibility", "salary_min", "salary_max",
        "salary_interval", "currency", "sponsorship_status", "clearance_status",
        "role_family", "seniority", "description_quality", "preliminary_score",
        "search_term", "search_priority", "status", "processing_attempts",
        "first_seen_at", "last_seen_at", "sent_at", "last_error", "n8n_response",
        "raw_record_json", "applicant_count"
    ]
    record = {k: j.get(k) for k in cols}
    record["first_seen_at"] = record.get("first_seen_at") or timestamp
    record["last_seen_at"] = timestamp
    record["processing_attempts"] = record.get("processing_attempts") or 0
    record["n8n_response"] = ""
    record["raw_record_json"] = json.dumps(j.get("raw_record", {}), default=str)
    placeholders = ",".join("?" for _ in cols)
    with db() as con:
        con.execute(f"INSERT OR REPLACE INTO jobs ({','.join(cols)}) VALUES ({placeholders})",
                    [record.get(c) for c in cols])


def set_status(job_id: str, status: str, error: str = "") -> None:
    with db() as con:
        con.execute("""UPDATE jobs SET status=?, last_error=?,
                       processing_attempts=processing_attempts+1,
                       sent_at=CASE WHEN ?='analyzed' THEN ? ELSE sent_at END
                       WHERE job_id=?""",
                    (status, error, status, now(), job_id))


def match_any(value: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, value, re.I) for p in patterns)


def sponsorship(description: str) -> str:
    d = clean(description).lower()
    if match_any(d, NO_SPONSOR):
        return "explicitly_no_sponsorship"
    if match_any(d, YES_SPONSOR):
        return "sponsorship_likely"
    if any(x in d for x in ("sponsorship", "visa", "h1b", "h-1b", "immigration")):
        return "sponsorship_unclear"
    return "not_mentioned"


def hard_reject_reason(description: str) -> str:
    d = clean(description).lower()
    if match_any(d, US_CITIZEN_ONLY):
        return "us_citizens_only"
    if match_any(d, CLEARANCE_REQUIRED):
        return "active_clearance_required"
    return "not_mentioned"


def remote_status(title: str, location: str, description: str, raw_remote: Any) -> str:
    combined = f"{title} {location} {description[:5000]}".lower()
    if raw_remote is True or re.search(r"\b(remote|work from home|anywhere in the us|anywhere in the united states)\b", combined):
        return "remote"
    if re.search(r"\bhybrid\b", combined):
        return "hybrid"
    if re.search(r"\b(on-site|onsite|in-office|in office)\b", combined):
        return "onsite"
    return "unknown"


def location_compatibility(location: str, remote: str) -> str:
    if remote == "remote":
        return "compatible_remote_us"
    value = norm(location)
    if not value:
        return "unknown"
    return "compatible_us" if any(marker in value for marker in US_MARKERS) else "possibly_incompatible"


def infer_seniority(title: str, description: str) -> str:
    t = norm(title)
    d = norm(description[:5000])
    if re.search(r"\b(chief|vice president|vp|director|head of)\b", t): return "director_plus"
    if re.search(r"\b(manager|principal|staff|lead)\b", t): return "lead_or_manager"
    if re.search(r"\b(senior|sr)\b", t): return "senior"
    if re.search(r"\b(junior|jr|entry|associate|intern)\b", t): return "entry"
    years = [int(x) for x in re.findall(r"(\d+)\+? years", d)]
    return "senior" if years and max(years) >= 6 else "mid_level"


# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# A free-text "role family" tag, used later to pick the right summary variant
# when tailoring. Add/rename families to match your own target domain.
def infer_role(title: str, description: str) -> str:
    value = norm(f"{title} {description[:4000]}")
    rules = [
        ("role_family_1", ["keyword", "keyword"]),
        ("role_family_2", ["keyword", "keyword"]),
    ]
    scores = [(family, sum(1 for k in keys if k in value)) for family, keys in rules]
    family, score = max(scores, key=lambda x: x[1])
    return family if score else "other"


def description_quality(description: str) -> str:
    d = clean(description)
    if not d: return "missing"
    if len(d) < 400: return "partial"
    if len(set(d.split())) < 50: return "suspected_boilerplate"
    return "complete"


def pre_score(title: str, description: str, sponsor: str, search_priority: int) -> int:
    t, all_text = norm(title), norm(f"{title} {description}")
    score = 10 + max(0, 8 - (search_priority - 1) * 2)
    for keyword, weight in POSITIVE.items():
        if keyword in all_text:
            score += weight if keyword in t else max(1, weight // 2)
    for keyword, penalty in NEGATIVE_TITLE.items():
        if keyword in t: score += penalty
    if sponsor == "explicitly_no_sponsorship": score -= 18
    elif sponsor == "sponsorship_likely": score += 8
    if description_quality(description) != "complete": score -= 8
    return max(0, min(100, score))


def normalize_record(raw: Dict[str, Any], search_term: str, priority: int,
                     cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = clean(raw.get("title"))
    company = clean(raw.get("company"))
    location = clean(raw.get("location"))
    url = normalize_url(raw.get("job_url") or raw.get("url") or "")
    if not title or not company or not url:
        return None
    apply_url = normalize_url(raw.get("job_url_direct") or "") or url
    li_id_match = re.search(r"linkedin\.com/jobs/view/(\d+)", url)
    applicant_count = _LINKEDIN_APPLICANT_COUNTS.get(li_id_match.group(1)) if li_id_match else None
    desc = clean(raw.get("description"))[:int(cfg["maximum_description_characters"])]
    date_posted = clean(raw.get("date_posted"))
    normalized_company = company_name(company)
    normalized_title = job_title(title)
    normalized_location = norm(location)
    freshness = year_month(date_posted)
    # Fingerprint includes a year-month freshness component so a repost a
    # few months later isn't silently suppressed as a duplicate.
    fingerprint = digest(
        f"{normalized_company}|{normalized_title}|{normalized_location}|{freshness}", 32
    )
    job_id = f"{normalized_company[:20].replace(' ', '_')}_{normalized_title[:30].replace(' ', '_')}_{fingerprint[:10]}"
    company_url = clean(raw.get("company_url") or raw.get("company_url_direct") or "")
    source = clean(raw.get("site") or "python-jobspy")
    remote = remote_status(title, location, desc, safe(raw.get("is_remote"), None))
    compat = location_compatibility(location, remote)
    sponsor = sponsorship(desc)
    reject_reason = hard_reject_reason(desc)
    role = infer_role(title, desc)
    seniority = infer_seniority(title, desc)
    score = pre_score(title, desc, sponsor, priority)
    return {
        "job_id": job_id, "fingerprint": fingerprint, "url": url, "apply_url": apply_url,
        "title": title, "company": company, "location": location,
        "description": desc, "source": source, "company_url": company_url,
        "company_domain": domain(company_url) or ("" if domain(url) in {"linkedin.com", "indeed.com", "google.com"} else domain(url)),
        "date_posted": date_posted,
        "job_type": clean(raw.get("job_type")),
        "remote_status": remote, "location_compatibility": compat,
        "salary_min": number(raw.get("min_amount")),
        "salary_max": number(raw.get("max_amount")),
        "salary_interval": clean(raw.get("interval")),
        "currency": clean(raw.get("currency")),
        "sponsorship_status": sponsor, "clearance_status": reject_reason,
        "role_family": role, "seniority": seniority,
        "description_quality": description_quality(desc),
        "preliminary_score": score, "search_term": search_term,
        "search_priority": priority, "status": "discovered",
        "applicant_count": applicant_count,
        "raw_record": raw
    }


# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# Rescue title-plausible jobs that the cheap keyword pre_score unfairly
# tanked (e.g. legitimate postings using vocabulary your POSITIVE dict
# doesn't cover) so they still reach a human/agent review instead of being
# silently archived. Edit the pattern to match your own target titles.
TITLE_RESCUE_PATTERN = re.compile(
    r"\b(your target title 1|your target title 2|close variant title)\b"
)
TITLE_RESCUE_EXCLUDE_PATTERN = re.compile(
    r"\b(director|vp|vice president|principal|chief|svp|head of)\b"
)
TITLE_RESCUE_MINIMUM_SCORE = 15


def eligible(j: Dict[str, Any], cfg: Dict[str, Any], stats: Stats) -> bool:
    if j["preliminary_score"] < int(cfg["minimum_preliminary_score"]):
        t = norm(j["title"])
        title_rescued = (
            j["preliminary_score"] >= TITLE_RESCUE_MINIMUM_SCORE
            and TITLE_RESCUE_PATTERN.search(t)
            and not TITLE_RESCUE_EXCLUDE_PATTERN.search(t)
        )
        if not title_rescued:
            stats.filtered_relevance += 1; j["status"] = "archived_low_relevance"; return False
        stats.rescued_by_title += 1
    if j["seniority"] == "director_plus":
        stats.filtered_seniority += 1; j["status"] = "archived_too_senior"; return False
    if j["clearance_status"] != "not_mentioned" and not cfg["allow_security_clearance_jobs"]:
        stats.filtered_clearance += 1
        j["status"] = f"archived_{j['clearance_status']}"
        return False
    minimum = cfg.get("minimum_salary")
    if minimum and j.get("salary_max") and j["salary_max"] < float(minimum):
        stats.filtered_salary += 1; j["status"] = "archived_salary"; return False
    if j["sponsorship_status"] == "explicitly_no_sponsorship" and not cfg["allow_explicit_no_sponsorship"]:
        j["status"] = "archived_sponsorship"; return False
    return True


def save_raw(run_id: str, records: List[Dict[str, Any]]) -> None:
    (RAW_DIR / f"{run_id}.json").write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")


def save_stats(stats: Stats, cfg: Dict[str, Any]) -> None:
    stats.completed_at = now()
    payload = asdict(stats)
    with db() as con:
        con.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)",
                    (stats.run_id, stats.started_at, stats.completed_at, json.dumps(payload)))
    if cfg["save_run_logs"]:
        (LOG_DIR / f"{stats.run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(hours_old_override: Optional[int] = None) -> None:
    cfg = load_config()
    if hours_old_override is not None:
        cfg["hours_old"] = hours_old_override
    else:
        cfg["hours_old"] = prompt_lookback_hours(int(cfg["hours_old"]))
    init_db()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats = Stats(run_id=run_id, started_at=now())
    raw_records: List[Dict[str, Any]] = []
    candidates: Dict[str, Dict[str, Any]] = {}

    with db() as con:
        previously_failed_ids = {
            row[0] for row in con.execute("SELECT job_id FROM jobs WHERE status='failed'")
        }
        # Some employers repost the exact same role under a fresh job_id every
        # scrape, so the job_id check above never catches it. Fall back to a
        # normalized (company, title) match.
        previously_failed_title_company = {
            (company_name(row[0]), job_title(row[1]))
            for row in con.execute("SELECT company, title FROM jobs WHERE status='failed'")
        }

    print(f"Run {run_id} started | test_mode={cfg['test_mode']}")
    terms_to_search = cfg["search_terms"][:2] if cfg["test_mode"] else cfg["search_terms"]
    for term in terms_to_search:
        priority = int(cfg.get("search_term_priorities", {}).get(term, 3))
        print(f"Scraping: {term}")
        try:
            frame = scrape_jobs(
                site_name=cfg["sites"], search_term=term, location=cfg["location"],
                results_wanted=int(cfg["results_per_search"]),
                hours_old=int(cfg["hours_old"]), country_indeed=cfg["country_indeed"],
                linkedin_fetch_description=bool(cfg["fetch_linkedin_description"])
            )
            rows = frame.to_dict(orient="records") if not frame.empty else []
            stats.raw_found += len(rows)
            raw_records.extend(rows)
            for raw in rows:
                j = normalize_record(raw, term, priority, cfg)
                if not j: continue
                stats.normalized += 1
                if seen("url", j["url"]):
                    stats.url_duplicates += 1
                    merge_direct_apply_link(j)
                    continue
                if seen("fingerprint", j["fingerprint"]):
                    stats.fingerprint_duplicates += 1
                    merge_direct_apply_link(j)
                    continue
                old = candidates.get(j["fingerprint"])
                if old:
                    stats.fingerprint_duplicates += 1
                    old_has_direct = is_direct_apply_url(old.get("apply_url", ""))
                    new_has_direct = is_direct_apply_url(j.get("apply_url", ""))
                    if j["preliminary_score"] > old["preliminary_score"]:
                        if old_has_direct and not new_has_direct:
                            j["apply_url"] = old["apply_url"]
                        candidates[j["fingerprint"]] = j
                    elif new_has_direct and not old_has_direct:
                        old["apply_url"] = j["apply_url"]
                else:
                    candidates[j["fingerprint"]] = j
        except Exception as exc:
            msg = f"{term}: {type(exc).__name__}: {exc}"
            stats.errors.append(msg)
            print(f"  Error: {msg}")

    if cfg["store_raw_records"]: save_raw(run_id, raw_records)

    eligible_jobs: List[Dict[str, Any]] = []
    for j in sorted(candidates.values(), key=lambda x: (-x["preliminary_score"], x["search_priority"])):
        is_eligible = eligible(j, cfg, stats)
        was_previously_failed = (
            j["job_id"] in previously_failed_ids
            or (company_name(j["company"]), job_title(j["title"])) in previously_failed_title_company
        )
        save_job(j)
        if is_eligible:
            if cfg.get("skip_already_analyzed", True) and already_analyzed(j["job_id"]):
                stats.cached_skipped += 1
                continue
            if was_previously_failed:
                stats.previously_failed_skipped += 1
                set_status(j["job_id"], "failed")
                continue
            eligible_jobs.append(j)

    if cfg["test_mode"]:
        eligible_jobs = eligible_jobs[:int(cfg["test_mode_maximum_jobs"])]

    stats.eligible = len(eligible_jobs)
    print(f"Eligible unique jobs: {len(eligible_jobs)} (skipped {stats.cached_skipped} already analyzed, "
          f"{stats.previously_failed_skipped} previously failed)")
    print(f"{len(eligible_jobs)} job(s) saved to DB -- run your scoring/tailoring step next.")

    save_stats(stats, cfg)
    print(json.dumps(asdict(stats), indent=2))
    print(f"Done. SQLite: {DB_PATH}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours-old", type=int, default=None,
                        help="Temporary scrape lookback in hours; does not change the saved schedule config")
    args = parser.parse_args()
    if args.hours_old is not None and args.hours_old < 1:
        parser.error("--hours-old must be at least 1")
    run(hours_old_override=args.hours_old)
```

Set `"test_mode": false` in `job_fetcher_config.json` once you've confirmed one test run (3 jobs)
works end to end — otherwise it only ever scrapes the first 2 search terms and caps results at 3.

---

## Appendix B — target-roles config template (`job_fetcher_config.json`)

This is the file you edit most often as you refine what the scraper looks for — no code changes
needed, just this JSON:

```json
{
  "search_terms": [
    "Your Primary Target Title",
    "A Close Variant Title 1",
    "A Close Variant Title 2",
    "An Adjacent Role You'd Also Take"
  ],
  "search_term_priorities": {
    "Your Primary Target Title": 1
  },
  "location": "United States",
  "country_indeed": "USA",
  "sites": ["indeed", "google", "linkedin"],
  "results_per_search": 100,
  "hours_old": 24,
  "fetch_linkedin_description": true,
  "batch_size": 8,
  "batch_delay_seconds": 20,
  "maximum_description_characters": 30000,
  "request_timeout_seconds": 300,
  "maximum_request_attempts": 3,
  "retry_delays_seconds": [10, 30, 60],
  "test_mode": false,
  "test_mode_maximum_jobs": 3,
  "minimum_preliminary_score": 35,
  "allow_explicit_no_sponsorship": true,
  "allow_security_clearance_jobs": false,
  "minimum_salary": null,
  "store_raw_records": true,
  "save_run_logs": true,
  "skip_already_analyzed": true,
  "max_consecutive_failures": 3,
  "use_n8n": false
}
```

Tuning notes:
- `search_terms`/`search_term_priorities` — the actual target-roles list; start with 3-6 while
  testing, expand once the pipeline works end to end.
- `location`/`country_indeed` — set to your target country/city; `"location": "Remote"` works too
  if you only want remote roles.
- `hours_old` — scrape lookback window; keep this slightly larger than your actual run interval
  (e.g. 3h lookback on a 2h schedule) so a slow/skipped run doesn't create a gap.
- `minimum_preliminary_score` — the cheap keyword pre-filter floor (Appendix A's `pre_score`); raise
  it if too much junk gets through, lower it if good postings are getting archived before a human/
  agent ever reads them.
- `allow_security_clearance_jobs` / `allow_explicit_no_sponsorship` — set based on your own
  citizenship/visa situation.

---

## Appendix C — working `analyze_jobs.py` (Option A: paid Anthropic API, copy-paste)

Full scoring + tailoring script. `>>> EDIT FOR YOUR TARGET ROLES <<<` marks the only things worth
customizing: `PRIORITY_COMPANIES` (dream employers you want tailored even if they score below your
normal bar) and the FAVOR/REDUCE lines in the scoring prompt. The candidate bio itself is pulled
live from your `master_resume.json` (`core_positioning` + `experience`), so you don't hand-edit a
name/years-of-experience blurb inside the script.

Requires: `pip install anthropic`, `.env` with `ANTHROPIC_API_KEY=sk-ant-...` (`chmod 600`).

```python
#!/usr/bin/env python3
"""Score, tailor, and generate cover letters for jobs using the Anthropic API.
Run this after your scraper (Appendix A) has populated the jobs table.

Usage:
    python analyze_jobs.py              # process all pending jobs
    python analyze_jobs.py --limit 50   # cap at 50 jobs this run
    python analyze_jobs.py --dry-run    # show pending jobs without analyzing
    python analyze_jobs.py --score-only # score only, no tailoring (use with a scheduled task)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

import job_fetcher as jf

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "job_fetcher.db"
MASTER_RESUME_PATH = BASE_DIR / "master_resume.json"
ENV_PATH = BASE_DIR / ".env"


def _load_api_key() -> str:
    if not ENV_PATH.exists():
        raise SystemExit(f"{ENV_PATH} not found -- add a line ANTHROPIC_API_KEY=sk-ant-...")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"ANTHROPIC_API_KEY not found in {ENV_PATH}")


SCORING_BATCH_SIZE = 8
SCORE_THRESHOLD_TAILOR = 70
SCORE_THRESHOLD_KEEP = 40
MAX_DESC_CHARS_SCORING = 4000
MAX_DESC_CHARS_TAILORING = 8000
SCORING_CACHE_VERSION = "fit-v1"

# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# Dream employers: anything from this list that clears the KEEP floor (>=40)
# gets tailored and shown even if it doesn't clear the normal TAILOR threshold.
PRIORITY_COMPANIES = [
    "google", "amazon", "meta", "apple", "microsoft",
    # add your own target companies here, lowercase substrings
]


def is_priority_company(company: str) -> bool:
    c = (company or "").lower()
    return any(p in c for p in PRIORITY_COMPANIES)


SCORING_MODEL = "claude-haiku-4-5-20251001"
TAILORING_MODEL = "claude-sonnet-4-6"

MODEL_PRICING_USD_PER_MTOK = {
    SCORING_MODEL: {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
    TAILORING_MODEL: {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
}


# ── Experience-gap penalty ──────────────────────────────────────────────────
_EXPLICIT_YEAR_PATTERNS = [
    re.compile(r'(\d{1,2})\s*\+\s*years?', re.I),
    re.compile(r'(\d{1,2})\s*-\s*\d{1,2}\s*years?', re.I),
    re.compile(r'minimum\s+(?:of\s+)?(\d{1,2})\s*years?', re.I),
    re.compile(r'at\s+least\s+(\d{1,2})\s*years?', re.I),
    re.compile(r'(\d{1,2})\s*years?\s+of\s+(?:professional\s+|relevant\s+|related\s+)?experience', re.I),
]
_TITLE_TIERS = [
    (re.compile(r'\b(staff|principal|director|head of|vp|vice president)\b', re.I), 8),
    (re.compile(r'\b(senior|sr\.?|lead)\b', re.I), 6),
    (re.compile(r'\b(associate|analyst\s+i\b|junior|jr\.?|entry.?level)\b', re.I), 0),
]
_MAX_PLAUSIBLE_YEARS = 20


def infer_required_years(title: str, description: str) -> int:
    for pattern in _EXPLICIT_YEAR_PATTERNS:
        for m in pattern.finditer(description or ""):
            years = int(m.group(1))
            if 0 < years <= _MAX_PLAUSIBLE_YEARS:
                return years
    for pattern, years in _TITLE_TIERS:
        if pattern.search(title or ""):
            return years
    return 3  # mid-level default


# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# How many years of YOUR OWN total experience the penalty bands assume as a
# "no penalty" ceiling. Set to your real total years of experience.
YOUR_TOTAL_YEARS_EXPERIENCE = 5


def experience_penalty(years: int) -> int:
    gap = years - YOUR_TOTAL_YEARS_EXPERIENCE
    if gap <= 0: return 0
    if gap <= 2: return 15
    if gap <= 4: return 30
    return 45


def apply_penalty(raw_score: int, title: str, description: str) -> int:
    years = infer_required_years(title, description)
    return max(0, raw_score - experience_penalty(years))


# ── DB helpers ───────────────────────────────────────────────────────────────

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def load_pending_jobs(
    limit: Optional[int], job_id: Optional[str] = None,
    since_days: Optional[int] = None, since_hours: Optional[int] = None,
) -> List[Dict[str, Any]]:
    with db() as con:
        query = """
            SELECT j.job_id, j.title, j.company, j.location, j.url, j.apply_url,
                   j.description, j.date_posted, j.remote_status, j.role_family,
                   j.seniority, j.preliminary_score
            FROM jobs j
            WHERE j.status = 'discovered'
              AND j.job_id NOT IN (SELECT job_id FROM job_analysis)
        """
        params: List[Any] = []
        if job_id:
            query += " AND j.job_id = ?"
            params.append(job_id)
        if since_days is not None and not job_id:
            query += " AND datetime(j.first_seen_at) >= datetime('now', ?)"
            params.append(f"-{since_days} days")
        if since_hours is not None and not job_id:
            query += " AND datetime(j.first_seen_at) >= datetime('now', ?)"
            params.append(f"-{since_hours} hours")
        query += " ORDER BY j.preliminary_score DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def save_analysis(
    job_id: str, match_score: int, tech_stack: List[str], missing_skills: List[str],
    pitch: str, tailored_summary: str = "", tailored_skills: str = "",
    tailored_resume_bullets: str = "", cover_letter: str = "",
    lead_with_projects: bool = False,
) -> None:
    status = "analyzed" if match_score >= SCORE_THRESHOLD_KEEP else "archived_low_match_score"
    with db() as con:
        con.execute("""
            INSERT INTO job_analysis
              (job_id, match_score, tech_stack, missing_skills, pitch,
               tailored_summary, tailored_skills, tailored_resume_bullets,
               cover_letter, lead_with_projects, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
              match_score=excluded.match_score, tech_stack=excluded.tech_stack,
              missing_skills=excluded.missing_skills, pitch=excluded.pitch,
              tailored_summary=excluded.tailored_summary, tailored_skills=excluded.tailored_skills,
              tailored_resume_bullets=excluded.tailored_resume_bullets,
              cover_letter=excluded.cover_letter, lead_with_projects=excluded.lead_with_projects,
              processed_at=excluded.processed_at
        """, (
            job_id, match_score, json.dumps(tech_stack), json.dumps(missing_skills), pitch,
            tailored_summary, tailored_skills, tailored_resume_bullets, cover_letter,
            int(bool(lead_with_projects)),
        ))
        con.execute(
            """UPDATE jobs SET status=?, sent_at=datetime('now'),
               processing_attempts=processing_attempts+1 WHERE job_id=?""",
            (status, job_id),
        )


def mark_failed(job_id: str, error: str) -> None:
    with db() as con:
        con.execute(
            """UPDATE jobs SET status='failed', last_error=?,
               processing_attempts=processing_attempts+1 WHERE job_id=?""",
            (error[:500], job_id),
        )


def scoring_cache_key(job: Dict[str, Any]) -> Optional[str]:
    description = " ".join((job.get("description") or "").split())
    if len(description) < 200:
        return None
    identity = {
        "version": SCORING_CACHE_VERSION, "model": SCORING_MODEL,
        "company": jf.company_name(job.get("company", "")),
        "title": jf.job_title(job.get("title", "")),
        "description": description,
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_json_list(value: Optional[str]) -> List[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(parsed, list):
        return parsed
    return [parsed] if parsed else []


def prepare_score_only_jobs(
    pending_jobs: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], int]:
    """Reuse one score for exact duplicate job descriptions across city listings."""
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS job_score_cache (
                cache_key TEXT PRIMARY KEY, match_score INTEGER NOT NULL,
                tech_stack TEXT NOT NULL, missing_skills TEXT NOT NULL,
                pitch TEXT NOT NULL, model TEXT NOT NULL,
                cached_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cached_rows = con.execute("""
            SELECT cache_key, match_score, tech_stack, missing_skills, pitch FROM job_score_cache
        """).fetchall()

    cache = {
        row["cache_key"]: {
            "match_score": int(row["match_score"]),
            "tech_stack": _parse_json_list(row["tech_stack"]),
            "missing_skills": _parse_json_list(row["missing_skills"]),
            "pitch": row["pitch"] or "",
        }
        for row in cached_rows
    }

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    uncacheable: List[Dict[str, Any]] = []
    for job in pending_jobs:
        key = scoring_cache_key(job)
        if key is None:
            uncacheable.append(job)
        else:
            grouped.setdefault(key, []).append(job)

    jobs_to_score = list(uncacheable)
    members_by_representative: Dict[str, List[Dict[str, Any]]] = {
        job["job_id"]: [job] for job in uncacheable
    }
    reused = 0
    for key, members in grouped.items():
        existing = cache.get(key)
        if existing:
            for job in members:
                save_analysis(
                    job["job_id"], existing["match_score"], existing["tech_stack"],
                    existing["missing_skills"], existing["pitch"],
                )
            reused += len(members)
            continue
        representative = members[0]
        jobs_to_score.append(representative)
        members_by_representative[representative["job_id"]] = members

    return jobs_to_score, members_by_representative, reused


def save_score_cache(job: Dict[str, Any], match_score: int,
                     tech_stack: List[str], missing_skills: List[str], pitch: str) -> None:
    key = scoring_cache_key(job)
    if key is None:
        return
    with db() as con:
        con.execute("""
            INSERT OR REPLACE INTO job_score_cache
              (cache_key, match_score, tech_stack, missing_skills, pitch, model, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (key, match_score, json.dumps(tech_stack), json.dumps(missing_skills),
              pitch, SCORING_MODEL))


def load_master_resume() -> Dict[str, Any]:
    if not MASTER_RESUME_PATH.exists():
        raise SystemExit(f"master_resume.json not found at {MASTER_RESUME_PATH}")
    return json.loads(MASTER_RESUME_PATH.read_text(encoding="utf-8"))


def _candidate_block(master: Dict[str, Any]) -> str:
    """Built live from master_resume.json so this script never hardcodes a
    name/years-of-experience blurb -- edit master_resume.json, not this script."""
    bio = master.get("core_positioning", "")
    exp_lines = [
        f"- {e.get('title', '')}, {e.get('company', '')} ({e.get('dates', '')})"
        for e in master.get("experience", [])
    ]
    return bio + "\n" + "\n".join(exp_lines)


# ── Claude API calls ─────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=_load_api_key())
    return _client


def record_api_usage(model: str, operation: str, usage: Any) -> None:
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if not pricing:
        return
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    estimated_cost = (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
        + cache_write_tokens * pricing["cache_write"] + cache_read_tokens * pricing["cache_read"]
    ) / 1_000_000
    try:
        with db() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    usage_id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL,
                    model TEXT NOT NULL, operation TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, cache_write_tokens INTEGER NOT NULL,
                    cache_read_tokens INTEGER NOT NULL, estimated_cost_usd REAL NOT NULL
                )
            """)
            con.execute("""
                INSERT INTO api_usage (recorded_at, model, operation, input_tokens, output_tokens,
                    cache_write_tokens, cache_read_tokens, estimated_cost_usd)
                VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """, (model, operation, input_tokens, output_tokens,
                  cache_write_tokens, cache_read_tokens, estimated_cost))
    except Exception as exc:
        print(f"Warning: could not record API usage ({exc})", file=sys.stderr)


def call_model(prompt: str, model: str, system: Optional[str] = None,
               operation: str = "other") -> str:
    kwargs: Dict[str, Any] = dict(model=model, max_tokens=4096,
                                   messages=[{"role": "user", "content": prompt}])
    if system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    response = _get_client().messages.create(**kwargs)
    record_api_usage(model, operation, response.usage)
    return "".join(block.text for block in response.content if block.type == "text")


def score_batch(jobs: List[Dict[str, Any]], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    skills_ctx = json.dumps({
        "core_positioning": master.get("core_positioning"),
        "skills_keyword_bank": master.get("skills_keyword_bank"),
    })
    jobs_payload = json.dumps([
        {
            "job_id": j["job_id"], "title": jf.job_title(j["title"]),
            "company": jf.company_name(j["company"]),
            "description": " ".join((j["description"] or "")[:MAX_DESC_CHARS_SCORING].split()),
        }
        for j in jobs
    ])

    # >>> EDIT FOR YOUR TARGET ROLES <<< the FAVOR/REDUCE line below.
    prompt = f"""You are evaluating job postings against a specific candidate profile. Score each job for fit.

CANDIDATE:
{_candidate_block(master)}

CANDIDATE SKILLS:
{skills_ctx}

SCORING ANCHORS -- be strict, most jobs should land 40-75, not 80-90+:
90-100: Exceptional -- required experience within your range AND deep direct overlap
75-89:  Strong    -- good skill overlap, seniority roughly matches or only slightly above candidate
60-74:  Good      -- real overlap but noticeable gap in skills or seniority
45-59:  Reasonable -- partial overlap, meaningful gap in skills or seniority (common bucket)
30-44:  Weak      -- minor overlap only
<30:    Poor fit

Score PURELY on skill/domain/seniority fit per the anchors above -- do NOT deduct anything yourself
for years-of-experience gaps. That deduction is applied deterministically in code AFTER your score,
using its own independent read of required years from the posting -- if you also deduct for it,
the gap gets penalized twice.

Score the role based on its responsibilities and requirements, not the particular city where it is
listed. Multiple listings with the same company, title, and description are the same role for scoring.

DOMAIN FIT MATTERS MORE THAN RAW KEYWORD OVERLAP. The real question is "how relatable is the actual
day-to-day work" -- not "how many exact keywords appear in the posting." Specific tools/keywords can
always be picked up fast; a genuine domain mismatch cannot. So:
  - NEVER treat ubiquitous baseline office/reporting tools (Excel, PowerPoint, Word, Outlook, Google
    Sheets/Slides) as a real gap.
  - Only list missing_skills that reflect a genuine, non-trivial capability gap.
  - When the underlying WORK is a strong match but the posting lists a few unfamiliar/generic tool
    names, score the domain/work fit -- don't let incidental tool-name mismatches drag it down.

FAVOR: [your target domains, e.g. Business Analysis, Analytics Engineering, SQL, Data Modeling]
REDUCE: [domains you don't want, e.g. heavy backend engineering, DevOps/infra, manufacturing]

JOB POSTINGS TO EVALUATE:
{jobs_payload}

Return ONLY a valid JSON array -- no markdown fences, no explanation, no extra text. One object per input job:
[{{"job_id":"...","match_score":75,"tech_stack":["SQL"],"missing_skills":["Airflow"],"pitch":"One sentence on fit."}}]"""

    text = _strip_fences(call_model(prompt, SCORING_MODEL, operation="score"))
    results = json.loads(text)
    if not isinstance(results, list):
        results = [results]
    return results


def _tailor_system_block(master: Dict[str, Any]) -> str:
    """Static instructions + master resume, identical on every call -- sent as
    a cached system block instead of re-sent in full each time (cost control)."""
    return f"""You tailor ONE resume for {master.get('contact', {}).get('name', 'the candidate')} per job, given a JOB block in the user message below.

CANDIDATE MASTER RESUME (JSON):
{json.dumps(master)}

The master resume's "experience" entries contain a pool of bullets, each tagged with role families
it's strongest for. "skills_keyword_bank" contains real, verified keywords grouped by category.

INSTRUCTIONS:
1. This resume MUST fit on ONE page. Target 12-13 bullets TOTAL across all employers combined.
   Respect each employer's minimum bullet count (defined alongside generate_resumes.py's
   MINIMUM_BULLETS_BY_COMPANY). Within each employer's bullets, select the MOST RELEVANT ones to
   this specific job first.
2. ORDER bullets within each employer from most to least relevant to THIS job description.
3. OPTIMIZE HARD for match score -- mirror the job description's exact terminology, tool names, and
   verb choice wherever the underlying work genuinely supports it. Weave in exact-match keywords
   from skills_keyword_bank aggressively, not just where they already happened to appear. Never
   imply more ownership, seniority, or credit than the source bullet describes.
4. TRANSFERABLE TOOLS: if the job names a specific tool/platform that's a close functional analog to
   something the candidate actually used, name-check the job's tool explicitly as a transferable
   parallel -- never as if it were hands-on experience with the tool itself.
5. Use Google's XYZ bullet format: "Accomplished [X] as measured by [Y], by doing [Z]" -- every
   bullet leads with the quantified result, THEN the method/tools. Every bullet must contain at
   least one number if the source bullet has one -- never invent one if it doesn't. Do not bold any
   part of the bullet text.
5b. OPENING ACTION VERBS: never repeat the same opening verb on two bullets within one resume.
   Match tone to company type (consulting -> Advised/Delivered/Managed; big tech/product ->
   Built/Shipped/Automated; traditional enterprise -> Reduced/Streamlined/Optimized). Wording only
   -- never change the underlying fact, metric, or scope.
6. HARD RULES (never crossed): never change/invent/round a quantified metric; never claim hands-on
   experience with a tool never used; never introduce a claim, employer, title, or scope of
   ownership not in the source bullet or skills_keyword_bank.
7. tailored_summary: EXACTLY ~170-190 characters, reads as 2 lines on a resume.
8. tailored_skills: SELECT the 12-15 single most relevant skills_keyword_bank entries for THIS job.
9. lead_with_projects: true only if a personal-project entry is genuinely STRONGER evidence for
   THIS job than your day-job experience -- judge per-job, not from a fixed title list.

Return ONLY valid JSON -- no markdown fences, single object (not array):
{{"tailored_summary":"...","tailored_skills":["...","..."],"tailored_resume_bullets":[{{"company":"...","bullets":["...","..."]}}],"lead_with_projects":true|false}}"""


def tailor_resume(job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
    system = _tailor_system_block(master)
    prompt = f"""JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {json.dumps((job['description'] or '')[:MAX_DESC_CHARS_TAILORING])}

Tailor this resume per the instructions and return the JSON object now."""
    text = _strip_fences(call_model(prompt, TAILORING_MODEL, system=system, operation="resume_tailoring"))
    return json.loads(text)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--job-id", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score-only", action="store_true",
                        help="Score and save jobs without generating tailored resumes "
                             "(use for the 2-hour scheduled task; tailor only after selection)")
    parser.add_argument("--since-days", type=int, default=None)
    parser.add_argument("--since-hours", type=int, default=None)
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found -- run job_fetcher.py first.")

    master = load_master_resume()
    jobs = load_pending_jobs(args.limit, args.job_id, args.since_days, args.since_hours)

    if not jobs:
        print("No pending jobs to analyze.")
        return

    print(f"Pending: {len(jobs)} job(s) to analyze")
    if args.dry_run:
        for j in jobs:
            print(f"  [{j['preliminary_score']:3d}] {j['title']} at {j['company']}")
        return

    score_members: Dict[str, List[Dict[str, Any]]] = {j["job_id"]: [j] for j in jobs}
    cached_score_reuse = 0
    if args.score_only:
        jobs, score_members, cached_score_reuse = prepare_score_only_jobs(jobs)
        if not jobs:
            print(f"All pending listings scored from cache ({cached_score_reuse} reused); no API calls needed.")
            return

    stats = {"scored": 0, "dropped": 0, "saved_no_tailor": 0, "tailored": 0, "errors": 0}

    total_batches = -(-len(jobs) // SCORING_BATCH_SIZE)
    for i in range(0, len(jobs), SCORING_BATCH_SIZE):
        batch = jobs[i:i + SCORING_BATCH_SIZE]
        batch_num = i // SCORING_BATCH_SIZE + 1
        print(f"\nBatch {batch_num}/{total_batches}: scoring {len(batch)} jobs...", end="", flush=True)
        batch_results: Dict[str, Dict[str, Any]] = {}
        try:
            results = score_batch(batch, master)
            for r in results:
                job_id = r.get("job_id")
                if not job_id:
                    continue
                orig = next((j for j in batch if j["job_id"] == job_id), {})
                raw_score = int(r.get("match_score", 0))
                r["match_score"] = apply_penalty(raw_score, orig.get("title", ""), orig.get("description", ""))
                batch_results[job_id] = r
                members = score_members.get(job_id, [orig])
                stats["scored"] += len(members)
                if args.score_only:
                    save_score_cache(orig, r["match_score"], r.get("tech_stack", []), r.get("missing_skills", []), r.get("pitch", ""))
            print(f" done ({len(results)} scored)")
        except Exception as exc:
            print(f" error: {exc}")
            stats["errors"] += 1
            for j in batch:
                mark_failed(j["job_id"], str(exc)[:300])
            continue

        for job in batch:
            result = batch_results.get(job["job_id"])
            if not result:
                continue
            score = result["match_score"]
            tech = result.get("tech_stack") or []
            missing = result.get("missing_skills") or []
            pitch = result.get("pitch", "")

            if args.score_only:
                for member in score_members.get(job["job_id"], [job]):
                    save_analysis(member["job_id"], score, tech, missing, pitch)
                stats["dropped" if score < SCORE_THRESHOLD_KEEP else "saved_no_tailor"] += len(score_members.get(job["job_id"], [job]))
                continue

            priority = is_priority_company(job.get("company", ""))
            if score < SCORE_THRESHOLD_KEEP:
                save_analysis(job["job_id"], score, tech, missing, pitch)
                stats["dropped"] += 1
            elif score >= SCORE_THRESHOLD_TAILOR or priority:
                try:
                    tailored = tailor_resume(job, master)
                    save_analysis(
                        job["job_id"], score, tech, missing, pitch,
                        tailored.get("tailored_summary", ""),
                        json.dumps(tailored.get("tailored_skills", [])),
                        json.dumps(tailored.get("tailored_resume_bullets", [])),
                        "", bool(tailored.get("lead_with_projects", False)),
                    )
                    stats["tailored"] += 1
                except Exception as exc:
                    print(f"  tailor error for {job['job_id']}: {exc}")
                    stats["errors"] += 1
                time.sleep(0.5)
            else:
                save_analysis(job["job_id"], score, tech, missing, pitch)
                stats["saved_no_tailor"] += 1

        if not args.score_only and stats["tailored"]:
            subprocess.run(["python3", str(BASE_DIR / "generate_resumes.py"),
                           "--min-score", str(SCORE_THRESHOLD_TAILOR)], cwd=BASE_DIR)

        if i + SCORING_BATCH_SIZE < len(jobs):
            time.sleep(1)

    print(f"\nScored: {stats['scored']}  Dropped: {stats['dropped']}  "
          f"Saved (no tailor): {stats['saved_no_tailor']}  Tailored: {stats['tailored']}  "
          f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
```

---

## Appendix D — working `manual_analyze.py` (Option B: no API cost, agent-driven scoring)

This companion script needs no edits at all — it's fully generic (it imports the shared helpers
from Appendix C's `analyze_jobs.py`, so build that one first even if you're using Option B, just
never call its `main()`/API path). Use this with Appendix F's scheduled task.

```python
#!/usr/bin/env python3
"""Score and tailor jobs WITHOUT calling the Anthropic API. Hands pending jobs
to whatever agent is driving it (a Claude Code scheduled task, see Appendix F)
via a JSON dump, and accepts that agent's own scoring/tailoring output back
via a JSON save file. No ANTHROPIC_API_KEY needed.

Usage:
    python manual_analyze.py --dump-pending --since-hours 3 --limit 50 > /tmp/pending.json
    # agent reads /tmp/pending.json, scores/tailors each job itself, writes
    # a JSON array of result objects to /tmp/results.json:
    #    [{"job_id": "...", "match_score": 82, "tech_stack": [...],
    #      "missing_skills": [...], "pitch": "...",
    #      "tailored_summary": "...", "tailored_skills": [...],
    #      "tailored_resume_bullets": [{"company": "...", "bullets": [...]}],
    #      "lead_with_projects": false}, ...]
    #    Jobs scoring below 40 only need job_id/match_score/tech_stack/
    #    missing_skills/pitch -- tailoring fields can be omitted/empty.
    python manual_analyze.py --save /tmp/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analyze_jobs import (
    SCORE_THRESHOLD_TAILOR, SCORE_THRESHOLD_KEEP, apply_penalty, is_priority_company,
    load_pending_jobs, prepare_score_only_jobs, save_analysis, save_score_cache,
)

BASE_DIR = Path(__file__).resolve().parent
MAX_DESC_CHARS = 4000


def dump_pending(limit: int | None, since_hours: int | None, since_days: int | None) -> None:
    jobs = load_pending_jobs(limit, None, since_days, since_hours)
    jobs_to_score, members_by_rep, reused = prepare_score_only_jobs(jobs)
    if reused:
        print(f"# Reused cached scores for {reused} duplicate listing(s); not included below.", file=sys.stderr)
    payload = [
        {
            "job_id": j["job_id"], "title": j["title"], "company": j["company"],
            "location": j["location"], "preliminary_score": j["preliminary_score"],
            "description": (j["description"] or "")[:MAX_DESC_CHARS],
            "is_priority_company": is_priority_company(j.get("company", "")),
            "duplicate_listing_count": len(members_by_rep.get(j["job_id"], [j])),
        }
        for j in jobs_to_score
    ]
    print(json.dumps(payload, indent=2))


def save_results(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("results file must be a JSON array of result objects")

    from analyze_jobs import db, scoring_cache_key

    with db() as con:
        job_rows = {row["job_id"]: row for row in con.execute("SELECT job_id, title, company, description FROM jobs").fetchall()}
        pending_rows = con.execute("""
            SELECT j.job_id, j.title, j.company, j.description FROM jobs j
            WHERE j.status = 'discovered' AND j.job_id NOT IN (SELECT job_id FROM job_analysis)
        """).fetchall()
    pending_by_key: dict[str, list[str]] = {}
    for row in pending_rows:
        key = scoring_cache_key(dict(row))
        if key:
            pending_by_key.setdefault(key, []).append(row["job_id"])

    saved = dropped = tailored = 0
    for r in data:
        job_id = r.get("job_id")
        if not job_id:
            print(f"  skip: result missing job_id: {r}", file=sys.stderr)
            continue
        row = job_rows.get(job_id)
        raw_score = int(r.get("match_score", 0))
        score = apply_penalty(raw_score, row["title"] if row else "", row["description"] if row else "")

        tech = r.get("tech_stack") or []
        if not isinstance(tech, list): tech = [tech]
        missing = r.get("missing_skills") or []
        if not isinstance(missing, list): missing = [missing]
        pitch = r.get("pitch", "")

        tailored_summary = r.get("tailored_summary", "") or ""
        tailored_skills = r.get("tailored_skills", "")
        if isinstance(tailored_skills, list): tailored_skills = json.dumps(tailored_skills)
        tailored_bullets = r.get("tailored_resume_bullets", "")
        if isinstance(tailored_bullets, list): tailored_bullets = json.dumps(tailored_bullets)
        cover_letter = r.get("cover_letter", "") or ""
        lead_with_projects = bool(r.get("lead_with_projects", False))

        target_ids = {job_id}
        if row:
            key = scoring_cache_key(dict(row))
            if key:
                target_ids.update(pending_by_key.get(key, []))
                save_score_cache(dict(row), score, tech, missing, pitch)

        for tid in target_ids:
            save_analysis(tid, score, tech, missing, pitch, tailored_summary, tailored_skills, tailored_bullets, cover_letter, lead_with_projects)
        saved += len(target_ids)
        if score < SCORE_THRESHOLD_KEEP:
            dropped += len(target_ids)
        elif tailored_summary or tailored_bullets:
            tailored += 1

    print(f"Saved {saved} job_analysis row(s): {dropped} dropped (<{SCORE_THRESHOLD_KEEP}), {tailored} tailored.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump-pending", action="store_true")
    parser.add_argument("--save", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--since-hours", type=int, default=None)
    parser.add_argument("--since-days", type=int, default=None)
    args = parser.parse_args()

    if args.dump_pending:
        dump_pending(args.limit, args.since_hours, args.since_days)
    elif args.save:
        save_results(args.save)
    else:
        parser.error("specify --dump-pending or --save PATH")


if __name__ == "__main__":
    main()
```

---

## Appendix E — working `generate_resumes.py` (PDF + the same `index.html` format)

This produces the identical index format (grouped by 2-hour scrape slot, best-match-first, with
Applied/Find-outreach checkboxes). `>>> EDIT FOR YOUR TARGET ROLES <<<` marks
`MINIMUM_BULLETS_BY_COMPANY` (use your own employer names from `master_resume.json`) and
`PROJECTS_FIRST_TITLE_KEYWORDS`.

Requires: `pip install reportlab pypdf`.

```python
#!/usr/bin/env python3
"""Render a one-page, per-job tailored PDF resume from job_analysis +
master_resume.json, and rebuild resumes/index.html.

    python generate_resumes.py                  # all analyzed jobs
    python generate_resumes.py --min-score 70    # only strong matches
    python generate_resumes.py --job-id abc123   # a single job
    python generate_resumes.py --refresh-index   # rebuild index.html only, no PDFs
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, HRFlowable

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "job_fetcher.db"
MASTER_RESUME_PATH = BASE_DIR / "master_resume.json"
OUTPUT_DIR = BASE_DIR / "resumes"


def initial_scale_for(bullet_count: int) -> float:
    if bullet_count <= 6: return 1.32
    elif bullet_count <= 8: return 1.18
    elif bullet_count <= 9: return 1.09
    elif bullet_count <= 11: return 1.0
    elif bullet_count <= 13: return 0.94
    elif bullet_count <= 16: return 0.86
    else: return 0.78


MIN_SCALE = 0.78


def build_styles(scale: float) -> Dict[str, ParagraphStyle]:
    s = scale
    return {
        "NAME_STYLE": ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=18 * s, leading=21 * s, spaceAfter=2 * s),
        "CONTACT_STYLE": ParagraphStyle("Contact", fontName="Helvetica", fontSize=9.5 * s, textColor="#444444", spaceAfter=8 * s),
        "SUMMARY_STYLE": ParagraphStyle("Summary", fontName="Helvetica-Oblique", fontSize=10.3 * s, leading=13.8 * s, spaceAfter=8 * s, alignment=TA_JUSTIFY),
        "SECTION_STYLE": ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=11.3 * s, spaceBefore=8 * s, spaceAfter=3 * s, textColor="#1a3c6e"),
        "JOB_HEADER_STYLE": ParagraphStyle("JobHeader", fontName="Helvetica-Bold", fontSize=10.3 * s, spaceBefore=5 * s, spaceAfter=1 * s),
        "JOB_SUB_STYLE": ParagraphStyle("JobSub", fontName="Helvetica-Oblique", fontSize=9.3 * s, textColor="#555555", spaceAfter=2 * s),
        "CONTEXT_STYLE": ParagraphStyle("Context", fontName="Helvetica-BoldOblique", fontSize=9.3 * s, textColor="#1a3c6e", spaceAfter=3 * s),
        "BULLET_STYLE": ParagraphStyle("Bullet", fontName="Helvetica", fontSize=10.3 * s, leading=13.4 * s, alignment=TA_JUSTIFY),
        "SKILLS_STYLE": ParagraphStyle("Skills", fontName="Helvetica", fontSize=10 * s, leading=13.5 * s),
        "EDU_HONORS_STYLE": ParagraphStyle("EduHonors", fontName="Helvetica-Oblique", fontSize=9.3 * s, leading=12 * s, textColor="#555555", spaceAfter=4 * s),
    }


_ABBREVIATIONS = ("incl", "etc", "approx", "vs", "e.g", "i.e", "Inc", "Corp", "Jr", "Sr", "Dr", "Mr", "Mrs", "Ms")
_ABBREV_END_RE = re.compile(r'\b(?:' + '|'.join(re.escape(a) for a in _ABBREVIATIONS) + r')\.$')


def _split_first_sentence(summary: str) -> str:
    parts = re.split(r'(?<=[.!?])\s+', summary)
    first = parts[0]
    i = 1
    while i < len(parts) and _ABBREV_END_RE.search(first):
        first = first + " " + parts[i]
        i += 1
    return first


_DANGLING_TRAILING_WORDS = ("and", "or", "with", "using", "via", "for", "of", "by", "from", "to",
    "that", "which", "in", "on", "including", "into", "onto", "within", "across", "through",
    "toward", "about", "over", "under", "between", "as")
_DANGLING_TRAILING_RE = re.compile(r"(?:^|\s)(?:" + "|".join(_DANGLING_TRAILING_WORDS) + r")$", re.I)


def _shorten_summary(summary: str, max_chars: int = 180) -> str:
    summary = summary.strip()
    first_sentence = _split_first_sentence(summary)
    if len(first_sentence) <= max_chars:
        return first_sentence
    text = first_sentence.rstrip(".!? ")
    segments = [s.strip() for s in text.split(",")]
    while len(segments) > 1 and len(", ".join(segments)) > max_chars:
        segments.pop()
    kept = ", ".join(segments)
    if len(kept) > max_chars:
        kept = kept[:max_chars].rsplit(" ", 1)[0]
    while _DANGLING_TRAILING_RE.search(kept):
        kept = _DANGLING_TRAILING_RE.sub("", kept)
    if kept.count("(") != kept.count(")"):
        kept = kept.rsplit("(", 1)[0]
    return kept.rstrip(",.; ") + "."


LETTER_BODY_STYLE = ParagraphStyle("LetterBody", fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=10)
LETTER_META_STYLE = ParagraphStyle("LetterMeta", fontName="Helvetica", fontSize=9.5, textColor="#444444", spaceAfter=16)


def load_master_resume() -> Dict[str, Any]:
    if not MASTER_RESUME_PATH.exists():
        raise SystemExit(f"master_resume.json not found at {MASTER_RESUME_PATH}")
    return json.loads(MASTER_RESUME_PATH.read_text(encoding="utf-8"))


def fetch_jobs(min_score: Optional[int], job_id: Optional[str], show_applied: bool = False,
               since: Optional[str] = None) -> List[sqlite3.Row]:
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found -- run your scraper at least once first.")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    query = """
        SELECT j.job_id, j.title, j.company, j.url, j.apply_url, j.applicant_count, j.first_seen_at,
               a.tailored_summary, a.tailored_skills, a.tailored_resume_bullets, a.match_score,
               a.cover_letter, a.processed_at, a.lead_with_projects
        FROM job_analysis a JOIN jobs j ON j.job_id = a.job_id
        WHERE a.tailored_resume_bullets IS NOT NULL AND a.tailored_resume_bullets != ''
    """
    params: List[Any] = []
    if not show_applied:
        query += " AND (j.applied IS NULL OR j.applied = 0)"
    if min_score is not None:
        query += " AND a.match_score >= ?"; params.append(min_score)
    if job_id:
        query += " AND j.job_id = ?"; params.append(job_id)
    if since:
        query += " AND a.processed_at >= ?"; params.append(since)
    rows = con.execute(query, params).fetchall()
    con.close()
    return rows


def safe_json(value: Any, default: Any) -> Any:
    if not value: return default
    try: return json.loads(value)
    except (TypeError, ValueError): return default


# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
# Use the exact company names from YOUR master_resume.json.
MINIMUM_BULLETS_BY_COMPANY = {
    "Your Current Employer": 5,
    "A Past Employer": 3,
    "Your Personal Project": 3,
}


def ensure_minimum_bullets(bullets_by_company: Dict[str, List[str]], master: Dict[str, Any]) -> Dict[str, List[str]]:
    for entry in master.get("experience", []):
        company = entry["company"]
        minimum = MINIMUM_BULLETS_BY_COMPANY.get(company, 1)
        current = bullets_by_company.setdefault(company, [])
        if len(current) >= minimum:
            continue
        selected_texts = set(current)
        for b in entry.get("bullets", []):
            if len(current) >= minimum: break
            if b["text"] not in selected_texts:
                current.append(b["text"]); selected_texts.add(b["text"])
    return bullets_by_company


def trim_to_fit_one_page(bullets_by_company: Dict[str, List[str]], max_total: int = 13) -> Dict[str, List[str]]:
    floor_for = lambda company: MINIMUM_BULLETS_BY_COMPANY.get(company, 1)
    total = sum(len(v) for v in bullets_by_company.values())
    while total > max_total:
        candidates = [c for c, v in bullets_by_company.items() if len(v) > floor_for(c)]
        if not candidates: break
        company = max(candidates, key=lambda c: len(bullets_by_company[c]))
        bullets_by_company[company].pop(); total -= 1
    return bullets_by_company


def _render_story(master, contact, summary, tailored_skills, bullets_by_company, styles, projects_first=False) -> List[Any]:
    NAME_STYLE, CONTACT_STYLE, SUMMARY_STYLE = styles["NAME_STYLE"], styles["CONTACT_STYLE"], styles["SUMMARY_STYLE"]
    SECTION_STYLE, JOB_HEADER_STYLE, JOB_SUB_STYLE = styles["SECTION_STYLE"], styles["JOB_HEADER_STYLE"], styles["JOB_SUB_STYLE"]
    CONTEXT_STYLE, BULLET_STYLE, SKILLS_STYLE = styles["CONTEXT_STYLE"], styles["BULLET_STYLE"], styles["SKILLS_STYLE"]
    EDU_HONORS_STYLE = styles["EDU_HONORS_STYLE"]

    story: List[Any] = []
    story.append(Paragraph(contact.get("name", ""), NAME_STYLE))
    contact_bits = [v for v in [contact.get("location"), contact.get("phone"), contact.get("email"), contact.get("linkedin"), contact.get("github")] if v]
    if contact_bits:
        story.append(Paragraph(" | ".join(contact_bits), CONTACT_STYLE))
    story.append(HRFlowable(width="100%", thickness=1, color="#1a3c6e", spaceAfter=8))

    if summary:
        story.append(Paragraph(summary, SUMMARY_STYLE))
    if tailored_skills:
        story.append(Paragraph("SKILLS", SECTION_STYLE))
        story.append(Paragraph(", ".join(tailored_skills), SKILLS_STYLE))

    experience_block: List[Any] = [Paragraph("EXPERIENCE", SECTION_STYLE)]
    for entry in master.get("experience", []):
        if entry.get("type") == "project": continue
        company = entry["company"]
        bullets = bullets_by_company.get(company)
        if not bullets: continue
        experience_block.append(Paragraph(f"{entry.get('title', '')} — {company}", JOB_HEADER_STYLE))
        sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
        if sub_bits:
            experience_block.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
        if entry.get("context"):
            experience_block.append(Paragraph(entry["context"], CONTEXT_STYLE))
        items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
        experience_block.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

    project_entries = [e for e in master.get("experience", []) if e.get("type") == "project" and bullets_by_company.get(e["company"])]
    project_block: List[Any] = []
    if project_entries:
        project_block.append(Paragraph("PROJECTS", SECTION_STYLE))
        for entry in project_entries:
            company = entry["company"]
            bullets = bullets_by_company.get(company)
            header = f"{entry.get('title', '')} — {company}" if entry.get("title") else company
            project_block.append(Paragraph(header, JOB_HEADER_STYLE))
            sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
            if sub_bits:
                project_block.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
            items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
            project_block.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

    if projects_first:
        story.extend(project_block); story.extend(experience_block)
    else:
        story.extend(experience_block); story.extend(project_block)

    if master.get("education"):
        story.append(Paragraph("EDUCATION", SECTION_STYLE))
        for ed in master["education"]:
            story.append(Paragraph(f"{ed.get('degree', '')} — {ed.get('school', '')}", JOB_HEADER_STYLE))
            sub_bits = [b for b in [ed.get("dates"), ed.get("location")] if b]
            if sub_bits:
                story.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
    return story


# >>> EDIT FOR YOUR TARGET ROLES <<< ----------------------------------------
PROJECTS_FIRST_TITLE_KEYWORDS = [
    "forward deployed", "gtm engineer", "applied ai", "ai solutions", "ai engineer",
]


def _should_lead_with_projects(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in PROJECTS_FIRST_TITLE_KEYWORDS)


def build_pdf(row: sqlite3.Row, master: Dict[str, Any], out_path: Path, max_bullets: int) -> None:
    contact = master.get("contact", {})
    tailored_bullets = safe_json(row["tailored_resume_bullets"], [])
    tailored_skills = safe_json(row["tailored_skills"], [])[:15]
    summary = _shorten_summary(row["tailored_summary"] or master.get("summary_variants", {}).get("default", ""))
    projects_first = bool(row["lead_with_projects"]) or _should_lead_with_projects(row["title"])

    bullets_by_company = {b.get("company"): list(b.get("bullets", [])) for b in tailored_bullets if isinstance(b, dict)}
    bullets_by_company = ensure_minimum_bullets(bullets_by_company, master)
    bullets_by_company = trim_to_fit_one_page(bullets_by_company, max_bullets)
    total_bullets = sum(len(v) for v in bullets_by_company.values())

    from pypdf import PdfReader

    scale = max(initial_scale_for(total_bullets), MIN_SCALE)
    n_pages = None
    while True:
        styles = build_styles(scale)
        story = _render_story(master, contact, summary, tailored_skills, bullets_by_company, styles, projects_first=projects_first)
        margin_scale = max(scale, 0.85)
        doc = SimpleDocTemplate(str(out_path), pagesize=LETTER,
            leftMargin=0.6 * inch * margin_scale, rightMargin=0.6 * inch * margin_scale,
            topMargin=0.42 * inch * margin_scale, bottomMargin=0.42 * inch * margin_scale)
        doc.build(story)
        n_pages = len(PdfReader(str(out_path)).pages)
        if n_pages <= 1 or scale <= MIN_SCALE:
            break
        scale = max(MIN_SCALE, scale - 0.06)

    if n_pages > 1:
        print(f"    warning: {out_path.name} still {n_pages} pages at floor scale ({total_bullets} bullets)")


SCRAPE_SLOT_HOURS = [9, 11, 13, 15, 17, 19]  # matches a 2-hour, 9am-7pm scrape schedule -- edit if yours differs
LOCAL_TZ = ZoneInfo("America/New_York")  # edit to your own timezone


def _scrape_slot(first_seen_at: str) -> tuple[str, str]:
    if not first_seen_at:
        return ("0000-00-00 00", "UNDATED JOBS")
    dt = datetime.fromisoformat(first_seen_at).astimezone(LOCAL_TZ)
    hour = dt.hour
    slot = SCRAPE_SLOT_HOURS[0]
    for h in SCRAPE_SLOT_HOURS:
        if hour >= h: slot = h
    label_hour = slot if slot <= 12 else slot - 12
    ampm = "AM" if slot < 12 else "PM"
    label = f"{dt.strftime('%b %d').upper()} {label_hour}{ampm} JOBS"
    sort_key = f"{dt.strftime('%Y-%m-%d')} {slot:02d}"
    return (sort_key, label)


def _all_analyzed_slots_today() -> Dict[str, str]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT DISTINCT j.first_seen_at FROM jobs j JOIN job_analysis a ON a.job_id = j.job_id
        WHERE date(j.first_seen_at, 'localtime') = date('now', 'localtime')
    """).fetchall()
    con.close()
    slots: Dict[str, str] = {}
    for r in rows:
        sort_key, label = _scrape_slot(r["first_seen_at"])
        slots[sort_key] = label
    return slots


def build_index(rows_written: List[Dict[str, Any]]) -> None:
    """Grouped by 2-hour scrape slot, newest first, best-match-first within
    each slot -- the exact same layout the original pipeline uses."""
    groups: Dict[str, tuple[str, List[Dict[str, Any]]]] = {}
    for r in rows_written:
        sort_key, label = _scrape_slot(r.get("first_seen_at", ""))
        groups.setdefault(sort_key, (label, []))[1].append(r)
    for sort_key, label in _all_analyzed_slots_today().items():
        groups.setdefault(sort_key, (label, []))
    for _, members in groups.values():
        members.sort(key=lambda r: -(r["match_score"] or 0))

    parts = [
        "<html><head><meta charset='utf-8'><title>Tailored Resumes</title>",
        "<style>body{font-family:-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 20px}",
        "table{width:100%;border-collapse:collapse;margin-bottom:28px} th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #ddd}",
        "th{background:#f5f5f5} .score{font-weight:bold} tr:hover{background:#fafafa}",
        "input[type=checkbox]{width:18px;height:18px;cursor:pointer}",
        "h3.slot{margin:28px 0 8px;color:#1a3c6e;border-bottom:2px solid #1a3c6e;padding-bottom:4px}",
        "</style></head><body>",
        f"<h2>Tailored Resumes ({len(rows_written)})</h2>",
        "<p style='color:#666;font-size:14px'>Check boxes to flag jobs, then tell Claude "
        "(e.g. \"process checked boxes\") -- it reads this page's state and marks jobs "
        "applied / researches outreach contacts for the ones flagged.</p>",
    ]
    for sort_key in sorted(groups.keys(), reverse=True):
        label, members = groups[sort_key]
        parts.append(f"<h3 class='slot'>{label} ({len(members)})</h3>")
        if not members:
            parts.append("<p style='color:#888;font-style:italic;margin:4px 0 24px'>Screened — no matches strong enough to tailor.</p>")
            continue
        parts.append(
            "<table><tr><th>Match</th><th>Company</th><th>Title</th><th>Applicants</th><th>Resume</th>"
            "<th>Posting</th><th>Direct Apply</th><th>Applied</th><th>Find outreach</th></tr>"
        )
        for r in members:
            has_direct = bool(r["apply_url"]) and r["apply_url"] != r["url"]
            direct_cell = "<span style='color:#0a7'>Yes</span>" if has_direct else "<span style='color:#999'>No</span>"
            applicants = r.get("applicant_count")
            applicants_cell = str(applicants) if applicants is not None else "—"
            jid = r["job_id"]
            parts.append(
                f"<tr data-job-id='{jid}'><td class='score'>{r['match_score']}</td><td>{r['company']}</td>"
                f"<td>{r['title']}</td><td>{applicants_cell}</td><td><a href='{r['filename']}'>Open PDF</a></td>"
                f"<td><a href='{r['url']}' target='_blank'>View posting</a></td>"
                f"<td>{direct_cell}</td>"
                f"<td><input type='checkbox' class='applied-box' data-job-id='{jid}'></td>"
                f"<td><input type='checkbox' class='outreach-box' data-job-id='{jid}'></td></tr>"
            )
        parts.append("</table>")
    parts.append(
        "<script>document.querySelectorAll('.applied-box,.outreach-box').forEach(function(box){"
        "var key='resume_index_'+box.className+'_'+box.dataset.jobId;"
        "box.checked = localStorage.getItem(key) === '1';"
        "box.addEventListener('change', function(){localStorage.setItem(key, box.checked ? '1' : '0');});"
        "});</script>"
    )
    parts.append("</body></html>")
    (OUTPUT_DIR / "index.html").write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-score", type=int, default=None)
    parser.add_argument("--job-id", type=str, default=None)
    parser.add_argument("--max-bullets", type=int, default=13)
    parser.add_argument("--show-applied", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--refresh-index", action="store_true")
    args = parser.parse_args()

    if args.refresh_index:
        index_rows = fetch_jobs(args.min_score, None, args.show_applied, args.since)
        rows_written = []
        for row in index_rows:
            filename = f"{row['job_id']}.pdf"
            if not (OUTPUT_DIR / filename).exists():
                continue
            rows_written.append({
                "job_id": row["job_id"], "company": row["company"], "title": row["title"],
                "url": row["url"] or "", "apply_url": row["apply_url"] or row["url"] or "",
                "filename": filename, "match_score": row["match_score"],
                "first_seen_at": row["first_seen_at"] or "", "applicant_count": row["applicant_count"],
            })
        build_index(rows_written)
        print(f"Refreshed index.html: {len(rows_written)} resume(s) linked, no PDFs (re)built.")
        return

    master = load_master_resume()
    rows = fetch_jobs(None if args.job_id else args.min_score, args.job_id, args.show_applied, args.since)
    if not rows:
        print("No analyzed jobs with tailored_resume_bullets found for these filters.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    index_rows = rows if not args.job_id else fetch_jobs(args.min_score, None, args.show_applied, args.since)

    def row_to_entry(row: sqlite3.Row, build: bool) -> Dict[str, Any]:
        filename = f"{row['job_id']}.pdf"
        out_path = OUTPUT_DIR / filename
        if build:
            build_pdf(row, master, out_path, args.max_bullets)
            print(f"  Wrote {out_path.name}")
        return {
            "job_id": row["job_id"], "company": row["company"], "title": row["title"],
            "url": row["url"] or "", "apply_url": row["apply_url"] or row["url"] or "",
            "filename": filename, "match_score": row["match_score"],
            "first_seen_at": row["first_seen_at"] or "", "applicant_count": row["applicant_count"],
        }

    rebuilt_ids = {row["job_id"] for row in rows}
    built = [row_to_entry(row, build=True) for row in rows]
    clears_threshold = lambda entry: args.min_score is None or entry["match_score"] >= args.min_score
    rows_written = [entry for entry in built if clears_threshold(entry)]
    for row in index_rows:
        if row["job_id"] in rebuilt_ids:
            continue
        entry = row_to_entry(row, build=False)
        if (OUTPUT_DIR / entry["filename"]).exists():
            rows_written.append(entry)

    build_index(rows_written)
    print(f"\nDone. {len(rows)} resume(s) in {OUTPUT_DIR}")
    print(f"Open {OUTPUT_DIR / 'index.html'} to browse them sorted by match score.")


if __name__ == "__main__":
    main()
```

---

## Appendix F — the actual every-2-hours schedule, both halves

**Both the scrape AND the score/tailor step run every 2 hours, offset ~30 minutes apart.** This is
the real cadence used, not a simplified version — scoring is never done once-daily, it rides the
same 2-hour cycle as the scraper so new postings get screened within the hour instead of sitting
overnight.

**Layer 1 — scrape every 2 hours (OS cron, no judgment needed, free).** `run_scraper.sh`:
```zsh
#!/bin/zsh
set -eu
cd /path/to/your/project
exec .venv/bin/python3 -u job_fetcher.py --hours-old 3 >> scraper.log 2>&1
```
macOS LaunchAgent (`~/Library/LaunchAgents/com.yourname.jobscraper.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.yourname.jobscraper</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>/path/to/run_scraper.sh</string></array>
  <key>StartInterval</key><integer>7200</integer>
  <key>StandardOutPath</key><string>/path/to/scraper_launchd.log</string>
  <key>StandardErrorPath</key><string>/path/to/scraper_launchd.log</string>
</dict></plist>
```
Load it: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourname.jobscraper.plist`.
(Linux: a `cron` line `0 9-19/2 * * * cd /path && .venv/bin/python3 job_fetcher.py --hours-old 3`
does the same thing.)

**Layer 2 — score/tailor every 2 hours, offset ~30-35 min after each scrape (Claude Code scheduled
task).** Ask Claude Code itself to create this (it has a built-in scheduled-task feature): "create a
scheduled task that runs every 2 hours from 9:30am-7:30pm." Give it this task description:

```
You're running the recurring "score and tailor new jobs" half of a job-search pipeline in
/path/to/your/project. A separate OS-level cron scrapes new postings into job_fetcher.db every
2 hours; this task runs ~30 min after each scrape to score and tailor whatever's new.

1. cd /path/to/your/project
2. Dump newly pending jobs from the last ~3 hours:
   python3 manual_analyze.py --dump-pending --since-hours 3 > /tmp/pending_recent.json
   Check the count (python3 -c "import json;print(len(json.load(open('/tmp/pending_recent.json'))))").
   If 0, stop here -- nothing to do this cycle.
3. Read master_resume.json for the candidate's real experience/skills.
4. Read analyze_jobs.py's score_batch()/_tailor_system_block() for the scoring rubric and tailoring
   rules (XYZ bullet format, no bolding, SCORE_THRESHOLD_TAILOR/SCORE_THRESHOLD_KEEP, experience-gap
   penalty via apply_penalty).
5. If the pending count is large (>40), delegate scoring/tailoring to a sub-agent (Agent tool): give
   it the rubric, master_resume.json, and /tmp/pending_recent.json, and have it write a results JSON
   array to /tmp/results.json in the exact schema manual_analyze.py's save_results() expects. If the
   count is small, score/tailor inline yourself.
6. Validate /tmp/results.json covers every job_id from /tmp/pending_recent.json, then:
   python3 manual_analyze.py --save /tmp/results.json
7. python3 generate_resumes.py --min-score 70   (builds PDFs + refreshes index.html for new matches)
8. Report a brief summary: jobs processed, how many scored >=70, any notably high scores.

Do not touch LinkedIn outreach or application submission -- this task is scoped only to
scoring/tailoring.
```

If you went with Option A (paid API) instead, Layer 2 is simpler — the scheduled task (or a second
cron job offset 30 min after the scraper) just runs `python3 analyze_jobs.py` and reports the
printed stats; no agent judgment needed since the API does the scoring itself.

---

Once Claude has this document, a reasonable build order is: §2 (resume data) → Appendix A/B
(scraper, paste as-is then edit the marked sections) → Appendix C or D (scoring/tailoring, pick one)
→ Appendix E (PDF + index rendering, paste as-is then edit the two marked dicts) → Appendix F
(wire up both halves to run every 2 hours) → §7 (optional review/apply layer) only if you want to go
further than "get a folder of tailored resumes, refreshed every 2 hours." §8 (LinkedIn outreach) is
independent of the rest and can be done by hand/interactively any time, with no code required at
all.
