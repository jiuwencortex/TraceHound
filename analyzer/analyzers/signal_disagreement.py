# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Signal disagreement analyzer.

The thalamus quality formula blends explicit ratings, LLM judge scores, and
implicit signals (task_completed, follow_up_correction, conversation_length).
When explicit ratings are present they act as ground truth, but they may
disagree with what the implicit signals suggest.

Two disagreement types:
  - OVER-OPTIMISTIC formula: explicit_rating="negative" but formula >= threshold
    The formula thinks the turn was fine; the user says it wasn't.
  - OVER-PESSIMISTIC formula: explicit_rating="positive" but formula <= (1 - threshold)
    The formula is penalising a turn the user actually liked.

This analyzer:
  1. Measures the overall disagreement rate on turns that have explicit ratings.
  2. Identifies which components appear most often in disagreement turns so
     developers know which skills or tools are hardest to judge automatically.
  3. Surfaces the largest individual disagreements (biggest delta between
     formula score and ground-truth label).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord
from ..scorer import compute_quality

_DEFAULT_DISAGREEMENT_THRESHOLD = 0.35   # | formula_score - expected | > threshold → disagree
_MIN_COMPONENT_TURNS = 3                 # min turns for per-component disagreement rate


@dataclass(frozen=True)
class DisagreementTurn:
    turn_id: str
    explicit_rating: str          # "positive" | "negative"
    formula_score: float
    expected_score: float         # 1.0 for positive, 0.0 for negative
    delta: float                  # |formula_score - expected_score|
    disagreement_type: str        # "over_optimistic" | "over_pessimistic"
    components: list[str]         # all components in context (name only)

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "explicit_rating": self.explicit_rating,
            "formula_score": round(self.formula_score, 4),
            "expected_score": self.expected_score,
            "delta": round(self.delta, 4),
            "disagreement_type": self.disagreement_type,
            "components": self.components,
        }


@dataclass(frozen=True)
class ComponentDisagreementRate:
    name: str
    component_type: str
    n_turns_with_rating: int       # turns where this component was present AND explicit rating exists
    n_disagreement_turns: int
    disagreement_rate: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "n_turns_with_rating": self.n_turns_with_rating,
            "n_disagreement_turns": self.n_disagreement_turns,
            "disagreement_rate": round(self.disagreement_rate, 4),
        }


@dataclass(frozen=True)
class SignalDisagreementResult:
    n_rated_turns: int                # turns with explicit_rating set
    n_disagreements: int
    disagreement_rate: float
    n_over_optimistic: int            # formula too high vs user rating
    n_over_pessimistic: int           # formula too low vs user rating
    worst_disagreements: list[DisagreementTurn]   # top 10 by delta descending
    components_by_disagreement_rate: list[ComponentDisagreementRate]  # sorted desc

    def to_dict(self) -> dict:
        return {
            "n_rated_turns": self.n_rated_turns,
            "n_disagreements": self.n_disagreements,
            "disagreement_rate": round(self.disagreement_rate, 4),
            "n_over_optimistic": self.n_over_optimistic,
            "n_over_pessimistic": self.n_over_pessimistic,
            "worst_disagreements": [d.to_dict() for d in self.worst_disagreements],
            "components_by_disagreement_rate": [
                c.to_dict() for c in self.components_by_disagreement_rate
            ],
        }


def _all_component_names(turn: TurnRecord) -> list[str]:
    return list(turn.skills) + list(turn.memory_sections) + list(turn.tools)


def _iter_components(turn: TurnRecord):
    for s in turn.skills:
        yield s, "skill"
    for m in turn.memory_sections:
        yield m, "memory"
    for t in turn.tools:
        yield t, "tool"


class SignalDisagreementAnalyzer:
    """Find turns where the quality formula disagrees with the user's explicit rating."""

    def __init__(
        self,
        turns: list[TurnRecord],
        disagreement_threshold: float = _DEFAULT_DISAGREEMENT_THRESHOLD,
        min_component_turns: int = _MIN_COMPONENT_TURNS,
    ) -> None:
        self._turns = turns
        self._threshold = disagreement_threshold
        self._min_turns = min_component_turns

    def analyze(self) -> SignalDisagreementResult:
        rated_turns = [t for t in self._turns if t.explicit_rating is not None]
        n_rated = len(rated_turns)

        if not n_rated:
            return SignalDisagreementResult(
                n_rated_turns=0,
                n_disagreements=0,
                disagreement_rate=0.0,
                n_over_optimistic=0,
                n_over_pessimistic=0,
                worst_disagreements=[],
                components_by_disagreement_rate=[],
            )

        disagreements: list[DisagreementTurn] = []
        n_over_optimistic = 0
        n_over_pessimistic = 0

        # Per-component: rated turns and disagreement turns
        comp_rated: dict[tuple[str, str], int] = {}
        comp_disagreed: dict[tuple[str, str], int] = {}

        for turn in rated_turns:
            expected = 1.0 if turn.explicit_rating == "positive" else 0.0
            # Compute formula score ignoring explicit_rating: temporarily override so
            # we can see what the implicit formula would have said on its own.
            formula_score = _formula_without_explicit(turn)
            delta = abs(formula_score - expected)

            for name, ctype in _iter_components(turn):
                key = (name, ctype)
                comp_rated[key] = comp_rated.get(key, 0) + 1

            if delta >= self._threshold:
                if turn.explicit_rating == "negative" and formula_score >= 0.5:
                    dtype = "over_optimistic"
                    n_over_optimistic += 1
                else:
                    dtype = "over_pessimistic"
                    n_over_pessimistic += 1

                disagreements.append(
                    DisagreementTurn(
                        turn_id=turn.turn_id,
                        explicit_rating=turn.explicit_rating,
                        formula_score=formula_score,
                        expected_score=expected,
                        delta=delta,
                        disagreement_type=dtype,
                        components=_all_component_names(turn),
                    )
                )
                for name, ctype in _iter_components(turn):
                    key = (name, ctype)
                    comp_disagreed[key] = comp_disagreed.get(key, 0) + 1

        disagreements.sort(key=lambda d: d.delta, reverse=True)

        # Build per-component disagreement rate table
        comp_stats: list[ComponentDisagreementRate] = []
        for key, n_r in comp_rated.items():
            if n_r < self._min_turns:
                continue
            name, ctype = key
            n_d = comp_disagreed.get(key, 0)
            comp_stats.append(
                ComponentDisagreementRate(
                    name=name,
                    component_type=ctype,
                    n_turns_with_rating=n_r,
                    n_disagreement_turns=n_d,
                    disagreement_rate=n_d / n_r,
                )
            )
        comp_stats.sort(key=lambda c: c.disagreement_rate, reverse=True)

        return SignalDisagreementResult(
            n_rated_turns=n_rated,
            n_disagreements=len(disagreements),
            disagreement_rate=len(disagreements) / n_rated,
            n_over_optimistic=n_over_optimistic,
            n_over_pessimistic=n_over_pessimistic,
            worst_disagreements=disagreements[:10],
            components_by_disagreement_rate=comp_stats,
        )


def _formula_without_explicit(turn: TurnRecord) -> float:
    """Compute quality using implicit signals and LLM judge only (ignore explicit rating)."""
    if turn.llm_judge_score is not None:
        return max(0.0, min(1.0, float(turn.llm_judge_score)))
    score = 0.5
    if turn.task_completed:
        score += 0.2
    if turn.follow_up_correction:
        score -= 0.3
    score += max(0.0, 0.1 - 0.02 * turn.conversation_length)
    return max(0.0, min(1.0, score))
