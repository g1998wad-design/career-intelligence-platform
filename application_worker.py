"""Prepare selected employer-site applications and wait for phone approval."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import ats_autofill as autofill
import job_fetcher as jf
from review_app import ensure_selection_queue


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = jf.DB_PATH
PROFILE_PATH = BASE_DIR / "autofill_profile.json"
POLL_SECONDS = 2


def update_request(request_id: str, status: str, *, report: dict | None = None,
                   error: str | None = None) -> None:
    with sqlite3.connect(DB_PATH, timeout=10) as con:
        if report is not None:
            existing = con.execute(
                "SELECT report_json FROM application_queue WHERE request_id=?", (request_id,)
            ).fetchone()
            try:
                merged = json.loads(existing[0] or "{}") if existing else {}
            except json.JSONDecodeError:
                merged = {}
            merged.update(report)
            report = merged
        con.execute("""
            UPDATE application_queue
            SET status=?, report_json=COALESCE(?, report_json), last_error=?,
                updated_at=datetime('now')
            WHERE request_id=?
        """, (status, json.dumps(report) if report is not None else None,
              error[:1500] if error else None, request_id))


def claim_next() -> dict | None:
    with sqlite3.connect(DB_PATH, timeout=10) as con:
        con.row_factory = sqlite3.Row
        con.execute("""
            UPDATE application_queue SET status='pending', last_error='Recovered after worker restart',
                updated_at=datetime('now')
            WHERE status='preparing' AND updated_at < datetime('now', '-30 minutes')
        """)
        row = con.execute("""
            SELECT q.request_id, q.job_id, j.title, j.company, j.location, j.url, j.apply_url,
                   j.description, j.date_posted, j.remote_status, j.role_family, j.seniority,
                   j.preliminary_score, a.match_score, a.tech_stack, a.missing_skills, a.pitch,
                   a.cover_letter
            FROM application_queue q
            JOIN jobs j ON j.job_id=q.job_id
            JOIN job_analysis a ON a.job_id=j.job_id
            WHERE q.status='pending'
            ORDER BY q.created_at LIMIT 1
        """).fetchone()
        if row is None:
            return None
        changed = con.execute("""
            UPDATE application_queue SET status='preparing', last_error=NULL,
                updated_at=datetime('now') WHERE request_id=? AND status='pending'
        """, (row['request_id'],)).rowcount
        return dict(row) if changed else None


def application_payload(row: dict) -> dict:
    base = row["job_id"]
    resume_name = f"{base}.pdf"
    cover_name = f"{base}__cover_letter.pdf"
    return {
        **row,
        # Never use a LinkedIn/Indeed/Google listing as a proxy for the employer
        # application URL. The review API queues only jobs with direct links.
        "url": row["apply_url"],
        "apply_url": row["apply_url"],
        "resume_filename": resume_name,
        "cover_letter_filename": cover_name if (autofill.RESUMES_DIR / cover_name).is_file() else None,
    }


def wait_for_decision(request_id: str, page, ats: str) -> None:
    print(f"Waiting for review-page approval: {request_id}", flush=True)
    while True:
        with sqlite3.connect(DB_PATH, timeout=10) as con:
            row = con.execute(
                "SELECT status FROM application_queue WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None or row[0] == "cancelled":
            return
        if row[0] == "approved":
            outcome = autofill.attempt_auto_submit(page, ats)
            if outcome.get("submitted"):
                with jf.db() as con:
                    con.execute("UPDATE jobs SET applied=1 WHERE job_id=(SELECT job_id FROM application_queue WHERE request_id=?)", (request_id,))
                update_request(request_id, "submitted", report={"ats": ats, "submission": outcome})
            else:
                update_request(request_id, "submission_check", report={"ats": ats, "submission": outcome})
            return
        time.sleep(POLL_SECONDS)


def process(row: dict, playwright) -> None:
    request_id = row["request_id"]
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        job = application_payload(row)
        resume_path = autofill.RESUMES_DIR / job["resume_filename"]
        if not resume_path.is_file():
            raise FileNotFoundError(f"Tailored resume not found: {resume_path.name}; prepare the resume again")

        profile_dir = autofill.CHROME_PROFILE_DIR
        if profile_dir.is_dir():
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir), headless=False, channel="chrome"
            )
            browser = None
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

        try:
            result, page = autofill.process_job(
                page, job, profile, headless=False, auto_submit_clean=False
            )
            if result.get("status") == "error":
                update_request(request_id, "failed", report=result, error=result.get("error"))
                return
            result["approval_note"] = (
                "Approval submits only a clean supported ATS form with no unresolved fields. "
                "Workday step navigation stops when the worker cannot confidently fill a step."
            )
            update_request(request_id, "awaiting_approval", report=result)
            wait_for_decision(request_id, page, result.get("ats", "unknown"))
        finally:
            try:
                context.close()
            except Exception:
                pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        update_request(request_id, "failed", error=f"{type(exc).__name__}: {exc}")
        print(f"Application preparation failed for {request_id}: {exc}", file=sys.stderr, flush=True)


def main() -> None:
    ensure_selection_queue()
    print("Application worker started; waiting for review-page requests.", flush=True)
    with sync_playwright() as playwright:
        while True:
            row = claim_next()
            if row is None:
                time.sleep(POLL_SECONDS)
                continue
            process(row, playwright)


if __name__ == "__main__":
    main()
