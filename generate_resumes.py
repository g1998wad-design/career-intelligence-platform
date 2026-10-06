#!/usr/bin/env python3
"""Render a one-page, per-job tailored PDF resume from job_analysis +
master_resume.json. Run this on its own after job_fetcher.py has
populated job_analysis (i.e. after an n8n run completes):

    python generate_resumes.py                  # all analyzed jobs
    python generate_resumes.py --min-score 85    # only your outreach tier
    python generate_resumes.py --job-id abc123   # a single job
    python generate_resumes.py --max-bullets 20  # raise the pre-shrink bullet cap

Every resume is guaranteed to fit on one page: build_pdf() renders, checks
the actual page count via pypdf, and if it's more than one page, shrinks
font/spacing/margins together and re-renders -- down to MIN_SCALE, a floor
below which text would be unreadably small (only hit for extreme content
volume; you'll get a console warning if that ever happens).

Requires: pip install reportlab pypdf --break-system-packages

Output: resumes/<company>__<title>__<job_id>.pdf, one per job. Existing
PDFs are overwritten on re-run so this is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, HRFlowable
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "job_fetcher.db"
MASTER_RESUME_PATH = BASE_DIR / "master_resume.json"
OUTPUT_DIR = BASE_DIR / "resumes"

def initial_scale_for(bullet_count: int) -> float:
    """A reasonable starting guess for font/spacing scale given bullet count --
    just the starting point for build_pdf's auto-shrink-to-one-page loop, not
    a guarantee on its own. Tiered (not continuous) so the handful of starting
    looks this produces can be visually verified rather than trusting an
    unbounded range."""
    if bullet_count <= 6:
        return 1.32
    elif bullet_count <= 8:
        return 1.18
    elif bullet_count <= 9:
        return 1.09
    elif bullet_count <= 11:
        return 1.0
    elif bullet_count <= 13:
        return 0.94
    elif bullet_count <= 16:
        return 0.86
    else:
        return 0.78


# Never shrink below this -- past this point a resume is unreadable, and it's
# better to accept a 2nd page (via the "still N pages" warning) than to
# silently ship sub-8pt text. Empirically, a 13-bullet one-pager needs ~0.78
# to actually fit given the current base font sizes -- still meaningfully
# bigger than the old 0.62 floor (~8pt vs ~5.8pt bullet text).
MIN_SCALE = 0.78


def build_styles(scale: float) -> Dict[str, ParagraphStyle]:
    s = scale
    return {
        "NAME_STYLE": ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=18 * s, leading=21 * s, spaceAfter=2 * s),
        "CONTACT_STYLE": ParagraphStyle("Contact", fontName="Helvetica", fontSize=9.5 * s, textColor="#444444", spaceAfter=8 * s),
        "SUMMARY_STYLE": ParagraphStyle("Summary", fontName="Helvetica-Oblique", fontSize=10.3 * s, leading=13.8 * s,
                                         spaceAfter=8 * s, alignment=TA_JUSTIFY),
        "SECTION_STYLE": ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=11.3 * s, spaceBefore=8 * s,
                                         spaceAfter=3 * s, textColor="#1a3c6e"),
        "JOB_HEADER_STYLE": ParagraphStyle("JobHeader", fontName="Helvetica-Bold", fontSize=10.3 * s, spaceBefore=5 * s, spaceAfter=1 * s),
        "JOB_SUB_STYLE": ParagraphStyle("JobSub", fontName="Helvetica-Oblique", fontSize=9.3 * s, textColor="#555555", spaceAfter=2 * s),
        "CONTEXT_STYLE": ParagraphStyle("Context", fontName="Helvetica-BoldOblique", fontSize=9.3 * s, textColor="#1a3c6e", spaceAfter=3 * s),
        "BULLET_STYLE": ParagraphStyle("Bullet", fontName="Helvetica", fontSize=10.3 * s, leading=13.4 * s, alignment=TA_JUSTIFY),
        "SKILLS_STYLE": ParagraphStyle("Skills", fontName="Helvetica", fontSize=10 * s, leading=13.5 * s),
        "EDU_HONORS_STYLE": ParagraphStyle("EduHonors", fontName="Helvetica-Oblique", fontSize=9.3 * s, leading=12 * s,
                                            textColor="#555555", spaceAfter=4 * s),
    }


_ABBREVIATIONS = ("incl", "etc", "approx", "vs", "e.g", "i.e",
                  "Inc", "Corp", "Jr", "Sr", "Dr", "Mr", "Mrs", "Ms")
_ABBREV_END_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(a) for a in _ABBREVIATIONS) + r')\.$'
)


def _split_first_sentence(summary: str) -> str:
    """Split off the first sentence on [.!?] boundaries, but don't stop at a
    period that belongs to an abbreviation like "incl." or "e.g." -- a plain
    sentence-boundary regex treats that period as a sentence end and chops
    the summary mid-clause (e.g. leaving a dangling open parenthesis)."""
    parts = re.split(r'(?<=[.!?])\s+', summary)
    first = parts[0]
    i = 1
    while i < len(parts) and _ABBREV_END_RE.search(first):
        first = first + " " + parts[i]
        i += 1
    return first


_DANGLING_TRAILING_WORDS = (
    "and", "or", "with", "using", "via", "for", "of", "by", "from",
    "to", "that", "which", "in", "on", "including",
    "into", "onto", "within", "across", "through", "toward", "about",
    "over", "under", "between", "as",
)
_DANGLING_TRAILING_RE = re.compile(
    r"(?:^|\s)(?:" + "|".join(_DANGLING_TRAILING_WORDS) + r")$", re.I
)


def _shorten_summary(summary: str, max_chars: int = 180) -> str:
    """Last-resort space reclaim when a resume is still 2 pages even at
    MIN_SCALE -- keep just the first sentence of the summary (usually the
    strongest one anyway) rather than continuing to shrink already-small text.
    If even that's too long, drop whole trailing comma-separated clauses
    (never a raw character slice) so the result always ends on a complete
    clause, never mid-word or on a dangling connector like "with" or an
    unclosed "(Python, LangChain, vector search.\""""
    summary = summary.strip()
    first_sentence = _split_first_sentence(summary)
    if len(first_sentence) <= max_chars:
        return first_sentence
    text = first_sentence.rstrip(".!? ")
    segments = [s.strip() for s in text.split(",")]
    while len(segments) > 1 and len(", ".join(segments)) > max_chars:
        segments.pop()
    kept = ", ".join(segments)
    if len(kept) > max_chars:
        # Even a single clause is too long on its own -- fall back to a
        # word-boundary cut, then keep peeling off trailing connector words
        # so it never ends on a dangling "with"/"for"/etc.
        kept = kept[:max_chars].rsplit(" ", 1)[0]
    while _DANGLING_TRAILING_RE.search(kept):
        kept = _DANGLING_TRAILING_RE.sub("", kept)
    # A clause can still end inside an open parenthetical, e.g. "...harnesses
    # (Python, LangChain, vector search" -- the "(" never gets its ")". If the
    # result left the parens unbalanced, drop back to before the unmatched "(".
    if kept.count("(") != kept.count(")"):
        kept = kept.rsplit("(", 1)[0]
    return kept.rstrip(",.; ") + "."


# Cover letters are always ~280-350 words by prompt design, so they don't need
# dynamic sizing -- these stay fixed for that one use.
LETTER_BODY_STYLE = ParagraphStyle("LetterBody", fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=10)
LETTER_META_STYLE = ParagraphStyle("LetterMeta", fontName="Helvetica", fontSize=9.5, textColor="#444444", spaceAfter=16)


def slug(v: str, length: int = 40) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", v).strip("_")[:length] or "untitled"


def load_master_resume() -> Dict[str, Any]:
    if not MASTER_RESUME_PATH.exists():
        raise SystemExit(f"master_resume.json not found at {MASTER_RESUME_PATH}")
    return json.loads(MASTER_RESUME_PATH.read_text(encoding="utf-8"))


def fetch_jobs(min_score: Optional[int], job_id: Optional[str], show_applied: bool = False,
               since: Optional[str] = None) -> List[sqlite3.Row]:
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found — run job_fetcher.py at least once first.")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    query = """
        SELECT j.job_id, j.title, j.company, j.url, j.apply_url, j.applicant_count, j.first_seen_at,
               a.tailored_summary, a.tailored_skills,
               a.tailored_resume_bullets, a.match_score, a.cover_letter, a.processed_at, a.lead_with_projects
        FROM job_analysis a
        JOIN jobs j ON j.job_id = a.job_id
        WHERE a.tailored_resume_bullets IS NOT NULL AND a.tailored_resume_bullets != ''
    """
    params: List[Any] = []
    if not show_applied:
        # Jobs already marked applied (mark_applied.py) are archived out of the
        # default view so you never have to re-look at ones you're done with.
        query += " AND (j.applied IS NULL OR j.applied = 0)"
    if min_score is not None:
        query += " AND a.match_score >= ?"
        params.append(min_score)
    if job_id:
        query += " AND j.job_id = ?"
        params.append(job_id)
    if since:
        # processed_at is when n8n tailored this job's resume -- filtering on
        # it (not scrape time) means "since" tracks when the analysis actually
        # ran, e.g. --since 2026-09-13 for "only today's tailored jobs".
        query += " AND a.processed_at >= ?"
        params.append(since)
    rows = con.execute(query, params).fetchall()
    con.close()
    return rows


def safe_json(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# Per-company minimums -- low enough that a strict one-page resume is
# achievable, just enough to guarantee each employer shows real evidence
# rather than being cut entirely. Keyed by exact master_resume.json company name.
MINIMUM_BULLETS_BY_COMPANY = {
    "Allegis Group": 5,
    "KPMG": 3,
    "Career Intelligence Platform (personal project, in progress)": 3,
    "Thrivent Federal Credit Union": 1,
}


def ensure_minimum_bullets(
    bullets_by_company: Dict[str, List[str]], master: Dict[str, Any]
) -> Dict[str, List[str]]:
    """Gemini's per-job tailoring picks bullets for relevance, but with only
    10-14 bullets total across 4 employers it often undershoots what you want
    guaranteed for each one. Top up any company below its minimum using its
    remaining (un-selected) master-resume bullets, in master order -- real,
    verified content, just not reworded/re-prioritized for this specific job
    the way Gemini's picks are."""
    for entry in master.get("experience", []):
        company = entry["company"]
        minimum = MINIMUM_BULLETS_BY_COMPANY.get(company, 1)
        current = bullets_by_company.setdefault(company, [])
        if len(current) >= minimum:
            continue
        selected_texts = set(current)
        for b in entry.get("bullets", []):
            if len(current) >= minimum:
                break
            if b["text"] not in selected_texts:
                current.append(b["text"])
                selected_texts.add(b["text"])
    return bullets_by_company


def trim_to_fit_one_page(bullets_by_company: Dict[str, List[str]], max_total: int = 13) -> Dict[str, List[str]]:
    """Gemini is instructed to target ~10-14 bullets total for a one-page fit, but
    prompts aren't guarantees. As a backstop, if the total still exceeds max_total,
    trim the LAST (lowest-priority, since Gemini already orders each employer's list
    most-relevant-first) bullet from whichever employer currently has the most --
    but never below each employer's floor (MINIMUM_BULLETS_BY_COMPANY).
    Dropping an employer below its floor would erase real, credibility-building
    content or the job entirely -- worse than running slightly over the target
    length. If everyone's already at their floor, stop trimming even if still over
    max_total."""
    floor_for = lambda company: MINIMUM_BULLETS_BY_COMPANY.get(company, 1)
    total = sum(len(v) for v in bullets_by_company.values())
    while total > max_total:
        candidates = [c for c, v in bullets_by_company.items() if len(v) > floor_for(c)]
        if not candidates:
            break  # everyone's at their floor -- can't trim further without erasing real content
        company = max(candidates, key=lambda c: len(bullets_by_company[c]))
        bullets_by_company[company].pop()
        total -= 1
    return bullets_by_company


def _render_story(master: Dict[str, Any], contact: Dict[str, Any], summary: str,
                   tailored_skills: List[str], bullets_by_company: Dict[str, List[str]],
                   styles: Dict[str, ParagraphStyle], projects_first: bool = False) -> List[Any]:
    NAME_STYLE = styles["NAME_STYLE"]
    CONTACT_STYLE = styles["CONTACT_STYLE"]
    SUMMARY_STYLE = styles["SUMMARY_STYLE"]
    SECTION_STYLE = styles["SECTION_STYLE"]
    JOB_HEADER_STYLE = styles["JOB_HEADER_STYLE"]
    JOB_SUB_STYLE = styles["JOB_SUB_STYLE"]
    CONTEXT_STYLE = styles["CONTEXT_STYLE"]
    BULLET_STYLE = styles["BULLET_STYLE"]
    SKILLS_STYLE = styles["SKILLS_STYLE"]
    EDU_HONORS_STYLE = styles["EDU_HONORS_STYLE"]

    story: List[Any] = []
    story.append(Paragraph(contact.get("name", ""), NAME_STYLE))
    contact_bits = [v for v in [
        contact.get("location"), contact.get("phone"), contact.get("email"),
        contact.get("linkedin"), contact.get("github")
    ] if v]
    if contact_bits:
        story.append(Paragraph(" | ".join(contact_bits), CONTACT_STYLE))
    story.append(HRFlowable(width="100%", thickness=1, color="#1a3c6e", spaceAfter=8))

    if summary:
        story.append(Paragraph(summary, SUMMARY_STYLE))

    if tailored_skills:
        story.append(Paragraph("SKILLS", SECTION_STYLE))
        story.append(Paragraph(", ".join(tailored_skills), SKILLS_STYLE))

    experience_block: List[Any] = [Paragraph("EXPERIENCE", SECTION_STYLE)]
    # Preserve master-resume ordering (reverse-chronological as authored),
    # skipping any employer Gemini didn't select bullets for, and skipping
    # anything tagged as a project -- those get their own section below.
    for entry in master.get("experience", []):
        if entry.get("type") == "project":
            continue
        company = entry["company"]
        bullets = bullets_by_company.get(company)
        if not bullets:
            continue
        header = f"{entry.get('title', '')} — {company}"
        experience_block.append(Paragraph(header, JOB_HEADER_STYLE))
        sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
        if sub_bits:
            experience_block.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
        # Always shown, independent of Gemini's per-job bullet picks -- a real
        # standout credential (e.g. Allegis's Employee of the Year / Rising
        # Star) shouldn't be left to chance on whether the LLM chose to surface it.
        if entry.get("context"):
            experience_block.append(Paragraph(entry["context"], CONTEXT_STYLE))
        items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
        experience_block.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

    project_entries = [e for e in master.get("experience", []) if e.get("type") == "project" and bullets_by_company.get(e["company"])]
    project_block: List[Any] = []
    if project_entries:
        project_block.append(Paragraph("PROJECTS", SECTION_STYLE))
        for entry in project_entries:
            company = entry["company"]
            bullets = bullets_by_company.get(company)
            header = f"{entry.get('title', '')} — {company}" if entry.get("title") else company
            project_block.append(Paragraph(header, JOB_HEADER_STYLE))
            sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
            if sub_bits:
                project_block.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
            items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
            project_block.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

    # projects_first is opt-in (default False) so the normal per-job pipeline's
    # section order never changes -- only callers like the generic AI/agentic
    # resume variant, where the personal project is the strongest evidence,
    # set it explicitly.
    if projects_first:
        story.extend(project_block)
        story.extend(experience_block)
    else:
        story.extend(experience_block)
        story.extend(project_block)

    if master.get("education"):
        story.append(Paragraph("EDUCATION", SECTION_STYLE))
        for ed in master["education"]:
            line = f"{ed.get('degree', '')} — {ed.get('school', '')}"
            story.append(Paragraph(line, JOB_HEADER_STYLE))
            sub_bits = [b for b in [ed.get("dates"), ed.get("location")] if b]
            if sub_bits:
                story.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
            if ed.get("honors"):
                honors_bits = []
                for h in ed["honors"].split(";"):
                    h = h.strip()
                    if not h:
                        continue
                    h = h[0].upper() + h[1:]
                    if h.endswith((".", "!", "?")):
                        h = h[:-1]
                    honors_bits.append(h)
                if honors_bits:
                    story.append(Paragraph(" • ".join(honors_bits), EDU_HONORS_STYLE))
            if ed.get("coursework"):
                story.append(Paragraph(f"Relevant Coursework: {ed['coursework']}", EDU_HONORS_STYLE))
    return story


# Role families where the personal AI project is stronger, more direct evidence
# than the day job (Treasury/Finance BA work) -- for these, lead with Projects
# instead of Experience. A simple title-keyword match since job_analysis doesn't
# carry whichever role-family tag Gemini used internally for tailoring.
PROJECTS_FIRST_TITLE_KEYWORDS = [
    "forward deployed", "gtm engineer", "applied ai", "ai solutions",
    "ai engineer", "customer engineer", "ai automation",
]


def _should_lead_with_projects(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in PROJECTS_FIRST_TITLE_KEYWORDS)


def build_pdf(row: sqlite3.Row, master: Dict[str, Any], out_path: Path, max_bullets: int) -> None:
    contact = master.get("contact", {})
    tailored_bullets = safe_json(row["tailored_resume_bullets"], [])
    # Backstop cap: the tailoring prompt is supposed to pick a relevant subset,
    # but a prompt is a request, not a guarantee -- without this, a job where
    # the model reordered instead of selecting can dump the entire ~70-keyword
    # skills_keyword_bank into one wall of text spanning 5-6 lines.
    tailored_skills = safe_json(row["tailored_skills"], [])[:15]
    # Always enforced, not just as a page-overflow fallback -- the tailoring prompt targets a
    # crisp 2-line summary but doesn't always hit it exactly, so this is the reliable guarantee.
    summary = _shorten_summary(row["tailored_summary"] or master.get("summary_variants", {}).get("default", ""))
    # Model-judged per-job (lead_with_projects, set by the tailoring prompt) takes priority;
    # the title-keyword heuristic is just a fallback for rows tailored before that field existed.
    projects_first = bool(row["lead_with_projects"]) or _should_lead_with_projects(row["title"])

    # Map company -> full metadata (title/dates/location) from the master resume,
    # since Gemini's output only carries company + bullets.
    meta_by_company = {e["company"]: e for e in master.get("experience", [])}
    bullets_by_company = {b.get("company"): list(b.get("bullets", [])) for b in tailored_bullets if isinstance(b, dict)}
    # Belt and suspenders: the prompt asks Gemini to hit certain per-employer
    # counts, but a prompt is a request, not a guarantee. Top every employer up
    # to MINIMUM_BULLETS_BY_COMPANY using real (un-reworded) master-resume
    # bullets so the resume never reads thin. Page fit is then guaranteed below
    # by shrinking font/spacing, not by cutting this content back down.
    bullets_by_company = ensure_minimum_bullets(bullets_by_company, master)
    bullets_by_company = trim_to_fit_one_page(bullets_by_company, max_bullets)

    total_bullets = sum(len(v) for v in bullets_by_company.values())

    from pypdf import PdfReader  # required now -- page-fit loop depends on it

    # Every job MUST fit on one page. Start from a reasonable guess for this
    # bullet count, then keep shrinking font/spacing/margins together until
    # pypdf confirms it actually fits, down to MIN_SCALE as a readability floor.
    scale = max(initial_scale_for(total_bullets), MIN_SCALE)
    n_pages = None
    while True:
        styles = build_styles(scale)
        story = _render_story(master, contact, summary, tailored_skills, bullets_by_company, styles, projects_first=projects_first)
        margin_scale = max(scale, 0.85)  # margins shrink less aggressively than text
        doc = SimpleDocTemplate(
            str(out_path), pagesize=LETTER,
            leftMargin=0.6 * inch * margin_scale, rightMargin=0.6 * inch * margin_scale,
            topMargin=0.42 * inch * margin_scale, bottomMargin=0.42 * inch * margin_scale,
        )
        doc.build(story)
        n_pages = len(PdfReader(str(out_path)).pages)
        if n_pages <= 1 or scale <= MIN_SCALE:
            break
        scale = max(MIN_SCALE, scale - 0.06)

    if n_pages > 1 and summary:
        short_summary = _shorten_summary(summary)
        if short_summary != summary:
            story = _render_story(master, contact, short_summary, tailored_skills, bullets_by_company, styles, projects_first=projects_first)
            doc = SimpleDocTemplate(
                str(out_path), pagesize=LETTER,
                leftMargin=0.6 * inch * margin_scale, rightMargin=0.6 * inch * margin_scale,
                topMargin=0.42 * inch * margin_scale, bottomMargin=0.42 * inch * margin_scale,
            )
            doc.build(story)
            n_pages = len(PdfReader(str(out_path)).pages)

    if n_pages > 1:
        print(f"    warning: {out_path.name} still {n_pages} pages at floor scale {MIN_SCALE} "
              f"({total_bullets} bullets) -- content genuinely doesn't fit one page even at minimum readable size")


def build_cover_letter_pdf(row: sqlite3.Row, master: Dict[str, Any], out_path: Path) -> None:
    """Format the already-generated cover letter text (cached from the 85+ branch
    of the n8n pipeline) as a clean one-page PDF, using the same contact header
    as the resume. Does nothing if no letter was ever generated for this job."""
    letter_text = (row["cover_letter"] or "").strip()
    if not letter_text:
        return

    contact = master.get("contact", {})
    letter_name_style = ParagraphStyle("LetterName", fontName="Helvetica-Bold", fontSize=18, leading=21, spaceAfter=2)
    letter_contact_style = ParagraphStyle("LetterContact", fontName="Helvetica", fontSize=9.5, textColor="#444444", spaceAfter=8)
    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    )
    story: List[Any] = []

    story.append(Paragraph(contact.get("name", ""), letter_name_style))
    contact_bits = [v for v in [
        contact.get("location"), contact.get("phone"), contact.get("email"), contact.get("linkedin")
    ] if v]
    if contact_bits:
        story.append(Paragraph(" | ".join(contact_bits), letter_contact_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"Re: {row['title']} at {row['company']}", LETTER_META_STYLE))

    # Gemini writes the letter as prose; split on blank lines so multi-paragraph
    # letters render as separate paragraphs instead of one dense block.
    for para in [p.strip() for p in letter_text.split("\n\n") if p.strip()]:
        story.append(Paragraph(para.replace("\n", " "), LETTER_BODY_STYLE))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Sincerely,", LETTER_BODY_STYLE))
    story.append(Paragraph(contact.get("name", ""), LETTER_BODY_STYLE))

    doc.build(story)


# Matches the launchd scrape schedule (com.jsbasics.jobpipeline.plist), local
# time -- used to bucket the index into the same "9am jobs / 11am jobs / ..."
# batches the pipeline actually runs in, rather than one flat score-sorted list.
SCRAPE_SLOT_HOURS = [9, 11, 13, 15, 17, 19]
LOCAL_TZ = ZoneInfo("America/New_York")


def _scrape_slot(first_seen_at: str) -> tuple[str, str]:
    """Bucket a job's first_seen_at (UTC ISO timestamp) into the local scrape
    slot it was discovered in. Returns (sort_key, label) -- sort_key sorts
    newest-slot-first, label is e.g. 'SEP 25 11AM JOBS'. Jobs with no
    timestamp (shouldn't normally happen) fall into a trailing 'UNDATED' bucket."""
    if not first_seen_at:
        return ("0000-00-00 00", "UNDATED JOBS")
    dt = datetime.fromisoformat(first_seen_at).astimezone(LOCAL_TZ)
    hour = dt.hour
    slot = SCRAPE_SLOT_HOURS[0]
    for h in SCRAPE_SLOT_HOURS:
        if hour >= h:
            slot = h
    label_hour = slot if slot <= 12 else slot - 12
    ampm = "AM" if slot < 12 else "PM"
    label = f"{dt.strftime('%b %d').upper()} {label_hour}{ampm} JOBS"
    sort_key = f"{dt.strftime('%Y-%m-%d')} {slot:02d}"
    return (sort_key, label)


def _all_analyzed_slots_today() -> Dict[str, str]:
    """Every scrape slot from TODAY where at least one job has been screened
    (has a job_analysis row), even if none of them cleared the tailoring bar --
    so the index can show e.g. 'SEP 25 11AM JOBS (0)' instead of silently
    omitting a slot that WAS screened and simply had no strong matches.
    Limited to today so the page doesn't accumulate empty-slot clutter for
    old days that no longer matter."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT DISTINCT j.first_seen_at
        FROM jobs j
        JOIN job_analysis a ON a.job_id = j.job_id
        WHERE date(j.first_seen_at, 'localtime') = date('now', 'localtime')
    """).fetchall()
    con.close()
    slots: Dict[str, str] = {}
    for r in rows:
        sort_key, label = _scrape_slot(r["first_seen_at"])
        slots[sort_key] = label
    return slots


def build_index(rows_written: List[Dict[str, Any]]) -> None:
    """A single clickable page, sorted best-match-first, so you never have
    to browse the resumes/ folder guessing which file matches which job.

    Jobs marked applied (see mark_applied.py) are excluded by default, so
    this page only ever shows what you still need to act on.

    Grouped into sections by scrape time-slot (e.g. "SEP 25 9AM JOBS", "SEP 25
    11AM JOBS", ...) matching the launchd scrape schedule, newest slot first,
    best-match-first within each slot -- so you can review a batch right after
    it lands instead of hunting through one long flat list.

    The "Applied" and "Find outreach" checkboxes persist to the browser's
    localStorage (keyed by job_id) since this is a static file regenerated
    daily -- there's no backend to write to. Checking a box doesn't trigger
    anything by itself; tell Claude you've checked some and it reads the
    live page state (via the Chrome MCP) to act on them -- marking jobs
    applied in job_fetcher.db, or doing bounded interactive LinkedIn
    outreach research for the ones flagged."""
    groups: Dict[str, tuple[str, List[Dict[str, Any]]]] = {}
    for r in rows_written:
        sort_key, label = _scrape_slot(r.get("first_seen_at", ""))
        groups.setdefault(sort_key, (label, []))[1].append(r)
    # Today's slots that were screened but produced zero tailor-worthy matches
    # still get a header (with a "(0)" count) rather than vanishing entirely --
    # otherwise a slot with no strong matches looks indistinguishable from a
    # slot that simply hasn't run yet.
    for sort_key, label in _all_analyzed_slots_today().items():
        groups.setdefault(sort_key, (label, []))
    for _, members in groups.values():
        members.sort(key=lambda r: -(r["match_score"] or 0))

    parts = [
        "<html><head><meta charset='utf-8'><title>Tailored Resumes</title>",
        "<style>body{font-family:-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 20px}",
        "table{width:100%;border-collapse:collapse;margin-bottom:28px} th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #ddd}",
        "th{background:#f5f5f5} .score{font-weight:bold} tr:hover{background:#fafafa}",
        "input[type=checkbox]{width:18px;height:18px;cursor:pointer}",
        "h3.slot{margin:28px 0 8px;color:#1a3c6e;border-bottom:2px solid #1a3c6e;padding-bottom:4px}",
        "</style></head><body>",
        f"<h2>Tailored Resumes ({len(rows_written)})</h2>",
        "<p style='color:#666;font-size:14px'>Check boxes to flag jobs, then tell Claude "
        "(e.g. \"process checked boxes\") -- it reads this page's state and marks jobs "
        "applied / researches outreach contacts for the ones flagged.</p>",
    ]
    for sort_key in sorted(groups.keys(), reverse=True):
        label, members = groups[sort_key]
        parts.append(f"<h3 class='slot'>{label} ({len(members)})</h3>")
        if not members:
            parts.append(
                "<p style='color:#888;font-style:italic;margin:4px 0 24px'>"
                "Screened — no matches strong enough to tailor.</p>"
            )
            continue
        parts.append(
            "<table><tr><th>Match</th><th>Company</th><th>Title</th><th>Applicants</th><th>Resume</th>"
            "<th>Cover Letter</th><th>Posting</th><th>Direct Apply</th>"
            "<th>Applied</th><th>Find outreach</th></tr>"
        )
        for r in members:
            cover_letter_cell = (
                f"<a href='{r['cover_letter_filename']}'>Open PDF</a>" if r.get("cover_letter_filename") else "—"
            )
            # apply_url is the actual ATS/company application link when JobSpy found one
            # (mainly Indeed postings); otherwise it falls back to the same listing url
            # (mainly LinkedIn).
            has_direct = bool(r["apply_url"]) and r["apply_url"] != r["url"]
            direct_cell = "<span style='color:#0a7'>Yes</span>" if has_direct else "<span style='color:#999'>No (LinkedIn only)</span>"
            # LinkedIn-only (jobspy has no applicant-count support for other sites).
            applicants = r.get("applicant_count")
            applicants_cell = str(applicants) if applicants is not None else "—"
            jid = r["job_id"]
            parts.append(
                f"<tr data-job-id='{jid}'><td class='score'>{r['match_score']}</td><td>{r['company']}</td>"
                f"<td>{r['title']}</td><td>{applicants_cell}</td><td><a href='{r['filename']}'>Open PDF</a></td>"
                f"<td>{cover_letter_cell}</td>"
                f"<td><a href='{r['url']}' target='_blank'>View posting</a></td>"
                f"<td>{direct_cell}</td>"
                f"<td><input type='checkbox' class='applied-box' data-job-id='{jid}'></td>"
                f"<td><input type='checkbox' class='outreach-box' data-job-id='{jid}'></td></tr>"
            )
        parts.append("</table>")
    parts.append(
        "<script>"
        "document.querySelectorAll('.applied-box,.outreach-box').forEach(function(box){"
        "var key='resume_index_'+box.className+'_'+box.dataset.jobId;"
        "box.checked = localStorage.getItem(key) === '1';"
        "box.addEventListener('change', function(){"
        "localStorage.setItem(key, box.checked ? '1' : '0');"
        "});"
        "});"
        "</script>"
    )
    parts.append("</body></html>")
    (OUTPUT_DIR / "index.html").write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-score", type=int, default=None, help="Only generate for match_score >= this")
    parser.add_argument("--job-id", type=str, default=None, help="Only generate for one specific job_id")
    parser.add_argument("--max-bullets", type=int, default=13,
                         help="Safety cap on total bullets across the whole resume, tuned for a strict one-page fit (default 13)")
    parser.add_argument("--show-applied", action="store_true",
                         help="Include jobs already marked applied (excluded by default -- see mark_applied.py)")
    parser.add_argument("--since", type=str, default=None,
                         help="Only jobs tailored (processed_at) on/after this date, e.g. --since 2026-09-13 for today only")
    parser.add_argument("--refresh-index", action="store_true",
                         help="Rebuild index.html only -- no PDFs are (re)built, jobs are linked in only if "
                              "their PDF already exists on disk. Safe to run every cycle (e.g. from the "
                              "scheduled screening task) even when zero jobs were tailored that run, so "
                              "screened-but-empty scrape slots still show up as a '(0)' section instead of "
                              "silently vanishing until the next job that happens to clear the tailoring bar.")
    args = parser.parse_args()

    if args.refresh_index:
        index_rows = fetch_jobs(args.min_score, None, args.show_applied, args.since)
        rows_written = []
        for row in index_rows:
            base = row["job_id"]
            filename = f"{base}.pdf"
            if not (OUTPUT_DIR / filename).exists():
                continue
            cover_letter_filename = f"{base}__cover_letter.pdf" if row["cover_letter"] else None
            if cover_letter_filename and not (OUTPUT_DIR / cover_letter_filename).exists():
                cover_letter_filename = None
            rows_written.append({
                "job_id": row["job_id"],
                "company": row["company"], "title": row["title"], "url": row["url"] or "",
                "apply_url": row["apply_url"] or row["url"] or "",
                "filename": filename, "match_score": row["match_score"],
                "cover_letter_filename": cover_letter_filename,
                "scraped_at": row["processed_at"] or "",
                "first_seen_at": row["first_seen_at"] or "",
                "applicant_count": row["applicant_count"],
            })
        build_index(rows_written)
        print(f"Refreshed index.html: {len(rows_written)} resume(s) linked, no PDFs (re)built.")
        return

    master = load_master_resume()
    # --job-id already disambiguates exactly which job you want -- --min-score
    # shouldn't also gate it out (e.g. forcing a PDF for a job you know scored
    # low on purpose). min_score still fully applies to the index below.
    rows = fetch_jobs(None if args.job_id else args.min_score, args.job_id, args.show_applied, args.since)
    if not rows:
        print("No analyzed jobs with tailored_resume_bullets found for these filters.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --job-id scopes which PDF(s) actually get (re)built -- but the index must
    # always reflect the FULL active list regardless, or every single-job
    # regen (e.g. "make a cover letter for X") silently wipes every other job
    # off the page even though their PDFs are untouched on disk.
    index_rows = rows if not args.job_id else fetch_jobs(args.min_score, None, args.show_applied, args.since)

    def row_to_entry(row: sqlite3.Row, build: bool) -> Dict[str, Any]:
        # job_id already encodes company + title (+ a hash for scraped jobs),
        # so re-prepending slug(company)__slug(title) just duplicates it and
        # makes filenames unreadably long. job_id alone is unique and readable.
        base = row["job_id"]
        filename = f"{base}.pdf"
        out_path = OUTPUT_DIR / filename
        if build:
            build_pdf(row, master, out_path, args.max_bullets)
            print(f"  Wrote {out_path.name}")
        cover_letter_filename = None
        if row["cover_letter"]:
            cover_letter_filename = f"{base}__cover_letter.pdf"
            if build:
                build_cover_letter_pdf(row, master, OUTPUT_DIR / cover_letter_filename)
                print(f"  Wrote {cover_letter_filename}")
        return {
            "job_id": row["job_id"],
            "company": row["company"], "title": row["title"], "url": row["url"] or "",
            "apply_url": row["apply_url"] or row["url"] or "",
            "filename": filename, "match_score": row["match_score"],
            "cover_letter_filename": cover_letter_filename,
            "scraped_at": row["processed_at"] or "",
            "first_seen_at": row["first_seen_at"] or "",
            "applicant_count": row["applicant_count"],
        }

    rebuilt_ids = {row["job_id"] for row in rows}
    # Build every requested PDF regardless of score (a --job-id force-build for a
    # job below --min-score still gets its file) -- but only add it to the visible
    # index if it actually clears the threshold, same as any other index row.
    built = [row_to_entry(row, build=True) for row in rows]
    clears_threshold = lambda entry: args.min_score is None or entry["match_score"] >= args.min_score
    rows_written = [entry for entry in built if clears_threshold(entry)]
    # For jobs NOT rebuilt this run (e.g. every other job when using --job-id),
    # only link them into the index if their PDF genuinely already exists on
    # disk -- otherwise a single-job regen with no --min-score would pull in
    # every tailored-but-never-built row (e.g. sub-70 priority-company jobs)
    # and silently produce dead "Open PDF" links.
    for row in index_rows:
        if row["job_id"] in rebuilt_ids:
            continue
        entry = row_to_entry(row, build=False)
        if (OUTPUT_DIR / entry["filename"]).exists():
            rows_written.append(entry)

    build_index(rows_written)
    print(f"\nDone. {len(rows)} resume(s) in {OUTPUT_DIR}")
    print(f"Open {OUTPUT_DIR / 'index.html'} to browse them sorted by match score.")


if __name__ == "__main__":
    main()
