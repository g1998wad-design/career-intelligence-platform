# Career Intelligence Platform

An AI-powered pipeline that scrapes job postings, scores them against my resume with an LLM, generates a tailored one-page PDF resume + cover letter per job, and auto-fills the ATS application form — cutting job-search research time by roughly 70%. Now used by 10+ other job seekers.

## Why

Job seekers waste hours re-searching the same sites, re-reading postings to judge fit, and re-typing the same fields into every ATS. This pipeline automates the repetitive 80% (search, scoring, tailoring, form-filling) and leaves the judgment calls (which jobs to actually apply to, answering EEO/legal questions, hitting Submit) to a human.

## Architecture

```
JobSpy (LinkedIn / Indeed / Google jobs)
        │  scrape + dedupe + relevance pre-filter
        ▼
   n8n webhook  ──▶  Gemini LLM
        │             (match scoring, missing-skills extraction,
        │              AI pitch / cover letter generation)
        ▼
   SQLite (job_fetcher.db)
        │
        ├──▶ generate_resumes.py ──▶ tailored PDF resume + cover letter per job
        │                             + resumes/index.html (sortable results table)
        │
        └──▶ ats_autofill.py ──▶ Playwright-driven browser fills name/email/
                                  phone/address/LinkedIn + uploads resume/cover
                                  letter into the real application form
```

## Components

- **`job_fetcher.py`** — Scrapes LinkedIn/Indeed/Google via [JobSpy](https://github.com/speedyapply/JobSpy), deduplicates by URL and cross-source fingerprint, detects sponsorship/clearance/citizenship requirements and role family, runs a lightweight pre-filter score before spending LLM calls, and posts batches to an n8n webhook with retry/backoff and poison-item isolation. Caches LLM output per job so re-runs never re-pay for jobs already analyzed.
- **`generate_resumes.py`** — Builds a one-page tailored PDF resume and cover letter per job from a master bullet bank (`master_resume.json`), auto-shrinking font/spacing until it fits exactly one page. Also builds `resumes/index.html`: a sortable results table (match score, company, title, resume/cover-letter links, direct-apply availability) with checkboxes to select a batch and export it for autofill.
- **`ats_autofill.py`** — Given a batch of selected jobs, opens each posting in a real browser via Playwright, detects the ATS platform (Greenhouse, Workday, iCIMS, Lever, Ashby, SmartRecruiters, Taleo, SuccessFactors), and fills whatever fields it can confidently match — name, email, phone, address, LinkedIn, resume/cover-letter file uploads. **Deliberately never** answers sponsorship, work authorization, EEO/demographic, salary, or clearance questions, and **never** clicks Submit — those are always flagged for manual review. Runs headed by default so you can review/finish each application yourself; `--headless` does a dry-run field-coverage scan against a new ATS before a real pass.
- **`apply_to_job.py`** / **`tailor_clipboard_job.py`** — One-off path for a single job pasted from clipboard, bypassing a full scrape run but reusing the same n8n/Gemini scoring and tailoring pipeline.

## Stack

Python, SQLite, n8n, Google Gemini, Playwright, ReportLab (PDF generation), JobSpy.

## Setup

```bash
pip install -r requirements.txt
playwright install
cp autofill_profile.example.json autofill_profile.json   # fill in your own details
```

Requires a running n8n instance with a webhook workflow wired to a Gemini API key (not included — this repo is the scraping/scoring/tailoring/autofill client, not the n8n workflow credentials).

## Status

Actively in use for my own job search. Not packaged as a hosted product — this is the real, working pipeline I run locally.
