# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Exploration analysis.

Compares quality of turns that used off-policy exploration vs. normal turns.
Also identifies which exploration additions (skills or tools added randomly)
were associated with positive or negative quality deltas.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord

_MIN_EXPLORATION_TURNS = 3   # need at least this many to produce per-component stats


@dataclass(frozen=True)
class ExplorationAdditionStats:
    name: str
    component_type: str    # "skill" | "memory" | "tool"
    n_times_explored: int
    mean_quality_delta: float  # vs. global mean; positive = better than average

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "n_times_explored": self.n_times_explored,
            "mean_quality_delta": round(self.mean_quality_delta, 4),
        }


@dataclass(frozen=True)
class ExplorationAnalysisResult:
    n_explored: int
    n_normal: int
    mean_quality_explored: float
    mean_quality_normal: float
    quality_delta: float          # explored - normal; positive = exploration is net beneficial
    promising_additions: list[ExplorationAdditionStats]   # mean_quality_delta > 0
    harmful_additions: list[ExplorationAdditionStats]     # mean_quality_delta < 0

    def to_dict(self) -> dict:
        return {
            "n_explored": self.n_explored,
            "n_normal": self.n_normal,
            "mean_quality_explored": round(self.mean_quality_explored, 4),
            "mean_quality_normal": round(self.mean_quality_normal, 4),
            "quality_delta": round(self.quality_delta, 4),
            "promising_additions": [a.to_dict() for a in self.promising_additions],
            "harmful_additions": [a.to_dict() for a in self.harmful_additions],
        }


class ExplorationAnalyzer:
    """Analyze whether off-policy exploration is beneficial."""

    def __init__(self, turns: list[TurnRecord], qualities: list[float]) -> None:
        self._turns = turns
        self._qualities = qualities

    def analyze(self) -> ExplorationAnalysisResult:
        global_mean = sum(self._qualities) / len(self._qualities) if self._qualities else 0.5

        explored_q: list[float] = []
        normal_q: list[float] = []

        # Per addition: (name, type) → list of quality deltas
        addition_deltas: dict[tuple[str, str], list[float]] = {}

        for turn, quality in zip(self._turns, self._qualities):
            if turn.explored:
                explored_q.append(quality)
                delta = quality - global_mean
                additions = turn.exploration_additions
                for name in additions.get("skills", []):
                    key = (name, "skill")
                    addition_deltas.setdefault(key, []).append(delta)
                for name in additions.get("memory", []):
                    key = (name, "memory")
                    addition_deltas.setdefault(key, []).append(delta)
                for name in additions.get("tools", []):
                    key = (name, "tool")
                    addition_deltas.setdefault(key, []).append(delta)
            else:
                normal_q.append(quality)

        mean_explored = sum(explored_q) / len(explored_q) if explored_q else 0.0
        mean_normal = sum(normal_q) / len(normal_q) if normal_q else 0.0
        quality_delta = mean_explored - mean_normal if (explored_q and normal_q) else 0.0

        promising: list[ExplorationAdditionStats] = []
        harmful: list[ExplorationAdditionStats] = []

        for (name, ctype), deltas in addition_deltas.items():
            if len(deltas) < _MIN_EXPLORATION_TURNS:
                continue
            mean_delta = sum(deltas) / len(deltas)
            stat = ExplorationAdditionStats(
                name=name,
                component_type=ctype,
                n_times_explored=len(deltas),
                mean_quality_delta=mean_delta,
            )
            if mean_delta > 0:
                promising.append(stat)
            else:
                harmful.append(stat)

        promising.sort(key=lambda s: s.mean_quality_delta, reverse=True)
        harmful.sort(key=lambda s: s.mean_quality_delta)

        return ExplorationAnalysisResult(
            n_explored=len(explored_q),
            n_normal=len(normal_q),
            mean_quality_explored=mean_explored,
            mean_quality_normal=mean_normal,
            quality_delta=quality_delta,
            promising_additions=promising,
            harmful_additions=harmful,
        )
