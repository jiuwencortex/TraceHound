# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Quality trends analyzer.

Aggregates quality scores per week and detects whether quality is improving,
degrading, or flat using a simple linear regression slope.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord

_TREND_SLOPE_THRESHOLD = 0.02   # absolute slope per week; above/below = improving/degrading
_MIN_WEEKS_FOR_TREND = 3        # need at least this many data points for trend detection


@dataclass(frozen=True)
class WeeklyQualitySummary:
    week_tag: str
    n_turns: int
    mean_quality: float
    n_explicit_positive: int
    n_explicit_negative: int
    n_task_completed: int
    n_follow_up_corrections: int

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "n_turns": self.n_turns,
            "mean_quality": round(self.mean_quality, 4),
            "n_explicit_positive": self.n_explicit_positive,
            "n_explicit_negative": self.n_explicit_negative,
            "n_task_completed": self.n_task_completed,
            "n_follow_up_corrections": self.n_follow_up_corrections,
        }


@dataclass(frozen=True)
class QualityTrendsResult:
    weeks: list[WeeklyQualitySummary]
    trend_direction: str   # "improving" | "degrading" | "flat" | "insufficient_data"
    best_week: str | None
    worst_week: str | None
    overall_mean: float

    def to_dict(self) -> dict:
        return {
            "weeks": [w.to_dict() for w in self.weeks],
            "trend_direction": self.trend_direction,
            "best_week": self.best_week,
            "worst_week": self.worst_week,
            "overall_mean": round(self.overall_mean, 4),
        }


def _linear_slope(ys: list[float]) -> float:
    """Return the slope of a simple OLS regression of ys against x=0,1,2,..."""
    n = len(ys)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(ys) / n
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(ys))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    return num / denom if denom else 0.0


class QualityTrendsAnalyzer:
    """Compute per-week quality statistics and detect trend direction."""

    def __init__(self, turns: list[TurnRecord], qualities: list[float]) -> None:
        self._turns = turns
        self._qualities = qualities

    def analyze(self) -> QualityTrendsResult:
        # Group by week_tag (preserve insertion order = chronological because turns
        # are sorted ascending by timestamp)
        week_order: list[str] = []
        week_data: dict[str, dict] = {}

        for turn, quality in zip(self._turns, self._qualities):
            wt = turn.week_tag
            if wt not in week_data:
                week_order.append(wt)
                week_data[wt] = {
                    "qualities": [],
                    "pos": 0,
                    "neg": 0,
                    "completed": 0,
                    "corrections": 0,
                }
            d = week_data[wt]
            d["qualities"].append(quality)
            if turn.explicit_rating == "positive":
                d["pos"] += 1
            elif turn.explicit_rating == "negative":
                d["neg"] += 1
            if turn.task_completed:
                d["completed"] += 1
            if turn.follow_up_correction:
                d["corrections"] += 1

        summaries: list[WeeklyQualitySummary] = []
        for wt in week_order:
            d = week_data[wt]
            qs = d["qualities"]
            summaries.append(
                WeeklyQualitySummary(
                    week_tag=wt,
                    n_turns=len(qs),
                    mean_quality=sum(qs) / len(qs),
                    n_explicit_positive=d["pos"],
                    n_explicit_negative=d["neg"],
                    n_task_completed=d["completed"],
                    n_follow_up_corrections=d["corrections"],
                )
            )

        if not summaries:
            return QualityTrendsResult(
                weeks=[],
                trend_direction="insufficient_data",
                best_week=None,
                worst_week=None,
                overall_mean=0.0,
            )

        best = max(summaries, key=lambda s: s.mean_quality)
        worst = min(summaries, key=lambda s: s.mean_quality)

        all_q = self._qualities
        overall_mean = sum(all_q) / len(all_q) if all_q else 0.0

        # Trend detection
        if len(summaries) < _MIN_WEEKS_FOR_TREND:
            trend = "insufficient_data"
        else:
            slope = _linear_slope([s.mean_quality for s in summaries])
            if slope > _TREND_SLOPE_THRESHOLD:
                trend = "improving"
            elif slope < -_TREND_SLOPE_THRESHOLD:
                trend = "degrading"
            else:
                trend = "flat"

        return QualityTrendsResult(
            weeks=summaries,
            trend_direction=trend,
            best_week=best.week_tag,
            worst_week=worst.week_tag,
            overall_mean=overall_mean,
        )
