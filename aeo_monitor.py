"""
AEO (Answer Engine Optimization) monitor.

Tracks how a defined target (a brand, product, or piece of content) shows up
in answers from AI answer engines -- Google AI Overviews, ChatGPT, Perplexity,
Claude -- for a fixed set of queries, over time. This is the "search
intelligence" analogue of classic rank tracking, except the thing being
tracked is presence/position inside a generated answer and which sources get
cited, not a blue-link SERP position.

Two ways results get into the DB:
  1. `run-claude` -- queries the Claude API directly (the only LLM API key
     this project has -- see .env) and auto-scores whether the target was
     mentioned. Kept to a small, fixed query set and the cheapest model
     (Haiku) so this stays effectively free to run occasionally.
  2. `record` -- most answer engines (Google AI Overviews, ChatGPT,
     Perplexity) don't have a public, ToS-compliant API for this kind of
     query, and scraping them isn't something this project does. Instead,
     `record` lets you paste in what you saw when you checked by hand, so
     manual and automated checks land in the same table and the same report.

Usage:
    python3 aeo_monitor.py run-claude --target "Autodesk" --query-set default
    python3 aeo_monitor.py record --engine chatgpt --query "..." \
        --target "Autodesk" --mentioned yes --position 2 \
        --sources "autodesk.com,g2.com" --notes "cited in 2nd paragraph"
    python3 aeo_monitor.py report
    python3 aeo_monitor.py queries   # list the built-in query set
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "aeo_monitor.db"
ENV_PATH = BASE_DIR / ".env"

MODEL = "claude-haiku-4-5-20251001"

# Small, fixed query set so `run-claude` cost stays predictable. These are
# genuine "answer engine" style questions -- the kind a buyer types into
# ChatGPT/Google AI Overview/Perplexity instead of a classic keyword search --
# in the search/AI-tooling space this project already lives in.
DEFAULT_QUERIES = [
    "What are the best AI tools for tracking job applications in 2026?",
    "How can I use AI to tailor my resume to a specific job posting?",
    "What is answer engine optimization and why does it matter for search teams?",
    "How do companies measure visibility in AI-generated search answers?",
    "What's the difference between traditional SEO and AEO?",
]


def _load_api_key() -> str:
    if not ENV_PATH.exists():
        raise SystemExit(f"{ENV_PATH} not found -- add a line ANTHROPIC_API_KEY=sk-ant-...")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"ANTHROPIC_API_KEY not found in {ENV_PATH}")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            query TEXT NOT NULL,
            target TEXT NOT NULL,
            response_text TEXT,
            target_mentioned INTEGER,
            target_position INTEGER,
            sources_cited TEXT,
            notes TEXT,
            checked_at TEXT NOT NULL
        )
        """
    )
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _score_mention(response_text: str, target: str) -> tuple[bool, Optional[int]]:
    """Cheap heuristic scoring: does the target string appear, and roughly
    how early (in sentences) does it show up. Good enough for a directional
    'share of answer' signal without a second LLM call per check."""
    lowered = response_text.lower()
    target_lower = target.lower()
    if target_lower not in lowered:
        return False, None
    sentences = response_text.replace("\n", " ").split(". ")
    for idx, sentence in enumerate(sentences):
        if target_lower in sentence.lower():
            return True, idx + 1
    return True, None


def cmd_run_claude(args: argparse.Namespace) -> None:
    import anthropic

    client = anthropic.Anthropic(api_key=_load_api_key())
    queries = DEFAULT_QUERIES if args.query_set == "default" else [args.query]
    con = _connect()
    for query in queries:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": query}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        mentioned, position = _score_mention(text, args.target)
        con.execute(
            """INSERT INTO checks
               (engine, query, target, response_text, target_mentioned, target_position,
                sources_cited, notes, checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("claude", query, args.target, text, int(mentioned), position, None, None, _now()),
        )
        status = f"mentioned (sentence {position})" if mentioned else "not mentioned"
        print(f"[claude] {query!r} -> {status}")
    con.commit()
    con.close()


def cmd_record(args: argparse.Namespace) -> None:
    con = _connect()
    mentioned = args.mentioned.lower() in ("yes", "y", "true", "1")
    sources = args.sources or None
    con.execute(
        """INSERT INTO checks
           (engine, query, target, response_text, target_mentioned, target_position,
            sources_cited, notes, checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            args.engine,
            args.query,
            args.target,
            args.response_text,
            int(mentioned),
            args.position,
            sources,
            args.notes,
            _now(),
        ),
    )
    con.commit()
    con.close()
    print(f"[{args.engine}] recorded check for {args.query!r} (mentioned={mentioned})")


def cmd_report(args: argparse.Namespace) -> None:
    con = _connect()
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT engine, query, target, target_mentioned, target_position, checked_at "
        "FROM checks ORDER BY checked_at DESC"
    ).fetchall()
    con.close()
    if not rows:
        print("No checks recorded yet. Run `run-claude` or `record` first.")
        return

    by_engine: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_engine.setdefault(row["engine"], []).append(row)

    print(f"AEO monitor report -- {len(rows)} checks across {len(by_engine)} engine(s)\n")
    for engine, engine_rows in sorted(by_engine.items()):
        mentioned = sum(r["target_mentioned"] for r in engine_rows)
        total = len(engine_rows)
        share = mentioned / total * 100
        print(f"{engine}: {mentioned}/{total} checks mentioned target ({share:.0f}% share of answer)")
        for r in engine_rows:
            flag = "YES" if r["target_mentioned"] else "no "
            pos = f" (sentence {r['target_position']})" if r["target_position"] else ""
            print(f"  [{flag}]{pos} {r['query'][:70]}  -- {r['checked_at']}")
        print()


def cmd_queries(args: argparse.Namespace) -> None:
    for q in DEFAULT_QUERIES:
        print(f"- {q}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run-claude", help="Query Claude directly and auto-score target mentions")
    p_run.add_argument("--target", required=True, help="Brand/topic/string to look for in the answer")
    p_run.add_argument("--query-set", choices=["default", "single"], default="default")
    p_run.add_argument("--query", help="Required if --query-set single")
    p_run.set_defaults(func=cmd_run_claude)

    p_rec = sub.add_parser("record", help="Manually record a result from an engine without an API (ChatGPT, Google AI Overview, Perplexity, etc.)")
    p_rec.add_argument("--engine", required=True)
    p_rec.add_argument("--query", required=True)
    p_rec.add_argument("--target", required=True)
    p_rec.add_argument("--mentioned", required=True, choices=["yes", "no"])
    p_rec.add_argument("--position", type=int, default=None, help="Roughly where the target appeared (sentence/paragraph number)")
    p_rec.add_argument("--sources", default=None, help="Comma-separated list of domains/sources the answer cited")
    p_rec.add_argument("--response-text", dest="response_text", default=None)
    p_rec.add_argument("--notes", default=None)
    p_rec.set_defaults(func=cmd_record)

    p_report = sub.add_parser("report", help="Print a share-of-answer summary across all recorded checks")
    p_report.set_defaults(func=cmd_report)

    p_queries = sub.add_parser("queries", help="List the built-in default query set")
    p_queries.set_defaults(func=cmd_queries)

    args = parser.parse_args()
    if args.command == "run-claude" and args.query_set == "single" and not args.query:
        parser.error("--query-set single requires --query")
    args.func(args)


if __name__ == "__main__":
    main()
