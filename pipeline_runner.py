#!/usr/bin/env python3
"""Run scheduled scrape and scoring; tailoring is queued only after selection.

Designed for a cloud scheduler (for example, every two hours). The scripts
run serially against the same SQLite database, and an OS lock prevents
overlapping scheduled runs.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def build_steps(analyze_limit: int | None, since_days: int,
                scrape_hours_old: int | None = None,
                analyze_since_hours: int | None = None,
                scrape_only: bool = False) -> list[tuple[str, list[str]]]:
    python = sys.executable
    scrape = [python, str(BASE_DIR / "job_fetcher.py")]
    if scrape_hours_old is not None:
        scrape.extend(["--hours-old", str(scrape_hours_old)])
    steps = [("Scrape new jobs", scrape)]
    if scrape_only:
        return steps
    analyze = [python, str(BASE_DIR / "analyze_jobs.py")]
    analyze.append("--score-only")
    if analyze_since_hours is not None:
        analyze.extend(["--since-hours", str(analyze_since_hours)])
    else:
        analyze.extend(["--since-days", str(since_days)])
    if analyze_limit is not None:
        analyze.extend(["--limit", str(analyze_limit)])
    steps.append(("Score new jobs (no tailoring until selected)", analyze))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print steps without running them")
    parser.add_argument("--analyze-limit", type=int, default=None,
                        help="Maximum pending jobs to analyze in this run")
    parser.add_argument("--since-days", type=int, default=3,
                        help="Ignore stale, unanalyzed jobs older than this many days")
    parser.add_argument("--scrape-hours-old", type=int, default=None,
                        help="Temporary scrape lookback in hours; leaves saved schedule unchanged")
    parser.add_argument("--analyze-since-hours", type=int, default=None,
                        help="Score only jobs first seen within this many hours")
    parser.add_argument("--scrape-only", action="store_true",
                        help="Skip the API-based analyze_jobs.py step entirely "
                             "(use when scoring/tailoring is handled elsewhere, e.g. "
                             "manual_analyze.py in an agent session)")
    args = parser.parse_args()

    if args.analyze_limit is not None and args.analyze_limit < 1:
        parser.error("--analyze-limit must be a positive integer")
    if args.since_days < 1:
        parser.error("--since-days must be a positive integer")
    if args.scrape_hours_old is not None and args.scrape_hours_old < 1:
        parser.error("--scrape-hours-old must be a positive integer")
    if args.analyze_since_hours is not None and args.analyze_since_hours < 1:
        parser.error("--analyze-since-hours must be a positive integer")

    steps = build_steps(args.analyze_limit, args.since_days,
                        args.scrape_hours_old, args.analyze_since_hours,
                        args.scrape_only)
    if args.dry_run:
        for label, command in steps:
            print(f"{label}: {' '.join(command)}")
        return 0

    lock_id = hashlib.sha256(str(BASE_DIR).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"career-intelligence-{lock_id}.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A pipeline run is already active; skipping this schedule tick.")
            return 0

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        for label, command in steps:
            print(f"\n=== {label} ===", flush=True)
            try:
                result = subprocess.run(
                    command,
                    cwd=BASE_DIR,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
            except OSError as exc:
                print(f"Could not start {label}: {exc}", file=sys.stderr)
                return 1
            if result.returncode:
                print(f"{label} failed with exit code {result.returncode}; stopping this run.",
                      file=sys.stderr)
                return result.returncode

    print("\nPipeline finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
