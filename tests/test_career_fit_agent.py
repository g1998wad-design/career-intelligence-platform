"""Smoke tests for the Career Fit Explainer agent system. No network calls
and no API keys required -- runs fully on the committed mock_scenarios data
through the local Zetaris federation + heuristic reasoner fallback."""

import json
import unittest
from pathlib import Path

from career_fit_agent.agents import decide_verdict, RiskNote
from career_fit_agent.orchestrator import CareerFitOrchestrator
from career_fit_agent.zetaris_client import ZetarisFederatedStore

BASE_DIR = Path(__file__).resolve().parent.parent


class TestZetarisFederatedStore(unittest.TestCase):
    def test_federates_all_sample_sources(self):
        store = ZetarisFederatedStore()
        status = store.status()
        self.assertEqual(status.mode, "local_federation")
        self.assertEqual(len(status.sources), 5)

    def test_sql_join_across_jobs_and_detail(self):
        store = ZetarisFederatedStore()
        rows = store.query(
            """
            SELECT j.title, d.required_skills FROM jobs j
            JOIN job_requirements_detail d ON j.job_id = d.job_id
            WHERE j.job_id = ?
            """,
            ("MOCK_LI_GREENHOUSE_001",),
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("SQL", rows[0]["required_skills"])


class TestDecideVerdict(unittest.TestCase):
    def test_strong_fit_applies(self):
        self.assertEqual(decide_verdict(gap_years=-2, overlap_ratio=1.0, risk_notes=[]), "apply")

    def test_big_gap_and_low_overlap_skips(self):
        self.assertEqual(decide_verdict(gap_years=2, overlap_ratio=0.25, risk_notes=[]), "skip")

    def test_small_gap_applies_with_caveats(self):
        self.assertEqual(decide_verdict(gap_years=1, overlap_ratio=1.0, risk_notes=[]), "apply_with_caveats")

    def test_high_risk_note_forces_caveats_even_with_no_gap(self):
        notes = [RiskNote(severity="high", message="x")]
        self.assertEqual(decide_verdict(gap_years=None, overlap_ratio=1.0, risk_notes=notes), "apply_with_caveats")


class TestOrchestratorEndToEnd(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CareerFitOrchestrator()

    def test_good_fit_job_recommends_apply(self):
        result = self.orchestrator.run("MOCK_LI_GREENHOUSE_001")
        self.assertEqual(result.verdict, "apply")
        self.assertGreater(len(result.reasons), 0)
        self.assertTrue(all(r["citations"] for r in result.reasons[:2]))

    def test_mild_gap_job_recommends_caveats_and_flags_sponsorship(self):
        result = self.orchestrator.run("MOCK_LI_WORKDAY_002")
        self.assertEqual(result.verdict, "apply_with_caveats")
        severities = {n["severity"] for n in result.risk_notes}
        self.assertIn("info", severities)

    def test_large_gap_job_recommends_skip_and_surfaces_missing_skills(self):
        result = self.orchestrator.run("MOCK_LI_NO_DIRECT_003")
        self.assertEqual(result.verdict, "skip")
        self.assertIn("LLM APIs", result.missing_skills)
        self.assertTrue(any(n["severity"] == "high" for n in result.risk_notes))

    def test_company_signal_retries_once_when_first_pass_finds_nothing_fresh(self):
        result = self.orchestrator.run("MOCK_LI_GREENHOUSE_001")
        retry_steps = [s for s in result.trace if s["step"] == "evaluator.retry"]
        self.assertEqual(len(retry_steps), 1)

    def test_trace_and_meterless_summary_are_populated(self):
        result = self.orchestrator.run("MOCK_LI_GREENHOUSE_001")
        self.assertGreaterEqual(len(result.trace), 6)
        self.assertGreater(result.meterless_summary["total_calls"], 0)
        self.assertIn("by_agent", result.meterless_summary)

    def test_run_result_round_trips_through_json(self):
        result = self.orchestrator.run("MOCK_LI_WORKDAY_002")
        json.dumps(result.to_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
