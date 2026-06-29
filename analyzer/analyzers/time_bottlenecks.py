# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Time bottleneck analyzer.

Uses per-turn ``duration_seconds`` (populated by the loader from jiuwenswarm
session message timestamps) and per-tool-call timing records to surface where
wall-clock time is being spent.

Produces:
  - Turn duration distribution (min / median / p90 / max / mean)
  - Slowest turns with their status, tools, and quality
  - Per-tool turn-duration correlation: which tools are found in the slowest turns
  - Per-tool call timing: how long each individual tool call takes on average
    (only populated when ``tool_call_timings`` carries matched call/result pairs)
  - Quality vs speed: does higher latency correlate with better or worse outcomes?
  - Hourly activity distribution: when is the agent being used most?
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..loader import ToolCallTiming, TurnRecord

_SLOW_TURN_PERCENTILE = 75   # turns above this percentile are "slow"
_MIN_TOOL_TURNS = 2           # minimum turns for per-tool correlation to be reported
_MIN_TIMED_CALLS = 2          # minimum matched calls for per-tool call timing


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - idx + lo) + sorted_vals[hi] * (idx - lo)


@dataclass(frozen=True)
class TurnTimingRecord:
    """Summary of a single turn's timing."""

    turn_id: str
    duration_seconds: float
    quality: float
    n_messages: int
    tools_called: list[str]
    task_completed: bool
    has_error: bool

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "duration_seconds": round(self.duration_seconds, 2),
            "quality": round(self.quality, 4),
            "n_messages": self.n_messages,
            "tools_called": self.tools_called,
            "task_completed": self.task_completed,
            "has_error": self.has_error,
        }


@dataclass(frozen=True)
class ToolTurnCorrelation:
    """How a tool's presence correlates with turn duration."""

    tool_name: str
    n_turns: int                   # turns where this tool was called
    mean_turn_duration_s: float    # mean wall-clock time of those turns
    global_mean_duration_s: float
    duration_ratio: float          # mean_turn_duration / global_mean; >1 = turns with this tool are slower

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "n_turns": self.n_turns,
            "mean_turn_duration_s": round(self.mean_turn_duration_s, 2),
            "global_mean_duration_s": round(self.global_mean_duration_s, 2),
            "duration_ratio": round(self.duration_ratio, 3),
        }


@dataclass(frozen=True)
class ToolCallTimingSummary:
    """Aggregate latency statistics for individual calls to one tool."""

    tool_name: str
    n_timed_calls: int             # calls where we have a matched result timestamp
    mean_duration_s: float
    median_duration_s: float
    p90_duration_s: float
    max_duration_s: float
    total_time_s: float

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "n_timed_calls": self.n_timed_calls,
            "mean_duration_s": round(self.mean_duration_s, 2),
            "median_duration_s": round(self.median_duration_s, 2),
            "p90_duration_s": round(self.p90_duration_s, 2),
            "max_duration_s": round(self.max_duration_s, 2),
            "total_time_s": round(self.total_time_s, 2),
        }


@dataclass(frozen=True)
class HourlyBucket:
    hour: int         # 0–23 UTC
    n_turns: int
    mean_quality: float
    mean_duration_s: float
    error_rate: float

    def to_dict(self) -> dict:
        return {
            "hour": self.hour,
            "n_turns": self.n_turns,
            "mean_quality": round(self.mean_quality, 4),
            "mean_duration_s": round(self.mean_duration_s, 2),
            "error_rate": round(self.error_rate, 4),
        }


@dataclass(frozen=True)
class TimeBottlenecksResult:
    """Complete time bottleneck analysis."""

    n_turns_with_timing: int        # turns where duration_seconds > 0
    n_turns_total: int
    min_duration_s: float
    median_duration_s: float
    mean_duration_s: float
    p90_duration_s: float
    max_duration_s: float
    total_time_s: float

    # Slow vs fast quality
    slow_quartile_mean_quality: float   # mean quality of top-25% slowest turns
    fast_half_mean_quality: float       # mean quality of bottom-50% fastest turns
    speed_quality_verdict: str          # "slower_is_better" | "slower_is_worse" | "no_correlation"

    # Slowest turns for inspection
    slowest_turns: list[TurnTimingRecord]

    # Per-tool turn-duration correlation (all tools, sorted by duration_ratio desc)
    tool_turn_correlation: list[ToolTurnCorrelation]

    # Per-tool individual call timing (only when matched call/result pairs found)
    tool_call_timing: list[ToolCallTimingSummary]

    # Hourly activity
    hourly_distribution: list[HourlyBucket]

    def to_dict(self) -> dict:
        return {
            "n_turns_with_timing": self.n_turns_with_timing,
            "n_turns_total": self.n_turns_total,
            "min_duration_s": round(self.min_duration_s, 2),
            "median_duration_s": round(self.median_duration_s, 2),
            "mean_duration_s": round(self.mean_duration_s, 2),
            "p90_duration_s": round(self.p90_duration_s, 2),
            "max_duration_s": round(self.max_duration_s, 2),
            "total_time_s": round(self.total_time_s, 2),
            "slow_quartile_mean_quality": round(self.slow_quartile_mean_quality, 4),
            "fast_half_mean_quality": round(self.fast_half_mean_quality, 4),
            "speed_quality_verdict": self.speed_quality_verdict,
            "slowest_turns": [t.to_dict() for t in self.slowest_turns],
            "tool_turn_correlation": [t.to_dict() for t in self.tool_turn_correlation],
            "tool_call_timing": [t.to_dict() for t in self.tool_call_timing],
            "hourly_distribution": [h.to_dict() for h in self.hourly_distribution],
        }


class TimeBottlenecksAnalyzer:
    """Analyze where wall-clock time is being spent across turns and tool calls."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
        tool_call_timings: list[ToolCallTiming] | None = None,
    ) -> None:
        self._turns = turns
        self._qualities = qualities
        self._tool_timings = tool_call_timings or []

    def analyze(self) -> TimeBottlenecksResult:
        turns = self._turns
        qualities = self._qualities

        if not turns:
            return TimeBottlenecksResult(
                n_turns_with_timing=0,
                n_turns_total=0,
                min_duration_s=0.0,
                median_duration_s=0.0,
                mean_duration_s=0.0,
                p90_duration_s=0.0,
                max_duration_s=0.0,
                total_time_s=0.0,
                slow_quartile_mean_quality=0.0,
                fast_half_mean_quality=0.0,
                speed_quality_verdict="no_correlation",
                slowest_turns=[],
                tool_turn_correlation=[],
                tool_call_timing=[],
                hourly_distribution=[],
            )

        # ----------------------------------------------------------------
        # Build per-turn timing records (only for turns with known duration)
        # ----------------------------------------------------------------
        timed: list[tuple[TurnRecord, float, float]] = []  # (turn, quality, duration)
        for turn, quality in zip(turns, qualities):
            if turn.duration_seconds > 0:
                timed.append((turn, quality, turn.duration_seconds))

        n_timed = len(timed)

        if not timed:
            return TimeBottlenecksResult(
                n_turns_with_timing=0,
                n_turns_total=len(turns),
                min_duration_s=0.0,
                median_duration_s=0.0,
                mean_duration_s=0.0,
                p90_duration_s=0.0,
                max_duration_s=0.0,
                total_time_s=0.0,
                slow_quartile_mean_quality=0.0,
                fast_half_mean_quality=0.0,
                speed_quality_verdict="no_correlation",
                slowest_turns=[],
                tool_turn_correlation=[],
                tool_call_timing=self._build_tool_call_timing(),
                hourly_distribution=self._build_hourly(turns, qualities),
            )

        durations = sorted(t[2] for t in timed)
        total_time = sum(durations)
        mean_dur = total_time / n_timed
        median_dur = statistics.median(durations)
        p90_dur = _percentile(durations, 90)

        # Slow vs fast quality comparison
        timed_sorted = sorted(timed, key=lambda x: x[2])  # ascending by duration
        n_slow = max(1, n_timed // 4)        # top 25%
        n_fast = max(1, n_timed // 2)        # bottom 50%
        fast_half = timed_sorted[:n_fast]
        slow_quartile = timed_sorted[-n_slow:]

        fast_mean_q = sum(x[1] for x in fast_half) / len(fast_half)
        slow_mean_q = sum(x[1] for x in slow_quartile) / len(slow_quartile)

        delta = slow_mean_q - fast_mean_q
        if abs(delta) < 0.05:
            verdict = "no_correlation"
        elif delta > 0:
            verdict = "slower_is_better"
        else:
            verdict = "slower_is_worse"

        # Top-10 slowest turns
        slowest_raw = sorted(timed, key=lambda x: x[2], reverse=True)[:10]
        slowest_turns = [
            TurnTimingRecord(
                turn_id=t.turn_id,
                duration_seconds=t.duration_seconds,
                quality=q,
                n_messages=t.conversation_length,
                tools_called=list(t.tools_called),
                task_completed=t.task_completed,
                has_error=t.follow_up_correction,
            )
            for t, q, _ in slowest_raw
        ]

        # ----------------------------------------------------------------
        # Per-tool turn-duration correlation
        # ----------------------------------------------------------------
        tool_dur: dict[str, list[float]] = defaultdict(list)
        for turn, quality, dur in timed:
            for tool in turn.tools_called:
                tool_dur[tool].append(dur)

        tool_corr: list[ToolTurnCorrelation] = []
        for tool_name, durs in tool_dur.items():
            if len(durs) < _MIN_TOOL_TURNS:
                continue
            mdur = sum(durs) / len(durs)
            ratio = mdur / mean_dur if mean_dur > 0 else 1.0
            tool_corr.append(
                ToolTurnCorrelation(
                    tool_name=tool_name,
                    n_turns=len(durs),
                    mean_turn_duration_s=mdur,
                    global_mean_duration_s=mean_dur,
                    duration_ratio=ratio,
                )
            )
        tool_corr.sort(key=lambda c: c.duration_ratio, reverse=True)

        # ----------------------------------------------------------------
        # Per-tool call timing from matched ToolCallTiming records
        # ----------------------------------------------------------------
        tool_call_timing = self._build_tool_call_timing()

        # ----------------------------------------------------------------
        # Hourly distribution
        # ----------------------------------------------------------------
        hourly_dist = self._build_hourly(turns, qualities)

        return TimeBottlenecksResult(
            n_turns_with_timing=n_timed,
            n_turns_total=len(turns),
            min_duration_s=min(durations),
            median_duration_s=float(median_dur),
            mean_duration_s=mean_dur,
            p90_duration_s=p90_dur,
            max_duration_s=max(durations),
            total_time_s=total_time,
            slow_quartile_mean_quality=slow_mean_q,
            fast_half_mean_quality=fast_mean_q,
            speed_quality_verdict=verdict,
            slowest_turns=slowest_turns,
            tool_turn_correlation=tool_corr,
            tool_call_timing=tool_call_timing,
            hourly_distribution=hourly_dist,
        )

    def _build_tool_call_timing(self) -> list[ToolCallTimingSummary]:
        """Aggregate per-tool call durations from matched ToolCallTiming records."""
        tool_durations: dict[str, list[float]] = defaultdict(list)
        for tc in self._tool_timings:
            if tc.duration_seconds > 0:
                tool_durations[tc.tool_name].append(tc.duration_seconds)

        summaries: list[ToolCallTimingSummary] = []
        for tool_name, durs in tool_durations.items():
            if len(durs) < _MIN_TIMED_CALLS:
                continue
            durs_sorted = sorted(durs)
            summaries.append(
                ToolCallTimingSummary(
                    tool_name=tool_name,
                    n_timed_calls=len(durs),
                    mean_duration_s=sum(durs) / len(durs),
                    median_duration_s=float(statistics.median(durs)),
                    p90_duration_s=_percentile(durs_sorted, 90),
                    max_duration_s=max(durs),
                    total_time_s=sum(durs),
                )
            )
        summaries.sort(key=lambda s: s.mean_duration_s, reverse=True)
        return summaries

    def _build_hourly(
        self, turns: list[TurnRecord], qualities: list[float]
    ) -> list[HourlyBucket]:
        """Build per-UTC-hour activity buckets."""
        by_hour: dict[int, dict] = defaultdict(
            lambda: {"n": 0, "q_sum": 0.0, "dur_sum": 0.0, "errors": 0}
        )
        for turn, quality in zip(turns, qualities):
            h = turn.timestamp.hour
            by_hour[h]["n"] += 1
            by_hour[h]["q_sum"] += quality
            by_hour[h]["dur_sum"] += turn.duration_seconds
            if turn.follow_up_correction:
                by_hour[h]["errors"] += 1

        buckets: list[HourlyBucket] = []
        for hour in sorted(by_hour):
            d = by_hour[hour]
            n = d["n"]
            buckets.append(
                HourlyBucket(
                    hour=hour,
                    n_turns=n,
                    mean_quality=d["q_sum"] / n,
                    mean_duration_s=d["dur_sum"] / n,
                    error_rate=d["errors"] / n,
                )
            )
        return buckets
