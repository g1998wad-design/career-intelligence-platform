#!/usr/bin/env python3
"""Resume sending jobs to n8n without re-scraping.

job_fetcher.py's run() always re-scrapes from scratch. But every eligible
job it finds gets saved to the `jobs` table (status='discovered') *before*
it's sent -- so if a run gets cut short by the consecutive-failures circuit
breaker, the unsent eligible jobs aren't lost, they're just sitting in the
DB unsent. This script picks those back up directly, applying the same
previously-failed (job_id and normalized company+title) skip logic as
run(), and sends them in the same batches/delays -- skipping the ~30 min
scrape phase entirely since nothing about the source postings changed.

Usage: python3 resume_send.py
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from job_fetcher import (
    Stats, PipelineHalted, RateLimited,
    load_config, db, company_name, job_title, process_batch, set_status,
    save_stats, now,
)


def main() -> None:
    cfg = load_config()

    with db() as con:
        previously_failed_title_company = {
            (company_name(row[0]), job_title(row[1]))
            for row in con.execute("SELECT company, title FROM jobs WHERE status='failed'")
        }
        col_names = [
            "job_id", "title", "company", "location", "description", "url", "source",
            "company_url", "company_domain", "date_posted", "job_type", "remote_status",
            "location_compatibility", "salary_min", "salary_max", "salary_interval",
            "currency", "sponsorship_status", "clearance_status", "role_family",
            "seniority", "description_quality", "preliminary_score", "search_term",
            "search_priority",
        ]
        rows = con.execute(f"""
            SELECT {','.join(col_names)}
            FROM jobs WHERE status='discovered' AND last_seen_at >= '2026-09-13T16:50'
            ORDER BY preliminary_score DESC, search_priority ASC
        """).fetchall()

    eligible_jobs: List[Dict[str, Any]] = []
    skipped = 0
    for row in rows:
        j = dict(zip(col_names, row))
        if (company_name(j["company"]), job_title(j["title"])) in previously_failed_title_company:
            skipped += 1
            set_status(j["job_id"], "failed")
            continue
        eligible_jobs.append(j)

    print(f"Resuming {len(eligible_jobs)} unsent job(s) from DB "
          f"(skipped {skipped} matching an already-failed company+title)")

    stats = Stats(run_id=f"resume_{now()}", started_at=now())
    size = int(cfg["batch_size"])
    try:
        for start in range(0, len(eligible_jobs), size):
            process_batch(eligible_jobs[start:start + size], cfg, stats)
            if start + size < len(eligible_jobs):
                time.sleep(int(cfg["batch_delay_seconds"]))
    except PipelineHalted as exc:
        reason = "rate limit" if isinstance(exc, RateLimited) else "repeated failures"
        stats.errors.append(f"Run stopped early ({reason}): {exc}")
        print(f"\nRun stopped early due to {reason}. {stats.sent} job(s) sent successfully "
              f"before the stop. Nothing sent so far is lost.")

    stats.eligible = len(eligible_jobs)
    save_stats(stats, cfg)
    print(f"\nDone. Sent: {stats.sent}, Failed: {stats.failed}")


if __name__ == "__main__":
    main()
