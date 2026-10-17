"""Zetaris integration: federates the fragmented data sources a career
decision depends on (job postings, a candidate's resume, third-party company
signals, market salary data) behind one SQL-queryable surface, the way
Zetaris's data fabric federates heterogeneous backends without an ETL step.

Two modes, selected automatically by environment:

- Live mode (ZETARIS_ENDPOINT + ZETARIS_API_KEY set): queries execute against
  Zetaris's Lightning REST API, which federates the *real* backends (the
  pipeline's job_fetcher.db, a company-signals feed, a market-data feed)
  without copying them into one physical warehouse.
- Local federation mode (default, used by the demo/tests): the same fragments
  are loaded as sample JSON files and federated in-process with an in-memory
  SQLite database, so `query()` runs genuine SQL across tables that started
  life as unrelated JSON documents. The query interface agents call is
  identical in both modes, so swapping in live Zetaris credentials later
  changes zero agent code.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JOBS_FILE = BASE_DIR / "mock_scenarios" / "jobs.json"
DEFAULT_JOB_DETAIL_FILE = BASE_DIR / "mock_scenarios" / "job_requirements_detail.json"
DEFAULT_COMPANY_NOTES_FILE = BASE_DIR / "mock_scenarios" / "company_notes.json"
DEFAULT_MARKET_SALARY_FILE = BASE_DIR / "mock_scenarios" / "market_salary.json"
DEFAULT_RESUME_FILE = BASE_DIR / "mock_scenarios" / "sample_master_resume.json"


@dataclass
class ZetarisStatus:
    mode: str  # "live" | "local_federation"
    endpoint: str | None
    sources: list[str]


class ZetarisFederatedStore:
    """Unified query surface over the fragmented career-decision data."""

    def __init__(
        self,
        jobs_file: Path = DEFAULT_JOBS_FILE,
        job_detail_file: Path = DEFAULT_JOB_DETAIL_FILE,
        company_notes_file: Path = DEFAULT_COMPANY_NOTES_FILE,
        market_salary_file: Path = DEFAULT_MARKET_SALARY_FILE,
        resume_file: Path = DEFAULT_RESUME_FILE,
    ) -> None:
        self.endpoint = os.environ.get("ZETARIS_ENDPOINT")
        self.api_key = os.environ.get("ZETARIS_API_KEY")
        self.live = bool(self.endpoint and self.api_key)

        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._sources = []
        self._load_jobs(jobs_file)
        self._load_job_detail(job_detail_file)
        self._load_company_notes(company_notes_file)
        self._load_market_salary(market_salary_file)
        self._load_resume(resume_file)

    def status(self) -> ZetarisStatus:
        return ZetarisStatus(
            mode="live" if self.live else "local_federation",
            endpoint=self.endpoint,
            sources=list(self._sources),
        )

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Run a federated SQL query. Same signature in live and local mode."""
        if self.live:
            return self._query_live(sql, params)
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def _query_live(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        # Zetaris's Lightning REST API accepts a federated SQL statement and
        # returns rows pulled live from whichever backends it spans.
        resp = requests.post(
            f"{self.endpoint}/lightning/v1/query",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"sql": sql, "params": list(params)},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("rows", [])

    # -- local federation loaders -------------------------------------------------

    def _load_jobs(self, path: Path) -> None:
        jobs = json.loads(path.read_text(encoding="utf-8"))
        self._conn.execute(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
                source TEXT, listing_url TEXT, apply_url TEXT, ats TEXT, description TEXT
            )
            """
        )
        for job in jobs:
            self._conn.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.get("job_id"), job.get("title"), job.get("company"),
                    job.get("location"), job.get("source"), job.get("listing_url"),
                    job.get("apply_url"), job.get("ats"), job.get("description", job.get("mock_case", "")),
                ),
            )
        self._sources.append(f"jobs ({path.name})")

    def _load_job_detail(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._conn.execute(
            "CREATE TABLE job_requirements_detail (job_id TEXT PRIMARY KEY, description TEXT, required_skills TEXT, preferred_skills TEXT)"
        )
        for job in data.get("jobs", []):
            self._conn.execute(
                "INSERT INTO job_requirements_detail VALUES (?, ?, ?, ?)",
                (
                    job["job_id"], job.get("description", ""),
                    json.dumps(job.get("required_skills", [])),
                    json.dumps(job.get("preferred_skills", [])),
                ),
            )
        self._sources.append(f"job_requirements_detail ({path.name})")

    def _load_company_notes(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._conn.execute(
            "CREATE TABLE company_notes (company TEXT, source TEXT, snippet TEXT, published_days_ago INTEGER)"
        )
        for note in data.get("companies", []):
            self._conn.execute(
                "INSERT INTO company_notes VALUES (?, ?, ?, ?)",
                (note["company"], note["source"], note["snippet"], note["published_days_ago"]),
            )
        self._sources.append(f"company_notes ({path.name})")

    def _load_market_salary(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._conn.execute(
            "CREATE TABLE market_salary (title_family TEXT, location_tier TEXT, low INTEGER, mid INTEGER, high INTEGER)"
        )
        for band in data.get("bands", []):
            self._conn.execute(
                "INSERT INTO market_salary VALUES (?, ?, ?, ?, ?)",
                (band["title_family"], band["location_tier"], band["low"], band["mid"], band["high"]),
            )
        self._sources.append(f"market_salary ({path.name})")

    def _load_resume(self, path: Path) -> None:
        resume = json.loads(path.read_text(encoding="utf-8"))
        self._resume_raw = resume
        self._conn.execute("CREATE TABLE resume_skills (skill TEXT, bucket TEXT)")
        for bucket, skills in resume.get("skills_keyword_bank", {}).items():
            for skill in skills:
                self._conn.execute("INSERT INTO resume_skills VALUES (?, ?)", (skill, bucket))

        self._conn.execute(
            "CREATE TABLE resume_experience (company TEXT, title TEXT, years REAL, bullet TEXT)"
        )
        for entry in resume.get("experience", []):
            for bullet in entry.get("bullets", []):
                self._conn.execute(
                    "INSERT INTO resume_experience VALUES (?, ?, ?, ?)",
                    (entry.get("company"), entry.get("title"), entry.get("years"), bullet["text"]),
                )
        self._sources.append(f"resume ({path.name})")

    def resume_profile(self) -> dict[str, Any]:
        return self._resume_raw
