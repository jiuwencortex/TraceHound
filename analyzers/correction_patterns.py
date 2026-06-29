# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Correction patterns analyzer.

Identifies components whose presence in context correlates with the user
issuing a follow-up correction.  Uses a "lift" metric:

    lift = correction_rate_when_component_present / baseline_correction_rate

A lift > 1.5 indicates the component is meaningfully associated with corrections.
"""

from __future__ import annotations

from dataclasses import dataclass

from jiuwenswarm.trajectories_analyzer.loader import TurnRecord

_DEFAULT_LIFT_THRESHOLD = 1.5
_MIN_TURNS_FOR_FLAG = 5


@dataclass(frozen=True)
class CorrectionPattern:
    component: str
    component_type: str    # "skill" | "memory" | "tool"
    correction_rate: float
    baseline_correction_rate: float
    lift: float
    n_turns_included: int
    n_corrected_turns: int

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "component_type": self.component_type,
            "correction_rate": round(self.correction_rate, 4),
            "baseline_correction_rate": round(self.baseline_correction_rate, 4),
            "lift": round(self.lift, 3),
            "n_turns_included": self.n_turns_included,
            "n_corrected_turns": self.n_corrected_turns,
        }


@dataclass(frozen=True)
class CorrectionPatternsResult:
    baseline_correction_rate: float
    total_corrected_turns: int
    total_turns: int
    high_lift_components: list[CorrectionPattern]   # sorted by lift descending

    def to_dict(self) -> dict:
        return {
            "baseline_correction_rate": round(self.baseline_correction_rate, 4),
            "total_corrected_turns": self.total_corrected_turns,
            "total_turns": self.total_turns,
            "high_lift_components": [p.to_dict() for p in self.high_lift_components],
        }


def _iter_components(turn: TurnRecord):
    for s in turn.skills:
        yield s, "skill"
    for m in turn.memory_sections:
        yield m, "memory"
    for t in turn.tools:
        yield t, "tool"


class CorrectionPatternsAnalyzer:
    """Find components strongly associated with follow-up corrections."""

    def __init__(
        self,
        turns: list[TurnRecord],
        lift_threshold: float = _DEFAULT_LIFT_THRESHOLD,
        min_turns: int = _MIN_TURNS_FOR_FLAG,
    ) -> None:
        self._turns = turns
        self._lift_threshold = lift_threshold
        self._min_turns = min_turns

    def analyze(self) -> CorrectionPatternsResult:
        n_total = len(self._turns)
        n_corrected_total = sum(1 for t in self._turns if t.follow_up_correction)
        baseline = n_corrected_total / n_total if n_total else 0.0

        # Per-component counts
        comp_total: dict[tuple[str, str], int] = {}
        comp_corrected: dict[tuple[str, str], int] = {}

        for turn in self._turns:
            for name, ctype in _iter_components(turn):
                key = (name, ctype)
                comp_total[key] = comp_total.get(key, 0) + 1
                if turn.follow_up_correction:
                    comp_corrected[key] = comp_corrected.get(key, 0) + 1

        patterns: list[CorrectionPattern] = []
        for key, n_included in comp_total.items():
            if n_included < self._min_turns:
                continue
            n_corr = comp_corrected.get(key, 0)
            rate = n_corr / n_included
            lift = rate / baseline if baseline > 0 else (1.0 if rate == 0 else float("inf"))
            if lift >= self._lift_threshold:
                name, ctype = key
                patterns.append(
                    CorrectionPattern(
                        component=name,
                        component_type=ctype,
                        correction_rate=rate,
                        baseline_correction_rate=baseline,
                        lift=lift,
                        n_turns_included=n_included,
                        n_corrected_turns=n_corr,
                    )
                )

        patterns.sort(key=lambda p: p.lift, reverse=True)

        return CorrectionPatternsResult(
            baseline_correction_rate=baseline,
            total_corrected_turns=n_corrected_total,
            total_turns=n_total,
            high_lift_components=patterns,
        )
