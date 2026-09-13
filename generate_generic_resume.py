#!/usr/bin/env python3
"""One-off generic AI-focused resume, not tied to any specific job posting or
job_analysis DB record. Filters master_resume.json for bullets tagged
'ai_solutions' per employer, tops up each employer to its normal minimum
bullet floor (same MINIMUM_BULLETS_BY_COMPANY rule the per-job pipeline uses),
and reuses generate_resumes.py's PDF-building machinery directly -- skipping
the n8n scoring/tailoring round-trip entirely since there's no specific job
to score against.

Usage: python3 generate_generic_resume.py
Output: resumes/Gurkirat_Singh_Wadhawan__AI_Solutions_Generic.pdf
"""
from __future__ import annotations

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate
from pypdf import PdfReader

from generate_resumes import (
    load_master_resume,
    ensure_minimum_bullets,
    trim_to_fit_one_page,
    _render_story,
    initial_scale_for,
    build_styles,
    MIN_SCALE,
    OUTPUT_DIR,
)

TAG = "ai_solutions"


def main() -> None:
    master = load_master_resume()
    contact = master.get("contact", {})
    summary = master["summary_variants"][TAG]

    bullets_by_company = {}
    for entry in master.get("experience", []):
        tagged = [b["text"] for b in entry.get("bullets", []) if TAG in b.get("tags", [])]
        if tagged:
            bullets_by_company[entry["company"]] = tagged

    bullets_by_company = ensure_minimum_bullets(bullets_by_company, master)
    bullets_by_company = trim_to_fit_one_page(bullets_by_company, max_total=18)

    skills_bank = master["skills_keyword_bank"]
    tailored_skills = (
        skills_bank["ai_llm"]
        + skills_bank["programming_automation"][:6]
        + skills_bank["data_warehousing"][:5]
    )

    total_bullets = sum(len(v) for v in bullets_by_company.values())

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "Gurkirat_Singh_Wadhawan__AI_Solutions_Generic.pdf"

    scale = initial_scale_for(total_bullets)
    n_pages = None
    while True:
        styles = build_styles(scale)
        story = _render_story(master, contact, summary, tailored_skills, bullets_by_company, styles, projects_first=True)
        margin_scale = max(scale, 0.85)
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
        print(f"warning: {out_path.name} still {n_pages} pages at floor scale {MIN_SCALE} "
              f"({total_bullets} bullets)")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
