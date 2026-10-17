"""Career Fit Explainer: a multi-agent system that investigates a single
job/resume pair across fragmented data sources and returns an evidence-backed
apply/skip recommendation, with full reasoning citations and a run trace.

Built for the Open Agent Hackathon 2026, track: "The Agent That Can Explain
Why". See career_fit_agent/README.md for architecture and sponsor-tech
integration details.
"""

from career_fit_agent.orchestrator import CareerFitOrchestrator, RunResult

__all__ = ["CareerFitOrchestrator", "RunResult"]
