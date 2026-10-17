"""Reasoner abstraction used only by ExplainerAgent to turn validated,
structured findings into natural-language narrative. Every *fact* in a
finding is produced deterministically by the research/evaluator/risk agents
(see agents.py) -- the reasoner never invents facts, it only writes them up.

Two implementations:

- AnthropicReasoner: used when ANTHROPIC_API_KEY is set.
- HeuristicReasoner: deterministic template-based fallback, so the whole
  system runs end-to-end on a clean checkout with zero API keys.
"""

from __future__ import annotations

import os
from typing import Protocol


class Reasoner(Protocol):
    def narrate(self, system: str, user: str) -> str: ...


class AnthropicReasoner:
    def __init__(self) -> None:
        import anthropic  # local import: only required when a key is configured

        self._client = anthropic.Anthropic()
        self._model = os.environ.get("CAREER_FIT_MODEL", "claude-sonnet-5-5")

    def narrate(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip()


class HeuristicReasoner:
    """No external calls. Composes the final narrative from the same
    structured reasons the Explainer already assembled, so the output is
    still specific and evidence-cited -- just templated rather than
    generated."""

    def narrate(self, system: str, user: str) -> str:
        return user.strip()


def get_reasoner() -> Reasoner:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicReasoner()
        except Exception:
            return HeuristicReasoner()
    return HeuristicReasoner()
