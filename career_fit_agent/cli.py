"""CLI entry point.

    python -m career_fit_agent.cli --job-id MOCK_LI_GREENHOUSE_001
    python -m career_fit_agent.cli --list-jobs

Writes a full run trace to logs/runs/<job_id>_<run_id>.json and prints a
human-readable summary with citations and the Meterless usage breakdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from career_fit_agent.orchestrator import CareerFitOrchestrator
from career_fit_agent.zetaris_client import ZetarisFederatedStore

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "logs" / "runs"


def _print_human(result) -> None:
    print(f"\n=== Career Fit Explainer -- {result.job_id} (run {result.run_id}) ===")
    print(f"Verdict: {result.verdict}  (confidence {result.confidence})")
    print(f"\n{result.narrative}\n")
    print("Evidence:")
    for r in result.reasons:
        print(f"  - {r['claim']}")
        for c in r["citations"]:
            print(f"      [{c['source']}: {c['locator']}]")
    if result.missing_skills:
        print(f"\nMissing skills: {', '.join(result.missing_skills)}")
    if result.risk_notes:
        print("\nRisk notes:")
        for n in result.risk_notes:
            print(f"  - ({n['severity']}) {n['message']}" + (f" -> {n['mitigation']}" if n["mitigation"] else ""))
    print(f"\nZetaris: {result.zetaris_status}")
    print(f"Meterless: {result.meterless_summary}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Career Fit Explainer agent")
    parser.add_argument("--job-id", help="job_id from mock_scenarios/jobs.json")
    parser.add_argument("--list-jobs", action="store_true", help="list available job_ids and exit")
    parser.add_argument("--out-dir", default=str(RUNS_DIR))
    args = parser.parse_args(argv)

    store = ZetarisFederatedStore()
    if args.list_jobs or not args.job_id:
        rows = store.query("SELECT job_id, title, company FROM jobs")
        for r in rows:
            print(f"{r['job_id']}: {r['title']} @ {r['company']}")
        if not args.job_id:
            return 0

    orchestrator = CareerFitOrchestrator(store=store)
    result = orchestrator.run(args.job_id)
    _print_human(result)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.job_id}_{result.run_id}.json"
    out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"\nFull trace written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
