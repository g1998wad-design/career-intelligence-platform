#!/usr/bin/env python3
"""
Score and tailor jobs WITHOUT calling the Anthropic API.

Companion to analyze_jobs.py, reusing its DB/schema helpers. Instead of
calling the Anthropic API for scoring/tailoring, this script hands pending
jobs to whatever agent is driving it (Claude Code, in an interactive or
scheduled-task session) via a JSON dump, and accepts that agent's own
scoring/tailoring output back via a JSON save file. No ANTHROPIC_API_KEY /
.env needed -- this is meant to replace analyze_jobs.py's API-billed path
entirely.

Usage:
    # 1. Dump pending jobs (not yet in job_analysis) as JSON for the agent to read.
    python manual_analyze.py --dump-pending --since-hours 6 --limit 50 > /tmp/pending.json

    # 2. Agent reads /tmp/pending.json, scores/tailors each job itself using the
    #    same rubric as analyze_jobs.py's score_batch/tailor_resume prompts, and
    #    writes a JSON array of result objects to a file, e.g. /tmp/results.json:
    #    [{"job_id": "...", "match_score": 82, "tech_stack": [...],
    #      "missing_skills": [...], "pitch": "...",
    #      "tailored_summary": "...", "tailored_skills": [...],
    #      "tailored_resume_bullets": [{"company": "...", "bullets": [...]}],
    #      "lead_with_projects": false}, ...]
    #    Jobs scoring below 40 only need job_id/match_score/tech_stack/
    #    missing_skills/pitch -- tailoring fields can be omitted/empty.

    # 3. Save results into job_analysis (applies the same experience-gap
    #    penalty and status transitions analyze_jobs.py uses).
    python manual_analyze.py --save /tmp/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analyze_jobs import (
    SCORE_THRESHOLD_TAILOR,
    SCORE_THRESHOLD_KEEP,
    apply_penalty,
    is_priority_company,
    load_pending_jobs,
    prepare_score_only_jobs,
    save_analysis,
    save_score_cache,
)

BASE_DIR = Path(__file__).resolve().parent
MAX_DESC_CHARS = 4000


def dump_pending(limit: int | None, since_hours: int | None, since_days: int | None) -> None:
    jobs = load_pending_jobs(limit, None, since_days, since_hours)
    # Dedup exact-repost duplicates (same company/title/description, different
    # city) the same way analyze_jobs.py --score-only does: reuse a cached
    # score if this exact req was already scored, and only surface ONE
    # representative per unique req for the agent to actually score.
    jobs_to_score, members_by_rep, reused = prepare_score_only_jobs(jobs)
    if reused:
        print(f"# Reused cached scores for {reused} duplicate listing(s); not included below.",
              file=sys.stderr)
    payload = [
        {
            "job_id": j["job_id"],
            "title": j["title"],
            "company": j["company"],
            "location": j["location"],
            "preliminary_score": j["preliminary_score"],
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
        job_rows = {
            row["job_id"]: row
            for row in con.execute(
                "SELECT job_id, title, company, description FROM jobs"
            ).fetchall()
        }
        # All still-pending jobs (not yet in job_analysis), to find exact-repost
        # duplicates of whatever the agent scored -- same dedup key dump_pending
        # used via prepare_score_only_jobs, so a job scored once here covers
        # every other city-copy of the same req still sitting unanalyzed.
        pending_rows = con.execute("""
            SELECT j.job_id, j.title, j.company, j.description
            FROM jobs j
            WHERE j.status = 'discovered'
              AND j.job_id NOT IN (SELECT job_id FROM job_analysis)
        """).fetchall()
    pending_by_key: dict[str, list[str]] = {}
    for row in pending_rows:
        key = scoring_cache_key(dict(row))
        if key:
            pending_by_key.setdefault(key, []).append(row["job_id"])

    saved = 0
    dropped = 0
    tailored = 0
    for r in data:
        job_id = r.get("job_id")
        if not job_id:
            print(f"  skip: result missing job_id: {r}", file=sys.stderr)
            continue
        row = job_rows.get(job_id)
        raw_score = int(r.get("match_score", 0))
        score = apply_penalty(raw_score, row["title"] if row else "", row["description"] if row else "")

        tech = r.get("tech_stack") or []
        if not isinstance(tech, list):
            tech = [tech]
        missing = r.get("missing_skills") or []
        if not isinstance(missing, list):
            missing = [missing]
        pitch = r.get("pitch", "")

        tailored_summary = r.get("tailored_summary", "") or ""
        tailored_skills = r.get("tailored_skills", "")
        if isinstance(tailored_skills, list):
            tailored_skills = json.dumps(tailored_skills)
        tailored_bullets = r.get("tailored_resume_bullets", "")
        if isinstance(tailored_bullets, list):
            tailored_bullets = json.dumps(tailored_bullets)
        cover_letter = r.get("cover_letter", "") or ""
        lead_with_projects = bool(r.get("lead_with_projects", False))

        # Same job_id, plus any other still-pending exact-repost duplicates.
        target_ids = {job_id}
        if row:
            key = scoring_cache_key(dict(row))
            if key:
                target_ids.update(pending_by_key.get(key, []))
                save_score_cache(dict(row), score, tech, missing, pitch)

        for tid in target_ids:
            save_analysis(
                tid, score, tech, missing, pitch,
                tailored_summary, tailored_skills, tailored_bullets,
                cover_letter, lead_with_projects,
            )
        saved += len(target_ids)
        if score < SCORE_THRESHOLD_KEEP:
            dropped += len(target_ids)
        elif tailored_summary or tailored_bullets:
            tailored += 1

    print(f"Saved {saved} job_analysis row(s): {dropped} dropped (<{SCORE_THRESHOLD_KEEP}), "
          f"{tailored} tailored.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump-pending", action="store_true", help="Print pending jobs as JSON")
    parser.add_argument("--save", type=str, default=None, help="Path to a JSON results file to save")
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
