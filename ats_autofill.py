#!/usr/bin/env python3
"""Batch-fill job applications from a hand-picked list of jobs.

Usage:
    1. Open resumes/index.html, check 10-15 jobs, click "Export Selected".
    2. Move the downloaded selected_batch.json into this project's root.
    3. Fill in autofill_profile.json (name/email/phone/etc -- do this once).
    4. Run:
       python3 ats_autofill.py

For each job it opens the posting URL in a real (visible) browser, detects
the ATS platform, and fills whatever common fields it can confidently match
(name, email, phone, address, resume/cover-letter upload). It NEVER fills in
or guesses answers to sensitive/legal questions -- work authorization,
sponsorship, EEO/demographic info, salary expectations, clearance, etc are
always left for you to answer, and it NEVER clicks Submit. After filling a
job it pauses so you can review/finish/submit it yourself, then press Enter
to move to the next one. A summary of what was filled vs. what needs your
attention is written to batch_run_log.json.

Use --headless to just scan every job for field coverage (no pausing, no
browser window) -- handy for checking how well the field-matching does
against a new ATS before running the real interactive pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, Page, Frame

BASE_DIR = Path(__file__).resolve().parent
BATCH_PATH = BASE_DIR / "selected_batch.json"
PROFILE_PATH = BASE_DIR / "autofill_profile.json"
LOG_PATH = BASE_DIR / "batch_run_log.json"
RESUMES_DIR = BASE_DIR / "resumes"
SCREENSHOT_DIR = BASE_DIR / "autofill_screenshots"

# label substring -> profile.json key. Checked only after the sensitive-word
# check below, so a field can never match both.
FIELD_KEYWORDS: Dict[str, List[str]] = {
    "first_name": ["first name", "given name", "legal first name"],
    "last_name": ["last name", "family name", "surname", "legal last name"],
    "full_name": ["full name", "your name", "applicant name", "candidate name"],
    "email": ["email address", "e-mail", "email"],
    "phone": ["phone number", "mobile number", "phone", "telephone", "contact number"],
    "linkedin": ["linkedin"],
    "website": ["website", "portfolio", "personal site", "github"],
    "city": ["city"],
    "state": ["state", "province", "region"],
    "zip": ["zip code", "postal code", "zip"],
    "country": ["country"],
    "address": ["street address", "address line 1", "address line", "mailing address", "address"],
}

# If a field's label contains any of these, it is ALWAYS flagged for manual
# review and NEVER auto-filled, regardless of what else it might match.
SENSITIVE_KEYWORDS = [
    "sponsorship", "sponsor", "visa", "authorized to work", "authorization to work",
    "work authorization", "legally eligible",
    "race", "ethnicity", "gender", "pronoun", "veteran", "disability", "lgbtq",
    "security clearance", "clearance", "salary", "compensation", "pay expectation",
    "date of birth", "birth date", "ssn", "social security",
    "criminal", "felony", "conviction", "background check",
    "how did you hear", "referral", "willing to relocate", "notice period",
    "start date", "available to start",
]

RESUME_FILE_KEYWORDS = ["resume", "cv", "curriculum vitae"]
COVER_LETTER_FILE_KEYWORDS = ["cover letter", "cover_letter", "coverletter"]

ATS_PATTERNS = {
    "greenhouse": ["greenhouse.io"],
    "workday": ["myworkdayjobs.com", "workday.com"],
    "icims": ["icims.com"],
    "lever": ["lever.co"],
    "ashby": ["ashbyhq.com"],
    "smartrecruiters": ["smartrecruiters.com"],
    "taleo": ["taleo.net"],
    "successfactors": ["successfactors.com"],
}

LOW_CONFIDENCE_ATS = {"workday"}  # heavy multi-step SPA -- generic filling is unreliable


def detect_ats(url: str) -> str:
    low = url.lower()
    for name, patterns in ATS_PATTERNS.items():
        if any(p in low for p in patterns):
            return name
    return "unknown"


def load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise SystemExit(f"{what} not found at {path}. See ats_autofill.py's module docstring for setup steps.")
    return json.loads(path.read_text(encoding="utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def label_for_element(frame: Frame, handle) -> str:
    """Best-effort text describing what a form field is asking for."""
    try:
        text = handle.evaluate(
            """(el) => {
                if (el.labels && el.labels.length) {
                    return [...el.labels].map(l => l.innerText).join(' ');
                }
                const aria = el.getAttribute('aria-label');
                if (aria) return aria;
                const describedBy = el.getAttribute('aria-describedby');
                if (describedBy) {
                    const d = document.getElementById(describedBy);
                    if (d) return d.innerText;
                }
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) return lbl.innerText;
                }
                const placeholder = el.getAttribute('placeholder');
                if (placeholder) return placeholder;
                const container = el.closest('div, fieldset, li, td, tr');
                if (container) return container.innerText.slice(0, 200);
                return '';
            }"""
        )
        return (text or "").strip().replace("\n", " ")
    except Exception:
        return ""


def find_upload_context(handle) -> str:
    """File inputs on ATS forms (Greenhouse especially) are usually hidden behind
    a button labeled just 'Attach' with 'Resume/CV' or 'Cover Letter' as a heading
    several DOM levels up, outside the small container label_for_element checks.
    Climb further, looking specifically for that heading text."""
    try:
        text = handle.evaluate(
            """(el) => {
                let node = el;
                for (let i = 0; i < 6 && node; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const t = (node.innerText || '').trim();
                    if (t.length > 0 && t.length < 400) {
                        const low = t.toLowerCase();
                        if (low.includes('resume') || low.includes(' cv') || low.includes('cover letter')) {
                            return t;
                        }
                    }
                    if (t.length > 800) break;  // climbed too far into unrelated page content
                }
                return '';
            }"""
        )
        return (text or "").strip().replace("\n", " ")
    except Exception:
        return ""


def match_field(label: str) -> Optional[str]:
    low = label.lower().strip()
    if low in ("name", "your name", "legal name"):
        return "full_name"
    for key, keys in FIELD_KEYWORDS.items():
        if any(k in low for k in keys):
            return key
    return None


def is_sensitive(label: str) -> bool:
    low = label.lower()
    return any(k in low for k in SENSITIVE_KEYWORDS)


def fill_frame(frame: Frame, profile: Dict[str, Any], job: Dict[str, Any],
                filled: List[str], needs_review: List[str], unmatched: List[str],
                seen_radio_groups: set) -> None:
    try:
        elements = frame.query_selector_all("input, textarea, select")
    except Exception:
        return

    for el in elements:
        try:
            if not el.is_visible():
                continue
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            input_type = (el.get_attribute("type") or "text").lower() if tag == "input" else tag

            # Radio/checkbox groups fire one element per option (e.g. an EEO race
            # question renders 6+ separate radios) -- flag the group once by its
            # `name` attribute instead of once per option, or review lists become
            # unreadable on EEO-heavy forms.
            if input_type in ("radio", "checkbox"):
                group_key = el.get_attribute("name") or el.get_attribute("id") or ""
                if group_key:
                    if group_key in seen_radio_groups:
                        continue
                    seen_radio_groups.add(group_key)

            label = label_for_element(frame, el)
            if not label:
                continue

            if input_type == "file":
                low = label.lower()
                if not any(k in low for k in RESUME_FILE_KEYWORDS + COVER_LETTER_FILE_KEYWORDS):
                    # The immediate label (often just the visible button text, e.g.
                    # "Attach") doesn't say which upload this is -- climb the DOM for
                    # a "Resume/CV" or "Cover Letter" section heading above it.
                    wider = find_upload_context(el)
                    if wider:
                        label = wider
                        low = label.lower()
                if any(k in low for k in RESUME_FILE_KEYWORDS):
                    resume_path = RESUMES_DIR / job["resume_filename"]
                    if resume_path.exists():
                        el.set_input_files(str(resume_path))
                        filled.append(f"[file] resume <- {resume_path.name} (label: {label[:60]})")
                    else:
                        needs_review.append(f"[file] resume upload found but {resume_path} is missing (label: {label[:60]})")
                elif any(k in low for k in COVER_LETTER_FILE_KEYWORDS):
                    cl_name = job.get("cover_letter_filename")
                    cl_path = RESUMES_DIR / cl_name if cl_name else None
                    if cl_path and cl_path.exists():
                        el.set_input_files(str(cl_path))
                        filled.append(f"[file] cover letter <- {cl_path.name} (label: {label[:60]})")
                    else:
                        needs_review.append(f"[file] cover letter upload found but none generated for this job (label: {label[:60]})")
                else:
                    needs_review.append(f"[file] unrecognized file upload (label: {label[:60]})")
                continue

            is_group = input_type in ("radio", "checkbox")

            if is_sensitive(label):
                tag_str = f"[{input_type} group]" if is_group else f"[{input_type}]"
                needs_review.append(f"{tag_str} {label[:80]}")
                continue

            if tag == "select" or is_group:
                # Never guess dropdown/radio/checkbox answers -- too easy to silently
                # pick the wrong option (this covers non-sensitive multi-choice
                # questions too, e.g. "how did you hear about us").
                tag_str = f"[{input_type} group]" if is_group else "[select]"
                needs_review.append(f"{tag_str} {label[:80]}")
                continue

            key = match_field(label)
            if key and profile.get(key):
                el.fill(str(profile[key]))
                filled.append(f"[{input_type}] {key} <- \"{profile[key]}\" (label: {label[:60]})")
            elif key:
                needs_review.append(f"[{input_type}] {label[:80]} (matched '{key}' but profile value is blank)")
            else:
                unmatched.append(f"[{input_type}] {label[:80]}")
        except Exception as e:
            unmatched.append(f"[error reading field: {e}]")


APPLY_BUTTON_PATTERN = re.compile(r"^\s*apply(\s+for\s+this\s+job|\s+now)?\s*$", re.IGNORECASE)
COOKIE_BUTTON_PATTERN = re.compile(r"^\s*(accept(\s+all)?(\s+cookies)?|i\s+accept|got\s+it|allow\s+all)\s*$", re.IGNORECASE)


def dismiss_cookie_banner(page: Page) -> bool:
    """Cookie-consent overlays are extremely common and sit on top of the page,
    intercepting clicks on whatever's underneath (e.g. Workday's Apply button).
    Best effort -- only clicks unambiguous accept/dismiss wording, never anything
    that looks like a real form choice."""
    for frame in page.frames:
        try:
            candidates = frame.get_by_role("button", name=COOKIE_BUTTON_PATTERN).all()
            for el in candidates:
                if el.is_visible():
                    el.click(timeout=3000)
                    page.wait_for_timeout(500)
                    return True
        except Exception:
            continue
    return False


def click_apply_button(page: Page) -> bool:
    """Many ATS pages (Ashby, Greenhouse, etc) show the job description first
    and only reveal the actual application form after an 'Apply' click. Best
    effort only -- if nothing matches, we just scan whatever's already on the
    page, which is correct for ATS platforms that show the form immediately."""
    for frame in page.frames:
        try:
            candidates = frame.get_by_role("button", name=APPLY_BUTTON_PATTERN).all() + \
                         frame.get_by_role("link", name=APPLY_BUTTON_PATTERN).all()
            for el in candidates:
                if el.is_visible():
                    el.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    return True
        except Exception:
            continue
    return False


def process_job(page: Page, job: Dict[str, Any], profile: Dict[str, Any],
                 headless: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "job_id": job.get("job_id"), "company": job.get("company"), "title": job.get("title"),
        "url": job.get("url"), "timestamp": now(),
    }

    if not job.get("url"):
        result.update(status="error", error="No posting URL for this job", ats="unknown")
        return result

    ats = detect_ats(job["url"])
    result["ats"] = ats

    from urllib.parse import urlparse
    host = (urlparse(job["url"]).hostname or "").lower()
    if host in {"www.linkedin.com", "linkedin.com", "www.indeed.com", "indeed.com"}:
        result.update(
            status="needs_review",
            filled_fields=[],
            unmatched_fields=[],
            needs_review_fields=[
                f"No direct ATS application link was found for this job -- this URL is just "
                f"the {host} listing page, which requires being logged in to apply (Easy Apply "
                f"or an external redirect). Not attempted here; apply manually."
            ],
        )
        print(f"\n{'='*70}\n{job.get('company')} -- {job.get('title')}  [{host}, no direct link]")
        print("  Skipped auto-fill -- no direct ATS URL available for this job, apply manually.")
        return result

    try:
        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)  # let JS-heavy ATS pages (Workday/Greenhouse) render the form
    except Exception as e:
        result.update(status="error", error=f"Failed to load page: {e}")
        return result

    dismiss_cookie_banner(page)
    click_apply_button(page)

    filled: List[str] = []
    needs_review: List[str] = []
    unmatched: List[str] = []
    seen_radio_groups: set = set()

    for frame in page.frames:
        fill_frame(frame, profile, job, filled, needs_review, unmatched, seen_radio_groups)

    if ats in LOW_CONFIDENCE_ATS:
        needs_review.insert(0, f"[low confidence] {ats} uses a multi-step application flow -- verify every field by hand")

    SCREENSHOT_DIR.mkdir(exist_ok=True)
    shot_path = SCREENSHOT_DIR / f"{job.get('company', 'job')}__{job.get('job_id', '')}.png".replace("/", "_").replace(" ", "_")
    try:
        page.screenshot(path=str(shot_path), full_page=True)
        result["screenshot"] = str(shot_path.relative_to(BASE_DIR))
    except Exception:
        pass

    result.update(
        status="needs_review" if needs_review or unmatched else "filled",
        filled_fields=filled, needs_review_fields=needs_review, unmatched_fields=unmatched,
    )

    print(f"\n{'='*70}\n{job.get('company')} -- {job.get('title')}  [{ats}]")
    print(f"  Filled: {len(filled)}   Needs review: {len(needs_review)}   Unmatched: {len(unmatched)}")
    for f in needs_review:
        print(f"  ! {f}")
    print(f"  Screenshot: {result.get('screenshot', 'n/a')}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--headless", action="store_true",
                         help="Scan every job without opening a visible browser. Never fills sensitive fields, never submits either way -- just faster for checking field-match coverage.")
    parser.add_argument("--keep-open-minutes", type=float, default=20.0,
                         help="In headed mode, how long to leave every filled tab open for you to review/submit before the browser closes (default 20 min).")
    args = parser.parse_args()

    batch = load_json(BATCH_PATH, "selected_batch.json")
    profile = load_json(PROFILE_PATH, "autofill_profile.json")

    if not batch:
        raise SystemExit("selected_batch.json is empty -- select some jobs in resumes/index.html first.")

    print(f"Loaded {len(batch)} job(s) from {BATCH_PATH.name}.")
    if len(batch) > 15:
        print(f"Note: that's more than the usual 10-15 batch size ({len(batch)} jobs) -- this will take a while.")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        contexts = []
        try:
            for job in batch:
                context = browser.new_context()
                page = context.new_page()
                results.append(process_job(page, job, profile, headless=args.headless))
                if args.headless:
                    context.close()
                else:
                    contexts.append(context)  # left open so every tab is visible for review at once

            if not args.headless and contexts:
                print(f"\n{'='*70}\n{len(contexts)} browser tab(s) are open and filled -- review, finish, and "
                      f"submit each one yourself (nothing here ever clicks Submit for you).")
                print(f"Closing automatically in {args.keep_open_minutes:.0f} minutes, or just close the windows yourself when done.")
                page.wait_for_timeout(int(args.keep_open_minutes * 60 * 1000))
        finally:
            for context in contexts:
                try:
                    context.close()
                except Exception:
                    pass
            browser.close()

    LOG_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    filled_ct = sum(1 for r in results if r["status"] == "filled")
    review_ct = sum(1 for r in results if r["status"] == "needs_review")
    error_ct = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'='*70}\nDone. {filled_ct} clean, {review_ct} need review, {error_ct} errored.")
    print(f"Full log: {LOG_PATH}")


if __name__ == "__main__":
    main()
