#!/usr/bin/env python3
"""
Self-Maintaining APIs -- automated version of the manual Stripe breaking-change
review validated across 3 real repos (nextjs-subscription-payments, papermark,
documenso): 2 real live bugs found, 0 false positives.

For a local clone of a repo that uses the Stripe SDK, this script:
 1. Finds the Stripe SDK's pinned `apiVersion` (if any) -- this matters because
    a pinned version keeps Stripe's old behavior forever, so a changelog entry
    that would otherwise be a live bug may just be a dormant future risk.
 2. Discovers every file that actually calls a Stripe SDK method
    (`new Stripe(`, `stripe.<x>.<y>(`, `stripe?.redirectToCheckout(`, etc).
 3. Fetches Stripe's public changelog and extracts entries flagged `breaking: true`.
 4. Filters to entries tagged with products this repo plausibly touches.
 5. Asks Claude, for each candidate entry, whether it actually affects this
    repo's code -- given the code AND the pinned API version.
 6. Writes a Markdown report of every AFFECTED verdict for human review.

This script never opens an issue or PR automatically. Posting is a deliberate,
separate, human-approved step (see stripe_api_validation.py / the manual
reviews this was built from).

Usage:
    python self_maintaining_api_watcher.py /path/to/repo/clone
    python self_maintaining_api_watcher.py /path/to/repo/clone --products checkout billing

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY in .env next to this script (same as analyze_jobs.py).
    NOTE: as of this writing the key tied to this .env has no credit balance --
    running this script will fail with a 400 "credit balance too low" error
    until that's topped up on console.anthropic.com. The code itself is
    otherwise complete and was shadow-tested by hand (see conversation log).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
REPORTS_DIR = BASE_DIR / "api_watcher_reports"

MODEL = "claude-sonnet-4-6"
CHANGELOG_URL = "https://docs.stripe.com/changelog"
DEFAULT_PRODUCTS = ["checkout", "billing"]

STRIPE_CALL_PATTERN = re.compile(
    r"new\s+Stripe\(|stripe\??\.\w+\.?\w*\(", re.IGNORECASE
)
API_VERSION_PATTERN = re.compile(r"apiVersion\s*:\s*['\"]([^'\"]+)['\"]")
CODE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_DIRS = {"node_modules", ".next", "dist", "build", ".git"}


def _load_api_key() -> str:
    if not ENV_PATH.exists():
        raise SystemExit(f"{ENV_PATH} not found -- add a line ANTHROPIC_API_KEY=sk-ant-...")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"ANTHROPIC_API_KEY not found in {ENV_PATH}")


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_load_api_key())


def discover_stripe_files(repo_path: Path) -> List[Path]:
    """Find every code file that makes an actual Stripe SDK call."""
    hits: List[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if STRIPE_CALL_PATTERN.search(text):
            hits.append(path)
    return hits


def discover_pinned_api_version(files: List[Path]) -> Optional[str]:
    """Look for an explicit apiVersion pin among the discovered Stripe files."""
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = API_VERSION_PATTERN.search(text)
        if match:
            return match.group(1)
    return None


def build_code_context(repo_path: Path, files: List[Path]) -> str:
    chunks = []
    for path in files:
        rel = path.relative_to(repo_path)
        chunks.append(f"--- {rel} ---\n{path.read_text(encoding='utf-8', errors='ignore')}")
    return "\n\n".join(chunks)


def fetch_breaking_entries() -> List[Dict[str, Any]]:
    """Fetch Stripe's changelog and extract every entry flagged breaking=true."""
    req = urllib.request.Request(CHANGELOG_URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")

    match = re.search(r"window\.__INITIAL_STATE__ = (\{.*?\});\s*\n", html, re.DOTALL)
    if not match:
        raise SystemExit("Could not find window.__INITIAL_STATE__ in changelog HTML -- page structure may have changed.")
    data = json.loads(match.group(1))

    entries: List[Dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if "breaking" in obj and "description" in obj:
                entries.append(obj)
                return
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data["article"]["content"])
    return [e for e in entries if e.get("breaking")]


def filter_relevant_entries(entries: List[Dict[str, Any]], products: List[str]) -> List[Dict[str, Any]]:
    return [e for e in entries if any(p in (e.get("products") or []) for p in products)]


PROMPT_TEMPLATE = """You are reviewing whether a Stripe API changelog entry actually
breaks or changes the behavior of a specific codebase. Be precise -- only flag it as
affected if the code genuinely uses the parameter/field/behavior described. Sharing a
similar keyword is NOT enough on its own.

This codebase pins its Stripe apiVersion to: {api_version}

Remember: if the codebase pins an apiVersion from BEFORE this change took effect,
Stripe continues honoring the old behavior for every call made with that pinned
version -- the change is a dormant future risk, not a live bug, unless/until the
pin is upgraded. Factor this into your verdict explicitly.

CHANGELOG ENTRY:
{description}

CODEBASE:
{code}

Respond in this exact format:
VERDICT: AFFECTED or NOT AFFECTED
SEVERITY: LIVE BUG, DORMANT (protected by version pin), or N/A
REASON: one or two sentences citing the exact line/field that is or isn't actually used
FIX: if affected, the exact code change needed. If not affected, write "N/A".
"""


def check_entry(client: anthropic.Anthropic, entry: Dict[str, Any], code: str, api_version: Optional[str]) -> str:
    prompt = PROMPT_TEMPLATE.format(
        api_version=api_version or "none (always runs on the account's current default version)",
        description=entry["description"],
        code=code,
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_path", type=Path, help="Path to a local clone of the target repo")
    parser.add_argument("--products", nargs="+", default=DEFAULT_PRODUCTS, help="Stripe product tags to filter changelog entries on")
    args = parser.parse_args()

    repo_path = args.repo_path.resolve()
    if not repo_path.is_dir():
        raise SystemExit(f"{repo_path} is not a directory")

    print(f"Scanning {repo_path} for Stripe call sites...")
    files = discover_stripe_files(repo_path)
    if not files:
        raise SystemExit("No Stripe SDK call sites found in this repo.")
    print(f"Found {len(files)} file(s) touching the Stripe SDK:")
    for f in files:
        print(f"  - {f.relative_to(repo_path)}")

    api_version = discover_pinned_api_version(files)
    print(f"\nPinned apiVersion: {api_version or '(none found -- runs on current default)'}")

    code_context = build_code_context(repo_path, files)

    print("\nFetching Stripe changelog...")
    entries = fetch_breaking_entries()
    relevant = filter_relevant_entries(entries, args.products)
    print(f"{len(entries)} breaking entries total, {len(relevant)} match products={args.products}")

    client = _get_client()
    affected: List[Dict[str, Any]] = []
    for i, entry in enumerate(relevant, 1):
        print(f"  [{i}/{len(relevant)}] checking {entry.get('id', entry.get('slug', '?'))}...")
        answer = check_entry(client, entry, code_context, api_version)
        if "VERDICT: AFFECTED" in answer:
            affected.append({"entry": entry, "answer": answer})

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{repo_path.name}_{date.today().isoformat()}.md"
    lines = [
        f"# Stripe breaking-change report: {repo_path.name}",
        f"Date: {date.today().isoformat()}",
        f"Pinned apiVersion: {api_version or 'none'}",
        f"Entries checked: {len(relevant)} (products={args.products})",
        f"Affected: {len(affected)}",
        "",
    ]
    for item in affected:
        entry = item["entry"]
        lines.append(f"## {entry.get('id', entry.get('slug', '?'))}")
        lines.append(f"**Changelog:** {entry['description']}")
        lines.append("")
        lines.append(item["answer"])
        lines.append("\n---\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDone. {len(affected)} affected entr{'y' if len(affected) == 1 else 'ies'} found.")
    print(f"Report written to {report_path} -- review before opening any issue/PR.")


if __name__ == "__main__":
    main()
