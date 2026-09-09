#!/usr/bin/env python3
"""Retroactively correct match_score for already-analyzed jobs where Gemini
skipped the mandatory experience-gap penalty (a known, confirmed LLM failure
mode -- verified against real jobs in this DB, e.g. a job stating "Experience
Required: 8+ Years" in its description scored 93 with no penalty applied).

This does NOT call Gemini again -- it deterministically extracts required
years from each job's already-stored description/title (regex first, title-
tier inference as fallback) and subtracts the same penalty bands used in the
scoring prompt, in code, so it's guaranteed to apply every time.

Since Gemini's existing match_score for penalty-skipped jobs is effectively
"skill-fit only" (the penalty step was silently dropped), subtracting the
correct penalty from that score recovers what it should have been -- no need
to re-score skill fit from scratch.

Usage:
    python3 apply_experience_penalty.py           # apply and save
    python3 apply_experience_penalty.py --dry-run # show what would change, no writes
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "job_fetcher.db"

# Same bands as the n8n scoring prompt.
def penalty_for_years(years: int) -> int:
    if years <= 5:
        return 0
    if years <= 7:
        return 15
    if years <= 9:
        return 30
    return 45


EXPLICIT_PATTERNS = [
    # "8+ years", "8 + years", "8-10 years", "minimum 6 years"
    re.compile(r"(\d{1,2})\s*\+\s*years?", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*-\s*\d{1,2}\s*years?", re.IGNORECASE),
    re.compile(r"minimum\s+(?:of\s+)?(\d{1,2})\s*years?", re.IGNORECASE),
    re.compile(r"at\s+least\s+(\d{1,2})\s*years?", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*years?\s+of\s+(?:professional\s+|relevant\s+|related\s+)?experience", re.IGNORECASE),
]

TITLE_TIERS = [
    (re.compile(r"\b(staff|principal|director|head of|vp|vice president)\b", re.IGNORECASE), 8),
    (re.compile(r"\b(senior|sr\.?|lead)\b", re.IGNORECASE), 6),
    (re.compile(r"\b(associate|analyst i\b|junior|jr\.?|entry.level)\b", re.IGNORECASE), 0),
]


MAX_PLAUSIBLE_YEARS = 20  # guards against false positives like "85 years of
# experience" (company-history boilerplate, e.g. T. Rowe Price's "more than
# 85 years of experience") being misread as a job requirement.


def infer_required_years(title: str, description: str) -> int:
    """Best-effort deterministic inference of required years, mirroring the
    scoring prompt's own STEP 1 logic but done in code instead of by the LLM.
    Scans every match per pattern (not just the first) and skips implausible
    values, since company-history blurbs ("85 years of experience") can
    otherwise get misread as the job's requirement."""
    text = description or ""
    for pattern in EXPLICIT_PATTERNS:
        for m in pattern.finditer(text):
            try:
                years = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if 0 < years <= MAX_PLAUSIBLE_YEARS:
                return years
    # No explicit number found -- fall back to title-based inference.
    for pattern, years in TITLE_TIERS:
        if pattern.search(title or ""):
            return years
    return 3  # mid-level default, matches "no seniority modifier -> 2-5 years"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT j.job_id, j.title, j.description, a.match_score
        FROM jobs j
        JOIN job_analysis a ON j.job_id = a.job_id
        WHERE a.match_score IS NOT NULL
        """
    ).fetchall()

    changed = 0
    updates = []
    for row in rows:
        years = infer_required_years(row["title"], row["description"])
        penalty = penalty_for_years(years)
        if penalty == 0:
            continue
        old_score = row["match_score"]
        new_score = max(0, old_score - penalty)
        if new_score == old_score:
            continue
        changed += 1
        updates.append((row["job_id"], row["title"], years, penalty, old_score, new_score))

    updates.sort(key=lambda u: -u[4])  # highest old_score first, most impactful to review
    for job_id, title, years, penalty, old_score, new_score in updates:
        print(f"  {old_score:>3} -> {new_score:>3}  (-{penalty:<2}, ~{years}yr req)  {title[:60]}  [{job_id}]")

    print(f"\n{changed} job(s) would have their match_score corrected downward.")

    if args.dry_run:
        print("Dry run -- no changes written. Re-run without --dry-run to apply.")
        return

    for job_id, _, _, _, _, new_score in updates:
        con.execute("UPDATE job_analysis SET match_score = ? WHERE job_id = ?", (new_score, job_id))
    con.commit()
    con.close()
    print("Applied. Re-run generate_resumes.py to rebuild resumes/index.html with corrected scores.")


if __name__ == "__main__":
    main()
