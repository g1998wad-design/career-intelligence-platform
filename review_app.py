"""Private API and mobile review page for scored job matches.

Run behind an HTTPS reverse proxy. Set REVIEW_USERNAME and REVIEW_PASSWORD
before exposing this service outside localhost.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from fastapi.security import HTTPBasic, HTTPBasicCredentials


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("JOB_DB_PATH", BASE_DIR / "job_fetcher.db"))
RESUMES_DIR = Path(os.environ.get("RESUMES_DIR", BASE_DIR / "resumes"))
WEB_DIR = BASE_DIR / "review_site"

app = FastAPI(title="Private Job Review", docs_url=None, redoc_url=None)
basic_auth = HTTPBasic(auto_error=False)


class LinkedInReferenceIn(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    title: str = Field(min_length=2, max_length=250)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(basic_auth)) -> str:
    expected_user = os.environ.get("REVIEW_USERNAME", "")
    expected_password = os.environ.get("REVIEW_PASSWORD", "")
    if not expected_user or not expected_password:
        raise HTTPException(status_code=503, detail="Review access is not configured")
    valid = bool(credentials) and secrets.compare_digest(credentials.username, expected_user)
    valid = valid and bool(credentials) and secrets.compare_digest(
        credentials.password, expected_password
    )
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def connect_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Job database is not available")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def ensure_selection_queue() -> None:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Job database is not available")
    with sqlite3.connect(DB_PATH, timeout=5) as con:
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
        con.execute("""
            CREATE TABLE IF NOT EXISTS application_queue (
                request_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                report_json TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def parse_json(value: Any) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []


def is_direct_apply_url(value: str | None) -> bool:
    host = (urlparse(value or "").hostname or "").lower().removeprefix("www.")
    aggregator_hosts = ("linkedin.com", "indeed.com", "google.com")
    return bool(host) and not any(
        host == root or host.endswith("." + root) for root in aggregator_hosts
    )


def job_document_path(job_id: str, document: str) -> Path:
    if not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in job_id):
        raise HTTPException(status_code=404, detail="Document not found")
    with connect_db() as con:
        row = con.execute(
            """SELECT j.company, j.title, a.cover_letter
               FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
               WHERE j.job_id=? AND a.tailored_resume_bullets IS NOT NULL
                 AND a.tailored_resume_bullets != ''""",
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Prepared job not found")
    base = job_id
    suffix = "__cover_letter" if document == "cover-letter" else ""
    path = (RESUMES_DIR / f"{base}{suffix}.pdf").resolve()
    try:
        path.relative_to(RESUMES_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document is not available")
    return path


@app.middleware("http")
async def private_no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/", include_in_schema=False)
def review_page(_: str = Depends(require_auth)):
    page = WEB_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=503, detail="Review page is not installed")
    return Response(page.read_text(encoding="utf-8"), media_type="text/html; charset=utf-8")


@app.get("/api/jobs")
def list_jobs(
    min_score: int = Query(default=40, ge=0, le=100),
    days: int = Query(default=3, ge=1, le=30),
    limit: int = Query(default=300, ge=1, le=500),
    _: str = Depends(require_auth),
):
    ensure_selection_queue()
    with connect_db() as con:
        rows = con.execute(
            """SELECT j.job_id, j.title, j.company, j.location, j.url, j.apply_url, j.source,
                      j.date_posted, j.applicant_count, j.remote_status,
                      j.location_compatibility, j.applied,
                      a.match_score, a.pitch, a.tech_stack, a.missing_skills,
                      a.tailored_resume_bullets, a.cover_letter, a.processed_at,
                      q.status AS preparation_status, q.last_error AS preparation_error
               FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
               LEFT JOIN selected_jobs q ON q.job_id=j.job_id
               WHERE a.match_score >= ?
                 AND (j.applied IS NULL OR j.applied=0)
                 AND datetime(a.processed_at) >= datetime('now', ?)
               ORDER BY a.processed_at DESC, a.match_score DESC
               LIMIT ?""",
            (min_score, f"-{days} days", limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tech_stack"] = parse_json(item["tech_stack"])
        item["missing_skills"] = parse_json(item["missing_skills"])
        item["has_resume"] = bool(item.pop("tailored_resume_bullets"))
        item["has_cover_letter"] = bool(item.pop("cover_letter"))
        item["direct_apply_available"] = is_direct_apply_url(item.get("apply_url"))
        result.append(item)
    return {"jobs": result, "count": len(result), "min_score": min_score, "days": days}


@app.post("/api/jobs/{job_id}/select")
def select_job(job_id: str, _: str = Depends(require_auth)):
    ensure_selection_queue()
    with connect_db() as con:
        row = con.execute(
            """SELECT a.tailored_resume_bullets
               FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
               WHERE j.job_id=? AND (j.applied IS NULL OR j.applied=0)""",
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found or already marked applied")

    existing_resume = bool(row["tailored_resume_bullets"])
    with sqlite3.connect(DB_PATH, timeout=5) as con:
        if existing_resume:
            con.execute("""
                INSERT INTO selected_jobs (job_id, status)
                VALUES (?, 'prepared')
                ON CONFLICT(job_id) DO UPDATE SET status='prepared',
                  updated_at=datetime('now'), last_error=NULL
            """, (job_id,))
            status = "prepared"
        else:
            con.execute("""
                INSERT INTO selected_jobs (job_id, status)
                VALUES (?, 'pending')
                ON CONFLICT(job_id) DO UPDATE SET
                  status=CASE WHEN selected_jobs.status='failed' THEN 'pending'
                              ELSE selected_jobs.status END,
                  updated_at=datetime('now'), last_error=NULL
            """, (job_id,))
            status = con.execute(
                "SELECT status FROM selected_jobs WHERE job_id=?", (job_id,)
            ).fetchone()[0]
    return {"job_id": job_id, "status": status}


@app.get("/api/applications")
def list_applications(_: str = Depends(require_auth)):
    ensure_selection_queue()
    with connect_db() as con:
        rows = con.execute("""
            SELECT q.request_id, q.job_id, q.status, q.report_json, q.last_error,
                   q.created_at, q.updated_at, j.title, j.company, j.url, j.apply_url,
                   j.source, a.match_score
            FROM application_queue q JOIN jobs j ON j.job_id=q.job_id
            LEFT JOIN job_analysis a ON a.job_id=j.job_id
            ORDER BY q.created_at DESC LIMIT 30
        """).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["report"] = json.loads(item.pop("report_json") or "{}")
        except json.JSONDecodeError:
            item["report"] = {}
        item["can_approve"] = bool(
            item["status"] == "awaiting_approval"
            and item["report"].get("ats") in {"greenhouse", "workday", "ashby", "lever", "smartrecruiters"}
            and not item["report"].get("needs_review_fields")
            and not item["report"].get("unmatched_fields")
        )
        items.append(item)
    return {"applications": items}


@app.post("/api/jobs/{job_id}/application")
def queue_application(job_id: str, _: str = Depends(require_auth)):
    ensure_selection_queue()
    with connect_db() as con:
        row = con.execute("""
            SELECT j.url, j.apply_url, a.tailored_resume_bullets
            FROM jobs j JOIN job_analysis a ON a.job_id=j.job_id
            WHERE j.job_id=? AND (j.applied IS NULL OR j.applied=0)
        """, (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found or already marked applied")
    if not row["tailored_resume_bullets"]:
        raise HTTPException(status_code=409, detail="Prepare the tailored resume first")
    candidate = row["apply_url"] or row["url"]
    if not is_direct_apply_url(candidate):
        raise HTTPException(
            status_code=409,
            detail="No direct employer application link is available for this job. Open the listing and add its employer application link first.",
        )
    request_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH, timeout=5) as con:
        con.execute("""
            INSERT INTO application_queue(request_id, job_id, status)
            VALUES(?, ?, 'pending')
        """, (request_id, job_id))
    return {"request_id": request_id, "job_id": job_id, "status": "pending"}


@app.post("/api/applications/{request_id}/approve")
def approve_application(request_id: str, _: str = Depends(require_auth)):
    ensure_selection_queue()
    with sqlite3.connect(DB_PATH, timeout=5) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("""
            SELECT q.status, q.report_json FROM application_queue q WHERE request_id=?
        """, (request_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Application request not found")
        try:
            report = json.loads(row["report_json"] or "{}")
        except json.JSONDecodeError:
            report = {}
        ats = report.get("ats")
        if row["status"] != "awaiting_approval":
            raise HTTPException(status_code=409, detail="This application is not waiting for approval")
        if ats not in {"greenhouse", "workday", "ashby", "lever", "smartrecruiters"}:
            raise HTTPException(status_code=409, detail="This ATS is not enabled for automatic submission")
        if report.get("needs_review_fields") or report.get("unmatched_fields"):
            raise HTTPException(status_code=409, detail="Review unresolved application fields before submission")
        con.execute("""
            UPDATE application_queue SET status='approved', updated_at=datetime('now')
            WHERE request_id=? AND status='awaiting_approval'
        """, (request_id,))
    return {"request_id": request_id, "status": "approved"}


@app.post("/api/applications/{request_id}/cancel")
def cancel_application(request_id: str, _: str = Depends(require_auth)):
    ensure_selection_queue()
    with sqlite3.connect(DB_PATH, timeout=5) as con:
        changed = con.execute("""
            UPDATE application_queue SET status='cancelled', updated_at=datetime('now')
            WHERE request_id=? AND status IN ('pending','awaiting_approval')
        """, (request_id,)).rowcount
    if not changed:
        raise HTTPException(status_code=409, detail="Application can no longer be cancelled from the review page")
    return {"request_id": request_id, "status": "cancelled"}


@app.get("/api/applications/{request_id}/screenshot")
def application_screenshot(request_id: str, _: str = Depends(require_auth)):
    from fastapi.responses import FileResponse

    ensure_selection_queue()
    with connect_db() as con:
        row = con.execute(
            "SELECT report_json FROM application_queue WHERE request_id=?", (request_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Application request not found")
    try:
        report = json.loads(row["report_json"] or "{}")
        relative = Path(report.get("screenshot", ""))
        if relative.parts[:1] != ("autofill_screenshots",):
            raise ValueError("Invalid screenshot path")
        path = (BASE_DIR / relative).resolve()
        path.relative_to((BASE_DIR / "autofill_screenshots").resolve())
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Screenshot is not available")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot is not available")
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.post("/api/linkedin-references")
def add_linkedin_reference(payload: LinkedInReferenceIn, _: str = Depends(require_auth)):
    """Queue a user-copied LinkedIn link for matching on non-LinkedIn sources."""
    parsed = urlparse(payload.url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise HTTPException(status_code=422, detail="Paste an https://linkedin.com job link")
    if "/jobs/" not in parsed.path:
        raise HTTPException(status_code=422, detail="The link does not look like a LinkedIn job posting")
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Job database is not available")
    ensure_selection_queue()
    reference_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH, timeout=5) as con:
        con.execute("""
            INSERT INTO linkedin_references(reference_id,url,title,company,location)
            VALUES(?,?,?,?,?)
        """, (reference_id, payload.url.strip(), payload.title.strip(),
              payload.company.strip(), payload.location.strip()))
    return {"reference_id": reference_id, "status": "pending"}


@app.get("/api/linkedin-references")
def list_linkedin_references(_: str = Depends(require_auth)):
    ensure_selection_queue()
    with connect_db() as con:
        rows = con.execute("""
            SELECT r.reference_id, r.url, r.title, r.company, r.location,
                   r.status, r.matched_job_id, r.direct_apply_url, r.last_error,
                   r.created_at, j.title AS matched_title, j.company AS matched_company,
                   j.source AS matched_source, j.url AS matched_url,
                   j.apply_url AS matched_apply_url
            FROM linkedin_references r
            LEFT JOIN jobs j ON j.job_id=r.matched_job_id
            ORDER BY r.created_at DESC LIMIT 30
        """).fetchall()
    return {"references": [dict(row) for row in rows]}


@app.get("/api/jobs/{job_id}/resume.pdf")
def get_resume(job_id: str, _: str = Depends(require_auth)):
    from fastapi.responses import FileResponse

    path = job_document_path(job_id, "resume")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.get("/api/jobs/{job_id}/cover-letter.pdf")
def get_cover_letter(job_id: str, _: str = Depends(require_auth)):
    from fastapi.responses import FileResponse

    path = job_document_path(job_id, "cover-letter")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.get("/api/health")
def health(_: str = Depends(require_auth)):
    return {"ok": True, "database_available": DB_PATH.is_file()}
