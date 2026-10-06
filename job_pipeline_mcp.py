"""MCP server exposing the job pipeline (job_fetcher.db + job_fetcher.py) as
tools an MCP client (Claude Desktop, Claude Code, etc.) can call directly --
e.g. "find me jobs scoring 80+ I haven't applied to" or "draft a cover letter
for the Sigma job" without opening a terminal.

This is a thin wrapper: all the real logic (scoring, tailoring, webhook
calls) already lives in job_fetcher.py. This file only adds the MCP
tool/resource boundary on top of it.

Run directly for local stdio use (e.g. registered in Claude Desktop's
config), or `mcp dev job_pipeline_mcp.py` to test with the MCP inspector.
"""
import json
import sqlite3
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

import job_fetcher as jf

mcp = MCPServer(
    name="job-pipeline",
    instructions=(
        "Tools for querying and acting on Gurkirat's job search pipeline "
        "(job_fetcher.db). Jobs are scraped, scored 0-100 against his resume "
        "by an LLM, and (for score >= 75) get a tailored resume + cover letter "
        "cached in job_analysis. Use list_jobs to find candidates, get_job for "
        "full detail on one, and mark_applied once he's actually applied."
    ),
)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


@mcp.tool()
def list_jobs(
    min_score: int = 75,
    limit: int = 20,
    exclude_applied: bool = True,
    title_contains: Optional[str] = None,
    company_contains: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List scored jobs from the pipeline, most relevant first.

    Args:
        min_score: only return jobs with match_score >= this (default 75).
        limit: max rows to return.
        exclude_applied: skip jobs already marked applied.
        title_contains: optional case-insensitive substring filter on title.
        company_contains: optional case-insensitive substring filter on company.
    """
    query = """
        SELECT j.job_id, j.title, j.company, j.location, j.url, j.applied,
               a.match_score, a.tech_stack, a.missing_skills, a.pitch,
               (a.cover_letter IS NOT NULL AND a.cover_letter != '') AS has_cover_letter
        FROM jobs j JOIN job_analysis a ON j.job_id = a.job_id
        WHERE a.match_score >= ?
    """
    params: list[Any] = [min_score]
    if exclude_applied:
        query += " AND (j.applied IS NULL OR j.applied = 0)"
    if title_contains:
        query += " AND j.title LIKE ?"
        params.append(f"%{title_contains}%")
    if company_contains:
        query += " AND j.company LIKE ?"
        params.append(f"%{company_contains}%")
    query += " ORDER BY a.match_score DESC LIMIT ?"
    params.append(limit)

    with jf.db() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


@mcp.tool()
def get_job(job_id: str) -> dict[str, Any]:
    """Get full detail for one job: description, score, tailored resume
    bullets, and cover letter text (if generated).

    Args:
        job_id: the job's primary key, as returned by list_jobs.
    """
    with jf.db() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """SELECT j.*, a.match_score, a.tech_stack, a.missing_skills, a.pitch,
                      a.tailored_summary, a.tailored_skills, a.tailored_resume_bullets,
                      a.cover_letter
               FROM jobs j LEFT JOIN job_analysis a ON j.job_id = a.job_id
               WHERE j.job_id = ?""",
            (job_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"No job found with job_id={job_id!r}")
    result = _row_to_dict(row)
    for field in ("tailored_skills", "tailored_resume_bullets"):
        if result.get(field):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


@mcp.tool()
def search_jobs(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Free-text search over job title, company, and description.

    Args:
        query: substring to search for (case-insensitive).
        limit: max rows to return.
    """
    like = f"%{query}%"
    with jf.db() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT j.job_id, j.title, j.company, j.location, j.url, j.applied,
                      a.match_score
               FROM jobs j LEFT JOIN job_analysis a ON j.job_id = a.job_id
               WHERE j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?
               ORDER BY a.match_score DESC NULLS LAST
               LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@mcp.tool()
def mark_applied(job_id: str) -> dict[str, Any]:
    """Mark a job as applied-to (so it stops showing up in list_jobs by default).

    Args:
        job_id: the job's primary key.
    """
    with jf.db() as con:
        cur = con.execute(
            "UPDATE jobs SET applied = 1, applied_at = ? WHERE job_id = ?",
            (jf.now(), job_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"No job found with job_id={job_id!r}")
        con.commit()
    return {"job_id": job_id, "applied": True}


@mcp.tool()
def pipeline_stats() -> dict[str, Any]:
    """Summary counts of the pipeline: total jobs, analyzed, scored >= 75,
    applied, and missing cover letters -- a quick health check."""
    with jf.db() as con:
        con.row_factory = sqlite3.Row
        total = con.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
        analyzed = con.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE status = 'analyzed'"
        ).fetchone()["c"]
        high_score = con.execute(
            "SELECT COUNT(*) AS c FROM job_analysis WHERE match_score >= 75"
        ).fetchone()["c"]
        applied = con.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE applied = 1"
        ).fetchone()["c"]
        missing_cover_letter = con.execute(
            """SELECT COUNT(*) AS c FROM job_analysis
               WHERE match_score >= 75 AND (cover_letter IS NULL OR cover_letter = '')"""
        ).fetchone()["c"]
    return {
        "total_jobs": total,
        "analyzed": analyzed,
        "scored_75_plus": high_score,
        "applied": applied,
        "missing_cover_letter_75_plus": missing_cover_letter,
    }


if __name__ == "__main__":
    mcp.run()
