"""Meterless integration: zero-instrumentation usage/cost metering.

Every agent step in the orchestrator runs inside `meter.step(agent_name)`.
That's the only line of metering code anywhere in this package -- no agent
hand-rolls timers or token counters. The meter derives a usage event (wall
time, a token-proxy size, and which data sources it touched) from the step's
input/output automatically and:

- always appends it to a local JSONL trace (so every run is auditable even
  offline), and
- forwards it to Meterless's usage-ingest endpoint when METERLESS_API_KEY is
  configured, so cost/usage shows up in Meterless without the agent code
  caring whether that endpoint exists.

A Meterless outage or missing credentials never fails the underlying agent
run -- metering is observability, not a dependency the business logic should
break on.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = BASE_DIR / "logs" / "meterless_usage.jsonl"


@dataclass
class UsageEvent:
    agent: str
    run_id: str
    started_at: float
    duration_ms: float
    input_units: int
    output_units: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 2),
            "input_units": self.input_units,
            "output_units": self.output_units,
        }


class MeterlessMeter:
    def __init__(self, run_id: str, log_path: Path = DEFAULT_LOG_PATH) -> None:
        self.run_id = run_id
        self.log_path = log_path
        self.endpoint = os.environ.get("METERLESS_ENDPOINT", "https://api.meterless.dev")
        self.api_key = os.environ.get("METERLESS_API_KEY")
        self.events: list[UsageEvent] = []
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def step(self, agent_name: str, input_payload: Any = None) -> Iterator[dict[str, Any]]:
        started = time.monotonic()
        started_at = time.time()
        output_holder: dict[str, Any] = {}
        try:
            yield output_holder
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            event = UsageEvent(
                agent=agent_name,
                run_id=self.run_id,
                started_at=started_at,
                duration_ms=duration_ms,
                input_units=_size_of(input_payload),
                output_units=_size_of(output_holder.get("result")),
            )
            self._record(event)

    def _record(self, event: UsageEvent) -> None:
        self.events.append(event)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")
        if self.api_key:
            try:
                requests.post(
                    f"{self.endpoint}/v1/usage",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=event.to_dict(),
                    timeout=5,
                )
            except requests.RequestException:
                pass  # metering never blocks or fails the underlying run

    def summary(self) -> dict[str, Any]:
        by_agent: dict[str, dict[str, float]] = {}
        for ev in self.events:
            bucket = by_agent.setdefault(ev.agent, {"calls": 0, "duration_ms": 0.0, "units": 0})
            bucket["calls"] += 1
            bucket["duration_ms"] += ev.duration_ms
            bucket["units"] += ev.input_units + ev.output_units
        return {
            "run_id": self.run_id,
            "total_calls": len(self.events),
            "total_duration_ms": round(sum(e.duration_ms for e in self.events), 2),
            "by_agent": by_agent,
            "metering_mode": "live" if self.api_key else "local_only",
        }


def _size_of(payload: Any) -> int:
    if payload is None:
        return 0
    try:
        return len(json.dumps(payload, default=str))
    except TypeError:
        return len(str(payload))
