#!/usr/bin/env python3
"""Print recent model token usage and estimated API spend by day/task."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "job_fetcher.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Number of recent days to include")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be a positive integer")
    if not DB_PATH.exists():
        parser.error(f"Database not found: {DB_PATH}")

    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as con:
        try:
            rows = con.execute("""
                SELECT date(recorded_at) AS day, operation, model,
                       COUNT(*) AS calls,
                       SUM(input_tokens) AS input_tokens,
                       SUM(output_tokens) AS output_tokens,
                       SUM(cache_write_tokens) AS cache_write_tokens,
                       SUM(cache_read_tokens) AS cache_read_tokens,
                       SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM api_usage
                WHERE date(recorded_at) >= date('now', ?)
                GROUP BY day, operation, model
                ORDER BY day DESC, estimated_cost_usd DESC
            """, (f"-{args.days - 1} days",)).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                print("No API usage has been recorded yet. Run the pipeline once first.")
                return 0
            raise

    if not rows:
        print(f"No API calls recorded in the last {args.days} day(s).")
        return 0

    print("Day         Operation          Model                         Calls   Input     Output    Cache read  Est. USD")
    print("-" * 112)
    total = 0.0
    for day, operation, model, calls, input_tokens, output_tokens, cache_write, cache_read, cost in rows:
        total += cost or 0.0
        print(f"{day:<11} {operation:<18} {model:<29} {calls:>5} "
              f"{input_tokens or 0:>9,} {output_tokens or 0:>9,} "
              f"{cache_read or 0:>11,} ${cost or 0:>8.4f}")
    print("-" * 112)
    print(f"Estimated total for displayed rows: ${total:.4f}")
    print("Estimates use the model rates in analyze_jobs.py; provider billing is authoritative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
