"""Export tailored-job data + PDFs from job_fetcher.db into resume-site/,
so the Next.js resume index has a static data.json + copied PDFs to serve.

Run this any time after generate_resumes.py regenerates PDFs, to push the
latest data into the deployed site. Mirrors the same query/filename
convention as generate_resumes.py's build_index(), so the two views never
drift apart.
"""
import json
import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "job_fetcher.db"
RESUMES_DIR = BASE_DIR / "resumes"
SITE_DIR = BASE_DIR / "resume-site"
SITE_PDFS_DIR = SITE_DIR / "public" / "pdfs"
SITE_DATA_PATH = SITE_DIR / "data" / "jobs.json"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT j.job_id, j.title, j.company, j.location, j.url, j.apply_url,
               j.applicant_count, a.match_score, a.cover_letter, a.processed_at
        FROM job_analysis a
        JOIN jobs j ON j.job_id = a.job_id
        WHERE a.tailored_resume_bullets IS NOT NULL
          AND (j.applied IS NULL OR j.applied = 0)
        ORDER BY a.match_score DESC
    """).fetchall()
    con.close()

    SITE_PDFS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Clear previously-copied PDFs so removed/applied jobs don't linger.
    for f in SITE_PDFS_DIR.glob("*.pdf"):
        f.unlink()

    jobs = []
    skipped_missing_pdf = 0
    for r in rows:
        base = r["job_id"]
        resume_filename = f"{base}.pdf"
        resume_src = RESUMES_DIR / resume_filename
        if not resume_src.exists():
            skipped_missing_pdf += 1
            continue
        shutil.copy(resume_src, SITE_PDFS_DIR / resume_filename)

        cover_letter_filename = None
        if r["cover_letter"] and r["cover_letter"].strip():
            cl_filename = f"{base}__cover_letter.pdf"
            cl_src = RESUMES_DIR / cl_filename
            if cl_src.exists():
                shutil.copy(cl_src, SITE_PDFS_DIR / cl_filename)
                cover_letter_filename = cl_filename

        jobs.append({
            "job_id": r["job_id"],
            "title": r["title"],
            "company": r["company"],
            "location": r["location"],
            "match_score": r["match_score"],
            "applicant_count": r["applicant_count"],
            "url": r["url"],
            "apply_url": r["apply_url"],
            "has_direct_apply": bool(r["apply_url"]) and r["apply_url"] != r["url"],
            "resume_filename": resume_filename,
            "cover_letter_filename": cover_letter_filename,
            "processed_at": r["processed_at"],
        })

    SITE_DATA_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    print(f"Exported {len(jobs)} job(s) to {SITE_DATA_PATH}")
    print(f"Copied PDFs to {SITE_PDFS_DIR}")
    if skipped_missing_pdf:
        print(f"Skipped {skipped_missing_pdf} job(s) with no resume PDF on disk "
              f"(run generate_resumes.py first)")


if __name__ == "__main__":
    main()
