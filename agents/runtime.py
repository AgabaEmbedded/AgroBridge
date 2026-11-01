"""Small runtime helpers shared by graph nodes (budgets, timings)."""

from __future__ import annotations

import time

from services.config import settings


def remaining(state: dict) -> float:
    deadline = state.get("deadline")
    if deadline is None:
        return settings.agent_timeout_seconds
    return deadline - time.monotonic()


def expired(state: dict, minimum: float = 0.6) -> bool:
    return remaining(state) <= minimum


def call_timeout(state: dict, share: float = 0.8) -> float:
    """Per-call timeout capped by both the agent limit and the workflow budget share."""
    budget = max(0.8, remaining(state) * share)
    return min(settings.agent_timeout_seconds, budget)


def timings_with(state: dict, **values: float) -> dict[str, float]:
    timings = dict(state.get("timings") or {})
    timings.update({key: round(value, 1) for key, value in values.items()})
    return timings
