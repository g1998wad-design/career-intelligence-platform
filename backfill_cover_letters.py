"""One-off backfill: re-send jobs that scored >=75 but ended up with an
empty cover_letter (see the n8n 'Extract cover letter' silent-empty bug)
back through the same n8n webhook, one at a time, so they get a real
cover letter this time. Safe to re-run -- cache_analysis_results() upserts
by job_id, so a job that succeeds this run just overwrites its old blank
row; a job that still fails is simply left as-is for the next attempt.
"""
import time
from job_fetcher import db, load_config, load_master_resume, n8n_payload, post_batch, cache_analysis_results

JOB_COLUMNS = [
    "job_id", "title", "company", "location", "description", "url", "source",
    "company_url", "company_domain", "date_posted", "job_type", "remote_status",
    "location_compatibility", "salary_min", "salary_max", "salary_interval",
    "currency", "sponsorship_status", "clearance_status", "role_family",
    "seniority", "description_quality", "preliminary_score", "search_term",
]


def main():
    cfg = load_config()
    load_master_resume()

    with db() as con:
        con.row_factory = __import__("sqlite3").Row
        rows = con.execute(f"""
            SELECT j.{', j.'.join(JOB_COLUMNS)}
            FROM jobs j JOIN job_analysis a ON j.job_id = a.job_id
            WHERE a.match_score >= 75 AND (a.cover_letter IS NULL OR a.cover_letter = '')
            ORDER BY a.match_score DESC
        """).fetchall()

    jobs = [{k: r[k] for k in JOB_COLUMNS} for r in rows]
    print(f"Re-sending {len(jobs)} job(s) missing a cover letter...\n")

    succeeded, still_empty, failed = [], [], []
    for j in jobs:
        label = f"{j['company']} -- {j['title']}"
        ok, response, error = post_batch([j], cfg)
        if not ok:
            print(f"  [FAILED]     {label}: {error}")
            failed.append(label)
            continue
        cached, low_match = cache_analysis_results(response)
        results = response.get("results", []) if isinstance(response, dict) else []
        cl = next((r.get("cover_letter") for r in results if r.get("job_id") == j["job_id"]), None)
        if cl and cl.strip():
            print(f"  [OK]         {label} ({len(cl.split())} words)")
            succeeded.append(label)
        else:
            print(f"  [STILL EMPTY] {label}")
            still_empty.append(label)
        time.sleep(2)  # be gentle on the same LLM calls that were flaking under rapid-fire load

    print(f"\nDone. {len(succeeded)} fixed, {len(still_empty)} still empty, {len(failed)} request-failed.")
    if still_empty:
        print("Still empty (worth a second pass or a manual cover letter from Claude):")
        for label in still_empty:
            print(f"  - {label}")


if __name__ == "__main__":
    main()
