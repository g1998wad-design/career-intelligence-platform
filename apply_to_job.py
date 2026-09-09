#!/usr/bin/env python3
"""Tailor a resume (and cover letter, if it scores 85+) for ONE job you found
yourself -- e.g. browsing a company's careers page directly -- without waiting
for or triggering a full scraping run.

Usage -- as simple as it gets:
    1. On the job posting, select and copy (Cmd+C) the full job description.
    2. Run:
       python3 apply_to_job.py
    3. Answer the 3 quick prompts (company, title, and optionally a URL).

That's it -- no file to create, no flags to remember. The job description is
read straight from your clipboard.

This sends the job through the exact same Gemini tailoring pipeline as the
scraper (same n8n webhook, same master_resume.json, same scoring/tailoring
rules), then immediately builds a tailored resume PDF -- and a cover letter
PDF too, if it scores 85+ -- in resumes/, and opens them automatically.
"""
from __future__ import annotations

import subprocess
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import job_fetcher as jf
import generate_resumes as gr


def read_clipboard() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        raise SystemExit(f"Could not read your clipboard ({e}). This script needs macOS's pbpaste.")


def main() -> None:
    description = read_clipboard()
    if not description or len(description) < 100:
        raise SystemExit(
            "Your clipboard doesn't look like it has a job description in it "
            "(it's empty or very short). Copy the full posting text (Cmd+C) and try again."
        )

    print(f"Got {len(description)} characters from your clipboard.\n")
    company = input("Company: ").strip()
    title = input("Job title: ").strip()
    if not company or not title:
        raise SystemExit("Company and title are both required.")
    location = input("Location (optional, press Enter to skip): ").strip()
    url = input("Job URL (optional, press Enter to skip): ").strip()

    cfg = jf.load_config()
    jf.init_db()

    normalized_company = jf.company_name(company)
    normalized_title = jf.job_title(title)
    fingerprint = jf.digest(f"manual|{normalized_company}|{normalized_title}|{jf.now()[:7]}", 32)
    job_id = f"manual_{normalized_company[:20].replace(' ', '_')}_{normalized_title[:30].replace(' ', '_')}_{fingerprint[:10]}"

    job = {
        "job_id": job_id, "fingerprint": fingerprint, "url": url, "apply_url": url,
        "title": title, "company": company, "location": location,
        "description": description[:int(cfg["maximum_description_characters"])],
        "source": "manual", "date_posted": jf.now()[:10],
        "remote_status": "unknown", "location_compatibility": "unknown",
        "sponsorship_status": "not_mentioned", "clearance_status": "not_mentioned",
        "role_family": "other", "seniority": "mid_level",
        "description_quality": "complete", "preliminary_score": 100,
        "search_term": "manual", "search_priority": 1, "status": "discovered",
        "raw_record": {"manual_entry": True},
    }
    jf.save_job(job)

    print(f"\nSending '{title}' at '{company}' to n8n for tailoring...")
    stats = jf.Stats(run_id="manual_" + jf.now()[:19].replace(":", "").replace("-", ""), started_at=jf.now())
    jf.process_batch([job], cfg, stats)

    if stats.sent == 0:
        print("Failed -- see the error above. Nothing was generated.")
        if stats.errors:
            print("Details:", stats.errors[-1])
        return

    print("Success. Building PDF(s)...")
    master = gr.load_master_resume()
    con = sqlite3.connect(gr.DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT j.job_id, j.title, j.company, j.url, a.tailored_summary, a.tailored_skills, "
        "a.tailored_resume_bullets, a.match_score, a.cover_letter "
        "FROM job_analysis a JOIN jobs j ON j.job_id = a.job_id WHERE a.job_id = ?",
        (job_id,)
    ).fetchone()
    con.close()

    if not row:
        print("Could not find cached analysis for this job -- something went wrong upstream.")
        return

    gr.OUTPUT_DIR.mkdir(exist_ok=True)
    base = f"{gr.slug(row['company'])}__{gr.slug(row['title'])}__{row['job_id']}"
    resume_path = gr.OUTPUT_DIR / f"{base}.pdf"
    gr.build_pdf(row, master, resume_path, max_bullets=11)
    print(f"  Match score: {row['match_score']}")
    print(f"  Resume: {resume_path}")

    opened = [str(resume_path)]
    if row["cover_letter"]:
        letter_path = gr.OUTPUT_DIR / f"{base}__cover_letter.pdf"
        gr.build_cover_letter_pdf(row, master, letter_path)
        print(f"  Cover letter: {letter_path}")
        opened.append(str(letter_path))
    else:
        print("  No cover letter (only generated automatically for 85+ matches).")

    try:
        subprocess.run(["open", *opened])
    except Exception:
        pass  # not critical -- the paths above are printed either way


if __name__ == "__main__":
    main()
