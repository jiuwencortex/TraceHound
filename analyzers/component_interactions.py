# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Component interaction analyzer.

Per-component analysis cannot detect combination effects.  A skill that
performs fine in isolation may drag quality down whenever it appears alongside
a specific tool or memory section.

This analyzer examines every pair of components that co-occur in at least
``min_cooccurrence`` turns and computes:

    expected_quality = (mean_quality_of_A + mean_quality_of_B) / 2
    actual_quality   = mean quality of turns where BOTH A and B are present
    interaction_delta = actual - expected

A strongly negative delta indicates a **toxic combination**: the two
components interact badly and their joint presence causes worse outcomes
than either would alone.

A strongly positive delta indicates a **synergistic combination**: the two
components amplify each other.

Results are split into:
  - toxic_pairs:      interaction_delta < -_TOXIC_THRESHOLD
  - synergistic_pairs: interaction_delta > +_SYNERGY_THRESHOLD
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord

_DEFAULT_TOXIC_THRESHOLD = 0.10
_DEFAULT_SYNERGY_THRESHOLD = 0.10
_DEFAULT_MIN_COOCCURRENCE = 5


@dataclass(frozen=True)
class ComponentPair:
    component_a: str
    type_a: str
    component_b: str
    type_b: str
    n_cooccurrence: int
    mean_quality_a: float          # mean quality when A is present (regardless of B)
    mean_quality_b: float          # mean quality when B is present (regardless of A)
    expected_quality: float        # (mean_a + mean_b) / 2
    actual_quality: float          # mean quality when both are present
    interaction_delta: float       # actual - expected

    def to_dict(self) -> dict:
        return {
            "component_a": self.component_a,
            "type_a": self.type_a,
            "component_b": self.component_b,
            "type_b": self.type_b,
            "n_cooccurrence": self.n_cooccurrence,
            "mean_quality_a": round(self.mean_quality_a, 4),
            "mean_quality_b": round(self.mean_quality_b, 4),
            "expected_quality": round(self.expected_quality, 4),
            "actual_quality": round(self.actual_quality, 4),
            "interaction_delta": round(self.interaction_delta, 4),
        }


@dataclass(frozen=True)
class ComponentInteractionsResult:
    n_pairs_evaluated: int
    toxic_pairs: list[ComponentPair]       # sorted by interaction_delta ascending (worst first)
    synergistic_pairs: list[ComponentPair] # sorted by interaction_delta descending (best first)

    def to_dict(self) -> dict:
        return {
            "n_pairs_evaluated": self.n_pairs_evaluated,
            "toxic_pairs": [p.to_dict() for p in self.toxic_pairs],
            "synergistic_pairs": [p.to_dict() for p in self.synergistic_pairs],
        }


def _iter_components(turn: TurnRecord) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for s in turn.skills:
        result.append((s, "skill"))
    for m in turn.memory_sections:
        result.append((m, "memory"))
    for t in turn.tools:
        result.append((t, "tool"))
    return result


class ComponentInteractionsAnalyzer:
    """Find toxic and synergistic component pairs via pairwise quality delta analysis."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
        min_cooccurrence: int = _DEFAULT_MIN_COOCCURRENCE,
        toxic_threshold: float = _DEFAULT_TOXIC_THRESHOLD,
        synergy_threshold: float = _DEFAULT_SYNERGY_THRESHOLD,
    ) -> None:
        self._turns = turns
        self._qualities = qualities
        self._min_cooccurrence = min_cooccurrence
        self._toxic_threshold = toxic_threshold
        self._synergy_threshold = synergy_threshold

    def analyze(self) -> ComponentInteractionsResult:
        if not self._turns:
            return ComponentInteractionsResult(
                n_pairs_evaluated=0,
                toxic_pairs=[],
                synergistic_pairs=[],
            )

        # Step 1: per-component individual quality means
        comp_qualities: dict[tuple[str, str], list[float]] = {}
        for turn, quality in zip(self._turns, self._qualities):
            for name, ctype in _iter_components(turn):
                comp_qualities.setdefault((name, ctype), []).append(quality)

        comp_mean: dict[tuple[str, str], float] = {
            key: sum(qs) / len(qs) for key, qs in comp_qualities.items()
        }

        # Step 2: pairwise co-occurrence qualities
        # Use a canonical ordering (key_a < key_b lexicographically) to avoid duplicates
        pair_qualities: dict[tuple, list[float]] = {}

        for turn, quality in zip(self._turns, self._qualities):
            comps = _iter_components(turn)
            if len(comps) < 2:
                continue
            # Generate all unique pairs within this turn's context
            seen: set[tuple] = set()
            for i in range(len(comps)):
                for j in range(i + 1, len(comps)):
                    a = comps[i]   # (name, type)
                    b = comps[j]
                    # Canonical ordering
                    pair_key = (min(a, b), max(a, b))
                    if pair_key not in seen:
                        seen.add(pair_key)
                        pair_qualities.setdefault(pair_key, []).append(quality)

        # Step 3: compute interaction delta for pairs with enough co-occurrences
        toxic_pairs: list[ComponentPair] = []
        synergistic_pairs: list[ComponentPair] = []
        n_evaluated = 0

        for (a, b), qs in pair_qualities.items():
            if len(qs) < self._min_cooccurrence:
                continue

            n_evaluated += 1
            name_a, type_a = a
            name_b, type_b = b
            mean_a = comp_mean.get(a, 0.5)
            mean_b = comp_mean.get(b, 0.5)
            expected = (mean_a + mean_b) / 2.0
            actual = sum(qs) / len(qs)
            delta = actual - expected

            pair = ComponentPair(
                component_a=name_a,
                type_a=type_a,
                component_b=name_b,
                type_b=type_b,
                n_cooccurrence=len(qs),
                mean_quality_a=mean_a,
                mean_quality_b=mean_b,
                expected_quality=expected,
                actual_quality=actual,
                interaction_delta=delta,
            )

            if delta < -self._toxic_threshold:
                toxic_pairs.append(pair)
            elif delta > self._synergy_threshold:
                synergistic_pairs.append(pair)

        toxic_pairs.sort(key=lambda p: p.interaction_delta)            # worst first
        synergistic_pairs.sort(key=lambda p: p.interaction_delta, reverse=True)  # best first

        return ComponentInteractionsResult(
            n_pairs_evaluated=n_evaluated,
            toxic_pairs=toxic_pairs,
            synergistic_pairs=synergistic_pairs,
        )
