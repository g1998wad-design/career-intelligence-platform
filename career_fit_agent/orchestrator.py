"""Runs one career-fit investigation end to end.

Flow (the "strong" pattern the hackathon rubric asks for):

    Planner -- builds the plan
        |
        v
    Research agents (job_requirements, resume_match, company_signal, market_context)
        |
        v
    Evaluator -- validates each finding; low-confidence ones get ONE bounded
                 retry with feedback (e.g. CompanySignalAgent is told to widen
                 its lookback window)
        |
        v
    Risk agent -- flags experience/skill gaps and legal/EEO-sensitive asks
        |
        v
    Planner.refine() -- turns a HIGH risk note into an explicit instruction
                         for the Explainer (the escalate-then-refine loop)
        |
        v
    Explainer -- synthesizes the validated findings + refinements into a
                 cited verdict

Every step runs inside MeterlessMeter.step(...) and is appended to a full
run trace, so the whole decision is reproducible and auditable.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from career_fit_agent.agents import (
    CompanySignalAgent,
    EvaluatorAgent,
    ExplainerAgent,
    JobRequirementsAgent,
    MarketContextAgent,
    PlannerAgent,
    ResumeMatchAgent,
    RiskAgent,
)
from career_fit_agent.llm import get_reasoner
from career_fit_agent.meterless_client import MeterlessMeter
from career_fit_agent.zetaris_client import ZetarisFederatedStore


@dataclass
class RunResult:
    run_id: str
    job_id: str
    verdict: str
    confidence: float
    narrative: str
    reasons: list[dict[str, Any]]
    missing_skills: list[str]
    risk_notes: list[dict[str, Any]]
    trace: list[dict[str, Any]] = field(default_factory=list)
    meterless_summary: dict[str, Any] = field(default_factory=dict)
    zetaris_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "narrative": self.narrative,
            "reasons": self.reasons,
            "missing_skills": self.missing_skills,
            "risk_notes": self.risk_notes,
            "trace": self.trace,
            "meterless_summary": self.meterless_summary,
            "zetaris_status": self.zetaris_status,
        }


class CareerFitOrchestrator:
    def __init__(self, store: ZetarisFederatedStore | None = None) -> None:
        self.store = store or ZetarisFederatedStore()
        self.planner = PlannerAgent()
        self.job_requirements_agent = JobRequirementsAgent()
        self.resume_match_agent = ResumeMatchAgent()
        self.company_signal_agent = CompanySignalAgent()
        self.market_context_agent = MarketContextAgent()
        self.evaluator = EvaluatorAgent()
        self.risk_agent = RiskAgent()
        self.explainer = ExplainerAgent()
        self.reasoner = get_reasoner()

    def run(self, job_id: str) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        meter = MeterlessMeter(run_id=run_id)
        trace: list[dict[str, Any]] = []

        def log(step: str, payload: dict[str, Any]) -> None:
            trace.append({"t": round(time.time(), 3), "step": step, **payload})

        plan = self.planner.initial_plan({"job_id": job_id})
        log("planner.initial_plan", {"plan": plan})

        with meter.step("job_requirements", {"job_id": job_id}) as box:
            job_requirements = self.job_requirements_agent.run(self.store, job_id)
            box["result"] = job_requirements.to_dict()
        log("job_requirements", {"finding": job_requirements.to_dict()})

        with meter.step("resume_match", {"job_id": job_id}) as box:
            resume_match = self.resume_match_agent.run(self.store, job_requirements)
            box["result"] = resume_match.to_dict()
        log("resume_match", {"finding": resume_match.to_dict()})

        company = job_requirements.details.get("company", "")
        company_signal = self._run_company_signal_with_retry(meter, log, company)

        resume_profile = self.store.resume_profile()
        with meter.step("market_context", {"job_id": job_id}) as box:
            market_context = self.market_context_agent.run(self.store, job_requirements, resume_profile)
            box["result"] = market_context.to_dict()
        log("market_context", {"finding": market_context.to_dict()})

        risk_notes = self.risk_agent.review(job_requirements, resume_match)
        log("risk_agent.review", {"risk_notes": [n.to_dict() for n in risk_notes]})

        refinements = self.planner.refine(risk_notes)
        log("planner.refine", refinements)

        with meter.step("explainer", {"job_id": job_id}) as box:
            result = self.explainer.synthesize(
                job_requirements, resume_match, company_signal, market_context,
                risk_notes, refinements, self.reasoner,
            )
            box["result"] = result
        log("explainer", {"result": result})

        return RunResult(
            run_id=run_id,
            job_id=job_id,
            verdict=result["verdict"],
            confidence=result["confidence"],
            narrative=result["narrative"],
            reasons=result["reasons"],
            missing_skills=result["missing_skills"],
            risk_notes=result["risk_notes"],
            trace=trace,
            meterless_summary=meter.summary(),
            zetaris_status=self.store.status().__dict__,
        )

    def _run_company_signal_with_retry(self, meter: MeterlessMeter, log, company: str):
        with meter.step("company_signal", {"company": company, "max_age_days": 30}) as box:
            finding = self.company_signal_agent.run(self.store, company, max_age_days=30)
            box["result"] = finding.to_dict()
        log("company_signal.attempt_1", {"finding": finding.to_dict()})

        if not self.evaluator.needs_retry(finding):
            return finding

        with meter.step("company_signal_retry", {"company": company, "max_age_days": 365}) as box:
            retried = self.company_signal_agent.run(self.store, company, max_age_days=365)
            box["result"] = retried.to_dict()
        log(
            "evaluator.retry",
            {
                "reason": "confidence below threshold on first pass -- broadening lookback window",
                "finding": retried.to_dict(),
            },
        )
        return retried
