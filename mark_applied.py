#!/usr/bin/env python3
"""Mark jobs as applied so they get archived out of resumes/index.html.

Usage -- mark specific jobs by job_id (no file needed):
    python3 mark_applied.py --job-id abc123 --job-id def456

Or mark everything currently generated (a full archive/reset):
    python3 mark_applied.py --all

After marking, re-run generate_resumes.py to rebuild index.html --
applied jobs are excluded from the default view from then on (pass
--show-applied to generate_resumes.py if you ever want to see them again).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import job_fetcher as jf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job-id", action="append", default=[], help="Mark a specific job_id applied (repeatable)")
    parser.add_argument("--all", action="store_true", help="Mark every currently-analyzed job as applied (bulk archive/reset)")
    args = parser.parse_args()

    jf.init_db()

    if args.all:
        con = sqlite3.connect(jf.DB_PATH)
        cur = con.execute(
            "UPDATE jobs SET applied = 1, applied_at = ? "
            "WHERE job_id IN (SELECT job_id FROM job_analysis WHERE tailored_resume_bullets IS NOT NULL) "
            "AND (applied IS NULL OR applied = 0)",
            (jf.now(),),
        )
        con.commit()
        con.close()
        print(f"Marked {cur.rowcount} job(s) as applied (bulk --all).")
        print("Re-run generate_resumes.py to rebuild index.html without them.")
        return

    job_ids: list[str] = list(args.job_id)
    if not job_ids:
        raise SystemExit("Nothing to do -- pass --job-id (repeatable) or --all.")
    con = sqlite3.connect(jf.DB_PATH)
    marked = 0
    for job_id in job_ids:
        cur = con.execute(
            "UPDATE jobs SET applied = 1, applied_at = ? WHERE job_id = ?",
            (jf.now(), job_id),
        )
        marked += cur.rowcount
    con.commit()
    con.close()

    print(f"Marked {marked}/{len(job_ids)} job(s) as applied.")
    if marked < len(job_ids):
        print("Some job_ids weren't found in the DB -- double check the export.")
    print("Re-run generate_resumes.py to rebuild index.html without them.")


if __name__ == "__main__":
    main()
