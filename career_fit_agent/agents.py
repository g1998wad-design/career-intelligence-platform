"""The agent roles. Each agent is specialised and interdependent:

Planner       -- decides what to investigate, and later what to re-investigate
                 when the Risk agent escalates a concern.
Research      -- JobRequirementsAgent, ResumeMatchAgent, CompanySignalAgent,
                 MarketContextAgent each own one fragmented data source,
                 queried through the shared Zetaris federated store.
Evaluator     -- validates every research finding; demands a retry (with
                 feedback) when confidence is too low, bounded to one retry.
Risk          -- a domain-specific guardrail that can escalate back to the
                 Planner, which then hands the Explainer extra constraints.
Explainer     -- synthesizes everything into an evidence-cited verdict.

All facts in a Finding/RiskNote are derived deterministically from queried
data -- the LLM reasoner (llm.py) is only used by the Explainer to narrate,
never to invent a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from career_fit_agent.llm import Reasoner
from career_fit_agent.zetaris_client import ZetarisFederatedStore

EXPLICIT_YEAR_PATTERNS = [
    re.compile(r"(\d{1,2})\s*\+\s*years?", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*-\s*\d{1,2}\s*years?", re.IGNORECASE),
    re.compile(r"minimum\s+(?:of\s+)?(\d{1,2})\s*years?", re.IGNORECASE),
    re.compile(r"at\s+least\s+(\d{1,2})\s*years?", re.IGNORECASE),
]
SPONSORSHIP_PATTERN = re.compile(r"sponsorship|citizenship|security clearance|work authorization", re.IGNORECASE)


@dataclass
class Citation:
    source: str
    locator: str
    snippet: str


@dataclass
class Finding:
    agent: str
    summary: str
    confidence: float
    evidence: list[Citation] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "summary": self.summary,
            "confidence": self.confidence,
            "evidence": [c.__dict__ for c in self.evidence],
            "details": self.details,
        }


@dataclass
class RiskNote:
    severity: str  # "info" | "low" | "medium" | "high"
    message: str
    mitigation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


class PlannerAgent:
    """Builds the initial investigation plan and later refines it when the
    Risk agent escalates, closing the Planner <-> Risk feedback loop."""

    def initial_plan(self, job: dict[str, Any]) -> list[str]:
        plan = ["job_requirements", "resume_match", "company_signal", "market_context"]
        return plan

    def refine(self, risk_notes: list[RiskNote]) -> dict[str, Any]:
        high = [n for n in risk_notes if n.severity == "high"]
        if not high:
            return {"explainer_instructions": []}
        return {
            "explainer_instructions": [
                f"Explicitly surface this gap and its mitigation in the explanation: {n.message}"
                for n in high
            ]
        }


class JobRequirementsAgent:
    def run(self, store: ZetarisFederatedStore, job_id: str) -> Finding:
        job_rows = store.query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        detail_rows = store.query(
            "SELECT * FROM job_requirements_detail WHERE job_id = ?", (job_id,)
        )
        if not job_rows:
            return Finding("job_requirements", f"No job record found for {job_id}", 0.0)
        job = job_rows[0]
        description = detail_rows[0]["description"] if detail_rows else job.get("description", "")
        required_skills = _json_list(detail_rows[0]["required_skills"]) if detail_rows else []

        required_years, years_confidence, years_source = _extract_required_years(description, job["title"])
        sponsorship_flag = bool(SPONSORSHIP_PATTERN.search(description))

        citations = [Citation("jobs", job_id, job["title"])]
        if detail_rows:
            citations.append(Citation("job_requirements_detail", job_id, description))

        summary = (
            f"{job['title']} at {job['company']} requires "
            f"{required_years if required_years is not None else 'an unspecified number of'} years "
            f"and lists {len(required_skills)} required skill(s): {', '.join(required_skills) or 'none captured'}."
        )
        return Finding(
            agent="job_requirements",
            summary=summary,
            confidence=years_confidence,
            evidence=citations,
            details={
                "required_years": required_years,
                "years_source": years_source,
                "required_skills": required_skills,
                "sponsorship_flag": sponsorship_flag,
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
            },
        )


class ResumeMatchAgent:
    def run(self, store: ZetarisFederatedStore, job_requirements: Finding) -> Finding:
        resume = store.resume_profile()
        skill_rows = store.query("SELECT skill FROM resume_skills")
        candidate_skills = {r["skill"].lower() for r in skill_rows}
        required_skills = job_requirements.details.get("required_skills", [])

        overlap = [s for s in required_skills if s.lower() in candidate_skills]
        missing = [s for s in required_skills if s.lower() not in candidate_skills]
        overlap_ratio = (len(overlap) / len(required_skills)) if required_skills else 1.0

        candidate_years = resume.get("years_experience")
        required_years = job_requirements.details.get("required_years")
        gap_years = (required_years - candidate_years) if (required_years is not None and candidate_years is not None) else None

        summary = (
            f"Candidate has {candidate_years} years; role wants "
            f"{required_years if required_years is not None else 'an unspecified amount'} "
            f"(gap={gap_years if gap_years is not None else 'unknown'}). "
            f"Skill overlap {len(overlap)}/{len(required_skills)}: matches {overlap or 'none'}, missing {missing or 'none'}."
        )
        confidence = 0.85 if required_years is not None else 0.5
        return Finding(
            agent="resume_match",
            summary=summary,
            confidence=confidence,
            evidence=[Citation("resume_skills", "sample_master_resume.json", f"skills: {sorted(candidate_skills)}")],
            details={
                "candidate_years": candidate_years,
                "gap_years": gap_years,
                "overlap_skills": overlap,
                "missing_skills": missing,
                "overlap_ratio": round(overlap_ratio, 2),
            },
        )


class CompanySignalAgent:
    def run(self, store: ZetarisFederatedStore, company: str, max_age_days: int) -> Finding:
        rows = store.query(
            "SELECT * FROM company_notes WHERE company = ? AND published_days_ago <= ? ORDER BY published_days_ago",
            (company, max_age_days),
        )
        if not rows:
            return Finding(
                agent="company_signal",
                summary=(
                    f"No independent signal for {company} within {max_age_days} days"
                    if max_age_days < 365
                    else f"No independent signal for {company} found in any available source window -- a genuine data gap"
                ),
                confidence=0.35 if max_age_days < 365 else 0.3,
                details={"max_age_days": max_age_days, "found": False},
            )
        summary = " / ".join(f"[{r['source']}] {r['snippet']}" for r in rows)
        citations = [Citation("company_notes", f"{company}/{r['source']}", r["snippet"]) for r in rows]
        return Finding(
            agent="company_signal",
            summary=summary,
            confidence=0.8,
            evidence=citations,
            details={"max_age_days": max_age_days, "found": True, "num_sources": len(rows)},
        )


class MarketContextAgent:
    def run(self, store: ZetarisFederatedStore, job_requirements: Finding, resume: dict[str, Any]) -> Finding:
        title = job_requirements.details.get("title", "")
        location = job_requirements.details.get("location", "") or ""
        title_family = title.lower()
        location_tier = "national_remote"

        rows = store.query(
            "SELECT * FROM market_salary WHERE title_family = ? AND location_tier = ?",
            (title_family, location_tier),
        )
        if not rows:
            return Finding("market_context", f"No market band found for '{title}'", 0.3)
        band = rows[0]
        target = resume.get("target_salary")
        position = None
        if target is not None:
            if target < band["low"]:
                position = "below band"
            elif target > band["high"]:
                position = "above band"
            else:
                position = "within band"

        summary = (
            f"Market band for {title} ({location or 'remote'}): "
            f"${band['low']:,}-${band['high']:,} (mid ${band['mid']:,})."
            + (f" Candidate target ${target:,} is {position}." if position else "")
        )
        is_remote = "remote" in location.lower()
        return Finding(
            agent="market_context",
            summary=summary,
            confidence=0.85 if is_remote else 0.6,
            evidence=[Citation("market_salary", title_family, summary)],
            details={"band": dict(band), "target_salary": target, "position_vs_band": position},
        )


class EvaluatorAgent:
    """Validates findings; requests a bounded retry when confidence is low."""

    LOW_CONFIDENCE_THRESHOLD = 0.5

    def needs_retry(self, finding: Finding) -> bool:
        return finding.confidence < self.LOW_CONFIDENCE_THRESHOLD


class RiskAgent:
    def review(self, job_requirements: Finding, resume_match: Finding) -> list[RiskNote]:
        notes: list[RiskNote] = []
        gap_years = resume_match.details.get("gap_years")
        overlap_ratio = resume_match.details.get("overlap_ratio", 1.0)

        if gap_years is not None and gap_years >= 2:
            notes.append(
                RiskNote(
                    severity="high",
                    message=f"Experience gap of {gap_years} year(s) vs. the stated requirement.",
                    mitigation="Address the gap directly (e.g. comparable project scope, fast ramp-up plan) rather than omitting it.",
                )
            )
        elif gap_years is not None and gap_years == 1:
            notes.append(
                RiskNote(
                    severity="low",
                    message="Candidate is 1 year short of the stated requirement.",
                    mitigation="Minor; worth a one-line note in the cover letter.",
                )
            )

        if overlap_ratio < 0.5:
            notes.append(
                RiskNote(
                    severity="high",
                    message=f"Only {overlap_ratio:.0%} of required skills are present on the resume.",
                    mitigation="Do not claim unlisted skills. Consider a learning plan or portfolio piece instead.",
                )
            )

        if job_requirements.details.get("sponsorship_flag"):
            notes.append(
                RiskNote(
                    severity="info",
                    message="Posting mentions work-authorization/sponsorship/clearance -- this is a legal/EEO question.",
                    mitigation="Must be answered by the candidate personally, never auto-filled or auto-answered.",
                )
            )
        return notes


def decide_verdict(gap_years: int | None, overlap_ratio: float, risk_notes: list[RiskNote]) -> str:
    high_risk = any(n.severity == "high" for n in risk_notes)
    if gap_years is not None and gap_years >= 2 and overlap_ratio < 0.5:
        return "skip"
    if high_risk or (gap_years is not None and gap_years >= 1) or overlap_ratio < 0.7:
        return "apply_with_caveats"
    return "apply"


class ExplainerAgent:
    def synthesize(
        self,
        job_requirements: Finding,
        resume_match: Finding,
        company_signal: Finding,
        market_context: Finding,
        risk_notes: list[RiskNote],
        planner_refinements: dict[str, Any],
        reasoner: Reasoner,
    ) -> dict[str, Any]:
        gap_years = resume_match.details.get("gap_years")
        overlap_ratio = resume_match.details.get("overlap_ratio", 1.0)
        verdict = decide_verdict(gap_years, overlap_ratio, risk_notes)

        reasons = [
            {"claim": job_requirements.summary, "citations": [c.__dict__ for c in job_requirements.evidence]},
            {"claim": resume_match.summary, "citations": [c.__dict__ for c in resume_match.evidence]},
            {"claim": company_signal.summary, "citations": [c.__dict__ for c in company_signal.evidence]},
            {"claim": market_context.summary, "citations": [c.__dict__ for c in market_context.evidence]},
        ]

        confidence = round(
            sum(f.confidence for f in (job_requirements, resume_match, company_signal, market_context)) / 4, 2
        )

        instructions = planner_refinements.get("explainer_instructions", [])
        fallback_text = _compose_fallback_narrative(
            verdict, job_requirements, resume_match, company_signal, market_context, risk_notes, instructions,
        )

        narrative = reasoner.narrate(
            system=(
                "Rewrite the following structured career-fit facts into a short, honest 3-5 sentence "
                "explanation for the candidate. Use ONLY the facts given -- do not invent, soften, or "
                "drop any of them, including risk notes and must-address items."
            ),
            user=fallback_text,
        )

        return {
            "verdict": verdict,
            "confidence": confidence,
            "narrative": narrative,
            "reasons": reasons,
            "missing_skills": resume_match.details.get("missing_skills", []),
            "risk_notes": [n.to_dict() for n in risk_notes],
            "planner_refinements": instructions,
        }


def _compose_fallback_narrative(
    verdict: str,
    job_requirements: Finding,
    resume_match: Finding,
    company_signal: Finding,
    market_context: Finding,
    risk_notes: list[RiskNote],
    instructions: list[str],
) -> str:
    sentences = [
        f"Recommendation: {verdict.replace('_', ' ')}.",
        job_requirements.summary,
        resume_match.summary,
        company_signal.summary,
        market_context.summary,
    ]
    sentences.extend(f"Risk ({n.severity}): {n.message} Mitigation: {n.mitigation}" for n in risk_notes)
    sentences.extend(f"Must address: {i}" for i in instructions)
    return " ".join(sentences)


def _extract_required_years(description: str, title: str) -> tuple[int | None, float, str]:
    for pattern in EXPLICIT_YEAR_PATTERNS:
        match = pattern.search(description or "")
        if match:
            return int(match.group(1)), 0.9, "explicit_pattern"

    title = (title or "").lower()
    if re.search(r"\b(staff|principal|director|head of|vp)\b", title):
        return 8, 0.6, "title_tier"
    if re.search(r"\b(senior|sr\.?|lead)\b", title):
        return 6, 0.6, "title_tier"
    if re.search(r"\b(junior|jr\.?|entry.level|associate)\b", title):
        return 0, 0.6, "title_tier"
    return None, 0.4, "unknown"


def _json_list(raw: str | None) -> list[str]:
    import json

    if not raw:
        return []
    return json.loads(raw)
