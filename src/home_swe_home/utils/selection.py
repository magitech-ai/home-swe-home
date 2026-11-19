"""Selection and composition of measured harness candidates.

A candidate is adopted only on a strict pass-rate win over the others; ties
and regressions keep the base harness. Composition takes each file from the
best-scoring candidate that actually changed it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Selection:
    """The chosen candidate name, or ``None`` when the base is kept."""

    winner: str | None
    reason: str


def select(scores: dict[str, float], *, base: str = "base") -> Selection:
    """Choose the strict highest scorer, defaulting to the base harness."""
    if not scores:
        return Selection(None, "no candidates were scored")
    best = max(scores.values())
    winners = sorted(name for name, score in scores.items() if score == best)
    if len(winners) != 1 or winners[0] == base:
        return Selection(None, f"no strict winner at {best:.2f}")
    return Selection(winners[0], f"highest pass rate {best:.2f}")


def compose(
    base: dict[str, str],
    candidates: dict[str, dict[str, str]],
    scores: dict[str, float],
) -> dict[str, str]:
    """Build a final tree from the best candidate that changed each file."""
    merged = dict(base)
    names = sorted({name for tree in candidates.values() for name in tree})
    for name in names:
        ranked = sorted(candidates, key=lambda key: (-scores.get(key, 0.0), key))
        for key in ranked:
            value = candidates[key].get(name)
            if value is not None and value != base.get(name):
                merged[name] = value
                break
    return merged
