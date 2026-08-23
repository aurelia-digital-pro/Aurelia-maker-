"""Narration-aware shot timing allocation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TimedShot:
    index: int
    duration: float


def _weight(shot: dict[str, Any], index: int, total: int) -> float:
    function = str(shot.get("shot_function") or shot.get("function") or "").lower()
    motion = str(shot.get("motion_intent") or shot.get("motion") or "").lower()
    value = 1.0
    if function in {"establishing", "climax", "resolution"}:
        value += 0.35
    if function in {"action", "transition"}:
        value += 0.10
    if motion in {"slow_drift", "reveal_wide", "pull_out"}:
        value += 0.10
    if index in {0, total - 1}:
        value += 0.10
    return value


def allocate(shots: Iterable[dict[str, Any]], narration_duration: float, minimum: float = 2.0, maximum: float = 15.0) -> list[float]:
    """Return bounded durations whose sum equals narration_duration when feasible."""
    items = list(shots)
    if not items:
        return []
    total = float(narration_duration)
    if total < len(items) * minimum:
        minimum = max(0.25, total / len(items))
    if total > len(items) * maximum:
        maximum = total / len(items)
    weights = [_weight(s, i, len(items)) for i, s in enumerate(items)]
    remaining = total - len(items) * minimum
    weight_sum = sum(weights) or float(len(items))
    durations = [minimum + remaining * (w / weight_sum) for w in weights]
    # Iteratively clip and redistribute surplus so the bounds remain true.
    for _ in range(len(items) + 2):
        low = [i for i, d in enumerate(durations) if d < minimum]
        high = [i for i, d in enumerate(durations) if d > maximum]
        if not low and not high:
            break
        surplus = 0.0
        locked = set()
        for i in low:
            surplus += minimum - durations[i]
            durations[i] = minimum
            locked.add(i)
        for i in high:
            surplus += durations[i] - maximum
            durations[i] = maximum
            locked.add(i)
        free = [i for i in range(len(items)) if i not in locked]
        if free and surplus:
            share = surplus / len(free)
            durations = [d + share if i in free else d for i, d in enumerate(durations)]
    correction = total - sum(durations)
    durations[-1] += correction
    if durations[-1] < minimum - 1e-6 or durations[-1] > maximum + 1e-6:
        durations = [total / len(items)] * len(items)
    rounded = [round(max(0.01, d), 6) for d in durations]
    rounded[-1] = round(rounded[-1] + (total - sum(rounded)), 6)
    return rounded


class ShotTimer:
    allocate = staticmethod(allocate)


__all__ = ["TimedShot", "ShotTimer", "allocate"]
