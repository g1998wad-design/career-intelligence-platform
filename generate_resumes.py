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
from pathlib import Path
from typing import Any, Dict, List, Optional

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
# better to know that (via the "still N pages" warning) than to silently ship
# 6pt text.
MIN_SCALE = 0.62


def build_styles(scale: float) -> Dict[str, ParagraphStyle]:
    s = scale
    return {
        "NAME_STYLE": ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=18 * s, leading=21 * s, spaceAfter=2 * s),
        "CONTACT_STYLE": ParagraphStyle("Contact", fontName="Helvetica", fontSize=9.5 * s, textColor="#444444", spaceAfter=8 * s),
        "SUMMARY_STYLE": ParagraphStyle("Summary", fontName="Helvetica-Oblique", fontSize=9.8 * s, leading=13 * s,
                                         spaceAfter=8 * s, alignment=TA_JUSTIFY),
        "SECTION_STYLE": ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=10.8 * s, spaceBefore=8 * s,
                                         spaceAfter=3 * s, textColor="#1a3c6e"),
        "JOB_HEADER_STYLE": ParagraphStyle("JobHeader", fontName="Helvetica-Bold", fontSize=9.8 * s, spaceBefore=5 * s, spaceAfter=1 * s),
        "JOB_SUB_STYLE": ParagraphStyle("JobSub", fontName="Helvetica-Oblique", fontSize=8.8 * s, textColor="#555555", spaceAfter=2 * s),
        "CONTEXT_STYLE": ParagraphStyle("Context", fontName="Helvetica-BoldOblique", fontSize=8.8 * s, textColor="#1a3c6e", spaceAfter=3 * s),
        "BULLET_STYLE": ParagraphStyle("Bullet", fontName="Helvetica", fontSize=9.3 * s, leading=12.2 * s, alignment=TA_JUSTIFY),
        "SKILLS_STYLE": ParagraphStyle("Skills", fontName="Helvetica", fontSize=9.3 * s, leading=12.8 * s),
        "EDU_HONORS_STYLE": ParagraphStyle("EduHonors", fontName="Helvetica-Oblique", fontSize=8.8 * s, leading=11.5 * s,
                                            textColor="#555555", spaceAfter=4 * s),
    }


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


def fetch_jobs(min_score: Optional[int], job_id: Optional[str], show_applied: bool = False) -> List[sqlite3.Row]:
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found — run job_fetcher.py at least once first.")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    query = """
        SELECT j.job_id, j.title, j.company, j.url, j.apply_url, j.applicant_count, a.tailored_summary, a.tailored_skills,
               a.tailored_resume_bullets, a.match_score, a.cover_letter, a.processed_at
        FROM job_analysis a
        JOIN jobs j ON j.job_id = a.job_id
        WHERE a.tailored_resume_bullets IS NOT NULL
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


# Per-company minimums, per your call that the resume was reading too thin.
# These are deliberately higher than a strict one-page resume would allow --
# the tradeoff (2 pages, much more concrete evidence per employer) is the
# point. Keyed by exact master_resume.json company name.
MINIMUM_BULLETS_BY_COMPANY = {
    "Allegis Group": 6,
    "KPMG": 4,
    "Career Intelligence Platform (personal project, in progress)": 3,
    "Thrivent Federal Credit Union": 2,
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
                   styles: Dict[str, ParagraphStyle]) -> List[Any]:
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
        contact.get("location"), contact.get("phone"), contact.get("email"), contact.get("linkedin")
    ] if v]
    if contact_bits:
        story.append(Paragraph(" | ".join(contact_bits), CONTACT_STYLE))
    story.append(HRFlowable(width="100%", thickness=1, color="#1a3c6e", spaceAfter=8))

    if summary:
        story.append(Paragraph(summary, SUMMARY_STYLE))

    if tailored_skills:
        story.append(Paragraph("SKILLS", SECTION_STYLE))
        story.append(Paragraph(", ".join(tailored_skills), SKILLS_STYLE))

    story.append(Paragraph("EXPERIENCE", SECTION_STYLE))
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
        story.append(Paragraph(header, JOB_HEADER_STYLE))
        sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
        if sub_bits:
            story.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
        # Always shown, independent of Gemini's per-job bullet picks -- a real
        # standout credential (e.g. Allegis's Employee of the Year / Rising
        # Star) shouldn't be left to chance on whether the LLM chose to surface it.
        if entry.get("context"):
            story.append(Paragraph(entry["context"], CONTEXT_STYLE))
        items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
        story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

    project_entries = [e for e in master.get("experience", []) if e.get("type") == "project" and bullets_by_company.get(e["company"])]
    if project_entries:
        story.append(Paragraph("PROJECTS", SECTION_STYLE))
        for entry in project_entries:
            company = entry["company"]
            bullets = bullets_by_company.get(company)
            header = f"{entry.get('title', '')} — {company}" if entry.get("title") else company
            story.append(Paragraph(header, JOB_HEADER_STYLE))
            sub_bits = [b for b in [entry.get("dates"), entry.get("location")] if b]
            if sub_bits:
                story.append(Paragraph(" | ".join(sub_bits), JOB_SUB_STYLE))
            items = [ListItem(Paragraph(b, BULLET_STYLE), leftIndent=12) for b in bullets]
            story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=14, spaceBefore=1, spaceAfter=4))

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


def build_pdf(row: sqlite3.Row, master: Dict[str, Any], out_path: Path, max_bullets: int) -> None:
    contact = master.get("contact", {})
    tailored_bullets = safe_json(row["tailored_resume_bullets"], [])
    tailored_skills = safe_json(row["tailored_skills"], [])
    summary = row["tailored_summary"] or master.get("summary_variants", {}).get("default", "")

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
    scale = initial_scale_for(total_bullets)
    n_pages = None
    while True:
        styles = build_styles(scale)
        story = _render_story(master, contact, summary, tailored_skills, bullets_by_company, styles)
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


def build_index(rows_written: List[Dict[str, Any]]) -> None:
    """A single clickable page, sorted best-match-first, so you never have
    to browse the resumes/ folder guessing which file matches which job.

    Jobs marked applied (see mark_applied.py) are excluded by default, so
    this page only ever shows what you still need to act on."""
    rows_written = sorted(rows_written, key=lambda r: -(r["match_score"] or 0))
    parts = [
        "<html><head><meta charset='utf-8'><title>Tailored Resumes</title>",
        "<style>body{font-family:-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 20px}",
        "table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #ddd}",
        "th{background:#f5f5f5} .score{font-weight:bold} tr:hover{background:#fafafa}",
        "</style></head><body>",
        f"<h2>Tailored Resumes ({len(rows_written)})</h2>",
        "<table><tr><th>Match</th><th>Company</th><th>Title</th><th>Applicants</th><th>Resume</th><th>Cover Letter</th><th>Scraped</th><th>Posting</th><th>Direct Apply</th></tr>"
    ]
    for r in rows_written:
        cover_letter_cell = (
            f"<a href='{r['cover_letter_filename']}'>Open PDF</a>" if r.get("cover_letter_filename") else "—"
        )
        scraped_display = r.get("scraped_at", "")[:10] or "—"  # YYYY-MM-DD from the ISO timestamp
        # apply_url is the actual ATS/company application link when JobSpy found one
        # (mainly Indeed postings); otherwise it falls back to the same listing url
        # (mainly LinkedIn).
        has_direct = bool(r["apply_url"]) and r["apply_url"] != r["url"]
        direct_cell = "<span style='color:#0a7'>Yes</span>" if has_direct else "<span style='color:#999'>No (LinkedIn only)</span>"
        # LinkedIn-only (jobspy has no applicant-count support for other sites).
        applicants = r.get("applicant_count")
        applicants_cell = str(applicants) if applicants is not None else "—"
        parts.append(
            f"<tr><td class='score'>{r['match_score']}</td><td>{r['company']}</td>"
            f"<td>{r['title']}</td><td>{applicants_cell}</td><td><a href='{r['filename']}'>Open PDF</a></td>"
            f"<td>{cover_letter_cell}</td>"
            f"<td>{scraped_display}</td>"
            f"<td><a href='{r['url']}' target='_blank'>View posting</a></td>"
            f"<td>{direct_cell}</td></tr>"
        )
    parts.append("</table></body></html>")
    (OUTPUT_DIR / "index.html").write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-score", type=int, default=None, help="Only generate for match_score >= this")
    parser.add_argument("--job-id", type=str, default=None, help="Only generate for one specific job_id")
    parser.add_argument("--max-bullets", type=int, default=18,
                         help="Safety cap on total bullets across the whole resume (default 18 -- MINIMUM_BULLETS_BY_COMPANY floors total ~15, so PDFs will now typically run 2 pages; tune down only if you want to go back to a strict 1-pager)")
    parser.add_argument("--show-applied", action="store_true",
                         help="Include jobs already marked applied (excluded by default -- see mark_applied.py)")
    args = parser.parse_args()

    master = load_master_resume()
    rows = fetch_jobs(args.min_score, args.job_id, args.show_applied)
    if not rows:
        print("No analyzed jobs with tailored_resume_bullets found for these filters.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    rows_written = []
    for row in rows:
        base = f"{slug(row['company'])}__{slug(row['title'])}__{row['job_id']}"
        filename = f"{base}.pdf"
        out_path = OUTPUT_DIR / filename
        build_pdf(row, master, out_path, args.max_bullets)
        print(f"  Wrote {out_path.name}")

        cover_letter_filename = None
        if row["cover_letter"]:
            cover_letter_filename = f"{base}__cover_letter.pdf"
            build_cover_letter_pdf(row, master, OUTPUT_DIR / cover_letter_filename)
            print(f"  Wrote {cover_letter_filename}")

        rows_written.append({
            "job_id": row["job_id"],
            "company": row["company"], "title": row["title"], "url": row["url"] or "",
            "apply_url": row["apply_url"] or row["url"] or "",
            "filename": filename, "match_score": row["match_score"],
            "cover_letter_filename": cover_letter_filename,
            "scraped_at": row["processed_at"] or "",
            "applicant_count": row["applicant_count"],
        })

    build_index(rows_written)
    print(f"\nDone. {len(rows)} resume(s) in {OUTPUT_DIR}")
    print(f"Open {OUTPUT_DIR / 'index.html'} to browse them sorted by match score.")


if __name__ == "__main__":
    main()
