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
(name, email, phone, address, resume/cover-letter upload). Sensitive/legal
questions (work authorization, sponsorship, EEO/demographic info, salary
expectations, clearance, background check, etc) are answered automatically
ONLY if you've pre-approved a standard answer for that specific question in
autofill_profile.json's standard_answers block (see resolve_standard_answer())
-- this covers the stable, job-invariant ones (work auth, EEO, relocation,
notice period). Anything without a matching pre-approved answer -- including
salary/compensation, which varies per role and is deliberately never
pre-answerable -- is always left for you. It NEVER clicks Submit by default
(see --auto-submit-clean). After filling a job it pauses so you can
review/finish/submit it yourself, then press Enter to move to the next one.
A summary of what was filled vs. what needs your attention is written to
batch_run_log.json.

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

# Auto-submit (--auto-submit-clean) is only attempted on ATS platforms known to
# render as a single-page form. Multi-step/SPA platforms (workday, icims, taleo,
# successfactors) are excluded even if a given posting happens to fill cleanly --
# not enough runs against them to trust a blind Submit click.
AUTO_SUBMIT_ALLOWED_ATS = {"greenhouse", "ashby", "lever", "smartrecruiters"}

SUBMIT_BUTTON_PATTERN = re.compile(r"^\s*submit(\s+application)?\s*$", re.IGNORECASE)
NEXT_STEP_BUTTON_PATTERN = re.compile(r"^\s*(next|continue|save\s+and\s+continue|next\s+step)\s*$", re.IGNORECASE)
SUCCESS_TEXT_PATTERNS = [
    "application submitted", "thank you for applying", "thanks for applying",
    "successfully applied", "application received", "application complete",
    "we've received your application", "we have received your application",
    "your application has been submitted",
]


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


def resolve_standard_answer(label: str, standard: Dict[str, Any]) -> Optional[str]:
    """Maps a sensitive field's label to a pre-approved standard answer from
    autofill_profile.json's standard_answers block, for the subset of
    sensitive questions that are genuinely stable across every posting (work
    auth, EEO, etc -- NOT salary, which varies by role). Assumes the common/
    typical phrasing of each question (e.g. "are you authorized to work"
    asked in the affirmative) -- an unusually-phrased question could still
    resolve to a wrong answer here. Every fill from this path is tagged
    [standard-answer] in the log specifically so it's easy to audit."""
    low = label.lower()

    def yes_no(value: Optional[bool]) -> Optional[str]:
        return None if value is None else ("Yes" if value else "No")

    if any(k in low for k in ("sponsorship", "sponsor")):
        return yes_no(standard.get("requires_sponsorship"))
    if any(k in low for k in ("authorized to work", "authorization to work", "work authorization", "legally eligible")):
        return yes_no(standard.get("work_authorized"))
    if any(k in low for k in ("relocate", "relocation")):
        return yes_no(standard.get("willing_to_relocate"))
    if "notice period" in low:
        return standard.get("notice_period")
    if "background check" in low:
        return yes_no(standard.get("background_check_consent"))
    if any(k in low for k in ("criminal", "felony", "conviction")):
        return yes_no(standard.get("criminal_history"))
    if any(k in low for k in ("race", "ethnicity")):
        return standard.get("eeo_race")
    if any(k in low for k in ("gender", "pronoun")):
        return standard.get("eeo_gender")
    if "veteran" in low:
        return standard.get("eeo_veteran")
    if "disability" in low:
        return standard.get("eeo_disability")
    return None


def apply_group_answer(frame: Frame, group_key: str, desired: str, question_label: str,
                        filled: List[str]) -> bool:
    """For a radio/checkbox group with a resolved standard answer: find the
    specific option among the group whose own label text matches the desired
    answer, and check it. Returns False (does nothing) if no option confidently
    matches -- falls back to manual review rather than clicking a guess."""
    try:
        options = frame.query_selector_all(f'input[name="{group_key}"]')
    except Exception:
        return False
    desired_low = desired.strip().lower()
    for opt in options:
        try:
            if not opt.is_visible():
                continue
            opt_label = label_for_element(frame, opt).strip().lower()
            if opt_label and (opt_label == desired_low or desired_low in opt_label or opt_label in desired_low):
                try:
                    opt.check(timeout=3000)
                except Exception:
                    opt.click(timeout=3000)
                filled.append(f"[standard-answer group] {question_label[:70]} <- \"{desired}\"")
                return True
        except Exception:
            continue
    return False


def apply_select_answer(el, desired: str, question_label: str, filled: List[str]) -> bool:
    """For a <select> with a resolved standard answer: try an exact option-label
    match first, then a loose substring match against the actual option text."""
    try:
        el.select_option(label=desired)
        filled.append(f"[standard-answer select] {question_label[:70]} <- \"{desired}\"")
        return True
    except Exception:
        pass
    try:
        option_texts = el.evaluate("el => Array.from(el.options).map(o => o.label || o.text)")
    except Exception:
        option_texts = []
    desired_low = desired.strip().lower()
    for opt_text in option_texts:
        if opt_text and (desired_low in opt_text.lower() or opt_text.lower() in desired_low):
            try:
                el.select_option(label=opt_text)
                filled.append(f"[standard-answer select] {question_label[:70]} <- \"{opt_text}\"")
                return True
            except Exception:
                continue
    return False


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
                desired = resolve_standard_answer(label, profile.get("standard_answers", {}))
                applied = False
                if desired:
                    if is_group:
                        if group_key:
                            applied = apply_group_answer(frame, group_key, desired, label, filled)
                    elif tag == "select":
                        applied = apply_select_answer(el, desired, label, filled)
                    elif input_type in ("text", "textarea") or tag == "textarea":
                        try:
                            el.fill(str(desired))
                            filled.append(f"[standard-answer] {label[:70]} <- \"{desired}\"")
                            applied = True
                        except Exception:
                            applied = False
                if applied:
                    continue
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


APPLY_BUTTON_PATTERN = re.compile(
    r"^\s*apply(\s+for\s+this\s+(job|position|role))?(\s+now)?\s*[»›→>»❯▸]*\s*$", re.IGNORECASE
)
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


def click_apply_button(page: Page) -> Page:
    """Many ATS pages (Ashby, Greenhouse, etc) show the job description first
    and only reveal the actual application form after an 'Apply' click. Best
    effort only -- if nothing matches, we just scan whatever's already on the
    page, which is correct for ATS platforms that show the form immediately.

    Some custom career sites (e.g. iCIMS-style portals) open the application
    in a new tab instead of navigating in place -- in that case the new tab
    is what actually has the form, so we return it instead of the original
    page. Returns the page to keep scanning (same page if nothing changed)."""
    for frame in page.frames:
        try:
            candidates = frame.get_by_role("button", name=APPLY_BUTTON_PATTERN).all() + \
                         frame.get_by_role("link", name=APPLY_BUTTON_PATTERN).all()
            for el in candidates:
                if el.is_visible():
                    try:
                        with page.context.expect_page(timeout=3000) as new_page_info:
                            el.click(timeout=5000)
                        new_page = new_page_info.value
                        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        return new_page
                    except Exception:
                        # No new tab opened -- the click navigated in place (the common case).
                        page.wait_for_timeout(1500)
                        return page
        except Exception:
            continue
    return page


def attempt_auto_submit(page: Page, ats: str) -> Dict[str, Any]:
    """Only called when a job filled 100% clean (no needs_review/unmatched
    fields) and the ATS is in AUTO_SUBMIT_ALLOWED_ATS. Still backs out instead
    of guessing if anything looks like a multi-step form or if success can't
    be confirmed afterward -- a silent bad submit is worse than one left for
    manual review."""
    # If a Next/Continue button is visible anywhere, this is a multi-step form
    # the initial scan didn't fully see (fields on later steps could still be
    # unfilled/sensitive) -- bail out rather than submitting an incomplete app.
    for frame in page.frames:
        try:
            for el in frame.get_by_role("button", name=NEXT_STEP_BUTTON_PATTERN).all():
                if el.is_visible():
                    return {"submitted": False, "detail": "multi-step form detected (Next/Continue button present) -- not attempted"}
        except Exception:
            continue

    submit_el = None
    for frame in page.frames:
        try:
            for el in frame.get_by_role("button", name=SUBMIT_BUTTON_PATTERN).all():
                if el.is_visible():
                    submit_el = el
                    break
            if submit_el:
                break
        except Exception:
            continue

    if submit_el is None:
        return {"submitted": False, "detail": "no Submit button found -- not attempted"}

    try:
        submit_el.click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        return {"submitted": False, "detail": f"click failed: {e}"}

    try:
        body_text = page.inner_text("body").lower()
    except Exception:
        body_text = ""
    url_low = page.url.lower()

    confirmed = any(p in body_text for p in SUCCESS_TEXT_PATTERNS) or \
        any(p in url_low for p in ("thank", "confirmation", "success", "submitted"))

    if confirmed:
        return {"submitted": True, "detail": f"confirmed via page content/URL after clicking Submit ({page.url})"}
    return {"submitted": False, "detail": "clicked Submit but could not confirm success on the resulting page -- verify manually"}


def process_job(page: Page, job: Dict[str, Any], profile: Dict[str, Any],
                 headless: bool, auto_submit_clean: bool = False) -> "tuple[Dict[str, Any], Page]":
    """Fills one job's application into `page` (navigating it in place). Returns
    (result, active_page) -- active_page is normally the same `page` passed in, but
    if the site's Apply button opens a new tab, active_page is that new tab instead
    (the original tab is closed so we don't accumulate orphaned tabs -- caller should
    keep using the returned page for the next job)."""
    result: Dict[str, Any] = {
        "job_id": job.get("job_id"), "company": job.get("company"), "title": job.get("title"),
        "url": job.get("url"), "timestamp": now(),
    }

    if not job.get("url"):
        result.update(status="error", error="No posting URL for this job", ats="unknown")
        return result, page

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
        return result, page

    try:
        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        try:
            # Heavy JS-SPA ATS platforms (Paycom, custom portals like TCS iBegin,
            # some Workday tenants) are still rendering right after DOMContentLoaded --
            # wait for network activity to settle before trusting the page is ready.
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass  # some ATS pages never go fully idle (polling/analytics) -- fall through
        page.wait_for_timeout(2000)  # let JS-heavy ATS pages (Workday/Greenhouse) render the form
    except Exception as e:
        result.update(status="error", error=f"Failed to load page: {e}")
        return result, page

    dismiss_cookie_banner(page)
    page_before = page
    page = click_apply_button(page)
    if page is not page_before:
        # Apply opened in a new tab -- that's now the page with the real form.
        # Close the old tab so we stay at one visible tab instead of accumulating them.
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        dismiss_cookie_banner(page)
        try:
            page_before.close()
        except Exception:
            pass

    filled: List[str] = []
    needs_review: List[str] = []
    unmatched: List[str] = []
    seen_radio_groups: set = set()

    for frame in page.frames:
        fill_frame(frame, profile, job, filled, needs_review, unmatched, seen_radio_groups)

    # If nothing was found at all, the page may still have been mid-render (SPA
    # hydration finishing late) -- give it one more chance before giving up.
    # Lists were empty going in, so a clean re-scan is safe (nothing to dedupe).
    if not filled and not needs_review and not unmatched:
        page.wait_for_timeout(3000)
        seen_radio_groups = set()
        for frame in page.frames:
            fill_frame(frame, profile, job, filled, needs_review, unmatched, seen_radio_groups)

    if ats in LOW_CONFIDENCE_ATS:
        needs_review.insert(0, f"[low confidence] {ats} uses a multi-step application flow -- verify every field by hand")

    is_clean = not needs_review and not unmatched
    status = "filled" if is_clean else "needs_review"

    submit_detail = None
    if auto_submit_clean and is_clean and ats in AUTO_SUBMIT_ALLOWED_ATS:
        outcome = attempt_auto_submit(page, ats)
        submit_detail = outcome["detail"]
        status = "submitted" if outcome["submitted"] else "filled"
        if not outcome["submitted"]:
            needs_review.append(f"[auto-submit not completed] {outcome['detail']}")

    SCREENSHOT_DIR.mkdir(exist_ok=True)
    shot_path = SCREENSHOT_DIR / f"{job.get('company', 'job')}__{job.get('job_id', '')}.png".replace("/", "_").replace(" ", "_")
    try:
        page.screenshot(path=str(shot_path), full_page=True)
        result["screenshot"] = str(shot_path.relative_to(BASE_DIR))
    except Exception:
        pass

    result.update(
        status=status,
        filled_fields=filled, needs_review_fields=needs_review, unmatched_fields=unmatched,
        auto_submit_detail=submit_detail,
    )

    print(f"\n{'='*70}\n{job.get('company')} -- {job.get('title')}  [{ats}]")
    print(f"  Filled: {len(filled)}   Needs review: {len(needs_review)}   Unmatched: {len(unmatched)}   Status: {status}")
    for f in needs_review:
        print(f"  ! {f}")
    if submit_detail:
        print(f"  Auto-submit: {submit_detail}")
    print(f"  Screenshot: {result.get('screenshot', 'n/a')}")

    return result, page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--headless", action="store_true",
                         help="Scan every job without opening a visible browser. Never fills sensitive fields, never submits either way -- just faster for checking field-match coverage.")
    parser.add_argument("--auto-submit-clean", action="store_true",
                         help="Click Submit automatically, but ONLY for jobs that filled 100%% clean "
                              "(zero flagged/unmatched fields) on a single-page ATS (greenhouse/ashby/"
                              "lever/smartrecruiters). Anything with even one flagged field, any "
                              "workday/icims/taleo/successfactors posting, or any form where a Next/"
                              "Continue button is still visible is left for manual review as usual -- "
                              "this never guesses on sensitive or ambiguous fields.")
    args = parser.parse_args()

    batch = load_json(BATCH_PATH, "selected_batch.json")
    profile = load_json(PROFILE_PATH, "autofill_profile.json")

    if not batch:
        raise SystemExit("selected_batch.json is empty -- select some jobs in resumes/index.html first.")

    print(f"Loaded {len(batch)} job(s) from {BATCH_PATH.name}.")
    if len(batch) > 15:
        print(f"Note: that's more than the usual 10-15 batch size ({len(batch)} jobs) -- this will take a while.")
    if args.auto_submit_clean:
        print(f"\n{'!'*70}\nAUTO-SUBMIT ENABLED: 100%-clean applications on {sorted(AUTO_SUBMIT_ALLOWED_ATS)} "
              f"will be submitted without pausing for review.\n{'!'*70}\n")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            for i, job in enumerate(batch):
                result, page = process_job(page, job, profile, headless=args.headless,
                                            auto_submit_clean=args.auto_submit_clean)
                results.append(result)

                is_last = i == len(batch) - 1
                if not args.headless and not is_last:
                    if result.get("status") == "submitted":
                        print("  Submitted -- moving to the next job automatically.")
                    else:
                        input(f"  Review/submit this tab now if you want, then press Enter to continue "
                              f"to job {i + 2}/{len(batch)}...")

            # Write the log and print the summary now, before waiting on the user --
            # so both are available immediately even if the browser is left open for
            # a long time (hours) before anyone comes back to it.
            LOG_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

            submitted_ct = sum(1 for r in results if r["status"] == "submitted")
            filled_ct = sum(1 for r in results if r["status"] == "filled")
            review_ct = sum(1 for r in results if r["status"] == "needs_review")
            error_ct = sum(1 for r in results if r["status"] == "error")
            print(f"\n{'='*70}\nDone. {submitted_ct} auto-submitted, {filled_ct} clean (review/submit yourself), "
                  f"{review_ct} need review, {error_ct} errored.")
            print(f"Full log: {LOG_PATH}")

            if not args.headless:
                print(f"\n{'='*70}\nAll {len(batch)} job(s) processed in this one browser window.")
                print("The browser stays open -- come back anytime to check each tab (submitted vs. "
                      "still needs your review/submit).")
                print("Press Enter in this terminal to close it now, or just leave this running and "
                      "close the window yourself whenever you're done.")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
