#!/usr/bin/env python3
"""
Score, tailor, and generate cover letters for jobs using the Anthropic API.
Replaces the n8n/Gemini workflow — run this after job_fetcher.py.

Usage:
    python analyze_jobs.py              # process all pending jobs
    python analyze_jobs.py --limit 50   # cap at 50 jobs this run
    python analyze_jobs.py --dry-run    # show pending jobs without analyzing
    python analyze_jobs.py --min-score 75 --job-id abc123  # re-process one job

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY in a .env file next to this script (not the shell
    profile -- keeps it out of shell history / other tools). Billed
    separately from any Claude Code subscription -- see console.anthropic.com.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
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
MAX_DESC_CHARS_SCORING = 4000   # per-job truncation in scoring batches
MAX_DESC_CHARS_TAILORING = 8000  # full context for tailoring/cover letter
SCORING_CACHE_VERSION = "claude-haiku-fit-v2"

# Target/dream employers -- the skill-overlap scoring rubric below favors
# SQL/Snowflake/analytics-engineering keyword overlap and doesn't credit
# brand name or generalist Excel/PPT consulting toolkits, so postings from
# these companies get systematically underscored even when they're roles
# worth applying to regardless of fit. Anything from this list that clears
# the KEEP floor (>=40, i.e. not a flat reject) gets tailored and shown in
# the index even if it doesn't clear the normal 70 skill-fit threshold.
PRIORITY_COMPANIES = [
    "mckinsey", "bain", "bcg", "boston consulting",
    "deloitte", "accenture", "pwc", "kpmg", "ey",
    "google", "amazon", "meta", "apple", "netflix", "microsoft",
    "capital one", "t. rowe price", "t rowe price", "trowe price",
]


def is_priority_company(company: str) -> bool:
    c = (company or "").lower()
    return any(p in c for p in PRIORITY_COMPANIES)

# Haiku for scoring (cheap, handles JSON well in batches)
# Sonnet for tailoring + cover letters (quality matters for the actual resume)
SCORING_MODEL = "claude-haiku-4-5-20251001"
TAILORING_MODEL = "claude-sonnet-4-6"

# Current standard API rates in USD per million tokens. Keep this map aligned
# with Anthropic's published pricing; token counts are also stored so past
# usage can be recalculated if rates change.
MODEL_PRICING_USD_PER_MTOK = {
    SCORING_MODEL: {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
    TAILORING_MODEL: {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
}


# ── Experience-gap penalty ────────────────────────────────────────────────────
# Mirrors the n8n JavaScript Code node exactly. Claude is instructed to apply
# this in its prompt, but we enforce it deterministically in code too — same
# reason as before: LLMs in JSON/batch mode silently skip it.

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
    return 3  # mid-level default — "no seniority modifier → 2-5 years"


def experience_penalty(years: int) -> int:
    if years <= 5: return 0
    if years <= 7: return 15
    if years <= 9: return 30
    return 45


def apply_penalty(raw_score: int, title: str, description: str) -> int:
    years = infer_required_years(title, description)
    return max(0, raw_score - experience_penalty(years))


# ── DB helpers ────────────────────────────────────────────────────────────────

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def load_pending_jobs(
    limit: Optional[int], job_id: Optional[str] = None,
    since_days: Optional[int] = None, since_hours: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Jobs scraped but not yet analyzed (status='discovered', no job_analysis row)."""
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
    job_id: str,
    match_score: int,
    tech_stack: List[str],
    missing_skills: List[str],
    pitch: str,
    tailored_summary: str = "",
    tailored_skills: str = "",
    tailored_resume_bullets: str = "",
    cover_letter: str = "",
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
              match_score=excluded.match_score,
              tech_stack=excluded.tech_stack,
              missing_skills=excluded.missing_skills,
              pitch=excluded.pitch,
              tailored_summary=excluded.tailored_summary,
              tailored_skills=excluded.tailored_skills,
              tailored_resume_bullets=excluded.tailored_resume_bullets,
              cover_letter=excluded.cover_letter,
              lead_with_projects=excluded.lead_with_projects,
              processed_at=excluded.processed_at
        """, (
            job_id, match_score,
            json.dumps(tech_stack),
            json.dumps(missing_skills),
            pitch,
            tailored_summary,
            tailored_skills,
            tailored_resume_bullets,
            cover_letter,
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
    """Identify jobs with identical scoring inputs, independent of listing city."""
    description = " ".join((job.get("description") or "").split())
    if len(description) < 200:
        # Short snippets are too generic to establish that two postings are the same role.
        return None
    identity = {
        "version": SCORING_CACHE_VERSION,
        "model": SCORING_MODEL,
        "company": jf.company_name(job.get("company", "")),
        "title": jf.job_title(job.get("title", "")),
        # Include the full description: the deterministic experience penalty can
        # inspect text beyond the 4,000 characters sent to the scoring model.
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
    """Reuse one score for exact duplicate job descriptions across city listings.

    The versioned cache is populated only by this scoring path, so older scores
    from a different prompt/model are never silently reused.
    """
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS job_score_cache (
                cache_key TEXT PRIMARY KEY,
                match_score INTEGER NOT NULL,
                tech_stack TEXT NOT NULL,
                missing_skills TEXT NOT NULL,
                pitch TEXT NOT NULL,
                model TEXT NOT NULL,
                cached_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cached_rows = con.execute("""
            SELECT cache_key, match_score, tech_stack, missing_skills, pitch
            FROM job_score_cache
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


# ── Claude API calls ──────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude sometimes adds despite instructions."""
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
    """Persist per-call token counts and an estimate of current-rate cost."""
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if not pricing:
        return
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    estimated_cost = (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_write_tokens * pricing["cache_write"]
        + cache_read_tokens * pricing["cache_read"]
    ) / 1_000_000
    try:
        with db() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    model TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cache_write_tokens INTEGER NOT NULL,
                    cache_read_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL
                )
            """)
            con.execute("""
                INSERT INTO api_usage (
                    recorded_at, model, operation, input_tokens, output_tokens,
                    cache_write_tokens, cache_read_tokens, estimated_cost_usd
                ) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """, (model, operation, input_tokens, output_tokens,
                  cache_write_tokens, cache_read_tokens, estimated_cost))
    except Exception as exc:
        # Usage logging must never turn a successful model response into a
        # failed analysis or cause an unnecessary retry/call.
        print(f"Warning: could not record API usage ({exc})", file=sys.stderr)


def call_model(prompt: str, model: str, system: Optional[str] = None,
               operation: str = "other") -> str:
    """Direct Anthropic API call -- separate billing from any Claude Code
    subscription, no session/usage-limit collisions.

    If `system` is given, it's sent as a cached system block (cache_control:
    ephemeral). The master-resume JSON + tailoring instructions are identical
    on every call within a run, so caching them turns ~150 full-price re-sends
    of a ~5000-token block into one cache write + ~150 ~90%-off cache reads --
    the single biggest lever on per-run API cost. Cache entries live 5 minutes
    and refresh on each hit, so as long as calls keep coming faster than that
    (true for batch tailoring), the whole run rides on one cache write.
    """
    kwargs: Dict[str, Any] = dict(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    response = _get_client().messages.create(**kwargs)
    record_api_usage(model, operation, response.usage)
    return "".join(block.text for block in response.content if block.type == "text")


def score_batch(
    jobs: List[Dict[str, Any]],
    master: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Score a batch of jobs. Returns a list of score dicts."""
    skills_ctx = json.dumps({
        "core_positioning": master.get("core_positioning"),
        "skills_keyword_bank": master.get("skills_keyword_bank"),
    })
    jobs_payload = json.dumps([
        {
            "job_id": j["job_id"],
            "title": jf.job_title(j["title"]),
            "company": jf.company_name(j["company"]),
            "description": " ".join((j["description"] or "")[:MAX_DESC_CHARS_SCORING].split()),
        }
        for j in jobs
    ])

    prompt = f"""You are evaluating job postings against a specific candidate profile. Score each job for fit.

CANDIDATE: Gurkirat Singh Wadhawan
~5.5 years total professional experience:
- Business Analyst II, Allegis Group (Feb 2024–present, ~2.5 yrs) — Employee of the Year
- MS Information Systems, University of Maryland (~2 yrs, counted toward professional experience)
- Analyst, KPMG (~2 yrs, IT Consulting — cloud transformation, business process, ITIL)
- Business Management Analyst Intern, Thrivent Federal Credit Union
Transitioning FROM BA/data analyst roles INTO analytics engineering. NOT a senior data engineer with 6+ years hands-on engineering experience.

CANDIDATE SKILLS:
{skills_ctx}

SCORING ANCHORS — be strict, most jobs should land 40-75, not 80-90+:
90-100: Exceptional — required experience ≤4 yrs AND deep direct overlap (Snowflake, SQL, analytics engineering, BA, data platform)
75-89:  Strong    — good skill overlap, seniority roughly matches or only slightly above candidate
60-74:  Good      — real overlap but noticeable gap in skills or seniority
45-59:  Reasonable — partial overlap, meaningful gap in skills or seniority (common bucket)
30-44:  Weak      — minor overlap only
<30:    Poor fit

Score PURELY on skill/domain/seniority fit per the anchors above -- do NOT deduct anything yourself
for years-of-experience gaps. That deduction is applied deterministically in code AFTER your score,
using its own independent read of required years from the posting -- if you also deduct for it,
the gap gets penalized twice and the score comes out too low. Just give your honest skill-fit score;
the years-experience adjustment is not your job here.

Score the role based on its responsibilities and requirements, not the particular city where it is
listed. Multiple listings with the same company, title, and description are the same role for scoring.

DOMAIN FIT MATTERS MORE THAN RAW KEYWORD OVERLAP. The real question is "how relatable is the actual
day-to-day work" -- not "how many exact keywords from skills_keyword_bank appear in the posting."
Specific tools/keywords can always be added to the resume or picked up fast; a genuine domain mismatch
(e.g. embedded systems, manufacturing controls, backend infra engineering) cannot. So:
  - NEVER treat ubiquitous baseline office/reporting tools (Excel, PowerPoint, Word, Outlook, Google
    Sheets/Slides, basic reporting) as a real gap -- assume the candidate has these regardless of
    whether they appear in skills_keyword_bank, and never list them in missing_skills.
  - Only list missing_skills that reflect a genuine, non-trivial capability gap (e.g. a specific
    platform, a technical method, a domain the candidate has no adjacent exposure to) -- not generic
    tools everyone in a business/analytics role already knows.
  - When the underlying WORK (analysis, stakeholder-facing, data/reporting, AI-adjacent, process
    improvement) is a strong match but the posting happens to list a few unfamiliar or generic tool
    names, score the domain/work fit -- don't let incidental tool-name mismatches drag the score down.

FAVOR: Business Analysis, Analytics Engineering, Snowflake, SQL, Data Modeling, Tableau, AI Automation, Product Analytics, Process Improvement, Solutions Engineering, Forward Deployed roles, Implementation Engineering
REDUCE: Heavy software/backend engineering, DevOps/infrastructure, manufacturing automation, PLC, embedded systems, non-data technical roles

JOB POSTINGS TO EVALUATE:
{jobs_payload}

Return ONLY a valid JSON array — no markdown fences, no explanation, no extra text. One object per input job:
[{{"job_id":"...","match_score":75,"tech_stack":["SQL","Snowflake"],"missing_skills":["Airflow"],"pitch":"One sentence on fit."}}]"""

    text = _strip_fences(call_model(prompt, SCORING_MODEL, operation="score"))
    results = json.loads(text)
    if not isinstance(results, list):
        results = [results]
    return results


def _tailor_system_block(master: Dict[str, Any]) -> str:
    """Static instructions + master resume, identical on every tailor_resume()
    call -- kept separate from the per-job prompt so it can be sent as a
    cached system block instead of re-sent (and re-billed) in full each time.
    """
    return f"""You tailor ONE resume for Gurkirat Singh Wadhawan per job, given a JOB block in the user message below.

CANDIDATE MASTER RESUME (JSON):
{json.dumps(master)}

The master resume's "experience" entries contain a pool of bullets, each tagged with role families it's strongest for. "skills_keyword_bank" contains real, verified keywords grouped by category.

INSTRUCTIONS:
1. This resume MUST fit on ONE page. Target 12-13 bullets TOTAL across all employers combined
   -- not per employer. MINIMUM per employer (never go below these):
   - Allegis Group: ≥5 bullets
   - KPMG: ≥3 bullets
   - Career Intelligence Platform (personal project, in progress): ≥3 bullets
   - Thrivent Federal Credit Union: ≥1 bullet
   That's 12 bullets already committed -- you have at most 1 extra bullet of headroom within the
   13-bullet cap. Spend it (if at all) on whichever employer is most relevant to this job. Within
   each employer's bullets, select the MOST RELEVANT ones to this specific job first -- relevance
   to the job description is the deciding factor, not bullet order in the master resume.

2. ORDER bullets within each employer from most to least relevant to THIS job description.

3. OPTIMIZE HARD for match score — both an ATS keyword scanner and a human recruiter skimming
   for 6 seconds should come away thinking "undeniable match." Mirror the job description's exact
   terminology, tool names, and verb choice wherever the underlying work genuinely supports it.
   Weave in exact-match keywords from skills_keyword_bank aggressively, not just where they
   already happened to appear. Never imply more ownership, seniority, or credit than the source
   bullet describes.

4. TRANSFERABLE TOOLS: if the job names a specific tool/platform that's a close functional analog
   to something the candidate actually used (e.g. job wants Power BI, candidate used Tableau; job
   wants Redshift/BigQuery, candidate used Snowflake; job wants Looker, candidate used Tableau),
   name-check the job's tool explicitly as a transferable parallel — e.g. "BI dashboard development
   (Tableau, directly transferable to Power BI-style platforms)" — never as if it were hands-on
   experience with the tool itself. The transfer must be a real, defensible category match (same
   type of tool solving the same kind of problem), not a stretch.

5. Use Google's XYZ bullet format: "Accomplished [X] as measured by [Y], by doing [Z]" — every bullet leads with the quantified result/business outcome, THEN the method/tools used to achieve it (e.g. "Cut query execution time by 40% by optimizing Snowflake data models and SQL transformations," not "Optimized Snowflake data models, cutting query execution time by 40%"). Every bullet must contain at least one number if the source bullet has one — never invent one if it doesn't. When two bullets are similarly relevant, prefer the one with a real quantified metric. Do not bold any part of the bullet text — bold is reserved for job titles, companies, and dates elsewhere in the resume, handled by the renderer, not inline markup.

5b. OPENING ACTION VERBS: never repeat the same opening verb on two bullets within one resume — vary word choice across the whole document. Choose the specific verb from strong resume-verb categories (Harvard Career Services style) based on what best fits BOTH the underlying accomplishment AND this specific company's likely tone:
   - Reduction/Efficiency: Cut, Reduced, Streamlined, Eliminated, Minimized, Shortened, Consolidated
   - Growth/Improvement: Increased, Improved, Enhanced, Boosted, Strengthened, Elevated, Scaled
   - Building/Technical: Built, Designed, Developed, Engineered, Architected, Implemented, Deployed, Automated
   - Achievement/Results: Achieved, Delivered, Drove, Secured, Attained, Exceeded
   - Analysis/Diagnosis: Analyzed, Diagnosed, Evaluated, Identified, Audited
   - Leadership/Collaboration: Led, Directed, Coordinated, Embedded, Partnered, Aligned, Advised, Presented
   Match tone to company type: consulting/professional-services companies (EY, KPMG, Deloitte, Accenture) lean toward Advised, Delivered, Managed, Presented, Recommended; big tech / product companies lean toward Built, Shipped, Automated, Engineered, Scaled; traditional enterprise (banks, utilities, insurance) lean toward Reduced, Streamlined, Reconciled, Optimized, Standardized. This is wording only — never change the underlying fact, metric, or scope of the bullet.

6. HARD RULES (never crossed, even in service of instructions 3-4 above):
   - Never change, invent, or round a quantified metric. Metrics stay exactly as in the source bullet.
   - Never claim hands-on experience with a specific tool the candidate never used — instruction 4's
     transferable-skill framing must stay clearly framed as transferable, not as direct experience.
   - Never introduce a claim, employer, title, or scope of ownership not in the source bullet or
     skills_keyword_bank.

7. tailored_summary: write a crisp summary that reads as EXACTLY 2 lines on a resume (roughly 170-190 characters, one or two sentences) -- start from the best-fitting summary_variant but tighten it, don't just concatenate variants. Weighted toward this job's exact keywords per instruction 3. This is a hard length target, not a suggestion -- a 3-sentence summary is too long.
8. tailored_skills: SELECT the 12-15 single most relevant skills_keyword_bank entries for THIS job specifically (not a reordering of the whole bank) -- most relevant first. This must read as a short, scannable list, not a wall of every keyword you know.
9. lead_with_projects: true if the Career Intelligence Platform project bullets are genuinely STRONGER, more direct evidence for THIS job than the Allegis Group treasury/finance experience (e.g. AI/ML/agent-building, forward-deployed engineering, GTM/solutions-engineering roles where hands-on AI-building matters more than treasury BA work) -- otherwise false. Judge this per-job, not from a fixed title list.

Return ONLY valid JSON — no markdown fences, no explanation, single object (not array):
{{"tailored_summary":"...","tailored_skills":["...","..."],"tailored_resume_bullets":[{{"company":"...","bullets":["...","..."]}}],"lead_with_projects":true|false}}"""


def tailor_resume(
    job: Dict[str, Any],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate tailored resume bullets, summary, and skills for one job."""
    system = _tailor_system_block(master)
    prompt = f"""JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {json.dumps((job['description'] or '')[:MAX_DESC_CHARS_TAILORING])}

Tailor this resume per the instructions and return the JSON object now."""

    text = _strip_fences(call_model(prompt, TAILORING_MODEL, system=system,
                                    operation="resume_tailoring"))
    return json.loads(text)


def write_cover_letter(
    job: Dict[str, Any],
    pitch: str,
    tech_stack: List[str],
    missing_skills: List[str],
    master: Dict[str, Any],
) -> str:
    """Generate a 280-350 word cover letter for one job."""
    contact = master.get("contact", {})

    # Build a concise resume narrative from master_resume for the cover letter context
    exp_lines = []
    for entry in master.get("experience", []):
        bullets_preview = " ".join(
            b["text"] for b in entry.get("bullets", [])[:3]
        )
        exp_lines.append(
            f"{entry.get('title', '')} — {entry['company']} ({entry.get('dates', '')}): {bullets_preview}"
        )
    exp_text = "\n".join(exp_lines)

    prompt = f"""Write a personalized cover letter for {contact.get('name', 'Gurkirat Singh Wadhawan')} applying to {job['title']} at {job['company']} ({job['location']}).

CANDIDATE BACKGROUND:
{exp_text}

CONTACT (use exactly if you reference how to reach the candidate -- never invent a different email/phone): {contact.get('email', '')} | {contact.get('phone', '')} | {contact.get('linkedin', '')}
EDUCATION: {'; '.join(f"{e.get('degree','')} — {e.get('school','')}" for e in master.get('education', []))}
SKILLS: {', '.join(s for group in master.get('skills_keyword_bank', {}).values() for s in (group if isinstance(group, list) else []))}

WHY THIS ROLE IS A STRONG MATCH: {pitch}
RELEVANT TECH STACK FOR THIS ROLE: {', '.join(tech_stack) if tech_stack else 'See resume'}
SKILLS THE ROLE WANTS THAT AREN'T ON THE RESUME (address only if it honestly strengthens the letter, e.g. as a fast learner with adjacent experience — never claim to have skills you don't): {', '.join(missing_skills) if missing_skills else 'None'}

REQUIREMENTS:
- 280-350 words
- Open with a specific, concrete hook tied to something real about {job['company']} or this specific role — never "I am writing to express my interest"
- Reference 2-3 specific things from the resume (real project names, tools, outcomes) and connect them directly to what this role needs
- Match tone to the role: professional and confident, not stiff or overblown
- Close with a specific, low-friction call to action — not "I look forward to hearing from you"
- Do not invent facts, metrics, or experience not present in the resume above
- If you mention how to reach the candidate, use the exact CONTACT details given above -- never invent an email, phone number, or handle
- Output ONLY the letter body — no subject line, no salutation, no "Dear Hiring Manager", no explanation of what you wrote"""

    return call_model(prompt, TAILORING_MODEL, operation="cover_letter").strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of pending jobs to process this run")
    parser.add_argument("--job-id", type=str, default=None,
                        help="Re-process a specific job_id (ignores status filter)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show pending jobs without analyzing them")
    parser.add_argument("--score-only", action="store_true",
                        help="Score and save jobs without generating tailored resumes")
    parser.add_argument("--since-days", type=int, default=None,
                        help="Only process jobs first seen within this many days")
    parser.add_argument("--since-hours", type=int, default=None,
                        help="Only process jobs first seen within this many hours")
    parser.add_argument("--cover-letter-for", type=str, default=None,
                        help="Generate (or regenerate) just the cover letter for one already-"
                             "tailored job_id, without re-scoring/re-tailoring the resume")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found — run job_fetcher.py first.")

    master = load_master_resume()

    if args.cover_letter_for:
        with db() as con:
            job_row = con.execute(
                "SELECT job_id, title, company, location, url, apply_url, description, "
                "date_posted, remote_status, role_family, seniority, preliminary_score "
                "FROM jobs WHERE job_id=?", (args.cover_letter_for,)
            ).fetchone()
            a_row = con.execute(
                "SELECT match_score, tech_stack, missing_skills, pitch, tailored_summary, "
                "tailored_skills, tailored_resume_bullets, lead_with_projects "
                "FROM job_analysis WHERE job_id=?", (args.cover_letter_for,)
            ).fetchone()
        if not job_row or not a_row:
            raise SystemExit(f"No tailored job_analysis row found for {args.cover_letter_for}")
        job = dict(job_row)
        tech = json.loads(a_row["tech_stack"] or "[]")
        missing = json.loads(a_row["missing_skills"] or "[]")
        cover_letter = write_cover_letter(job, a_row["pitch"] or "", tech, missing, master)
        save_analysis(
            job["job_id"], a_row["match_score"], tech, missing, a_row["pitch"] or "",
            a_row["tailored_summary"] or "", a_row["tailored_skills"] or "",
            a_row["tailored_resume_bullets"] or "", cover_letter,
            bool(a_row["lead_with_projects"]),
        )
        print(f"Cover letter generated for {args.cover_letter_for}.")
        return

    if args.since_days is not None and args.since_days < 1:
        parser.error("--since-days must be at least 1")
    if args.since_hours is not None and args.since_hours < 1:
        parser.error("--since-hours must be at least 1")

    jobs = load_pending_jobs(args.limit, args.job_id, args.since_days, args.since_hours)

    if not jobs:
        print("No pending jobs to analyze (all discovered jobs already have analysis results).")
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
        if cached_score_reuse:
            print(f"Reused saved scores for {cached_score_reuse} identical listing(s); no API call.")
        if not jobs:
            print("All pending listings were scored from the local duplicate cache; no API calls needed.")
            return

    stats = {
        "scored": 0, "dropped": 0, "saved_no_tailor": 0,
        "tailored": 0, "reused": 0, "score_cache_reused": cached_score_reuse,
        "cover_letters": 0, "errors": 0,
    }

    # ── Tailoring reuse cache ────────────────────────────────────────────────
    # Large employers (PwC, Deloitte, Databricks, Google, Amazon...) routinely
    # repost the SAME req across dozens of US cities. job_fetcher.py fingerprints
    # each city listing separately (location is part of the fingerprint, by
    # design, so you can pick which city's listing to actually apply to), so
    # without this cache every city-copy triggers its own full-price Sonnet
    # tailoring call for what is, in substance, one tailoring decision.
    # Confirmed cost driver: 152 of 582 all-time-tailored rows (26%) were exact
    # company+title duplicates of an already-tailored posting -- one job (PwC
    # "CTIO-AI Engineer-Sr Associate") alone was independently tailored 25
    # times. Build a lookup from what's already tailored in the DB, keyed by
    # normalized (company, title), and reuse that output for any later posting
    # recognized as the same req instead of re-calling the model. The resume
    # content genuinely doesn't depend on which city copy scraped it.
    tailoring_cache: Dict[tuple, Dict[str, Any]] = {}
    with db() as con:
        existing_rows = con.execute("""
            SELECT j.company, j.title, a.tailored_summary, a.tailored_skills,
                   a.tailored_resume_bullets, a.lead_with_projects
            FROM job_analysis a JOIN jobs j ON j.job_id = a.job_id
            WHERE a.tailored_resume_bullets IS NOT NULL AND a.tailored_resume_bullets != ''
        """).fetchall()
    for row in existing_rows:
        key = (jf.company_name(row["company"]), jf.job_title(row["title"]))
        tailoring_cache[key] = {
            "tailored_summary": row["tailored_summary"] or "",
            "tailored_skills": row["tailored_skills"] or "",
            "tailored_resume_bullets": row["tailored_resume_bullets"] or "",
            "lead_with_projects": bool(row["lead_with_projects"]),
        }

    # Each batch is scored, triaged, AND (unless --score-only) tailored before moving to the next
    # batch -- so ≥75 matches land in job_analysis (and can be turned into
    # PDFs via generate_resumes.py) throughout the run instead of all at
    # once at the very end. Lets you start applying while later batches
    # are still processing.
    total_batches = -(-len(jobs) // SCORING_BATCH_SIZE)  # ceiling division
    operation = "Scoring" if args.score_only else "Scoring + tailoring"
    print(f"\n{operation} {len(jobs)} jobs in batches of {SCORING_BATCH_SIZE} "
          f"(score: {SCORING_MODEL}" + ("" if args.score_only else f", tailor: {TAILORING_MODEL}") + ")...")
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
                # Apply deterministic experience-gap penalty
                orig = next((j for j in batch if j["job_id"] == job_id), {})
                raw_score = int(r.get("match_score", 0))
                r["match_score"] = apply_penalty(raw_score, orig.get("title", ""), orig.get("description", ""))
                batch_results[job_id] = r
                members = score_members.get(job_id, [orig])
                stats["scored"] += len(members)
                if args.score_only:
                    save_score_cache(
                        orig, r["match_score"], r.get("tech_stack", []),
                        r.get("missing_skills", []), r.get("pitch", ""),
                    )
            print(f" ✓ ({len(results)} scored)")
        except Exception as exc:
            print(f" ✗ error: {exc}")
            stats["errors"] += 1
            if "credit balance is too low" in str(exc).lower():
                print("  API credits are exhausted; stopping before sending more batches. "
                      "This batch remains pending so it can be retried after credits are added.")
                break
            for j in batch:
                mark_failed(j["job_id"], str(exc)[:300])
            if i + SCORING_BATCH_SIZE < len(jobs):
                time.sleep(1)
            continue

        # Triage + tailor this batch immediately, right after it's scored.
        batch_tailored = 0
        for job in batch:
            result = batch_results.get(job["job_id"])
            if not result:
                continue
            score = result["match_score"]
            tech = result.get("tech_stack", [])
            if not isinstance(tech, list):
                tech = [tech] if tech else []
            missing = result.get("missing_skills", [])
            if not isinstance(missing, list):
                missing = [missing] if missing else []
            pitch = result.get("pitch", "")

            # Scheduled discovery runs stop after inexpensive scoring. Tailoring
            # happens only after an explicit selection in the review queue.
            if args.score_only:
                members = score_members.get(job["job_id"], [job])
                for member in members:
                    save_analysis(member["job_id"], score, tech, missing, pitch)
                if score < SCORE_THRESHOLD_KEEP:
                    stats["dropped"] += len(members)
                    print(f"  DROP  [{score:3d}] {job['title']} at {job['company']} "
                          f"({len(members)} identical listing(s) saved)")
                else:
                    stats["saved_no_tailor"] += len(members)
                    print(f"  SCORE [{score:3d}] {job['title']} at {job['company']} "
                          f"({len(members)} identical listing(s) saved)")
                continue

            priority = is_priority_company(job.get("company", ""))

            if score < SCORE_THRESHOLD_KEEP:
                save_analysis(job["job_id"], score, tech, missing, pitch)
                stats["dropped"] += 1
                print(f"  DROP  [{score:3d}] {job['title']} at {job['company']}")
            elif score >= SCORE_THRESHOLD_TAILOR or priority:
                tag = "TAILOR*" if priority and score < SCORE_THRESHOLD_TAILOR else "TAILOR "
                print(f"  {tag}[{score:3d}] {job['title']} at {job['company']}", end="", flush=True)
                tailored_summary = ""
                tailored_skills = ""
                tailored_bullets = ""
                cover_letter = ""
                lead_with_projects = False
                dedup_key = (jf.company_name(job.get("company", "")), jf.job_title(job.get("title", "")))
                cached = tailoring_cache.get(dedup_key)
                if cached:
                    tailored_summary = cached["tailored_summary"]
                    tailored_skills = cached["tailored_skills"]
                    tailored_bullets = cached["tailored_resume_bullets"]
                    lead_with_projects = cached["lead_with_projects"]
                    stats["tailored"] += 1
                    stats["reused"] += 1
                    batch_tailored += 1
                    print(" resume↻ (reused, same req/city-repost)", end="", flush=True)
                else:
                    try:
                        tailored = tailor_resume(job, master)
                        tailored_summary = tailored.get("tailored_summary", "")
                        tailored_skills = json.dumps(tailored.get("tailored_skills", []))
                        tailored_bullets = json.dumps(tailored.get("tailored_resume_bullets", []))
                        lead_with_projects = bool(tailored.get("lead_with_projects", False))
                        tailoring_cache[dedup_key] = {
                            "tailored_summary": tailored_summary,
                            "tailored_skills": tailored_skills,
                            "tailored_resume_bullets": tailored_bullets,
                            "lead_with_projects": lead_with_projects,
                        }
                        stats["tailored"] += 1
                        batch_tailored += 1
                        print(" resume✓", end="", flush=True)
                    except Exception as exc:
                        print(f" resume✗({exc})", end="", flush=True)
                        stats["errors"] += 1
                # Cover letters are no longer generated automatically -- most postings
                # don't take one, and it's a second full tailoring-cost API call per job.
                # Generate on demand per job_id once you know which ones actually want it
                # (see --cover-letter-for).
                save_analysis(
                    job["job_id"], score, tech, missing, pitch,
                    tailored_summary, tailored_skills, tailored_bullets, cover_letter,
                    lead_with_projects,
                )
                print()
                time.sleep(0.5)
            else:
                # 40-74: save score/pitch/tech only — no tailoring per user request
                save_analysis(job["job_id"], score, tech, missing, pitch)
                stats["saved_no_tailor"] += 1
                print(f"  KEEP  [{score:3d}] {job['title']} at {job['company']}")

        if batch_tailored:
            print(f"  Refreshing resumes/index.html ({batch_tailored} new)...", end="", flush=True)
            result = subprocess.run(
                ["python3", str(BASE_DIR / "generate_resumes.py"), "--min-score", str(SCORE_THRESHOLD_TAILOR)],
                cwd=BASE_DIR, capture_output=True, text=True,
            )
            print(" ✓" if result.returncode == 0 else f" ✗ ({result.stderr[-200:]})")

        if i + SCORING_BATCH_SIZE < len(jobs):
            time.sleep(1)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print(f"Analysis complete.")
    print(f"  Scored:           {stats['scored']}")
    print(f"  Dropped (<{SCORE_THRESHOLD_KEEP}):     {stats['dropped']}")
    print(f"  Saved no tailor:  {stats['saved_no_tailor']}  (score {SCORE_THRESHOLD_KEEP}–{SCORE_THRESHOLD_TAILOR - 1})")
    print(f"  Tailored (≥{SCORE_THRESHOLD_TAILOR}):   {stats['tailored']}  ({stats['reused']} reused, same req reposted to another city -- no API call)")
    print(f"  Cover letters:    {stats['cover_letters']}")
    if stats["errors"]:
        print(f"  Errors:           {stats['errors']}")
    if stats["tailored"] > 0:
        print(f"\nRun `python generate_resumes.py --min-score {SCORE_THRESHOLD_TAILOR}` to build PDFs.")


if __name__ == "__main__":
    main()
