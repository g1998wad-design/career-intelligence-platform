"""Tailor resumes on demand for jobs explicitly selected from the review page."""

from __future__ import annotations

import argparse
import difflib
import fcntl
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import analyze_jobs as analyzer
import job_fetcher as jf


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = jf.DB_PATH


def ensure_queue() -> None:
    with jf.db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS selected_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                selected_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_error TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_references (
                reference_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                matched_job_id TEXT,
                direct_apply_url TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def set_status(job_id: str, status: str, error: str | None = None) -> None:
    with jf.db() as con:
        con.execute(
            "UPDATE selected_jobs SET status=?, updated_at=datetime('now'), last_error=? WHERE job_id=?",
            (status, error[:1000] if error else None, job_id),
        )


def load_selected_job(job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with jf.db() as con:
        row = con.execute("""
            SELECT j.job_id, j.title, j.company, j.location, j.url, j.apply_url,
                   j.description, j.date_posted, j.remote_status, j.role_family,
                   j.seniority, j.preliminary_score,
                   a.match_score, a.tech_stack, a.missing_skills, a.pitch,
                   a.tailored_summary, a.tailored_skills, a.tailored_resume_bullets,
                   a.cover_letter, a.lead_with_projects,
                   q.status AS queue_status
            FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
            JOIN selected_jobs q ON q.job_id=j.job_id
            WHERE j.job_id=?
        """, (job_id,)).fetchone()
    if row is None:
        raise ValueError("Selected job or analysis was not found")
    if row["queue_status"] == "prepared" and row["tailored_resume_bullets"]:
        raise AlreadyPrepared("Job already has a tailored resume")
    job = {key: row[key] for key in (
        "job_id", "title", "company", "location", "url", "apply_url",
        "description", "date_posted", "remote_status", "role_family",
        "seniority", "preliminary_score",
    )}
    analysis = {key: row[key] for key in (
        "match_score", "tech_stack", "missing_skills", "pitch", "cover_letter",
    )}
    for field in ("tech_stack", "missing_skills"):
        try:
            analysis[field] = json.loads(analysis[field] or "[]")
        except (json.JSONDecodeError, TypeError):
            analysis[field] = []
    return job, analysis


def cached_tailoring(job: dict[str, Any]) -> dict[str, Any] | None:
    """Reuse a prior tailored result for the same employer and role."""
    key = (jf.company_name(job.get("company", "")), jf.job_title(job.get("title", "")))
    with jf.db() as con:
        rows = con.execute("""
            SELECT j.company, j.title, a.tailored_summary, a.tailored_skills,
                   a.tailored_resume_bullets, a.lead_with_projects
            FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
            WHERE j.job_id != ? AND a.tailored_resume_bullets IS NOT NULL
              AND a.tailored_resume_bullets != ''
        """, (job["job_id"],)).fetchall()
    for row in rows:
        if key == (jf.company_name(row["company"]), jf.job_title(row["title"])):
            return {
                "tailored_summary": row["tailored_summary"] or "",
                "tailored_skills": json.loads(row["tailored_skills"] or "[]"),
                "tailored_resume_bullets": json.loads(row["tailored_resume_bullets"] or "[]"),
                "lead_with_projects": bool(row["lead_with_projects"]),
            }
    return None


class AlreadyPrepared(Exception):
    pass


def prepare_job(job_id: str) -> None:
    set_status(job_id, "processing")
    try:
        job, analysis = load_selected_job(job_id)
        master = analyzer.load_master_resume()
        tailored = cached_tailoring(job)
        reused = tailored is not None
        if tailored is None:
            tailored = analyzer.tailor_resume(job, master)
        analyzer.save_analysis(
            job_id,
            int(analysis["match_score"]),
            analysis["tech_stack"],
            analysis["missing_skills"],
            analysis["pitch"] or "",
            tailored.get("tailored_summary", ""),
            json.dumps(tailored.get("tailored_skills", [])),
            json.dumps(tailored.get("tailored_resume_bullets", [])),
            analysis["cover_letter"] or "",
            bool(tailored.get("lead_with_projects", False)),
        )
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "generate_resumes.py"), "--job-id", job_id],
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Resume generation exited with status {result.returncode}")
        set_status(job_id, "prepared")
        action = "Prepared resume (reused matching role)" if reused else "Prepared tailored resume"
        print(f"{action} for {job['company']} — {job['title']}", flush=True)
    except AlreadyPrepared:
        set_status(job_id, "prepared")
    except Exception as exc:
        set_status(job_id, "failed", str(exc))
        print(f"Could not prepare {job_id}: {exc}", file=sys.stderr, flush=True)


def claim_next() -> str | None:
    with jf.db() as con:
        # Recover work interrupted by a process or host restart.
        con.execute("""
            UPDATE selected_jobs SET status='pending', updated_at=datetime('now'),
                   last_error='Recovered after worker restart'
            WHERE status='processing' AND updated_at < datetime('now', '-30 minutes')
        """)
        row = con.execute("""
            SELECT job_id FROM selected_jobs
            WHERE status='pending' ORDER BY selected_at LIMIT 1
        """).fetchone()
        if row is None:
            return None
        job_id = row["job_id"]
        changed = con.execute("""
            UPDATE selected_jobs SET status='processing', updated_at=datetime('now')
            WHERE job_id=? AND status='pending'
        """, (job_id,)).rowcount
        return job_id if changed else None


def claim_next_linkedin_reference() -> dict[str, Any] | None:
    """Claim a link the user copied manually; never open or fetch LinkedIn."""
    with jf.db() as con:
        con.execute("""
            UPDATE linkedin_references SET status='pending', updated_at=datetime('now'),
                   last_error='Recovered after worker restart'
            WHERE status='searching' AND updated_at < datetime('now', '-30 minutes')
        """)
        row = con.execute("""
            SELECT reference_id, title, company, location
            FROM linkedin_references WHERE status='pending'
            ORDER BY created_at LIMIT 1
        """).fetchone()
        if row is None:
            return None
        changed = con.execute("""
            UPDATE linkedin_references SET status='searching', updated_at=datetime('now')
            WHERE reference_id=? AND status='pending'
        """, (row['reference_id'],)).rowcount
        return dict(row) if changed else None


def update_linkedin_reference(reference_id: str, status: str, *,
                              job_id: str | None = None,
                              direct_url: str | None = None,
                              error: str | None = None) -> None:
    with jf.db() as con:
        con.execute("""
            UPDATE linkedin_references
            SET status=?, matched_job_id=?, direct_apply_url=?, last_error=?,
                updated_at=datetime('now')
            WHERE reference_id=?
        """, (status, job_id, direct_url, error[:1000] if error else None, reference_id))


def match_linkedin_reference(reference: dict[str, Any]) -> None:
    """Search Indeed/Google for a matching role and store only that external result."""
    search_term = f"{reference['company']} {reference['title']}"
    try:
        frame = jf.scrape_jobs(
            site_name=['indeed', 'google'],
            search_term=search_term,
            location=reference.get('location') or 'United States',
            results_wanted=20,
            hours_old=168,
            country_indeed='USA',
            linkedin_fetch_description=False,
        )
    except Exception as exc:
        update_linkedin_reference(reference['reference_id'], 'failed', error=str(exc))
        print(f"External search failed for {search_term}: {exc}", file=sys.stderr, flush=True)
        return

    if frame is None or frame.empty:
        update_linkedin_reference(reference['reference_id'], 'not_found')
        return

    wanted_company = jf.company_name(reference['company'])
    wanted_title = jf.job_title(reference['title'])
    candidates: list[tuple[float, dict[str, Any]]] = []
    cfg = jf.load_config()
    for raw in frame.to_dict(orient='records'):
        candidate = jf.normalize_record(raw, search_term, 1, cfg)
        if not candidate:
            continue
        if jf.company_name(candidate['company']) != wanted_company:
            continue
        title_score = difflib.SequenceMatcher(
            None, wanted_title, jf.job_title(candidate['title'])
        ).ratio()
        if title_score < 0.76:
            continue
        direct_bonus = 0.15 if jf.is_direct_apply_url(candidate.get('apply_url', '')) else 0
        location_score = 0.0
        if reference.get('location') and candidate.get('location'):
            location_score = 0.05 * difflib.SequenceMatcher(
                None, jf.norm(reference['location']), jf.norm(candidate['location'])
            ).ratio()
        candidates.append((title_score + direct_bonus + location_score, candidate))

    if not candidates:
        update_linkedin_reference(reference['reference_id'], 'not_found')
        return

    _, matched = max(candidates, key=lambda item: item[0])
    with jf.db() as con:
        existing = con.execute(
            "SELECT job_id FROM jobs WHERE fingerprint=? ORDER BY last_seen_at DESC LIMIT 1",
            (matched['fingerprint'],),
        ).fetchone()
    if existing:
        matched_id = existing['job_id']
        jf.merge_direct_apply_link(matched)
    else:
        jf.save_job(matched)
        matched_id = matched['job_id']

    # The user supplied this role intentionally, so score the matched public
    # listing even if it was previously archived by broad automatic filters.
    with jf.db() as con:
        has_analysis = con.execute(
            "SELECT 1 FROM job_analysis WHERE job_id=?", (matched_id,)
        ).fetchone()
        if not has_analysis:
            con.execute("UPDATE jobs SET status='discovered' WHERE job_id=?", (matched_id,))
    if not has_analysis:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / 'analyze_jobs.py'), '--score-only', '--job-id', matched_id],
            cwd=BASE_DIR, stdin=subprocess.DEVNULL, check=False,
        )
        if result.returncode:
            update_linkedin_reference(reference['reference_id'], 'failed', job_id=matched_id,
                                      error=f"Scoring failed with exit code {result.returncode}")
            return

    with jf.db() as con:
        stored = con.execute("SELECT apply_url FROM jobs WHERE job_id=?", (matched_id,)).fetchone()
    stored_apply_url = stored['apply_url'] if stored else matched.get('apply_url')
    direct_url = stored_apply_url if jf.is_direct_apply_url(stored_apply_url or '') else None
    status = 'matched' if direct_url else 'matched_listing'
    update_linkedin_reference(reference['reference_id'], status, job_id=matched_id,
                              direct_url=direct_url)
    print(f"LinkedIn reference matched on {matched.get('source')}: "
          f"{matched['company']} — {matched['title']} ({status})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process the current queue, then exit")
    parser.add_argument("--poll-seconds", type=int, default=10,
                        help="Seconds between checks when the queue is empty")
    args = parser.parse_args()
    if args.poll_seconds < 1:
        parser.error("--poll-seconds must be at least 1")
    if not DB_PATH.exists():
        parser.error(f"Database not found: {DB_PATH}")

    lock_path = Path(tempfile.gettempdir()) / "career-intelligence-selected-worker.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A selected-job worker is already running.")
            return 0
        ensure_queue()
        print("Selected-job worker started; waiting for phone selections.", flush=True)
        try:
            while True:
                job_id = claim_next()
                if job_id:
                    prepare_job(job_id)
                else:
                    reference = claim_next_linkedin_reference()
                    if reference:
                        match_linkedin_reference(reference)
                    elif args.once:
                        break
                    else:
                        time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            print("Selected-job worker stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
