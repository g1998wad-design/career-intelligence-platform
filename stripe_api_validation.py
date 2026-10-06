#!/usr/bin/env python3
"""
Wizard-of-oz validation for "self-maintaining APIs": can an LLM correctly
tell the difference between a Stripe changelog entry that actually breaks
a given piece of real-world code, vs. one that just shares similar keywords
but doesn't actually apply?

This is step 1 of the MVP -- no GitHub App, no automation. Just answering
the one question that makes or breaks the whole idea: is the LLM reliable
enough at this to be trusted with an auto-generated PR?

Usage:
    python stripe_api_validation.py

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY in .env next to this script (already present, shared
    with analyze_jobs.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import anthropic

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
REPO_PATH = Path("/tmp/nextjs-subscription-payments")
MODEL = "claude-sonnet-4-6"


def _load_api_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"ANTHROPIC_API_KEY not found in {ENV_PATH}")


_client = anthropic.Anthropic(api_key=_load_api_key())

# Real code pulled from vercel/nextjs-subscription-payments (a well-known,
# actively used Stripe-integrated SaaS starter).
CHECKOUT_CODE = (REPO_PATH / "utils/stripe/server.ts").read_text()
WEBHOOK_CODE = (REPO_PATH / "app/api/webhooks/route.ts").read_text()
CONFIG_CODE = (REPO_PATH / "utils/stripe/config.ts").read_text()
CODE_CONTEXT = f"""--- utils/stripe/config.ts ---
{CONFIG_CODE}

--- utils/stripe/server.ts ---
{CHECKOUT_CODE}

--- app/api/webhooks/route.ts ---
{WEBHOOK_CODE}
"""

# 4 real entries pulled from Stripe's own changelog (docs.stripe.com/changelog),
# chosen deliberately: 1 should actually affect this repo, 3 share keywords
# with this repo's code but do NOT actually apply. This tests whether the
# LLM can tell the difference, not just whether it can pattern-match text.
CANDIDATE_ENTRIES = [
    {
        "id": "billing-mode-default-flexible-ga",
        "expected": "AFFECTED",
        "description": (
            "Subscriptions you create through the API now default to flexible "
            "billing mode. To use classic, set the billing_mode.type parameter "
            "to classic."
        ),
    },
    {
        "id": "2022-08-01-6",
        "expected": "NOT AFFECTED",
        "description": (
            "Removes the subscription_data[coupon] parameter from the Create "
            "Checkout Session endpoint. Use the discounts parameter instead."
        ),
    },
    {
        "id": "2022-08-01-5",
        "expected": "NOT AFFECTED",
        "description": (
            "Removes the following parameters from the Create Checkout Session "
            "endpoint: line_items[amount], line_items[currency], line_items[name], "
            "line_items[description], line_items[images]. Use the price and "
            "price_data parameters instead."
        ),
    },
    {
        "id": "2025-03-13_cs_deprecate_singular_coupon_promotion_code",
        "expected": "NOT AFFECTED",
        "description": (
            "We're removing the singular coupon and promotion_code parameters "
            "in favor of the discounts parameter that supports applying "
            "multiple discounts."
        ),
    },
]

PROMPT_TEMPLATE = """You are reviewing whether a Stripe API changelog entry actually
breaks or changes the behavior of a specific codebase. Be precise -- only flag it as
affected if the code genuinely uses the parameter/field/behavior described. Sharing a
similar keyword (e.g. both mention "coupon") is NOT enough on its own.

CHANGELOG ENTRY:
{description}

CODEBASE:
{code}

Respond in this exact format:
VERDICT: AFFECTED or NOT AFFECTED
REASON: one or two sentences citing the exact line/field that is or isn't actually used
FIX: if affected, the exact code change needed. If not affected, write "N/A".
"""


def check_entry(entry: Dict[str, Any]) -> str:
    prompt = PROMPT_TEMPLATE.format(description=entry["description"], code=CODE_CONTEXT)
    response = _client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def main() -> None:
    results = []
    for entry in CANDIDATE_ENTRIES:
        print(f"\n{'=' * 70}\nEntry: {entry['id']}  (expected: {entry['expected']})\n{'=' * 70}")
        answer = check_entry(entry)
        print(answer)
        got_verdict = "AFFECTED" if "VERDICT: AFFECTED" in answer else "NOT AFFECTED"
        correct = got_verdict == entry["expected"]
        results.append({"id": entry["id"], "expected": entry["expected"], "got": got_verdict, "correct": correct})

    print(f"\n\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for r in results:
        mark = "PASS" if r["correct"] else "FAIL"
        print(f"[{mark}] {r['id']}: expected {r['expected']}, got {r['got']}")
    score = sum(r["correct"] for r in results)
    print(f"\n{score}/{len(results)} correct")


if __name__ == "__main__":
    main()
