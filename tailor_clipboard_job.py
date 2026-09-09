#!/usr/bin/env python3
"""Tailor a resume for a single ad-hoc job (e.g. one you found manually and
copied the description for) without running the full job_fetcher.py scrape.

Reads the job description from your clipboard (macOS `pbpaste`), asks for
title/company/location/url, inserts it into job_fetcher.db exactly like a
normal scrape would, sends it to the same n8n webhook for scoring +
tailoring, caches the result, and tells you the job_id to render with
generate_resumes.py.

Usage:
    python tailor_clipboard_job.py --title "Sr. Business Analyst - US Card" \\
        --company "Capital One" --location "Remote" \\
        [--url "https://..."]

Then:
    python generate_resumes.py --job-id <job_id printed above>
    python generate_resumes.py   # full regen afterward, so index.html isn't clobbered
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import job_fetcher as jf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--location", default="United States")
    ap.add_argument("--url", default="", help="Job posting URL (optional, but recommended for apply_url)")
    args = ap.parse_args()

    description = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout.strip()
    if not description:
        sys.exit("Clipboard is empty -- copy the job description first.")

    cfg = jf.load_config()
    jf.init_db()

    raw = {
        "title": args.title,
        "company": args.company,
        "location": args.location,
        "job_url": args.url or f"manual://{jf.digest(args.title + args.company)}",
        "description": description,
        "site": "manual",
    }
    normalized = jf.normalize_record(raw, search_term="manual", priority=1, cfg=cfg)
    if normalized is None:
        sys.exit("Could not normalize job -- title/company/url missing.")

    job_id = normalized["job_id"]
    print(f"job_id: {job_id}")

    if jf.already_analyzed(job_id):
        print("Already analyzed previously -- skipping n8n call, just render it.")
    else:
        jf.save_job(normalized)
        ok, data, error = jf.post_batch([normalized], cfg)
        if not ok:
            sys.exit(f"n8n call failed: {error}")
        cached, dropped = jf.cache_analysis_results(data)
        if job_id in dropped:
            sys.exit(f"Scored below the match threshold -- n8n dropped it before tailoring. Response: {data}")
        if cached == 0:
            sys.exit(f"n8n responded but no result was cached. Raw response: {data}")
        jf.set_status(job_id, "analyzed", response=data)
        print(f"Scored + tailored. Cached {cached} result(s).")

    print(f"\nNow run:\n  python generate_resumes.py --job-id {job_id}\n  python generate_resumes.py   # full regen so index.html isn't left truncated")


if __name__ == "__main__":
    main()
