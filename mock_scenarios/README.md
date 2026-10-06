# Mock job application scenarios

These are fictional examples for explaining the intended workflow. They are not in `job_fetcher.db`, are not queued, and their URLs must not be used to apply.

## 1. LinkedIn → Greenhouse

The LinkedIn scraper saves the LinkedIn listing URL. With JobSpy LinkedIn detail fetching enabled, it may also return the employer's Greenhouse URL as `job_url_direct`. The job appears in review with a direct application link. After you select it and the tailored resume is ready, **Prepare application** opens the Greenhouse URL in Chrome, fills recognized fields, uploads the resume, and stores a screenshot/report. If every field is recognized and answered, the phone review page offers **Approve & submit**. The worker submits only after that approval.

If JobSpy cannot extract the external URL, this scenario becomes case 3 instead.

## 2. LinkedIn → Workday

When the direct Workday URL is captured, the worker opens Workday directly. It fills fields it can match to the saved profile and tailored resume. It advances through clearly labeled Next/Continue steps only when it found no unanswered or unrecognized fields on the current step. It stops for review at unknown questions, missing answers, an interstitial, or the navigation limit. If it reaches a clean final form, it waits for **Approve & submit**. The submission code also refuses to proceed while another Next/Continue button is present.

Workday pages vary by employer; this is best-effort form support and still needs validation against real postings before relying on it.

## 3. LinkedIn listing with no external URL

The job can still be scored and shown with its LinkedIn listing link, but the application worker cannot begin from the employer site without an employer URL. The app queue rejects it rather than guessing or submitting to the LinkedIn listing. The current fallback is the existing Indeed/Google exact-company/title match. If that finds a direct employer URL, use the matched job; if it does not, the system needs a manual external-link handoff feature before this job can enter the application worker.
