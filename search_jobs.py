import json
import sys
import logging
from jobspy import scrape_jobs


# Keep JobSpy logs out of stdout so Next.js can parse clean JSON.
logging.basicConfig(level=logging.ERROR)


def search_jobs(roles, hours_old=24):
    results = []
    seen_urls = set()

    for role in roles:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "google"],
                search_term=role,
                location="United States",
                results_wanted=10,
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=False,
            )

            if jobs.empty:
                continue

            records = jobs.to_dict(orient="records")

            for job in records:
                url = str(job.get("job_url", "")).strip()

                if not url:
                    continue

                if url in seen_urls:
                    continue

                seen_urls.add(url)

                results.append({
                    "title": str(job.get("title", "")),
                    "company": str(job.get("company", "")),
                    "location": str(job.get("location", "")),
                    "url": url,
                    "source": str(job.get("site", "")),
                    "role_searched": role,
                })

        except Exception as e:
            # Print errors to stderr so stdout remains valid JSON.
            print(f"Error searching {role}: {e}", file=sys.stderr)

    return results


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            roles = ["Analytics Engineer", "GTM Engineer"]
        else:
            roles = json.loads(sys.argv[1])

        jobs = search_jobs(roles)

        print(json.dumps(jobs))

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        print(json.dumps([]))