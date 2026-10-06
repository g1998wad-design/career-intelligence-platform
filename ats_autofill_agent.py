#!/usr/bin/env python3
"""Agentic reasoning layer over ats_autofill.py's "unmatched" free-text fields.

ats_autofill.py is deterministic/rule-based by design: it fills fields it can
confidently match (name/email/phone/etc via FIELD_KEYWORDS, sensitive fields
via pre-approved standard_answers), and otherwise leaves them for a human --
either flagged in `needs_review` (sensitive/select/radio/checkbox with no
resolvable answer) or logged in `unmatched` (free-text fields whose label
didn't match anything, e.g. custom screening questions like "Why do you want
to work here?" or "Describe a project where you...").

This module does NOT touch ats_autofill.py, does NOT drive a live browser,
and NEVER auto-fills or auto-submits anything. It reads ONLY the free-text
`unmatched`/`needs_review` field labels already captured in batch_run_log.json
(or a fixture file, for isolated testing) and uses the Claude Agent SDK to
draft candidate answers grounded strictly in master_resume.json and
autofill_profile.json, each with a confidence level and a cited reasoning
trail. Output is written to a separate review file
(agent_review_suggestions.json) for a human to read, edit, and paste in by
hand -- it upgrades "left blank, go figure it out yourself" into "here's a
grounded draft + how confident I am + why", nothing more.

Usage:
    python3 ats_autofill_agent.py --log batch_run_log.json
    python3 ats_autofill_agent.py --demo   # runs against built-in fixture examples, no log needed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

# Reused, read-only, from the existing (untouched) pipeline -- no duplication
# of its field vocabulary or path conventions.
from ats_autofill import BASE_DIR, PROFILE_PATH, load_json, now

MASTER_RESUME_PATH = BASE_DIR / "master_resume.json"
OUTPUT_PATH = BASE_DIR / "agent_review_suggestions.json"

# Only genuinely free-text fields are worth an LLM draft. Selects/radios/
# checkboxes are deliberately never guessed by ats_autofill.py (see
# fill_frame()'s comment: "too easy to silently pick the wrong option") --
# this layer respects that same boundary and does not touch them.
FREE_TEXT_TYPES = {"text", "textarea", "email", "tel", "url"}

FIELD_LINE_RE = re.compile(r"^\[([a-zA-Z ]+)\]\s*(.*)$")

SYSTEM_PROMPT = """You are a job-application drafting assistant. You are given
a job posting's title/company/description and a candidate's resume and
profile facts. You will be shown one or more free-text application questions
that a deterministic autofill script could not confidently match to a known
field.

For EACH question, draft a candidate answer using ONLY facts present in the
provided resume/profile -- never invent experience, numbers, dates, or
skills that are not there. If the resume doesn't contain enough to answer
truthfully and specifically, say so plainly and give a "low" confidence
rating with an empty or minimal answer, rather than fabricating anything.

Respond with ONLY a JSON array (no prose, no markdown fences), one object per
question in the same order given, each shaped exactly as:
{"label": "<the question as given>", "answer": "<drafted answer, or empty string if not answerable>", "confidence": "high"|"medium"|"low", "reasoning": "<1-2 sentences: what resume facts you used, or why you couldn't answer>"}
"""


def load_context() -> Dict[str, Any]:
    profile = load_json(PROFILE_PATH, "autofill_profile.json")
    master_resume = json.loads(MASTER_RESUME_PATH.read_text(encoding="utf-8"))
    return {"profile": profile, "master_resume": master_resume}


def parse_free_text_fields(field_lines: List[str]) -> List[str]:
    """Filters unmatched/needs_review log lines down to genuinely free-text
    labels worth drafting (skips file uploads, selects, radio/checkbox
    groups, search boxes, and the "(matched 'x' but profile value is blank)"
    variant, which needs a profile fix, not a drafted answer)."""
    labels: List[str] = []
    for line in field_lines:
        m = FIELD_LINE_RE.match(line.strip())
        if not m:
            continue
        tag, label = m.group(1).strip().lower(), m.group(2).strip()
        if tag not in FREE_TEXT_TYPES:
            continue
        if "matched '" in label and "profile value is blank" in label:
            continue
        if label:
            labels.append(label)
    return labels


def _build_prompt(job: Dict[str, Any], profile: Dict[str, Any],
                   master_resume: Dict[str, Any], labels: List[str]) -> str:
    questions_block = "\n".join(f"{i+1}. {label}" for i, label in enumerate(labels))
    return f"""JOB
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description: {job.get('description', '(not provided)')[:2000]}

CANDIDATE PROFILE
{json.dumps({k: v for k, v in profile.items() if k not in ("standard_answers",)}, indent=2)}

CANDIDATE RESUME (source of truth for all experience claims)
{json.dumps(master_resume, indent=2)}

QUESTIONS TO DRAFT
{questions_block}
"""


async def _run_agent_query(prompt: str) -> str:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        max_turns=2,
    )
    chunks: List[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
    return "".join(chunks)


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in agent response: {text[:200]!r}")
    return json.loads(text[start:end + 1])


async def resolve_job_fields(job: Dict[str, Any], labels: List[str],
                              context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not labels:
        return []
    prompt = _build_prompt(job, context["profile"], context["master_resume"], labels)
    raw = await _run_agent_query(prompt)
    try:
        resolved = _extract_json_array(raw)
    except (ValueError, json.JSONDecodeError) as e:
        return [{"label": lbl, "answer": "", "confidence": "low",
                  "reasoning": f"Agent response could not be parsed: {e}"} for lbl in labels]
    return resolved


async def process_log(log_path: Path) -> List[Dict[str, Any]]:
    context = load_context()
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    results = []
    for entry in entries:
        labels = parse_free_text_fields(
            entry.get("unmatched_fields", []) + entry.get("needs_review_fields", [])
        )
        if not labels:
            continue
        job = {"title": entry.get("title", ""), "company": entry.get("company", ""),
               "description": entry.get("description", "")}
        resolved = await resolve_job_fields(job, labels, context)
        results.append({
            "job_id": entry.get("job_id"),
            "company": entry.get("company"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "suggestions": resolved,
        })
    return results


DEMO_FIXTURES = [
    {
        "job_id": "demo_appen_fde",
        "company": "Appen",
        "title": "Forward Deployed Engineer",
        "url": "https://example.com/demo",
        "unmatched_fields": [
            "[textarea] Why are you interested in this role?",
            "[textarea] Describe a time you built an internal tool or automation that solved a real business problem.",
            "[text] How many years of experience do you have with Kubernetes?",
        ],
        "needs_review_fields": [],
    }
]


async def process_demo() -> List[Dict[str, Any]]:
    context = load_context()
    results = []
    for entry in DEMO_FIXTURES:
        labels = parse_free_text_fields(entry["unmatched_fields"] + entry["needs_review_fields"])
        job = {"title": entry["title"], "company": entry["company"], "description": ""}
        resolved = await resolve_job_fields(job, labels, context)
        results.append({
            "job_id": entry["job_id"], "company": entry["company"], "title": entry["title"],
            "url": entry["url"], "suggestions": resolved,
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=BASE_DIR / "batch_run_log.json",
                         help="Path to batch_run_log.json (never modified)")
    parser.add_argument("--demo", action="store_true",
                         help="Run against built-in fixture questions instead of a real log")
    args = parser.parse_args()

    if args.demo:
        results = asyncio.run(process_demo())
    else:
        if not args.log.exists():
            print(f"No log at {args.log}")
            return
        results = asyncio.run(process_log(args.log))

    OUTPUT_PATH.write_text(json.dumps({"generated_at": now(), "jobs": results}, indent=2),
                            encoding="utf-8")

    total_qs = sum(len(r["suggestions"]) for r in results)
    print(f"Drafted {total_qs} answer(s) across {len(results)} job(s) -> {OUTPUT_PATH}")
    for r in results:
        print(f"\n{r['company']} -- {r['title']}")
        for s in r["suggestions"]:
            print(f"  [{s['confidence']}] {s['label']}")
            print(f"      -> {s['answer'][:150]}")


if __name__ == "__main__":
    main()
