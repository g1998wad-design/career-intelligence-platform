#!/usr/bin/env python3
"""Reliable JobSpy -> n8n job ingestion service.

Features:
- Full job descriptions with configurable safety limit
- URL and cross-source fingerprint deduplication
- SQLite persistence and processing statuses
- Sponsorship, clearance/citizenship, role-family detection
- Lightweight relevance scoring before paid LLM processing
- Batch retries with exponential backoff and poison-item isolation
- Raw record preservation, run logs, deterministic job IDs
- Configurable search terms and test mode
- LLM output caching (job_analysis table) so re-runs don't re-pay for
  jobs already analyzed
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

# --- LinkedIn applicant-count patch ---
# JobSpy's JobPost model has no applicant-count field, so it's silently
# dropped even though the same job-detail page fetch JobSpy already makes
# (via linkedin_fetch_description) contains it, e.g.:
#   <figcaption class="num-applicants__caption">Over 200 applicants</figcaption>
# Confirmed live against a real posting (2026-09-07). Rather than fork the
# library or double every LinkedIn request, replace LinkedIn._get_job_details
# with a copy of the original (same jobspy version, same single HTTP call)
# plus one extra parse step, stashing the count in a module-level dict keyed
# by LinkedIn's numeric job_id. normalize_record() reads from this dict.
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

DEFAULT_CONFIG = {
    "n8n_webhook_url": "http://localhost:5678/webhook/job-ingest",
    "search_terms": [
        "Analytics Engineer", "Business Intelligence Engineer", "BI Engineer",
        "Finance Analytics Engineer", "Analytics Data Engineer", "Data Analyst",
        "Senior Data Analyst", "Technical Business Analyst",
        "Business Intelligence Analyst", "Product Data Analyst", "Product Analyst",
        "Finance Systems Analyst", "ERP Analyst", "Oracle Fusion Analyst",
        "Snowflake Developer", "Data Engineer", "AI Solutions Engineer",
        "Forward Deployed Engineer", "Implementation Engineer",
        # Close variants worth explicit coverage rather than hoping a job
        # board's own search relevance catches them under an existing term.
        "Data Analytics Engineer", "Reporting Analyst", "Insights Analyst",
        "BI Developer", "Solutions Engineer", "Customer Engineer",
        "Applied AI Analyst"
    ],
    "search_term_priorities": {
        "Analytics Engineer": 1, "Finance Analytics Engineer": 1,
        "Business Intelligence Engineer": 1, "BI Engineer": 1,
        "Analytics Data Engineer": 1, "Finance Systems Analyst": 1,
        "Snowflake Developer": 1
    },
    "location": "United States",
    "country_indeed": "USA",
    "sites": ["linkedin", "indeed", "google"],
    # Maximize interviews, minimize false negatives: cast a wide net.
    "results_per_search": 100,
    # 1 week lookback. Deduplication (url/fingerprint) handles repeats,
    # so this just protects against missed days (e.g. laptop off Monday).
    "hours_old": 168,
    "fetch_linkedin_description": True,
    # Keep batches small (1) while we're still validating the pipeline
    # end to end. Bump to 5-10 once JobSpy/SQLite/n8n/Gemini are confirmed
    # working and outputs are landing in job_analysis.
    "batch_size": 1,
    "batch_delay_seconds": 20,
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
    # Skip jobs already present in job_analysis (already paid for the
    # LLM pass) unless you explicitly want to force a re-analysis.
    "skip_already_analyzed": True,
    # Stop the run if this many jobs in a row fail for ANY reason -- almost
    # always a systemic problem (broken credential, depleted balance, a
    # downstream step being down), not several unrelated bad jobs.
    "max_consecutive_failures": 3
}

POSITIVE = {
    "analytics engineer": 15, "analytics engineering": 15, "snowflake": 10,
    "dbt": 10, "sql": 8, "tableau": 8, "data modeling": 8,
    "dimensional modeling": 8, "semantic layer": 8, "business intelligence": 7,
    "power bi": 6, "python": 6, "data quality": 6, "data lineage": 6,
    "etl": 6, "elt": 6, "oracle fusion": 8, "peoplesoft": 8,
    "finance analytics": 7, "treasury": 6, "accounts receivable": 6,
    "product analytics": 6, "technical business analyst": 6,
    "business analyst": 5, "ai automation": 6, "snowflake cortex": 6,
    "llm": 4, "databricks": 4, "airflow": 4, "data warehouse": 6,
    "reconciliation": 6, "kpi": 5, "dashboard": 4, "stakeholder": 3,
    # AI Solutions / Forward Deployed / Implementation Engineer roles are
    # explicit search terms but were previously under-weighted relative to
    # analytics-heavy postings, risking real matches getting archived before
    # Gemini ever saw them.
    "forward deployed": 12, "solutions engineer": 8, "implementation engineer": 8,
    "customer engineer": 6, "technical discovery": 6, "solution architecture": 6,
    "generative ai": 8, "genai": 8, "rag": 6, "vector database": 6,
    "vector search": 6, "prompt engineering": 6, "openai": 5, "gpt": 4,
    "structured outputs": 4, "human-in-the-loop": 4,
    # Product Analyst / Product Data Analyst roles are also explicit search
    # terms but had almost no supporting keywords at all.
    "a/b testing": 6, "experimentation": 5, "funnel analysis": 6,
    "cohort analysis": 6, "retention": 4, "activation": 4,
    "user segmentation": 4, "product metrics": 5,
}
NEGATIVE_TITLE = {
    "plc": -45, "embedded": -40, "electrical engineer": -35,
    "mechanical engineer": -35, "manufacturing engineer": -30,
    "controls engineer": -30, "network engineer": -25,
    "desktop support": -25, "help desk": -25, "firmware": -35,
    "civil engineer": -40, "robotics engineer": -25
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

# --- Hard-reject filters -----------------------------------------------
# Everything else (no sponsorship mentioned, sponsorship unclear, "must be
# authorized to work in the US", "no future sponsorship", ambiguous
# language, location, etc.) is KEPT. We'd rather review extra jobs than
# accidentally throw away the one company willing to sponsor. Archive
# ONLY on these two explicit categories:
US_CITIZEN_ONLY = [
    r"\bus citizens? only\b",
    r"\bu\.s\. citizens? only\b",
    r"\bmust be a u\.s\. citizen\b",
    r"\bcitizenship required\b",
]
CLEARANCE_REQUIRED = [
    r"\bactive clearance\b",
    r"\bactive secret clearance\b",
    r"\bcurrent clearance\b",
    r"\btop secret\b",
    r"\bts/sci\b",
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
    filtered_clearance: int = 0
    filtered_salary: int = 0
    filtered_seniority: int = 0
    cached_skipped: int = 0
    eligible: int = 0
    sent: int = 0
    failed: int = 0
    consecutive_failures: int = 0
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


def year_month(date_str: str) -> str:
    """Best-effort YYYY-MM extraction from a date_posted string, falling
    back to the current run's year-month if unparseable/missing. This is
    the fingerprint's "freshness" component: two identical postings a
    few months apart are treated as distinct (legitimate repostings),
    while the same posting seen twice in one run/week still dedupes."""
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
    cfg["n8n_webhook_url"] = os.getenv("N8N_WEBHOOK_URL", cfg["n8n_webhook_url"])
    return cfg


LOOKBACK_CHOICES = {"1": 5, "2": 24, "3": 48, "4": 168}


def prompt_lookback_hours(default_hours: int) -> int:
    """Only prompts when run directly in a terminal by a human -- the 2hr
    scheduled task invokes this script with no attached tty, so it silently
    keeps the config default (168h) instead of hanging forever waiting for
    input that will never come."""
    if not sys.stdin.isatty():
        return default_hours
    print("\nHow far back should this scrape look for postings?")
    print("  1) 5 hours\n  2) 1 day\n  3) 2 days\n  4) 1 week (default)")
    choice = input("Choice [1-4, Enter for default]: ").strip()
    return LOOKBACK_CHOICES.get(choice, default_hours)


_MASTER_RESUME_CACHE: Optional[Dict[str, Any]] = None


def load_master_resume() -> Dict[str, Any]:
    """Loaded once per process and sent along with every batch so the
    n8n Gemini prompt can mix-and-match bullets across role families
    instead of using one fixed resume block."""
    global _MASTER_RESUME_CACHE
    if _MASTER_RESUME_CACHE is None:
        if MASTER_RESUME_PATH.exists():
            _MASTER_RESUME_CACHE = json.loads(MASTER_RESUME_PATH.read_text(encoding="utf-8"))
        else:
            print(f"  Warning: {MASTER_RESUME_PATH} not found — sending an empty master_resume.")
            _MASTER_RESUME_CACHE = {}
    return _MASTER_RESUME_CACHE


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
          n8n_response TEXT, raw_record_json TEXT
        )""")
        # Migration: existing DBs predate the apply_url column.
        existing_cols = {row["name"] for row in con.execute("PRAGMA table_info(jobs)")}
        if "apply_url" not in existing_cols:
            con.execute("ALTER TABLE jobs ADD COLUMN apply_url TEXT")
        # Migration: existing DBs predate applied-tracking columns.
        if "applied" not in existing_cols:
            con.execute("ALTER TABLE jobs ADD COLUMN applied INTEGER DEFAULT 0")
        if "applied_at" not in existing_cols:
            con.execute("ALTER TABLE jobs ADD COLUMN applied_at TEXT")
        # Migration: existing DBs predate applicant-count (LinkedIn only).
        if "applicant_count" not in existing_cols:
            con.execute("ALTER TABLE jobs ADD COLUMN applicant_count INTEGER")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT,
          statistics_json TEXT
        )""")
        # LLM output cache. Once a job has a row here, we don't pay to
        # re-analyze it on a later run even if it resurfaces. Columns
        # mirror exactly what the n8n workflow's Gemini step returns
        # (see "Message a model" node's required output format).
        con.execute("""
        CREATE TABLE IF NOT EXISTS job_analysis (
          job_id TEXT PRIMARY KEY,
          match_score INTEGER,
          tech_stack TEXT,
          missing_skills TEXT,
          pitch TEXT,
          tailored_summary TEXT,
          tailored_skills TEXT,
          tailored_resume_bullets TEXT,
          cover_letter TEXT,
          processed_at TEXT
        )""")


def seen(field: str, value: str) -> bool:
    """A job only counts as permanently "seen" (never retried) once it's
    reached a genuinely terminal state: successfully analyzed, or deliberately
    archived for a real reason (low relevance, clearance/citizenship,
    low match_score, etc.). A job stuck at "discovered" -- saved right after
    scraping but never actually reached n8n because the script was
    interrupted, crashed, or lost power -- or "failed" -- hit a transient
    error like a rate limit -- is NOT treated as seen, so it gets picked up
    and retried on the next run instead of silently disappearing forever."""
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


def cache_analysis_results(response: Any) -> Tuple[int, List[str]]:
    """The n8n workflow responds with {"success": true, "results": [...]}
    where each result is one job's Gemini output (job_id, match_score,
    tech_stack, missing_skills, pitch, tailored_resume_bullets, and
    optionally cover_letter once that branch is enabled). Cache every
    entry we can key by job_id so a future run skips paying for this job
    again. Returns (rows cached, job_ids with match_score < 40 — n8n
    already drops these before writing to the Sheet, so we mirror that
    locally instead of leaving them stuck at status='analyzed')."""
    if not isinstance(response, dict):
        return 0, []
    results = response.get("results")
    if not isinstance(results, list):
        return 0, []
    cached = 0
    low_match: List[str] = []
    with db() as con:
        for item in results:
            if not isinstance(item, dict) or not item.get("job_id"):
                continue
            tech_stack = item.get("tech_stack")
            missing_skills = item.get("missing_skills")
            tailored = item.get("tailored_resume_bullets")
            tailored_skills = item.get("tailored_skills")
            con.execute("""
                INSERT INTO job_analysis
                  (job_id, match_score, tech_stack, missing_skills, pitch,
                   tailored_summary, tailored_skills, tailored_resume_bullets,
                   cover_letter, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  match_score=excluded.match_score,
                  tech_stack=excluded.tech_stack,
                  missing_skills=excluded.missing_skills,
                  pitch=excluded.pitch,
                  tailored_summary=excluded.tailored_summary,
                  tailored_skills=excluded.tailored_skills,
                  tailored_resume_bullets=excluded.tailored_resume_bullets,
                  cover_letter=excluded.cover_letter,
                  processed_at=excluded.processed_at
            """, (
                item["job_id"],
                item.get("match_score"),
                json.dumps(tech_stack, default=str) if isinstance(tech_stack, list) else tech_stack,
                json.dumps(missing_skills, default=str) if isinstance(missing_skills, list) else missing_skills,
                item.get("pitch"),
                item.get("tailored_summary"),
                json.dumps(tailored_skills, default=str) if isinstance(tailored_skills, list) else tailored_skills,
                json.dumps(tailored, default=str) if isinstance(tailored, (list, dict)) else tailored,
                item.get("cover_letter"),
                now(),
            ))
            cached += 1
            score = number(item.get("match_score"))
            if score is not None and score < 40:
                low_match.append(item["job_id"])
    return cached, low_match


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
    record["n8n_response"] = json.dumps(record.get("n8n_response"), default=str) if record.get("n8n_response") else ""
    record["raw_record_json"] = json.dumps(j.get("raw_record", {}), default=str)
    placeholders = ",".join("?" for _ in cols)
    with db() as con:
        con.execute(f"INSERT OR REPLACE INTO jobs ({','.join(cols)}) VALUES ({placeholders})",
                    [record.get(c) for c in cols])


def set_status(job_id: str, status: str, error: str = "", response: Any = None) -> None:
    with db() as con:
        con.execute("""UPDATE jobs SET status=?, last_error=?, n8n_response=?,
                       processing_attempts=processing_attempts+1,
                       sent_at=CASE WHEN ?='analyzed' THEN ? ELSE sent_at END
                       WHERE job_id=?""",
                    (status, error, json.dumps(response, default=str) if response else "",
                     status, now(), job_id))


def is_rate_limit_error(error: str) -> bool:
    """Detect a rate-limit/quota-exhaustion signature in an error message.
    These are systemic failures -- retrying individual jobs against an
    already-exhausted quota just burns more calls into the same wall."""
    e = error.lower()
    return any(s in e for s in (
        "429", "rate limit", "too many requests", "quota", "resource_exhausted"
    ))


class PipelineHalted(Exception):
    """Base class for a clean, intentional run-stop -- something systemic
    is wrong, and continuing would just burn more API calls into the same
    broken thing (an expired credential, a depleted balance, a downstream
    step that's down, etc)."""
    pass


class RateLimited(PipelineHalted):
    """A specific, recognized rate-limit/quota pattern."""
    pass


class TooManyConsecutiveFailures(PipelineHalted):
    """A broader catch-all: N jobs in a row failed for ANY reason. This is
    what should have caught the Sheets-credential outage that burned
    through a prepay balance on repeated, pointless Gemini calls before
    the specific rate-limit check ever had a chance to fire -- that outage
    didn't look like a rate limit, it looked like a generic empty response,
    so nothing stopped it. This does."""
    pass


def notify_mac(title: str, message: str) -> None:
    """Best-effort native macOS notification so you don't have to keep
    checking the terminal during a multi-hour unattended run. Silently
    does nothing on non-Mac systems or if osascript isn't available --
    never worth crashing a run over."""
    try:
        import subprocess
        safe_title = title.replace('"', "'")
        safe_message = message.replace('"', "'")
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_message}" with title "{safe_title}"'],
            check=False, timeout=5, capture_output=True
        )
    except Exception:
        pass


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
    """The ONLY two reasons we archive a job outright. Everything else —
    no sponsorship mentioned, sponsorship unclear, "must be authorized to
    work in the US", "no future sponsorship", ambiguous language — is
    kept for review."""
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
    # Informational only — no longer affects scoring or eligibility.
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


def infer_role(title: str, description: str) -> str:
    value = norm(f"{title} {description[:4000]}")
    rules = [
        ("analytics_engineering", ["analytics engineer", "dbt", "semantic layer"]),
        ("finance_systems", ["oracle fusion", "peoplesoft", "finance systems", "erp analyst"]),
        ("product_analytics", ["product analyst", "product analytics", "growth analyst"]),
        ("ai_solutions", ["ai solutions", "forward deployed", "llm", "generative ai"]),
        ("technical_business_analysis", ["technical business analyst", "business systems analyst"]),
        ("business_intelligence", ["business intelligence", "bi developer", "tableau developer"]),
        ("data_engineering", ["data engineer", "airflow", "spark", "kafka"]),
        ("data_analytics", ["data analyst", "reporting analyst"])
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
    # Note: no location penalty here anymore (removed by request — location
    # doesn't affect score, since the search is nationwide and IDC where
    # a given posting is based).
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
    # job_url_direct is the actual company/ATS application link JobSpy
    # scrapes for Indeed postings (Workday/Greenhouse/iCIMS/etc, not a
    # tracking redirect). LinkedIn postings don't have one -- JobSpy leaves
    # it blank there, so we fall back to the LinkedIn listing url itself.
    apply_url = normalize_url(raw.get("job_url_direct") or "") or url
    li_id_match = re.search(r"linkedin\.com/jobs/view/(\d+)", url)
    applicant_count = _LINKEDIN_APPLICANT_COUNTS.get(li_id_match.group(1)) if li_id_match else None
    desc = clean(raw.get("description"))[:int(cfg["maximum_description_characters"])]
    date_posted = clean(raw.get("date_posted"))
    normalized_company = company_name(company)
    normalized_title = job_title(title)
    normalized_location = norm(location)
    freshness = year_month(date_posted)
    # Fingerprint now includes a year-month freshness component so a
    # reposting a few months later isn't silently suppressed as a
    # duplicate of the original listing.
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


def eligible(j: Dict[str, Any], cfg: Dict[str, Any], stats: Stats) -> bool:
    if j["preliminary_score"] < int(cfg["minimum_preliminary_score"]):
        stats.filtered_relevance += 1; j["status"] = "archived_low_relevance"; return False
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


def n8n_payload(j: Dict[str, Any]) -> Dict[str, Any]:
    # Existing six fields remain unchanged; enriched fields are additive.
    return {k: j.get(k) for k in [
        "job_id", "title", "company", "location", "description", "url", "source",
        "company_url", "company_domain", "date_posted", "job_type", "remote_status",
        "location_compatibility", "salary_min", "salary_max", "salary_interval",
        "currency", "sponsorship_status", "clearance_status", "role_family",
        "seniority", "description_quality", "preliminary_score", "search_term"
    ]}


def post_batch(batch: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[bool, Any, str]:
    # NOTE: response.json() parsing intentionally left as-is (no
    # try/except hardening) per your call to skip that fix. If n8n ever
    # returns a non-JSON body this will raise and be caught by the outer
    # except below, so it still gets retried — it just won't distinguish
    # "bad JSON" from other failures in the error message.
    attempts = int(cfg["maximum_request_attempts"])
    delays = cfg["retry_delays_seconds"]
    for attempt in range(attempts):
        try:
            response = requests.post(cfg["n8n_webhook_url"],
                                     json={"jobs": [n8n_payload(j) for j in batch],
                                           "master_resume": load_master_resume()},
                                     timeout=int(cfg["request_timeout_seconds"]))
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    # n8n returned something that isn't valid JSON at all (empty
                    # body, an HTML error page, a truncated response, etc.) --
                    # show the raw text so this is actually debuggable instead of
                    # just "JSONDecodeError: Expecting value: line 1 column 1".
                    snippet = response.text[:500] if response.text else "(empty response body)"
                    error = f"n8n returned non-JSON response (HTTP 200): {snippet!r}"
                    data = None
                if data is not None:
                    if data.get("success") is True:
                        return True, data, ""
                    error = f"n8n response missing success=true: {data}"
            else:
                error = f"HTTP {response.status_code}: {response.text[:1000]}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        if attempt < attempts - 1:
            pause = delays[min(attempt, len(delays) - 1)]
            print(f"  Attempt {attempt + 1} failed. Retrying in {pause}s: {error}")
            time.sleep(pause)
    return False, None, error


def process_batch(batch: List[Dict[str, Any]], cfg: Dict[str, Any], stats: Stats) -> None:
    if not batch: return
    print(f"Sending {len(batch)} job(s) to n8n...")
    ok, response, error = post_batch(batch, cfg)
    if ok:
        for j in batch: set_status(j["job_id"], "analyzed", response=response)
        cached, low_match = cache_analysis_results(response)
        for job_id in low_match:
            set_status(job_id, "archived_low_match_score")
        stats.sent += len(batch)
        stats.consecutive_failures = 0
        print(f"  Success: {len(batch)} job(s), cached {cached} analysis row(s), "
              f"{len(low_match)} below match_score 40")
        return
    if is_rate_limit_error(error):
        # Systemic failure, not a bad job. Every job left in this run is
        # still sitting at status="discovered" and will be picked up
        # automatically on the next run (see the seen() function) -- so
        # stopping here loses nothing, while continuing would just keep
        # hammering an exhausted quota and mark good jobs "failed" for
        # no reason.
        print(f"  Rate limit detected: {error}")
        print("  Stopping this run cleanly -- nothing is lost, remaining "
              "jobs will be picked up automatically on the next run.")
        raise RateLimited(error)
    # Poison-item isolation: retry failed multi-item batches individually.
    # Only reached for genuine per-job failures, not systemic rate limits.
    if len(batch) > 1:
        print("  Batch failed. Retrying each job individually...")
        for j in batch: process_batch([j], cfg, stats)
        return
    j = batch[0]
    set_status(j["job_id"], "failed", error=error)
    stats.failed += 1
    stats.consecutive_failures += 1
    stats.errors.append(f"{j['job_id']}: {error}")
    print(f"  Failed: {j['title']} at {j['company']} | {error}")
    max_failures = int(cfg.get("max_consecutive_failures", 3))
    if stats.consecutive_failures >= max_failures:
        print(f"  {stats.consecutive_failures} jobs failed in a row -- this looks systemic "
              f"(broken credential, dead API key, downstream outage), not per-job problems.")
        print("  Stopping this run cleanly to avoid burning more calls into the same issue.")
        raise TooManyConsecutiveFailures(
            f"{stats.consecutive_failures} consecutive failures. Last error: {error}"
        )


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


def run() -> None:
    cfg = load_config()
    cfg["hours_old"] = prompt_lookback_hours(int(cfg["hours_old"]))
    init_db()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats = Stats(run_id=run_id, started_at=now())
    raw_records: List[Dict[str, Any]] = []
    candidates: Dict[str, Dict[str, Any]] = {}

    print(f"Run {run_id} started | test_mode={cfg['test_mode']}")
    # In test_mode, only scrape the first couple of search terms -- test_mode
    # only ever sends test_mode_maximum_jobs to n8n anyway, so scraping all
    # 19 terms first just wastes time before you ever see whether the
    # pipeline works end to end.
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
                if seen("url", j["url"]): stats.url_duplicates += 1; continue
                if seen("fingerprint", j["fingerprint"]): stats.fingerprint_duplicates += 1; continue
                # Global in-run deduplication. Keep higher-scoring version.
                old = candidates.get(j["fingerprint"])
                if old:
                    stats.fingerprint_duplicates += 1
                    if j["preliminary_score"] > old["preliminary_score"]: candidates[j["fingerprint"]] = j
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
        save_job(j)
        if is_eligible:
            if cfg.get("skip_already_analyzed", True) and already_analyzed(j["job_id"]):
                stats.cached_skipped += 1
                continue
            eligible_jobs.append(j)

    if cfg["test_mode"]:
        eligible_jobs = eligible_jobs[:int(cfg["test_mode_maximum_jobs"])]

    stats.eligible = len(eligible_jobs)
    print(f"Eligible unique jobs: {len(eligible_jobs)} (skipped {stats.cached_skipped} already analyzed)")
    size = int(cfg["batch_size"])
    try:
        for start in range(0, len(eligible_jobs), size):
            process_batch(eligible_jobs[start:start + size], cfg, stats)
            if start + size < len(eligible_jobs): time.sleep(int(cfg["batch_delay_seconds"]))
    except PipelineHalted as exc:
        reason = "rate limit" if isinstance(exc, RateLimited) else "repeated failures"
        stats.errors.append(f"Run stopped early ({reason}): {exc}")
        print(f"\nRun stopped early due to {reason}. {stats.sent} job(s) sent "
              f"successfully before the stop. Fix the underlying issue, then re-run "
              f"job_fetcher.py -- nothing sent so far is lost, and nothing left unsent "
              f"will be skipped as a duplicate.")
        notify_mac(
            f"Job fetcher: stopped ({reason})",
            f"Sent {stats.sent}, then stopped. Fix the issue and re-run -- nothing is lost."
        )

    save_stats(stats, cfg)
    print(json.dumps(asdict(stats), indent=2))
    print(f"Done. SQLite: {DB_PATH}")

    if stats.failed > 0:
        notify_mac(
            "Job fetcher: done (with failures)",
            f"Sent {stats.sent}, failed {stats.failed} of {stats.eligible} eligible jobs."
        )
    else:
        notify_mac(
            "Job fetcher: done",
            f"Sent {stats.sent} of {stats.eligible} eligible jobs successfully."
        )


if __name__ == "__main__":
    run()
