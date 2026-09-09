#!/usr/bin/env python3
"""Render a single general-purpose PDF resume straight from master_resume.json
(no job tailoring, no one-page trim) -- for uploading to AI agents/parsers like
Tsenta that build their own profile and do their own downstream tailoring, so
more real context (every bullet, full skill list) beats a squeezed one-pager.

For a human-facing cold-outreach resume where page count matters, use one of
the tailored PDFs in resumes/ instead.

Usage:
    python3 generate_master_resume.py

Output: master_resume.pdf in the current directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import generate_resumes as gr

BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / "master_resume.pdf"


def main() -> None:
    master = gr.load_master_resume()

    # Full skill list, no trimming -- an AI parser benefits from complete
    # context, unlike a human-facing one-pager.
    skills = []
    for bucket in master.get("skills_keyword_bank", {}).values():
        skills.extend(bucket)

    # Every real bullet from every experience entry (including projects),
    # untrimmed -- let the page count be whatever it needs to be.
    tailored_bullets = [
        {"company": e["company"], "bullets": [b["text"] for b in e.get("bullets", [])]}
        for e in master.get("experience", [])
    ]

    row = {
        "tailored_resume_bullets": json.dumps(tailored_bullets),
        "tailored_skills": json.dumps(skills),
        "tailored_summary": master.get("summary_variants", {}).get("default", ""),
        "cover_letter": "",
    }

    # max_bullets set high enough that trim_to_fit_one_page (called inside
    # build_pdf) never has to cut anything for a resume of this size.
    gr.build_pdf(row, master, OUT_PATH, max_bullets=999)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
