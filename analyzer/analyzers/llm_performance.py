# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""LLM performance analyzer.

Analyzes LLM performance timing from jiuwenswarm session logs, producing
overall latency distributions, slow-turn diagnostics, per-model comparisons,
and weekly latency trends.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from ..loader import TurnRecord

_SLOW_TURNS_LIMIT = 10
_TTFT_SLOW_THRESHOLD_MS = 5000.0   # > 5 s flagged as slow prompt processing
_TPOT_SLOW_THRESHOLD_MS = 100.0    # > 100 ms flagged as slow generation


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - idx + lo) + sorted_vals[hi] * (idx - lo)


def _latency_distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "min": 0.0,
            "median": 0.0,
            "mean": 0.0,
            "p90": 0.0,
            "max": 0.0,
        }
    sorted_vals = sorted(values)
    return {
        "min": sorted_vals[0],
        "median": float(statistics.median(sorted_vals)),
        "mean": sum(sorted_vals) / len(sorted_vals),
        "p90": _percentile(sorted_vals, 90.0),
        "max": sorted_vals[-1],
    }


def _to_latency_dist(values: list[float]) -> LatencyDistribution:
    d = _latency_distribution(values)
    return LatencyDistribution(
        min=d["min"],
        median=d["median"],
        mean=d["mean"],
        p90=d["p90"],
        max=d["max"],
    )


@dataclass(frozen=True)
class LatencyDistribution:
    """Latency distribution for a single metric (min/median/mean/p90/max)."""

    min: float
    median: float
    mean: float
    p90: float
    max: float

    def to_dict(self) -> dict:
        return {
            "min": round(self.min, 2),
            "median": round(self.median, 2),
            "mean": round(self.mean, 2),
            "p90": round(self.p90, 2),
            "max": round(self.max, 2),
        }


@dataclass(frozen=True)
class SlowTurnRecord:
    """Details of a slow turn for diagnostic inspection."""

    turn_id: str
    total_latency_ms: float
    ttft_ms: float
    tpot_ms: float
    model_name: str
    quality: float
    token_count: int
    status: str           # e.g. "completed" | "error"

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "ttft_ms": round(self.ttft_ms, 2),
            "tpot_ms": round(self.tpot_ms, 2),
            "model_name": self.model_name,
            "quality": round(self.quality, 4),
            "token_count": self.token_count,
            "status": self.status,
        }


@dataclass(frozen=True)
class ModelPerformanceSummary:
    """Timing statistics for a single model."""

    model_name: str
    n_turns: int
    total_latency: LatencyDistribution
    ttft: LatencyDistribution
    tpot: LatencyDistribution
    mean_tokens_per_second: float
    mean_output_tokens_per_second: float
    slow_prompt_processing_count: int   # TTFT > 5 s
    slow_generation_count: int          # TPOT > 100 ms

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "n_turns": self.n_turns,
            "total_latency": self.total_latency.to_dict(),
            "ttft": self.ttft.to_dict(),
            "tpot": self.tpot.to_dict(),
            "mean_tokens_per_second": round(self.mean_tokens_per_second, 2),
            "mean_output_tokens_per_second": round(self.mean_output_tokens_per_second, 2),
            "slow_prompt_processing_count": self.slow_prompt_processing_count,
            "slow_generation_count": self.slow_generation_count,
        }


@dataclass(frozen=True)
class WeeklyLatencySummary:
    """Aggregate latency trend for a single week."""

    week_tag: str
    n_turns: int
    mean_total_latency_ms: float
    median_total_latency_ms: float
    mean_ttft_ms: float
    mean_tpot_ms: float
    mean_tokens_per_second: float
    slow_prompt_processing_count: int
    slow_generation_count: int

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "n_turns": self.n_turns,
            "mean_total_latency_ms": round(self.mean_total_latency_ms, 2),
            "median_total_latency_ms": round(self.median_total_latency_ms, 2),
            "mean_ttft_ms": round(self.mean_ttft_ms, 2),
            "mean_tpot_ms": round(self.mean_tpot_ms, 2),
            "mean_tokens_per_second": round(self.mean_tokens_per_second, 2),
            "slow_prompt_processing_count": self.slow_prompt_processing_count,
            "slow_generation_count": self.slow_generation_count,
        }


@dataclass(frozen=True)
class LLMPerformanceResult:
    """Complete LLM performance analysis result."""

    n_turns_analyzed: int
    n_turns_with_timing: int

    # Overall distributions
    total_latency: LatencyDistribution
    ttft: LatencyDistribution
    tpot: LatencyDistribution

    # Slowest turns
    slowest_turns: list[SlowTurnRecord]

    # TTFT vs TPOT breakdown for slow turns
    slow_turns_slow_prompt_processing: int
    slow_turns_slow_generation: int
    slow_turns_both_slow: int

    # Per-model comparison
    model_summaries: list[ModelPerformanceSummary]

    # Weekly trends
    weekly_summaries: list[WeeklyLatencySummary]

    # Token throughput
    mean_tokens_per_second: float
    mean_output_tokens_per_second: float

    # Correlation hints
    high_latency_error_count: int   # turns with total_latency > p90 AND error
    high_latency_error_rate: float
    slow_prompt_processing_count: int   # TTFT > 5 s overall
    slow_generation_count: int          # TPOT > 100 ms overall

    def to_dict(self) -> dict:
        return {
            "n_turns_analyzed": self.n_turns_analyzed,
            "n_turns_with_timing": self.n_turns_with_timing,
            "total_latency": self.total_latency.to_dict(),
            "ttft": self.ttft.to_dict(),
            "tpot": self.tpot.to_dict(),
            "slowest_turns": [t.to_dict() for t in self.slowest_turns],
            "slow_turns_slow_prompt_processing": self.slow_turns_slow_prompt_processing,
            "slow_turns_slow_generation": self.slow_turns_slow_generation,
            "slow_turns_both_slow": self.slow_turns_both_slow,
            "model_summaries": [m.to_dict() for m in self.model_summaries],
            "weekly_summaries": [w.to_dict() for w in self.weekly_summaries],
            "mean_tokens_per_second": round(self.mean_tokens_per_second, 2),
            "mean_output_tokens_per_second": round(self.mean_output_tokens_per_second, 2),
            "high_latency_error_count": self.high_latency_error_count,
            "high_latency_error_rate": round(self.high_latency_error_rate, 4),
            "slow_prompt_processing_count": self.slow_prompt_processing_count,
            "slow_generation_count": self.slow_generation_count,
        }


class LLMPerformanceAnalyzer:
    """Analyze LLM timing metrics from turn records."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
    ) -> None:
        self._turns = turns
        self._qualities = qualities

    def analyze(self) -> LLMPerformanceResult:
        turns = self._turns
        qualities = self._qualities

        # Filter out heartbeat turns
        filtered: list[tuple[TurnRecord, float]] = []
        for turn, quality in zip(turns, qualities):
            if not turn.is_heartbeat:
                filtered.append((turn, quality))

        n_analyzed = len(filtered)

        # Extract turns with valid LLM timing
        timed: list[tuple[TurnRecord, float]] = []
        for turn, quality in filtered:
            if turn.total_latency_ms > 0 and turn.ttft_ms > 0 and turn.tpot_ms > 0:
                timed.append((turn, quality))

        n_timed = len(timed)

        if not timed:
            empty_dist = LatencyDistribution(min=0.0, median=0.0, mean=0.0, p90=0.0, max=0.0)
            return LLMPerformanceResult(
                n_turns_analyzed=n_analyzed,
                n_turns_with_timing=0,
                total_latency=empty_dist,
                ttft=empty_dist,
                tpot=empty_dist,
                slowest_turns=[],
                slow_turns_slow_prompt_processing=0,
                slow_turns_slow_generation=0,
                slow_turns_both_slow=0,
                model_summaries=[],
                weekly_summaries=[],
                mean_tokens_per_second=0.0,
                mean_output_tokens_per_second=0.0,
                high_latency_error_count=0,
                high_latency_error_rate=0.0,
                slow_prompt_processing_count=0,
                slow_generation_count=0,
            )

        # Overall latency distributions
        total_latencies = [t.total_latency_ms for t, _ in timed]
        ttft_values = [t.ttft_ms for t, _ in timed]
        tpot_values = [t.tpot_ms for t, _ in timed]

        total_lat_dist = _to_latency_dist(total_latencies)
        ttft_dist = _to_latency_dist(ttft_values)
        tpot_dist = _to_latency_dist(tpot_values)
        p90_total = total_lat_dist.p90

        # Overall token throughput
        total_tps_values: list[float] = []
        output_tps_values: list[float] = []
        for turn, _ in timed:
            latency_s = turn.total_latency_ms / 1000.0
            if latency_s > 0:
                total_tps_values.append(turn.total_tokens / latency_s)
                output_tps_values.append(turn.output_tokens / latency_s)
        mean_total_tps = sum(total_tps_values) / len(total_tps_values) if total_tps_values else 0.0
        mean_output_tps = sum(output_tps_values) / len(output_tps_values) if output_tps_values else 0.0

        # Slowest turns (top 10 by total_latency_ms)
        by_latency = sorted(timed, key=lambda x: x[0].total_latency_ms, reverse=True)
        slowest = by_latency[:_SLOW_TURNS_LIMIT]
        slowest_turns: list[SlowTurnRecord] = []
        slow_prompt_slow = 0
        slow_generation_slow = 0
        both_slow = 0
        for turn, quality in slowest:
            is_slow_prompt = turn.ttft_ms > _TTFT_SLOW_THRESHOLD_MS
            is_slow_gen = turn.tpot_ms > _TPOT_SLOW_THRESHOLD_MS
            if is_slow_prompt:
                slow_prompt_slow += 1
            if is_slow_gen:
                slow_generation_slow += 1
            if is_slow_prompt and is_slow_gen:
                both_slow += 1
            status = "error" if turn.follow_up_correction else "completed"
            slowest_turns.append(
                SlowTurnRecord(
                    turn_id=turn.turn_id,
                    total_latency_ms=turn.total_latency_ms,
                    ttft_ms=turn.ttft_ms,
                    tpot_ms=turn.tpot_ms,
                    model_name=turn.model_name,
                    quality=quality,
                    token_count=turn.total_tokens,
                    status=status,
                )
            )

        # High-latency + error correlation
        high_latency_error_count = 0
        for turn, _ in timed:
            if turn.total_latency_ms > p90_total and turn.follow_up_correction:
                high_latency_error_count += 1
        high_latency_error_rate = high_latency_error_count / n_timed if n_timed else 0.0

        # Overall slow counts
        overall_slow_prompt = sum(1 for turn, _ in timed if turn.ttft_ms > _TTFT_SLOW_THRESHOLD_MS)
        overall_slow_gen = sum(1 for turn, _ in timed if turn.tpot_ms > _TPOT_SLOW_THRESHOLD_MS)

        # Per-model summaries
        by_model: dict[str, list[tuple[TurnRecord, float]]] = defaultdict(list)
        for turn, quality in timed:
            model = turn.model_name or "unknown"
            by_model[model].append((turn, quality))

        model_summaries: list[ModelPerformanceSummary] = []
        for model_name, entries in sorted(by_model.items()):
            tl = [t.total_latency_ms for t, _ in entries]
            tv = [t.ttft_ms for t, _ in entries]
            pv = [t.tpot_ms for t, _ in entries]
            tps_list: list[float] = []
            otps_list: list[float] = []
            sp_count = 0
            sg_count = 0
            for turn, _ in entries:
                latency_s = turn.total_latency_ms / 1000.0
                if latency_s > 0:
                    tps_list.append(turn.total_tokens / latency_s)
                    otps_list.append(turn.output_tokens / latency_s)
                if turn.ttft_ms > _TTFT_SLOW_THRESHOLD_MS:
                    sp_count += 1
                if turn.tpot_ms > _TPOT_SLOW_THRESHOLD_MS:
                    sg_count += 1
            model_summaries.append(
                ModelPerformanceSummary(
                    model_name=model_name,
                    n_turns=len(entries),
                    total_latency=_to_latency_dist(tl),
                    ttft=_to_latency_dist(tv),
                    tpot=_to_latency_dist(pv),
                    mean_tokens_per_second=sum(tps_list) / len(tps_list) if tps_list else 0.0,
                    mean_output_tokens_per_second=sum(otps_list) / len(otps_list) if otps_list else 0.0,
                    slow_prompt_processing_count=sp_count,
                    slow_generation_count=sg_count,
                )
            )
        # Sort by mean total latency descending for comparison
        model_summaries.sort(key=lambda m: m.total_latency.mean, reverse=True)

        # Weekly summaries
        by_week: dict[str, list[tuple[TurnRecord, float]]] = defaultdict(list)
        for turn, quality in timed:
            by_week[turn.week_tag].append((turn, quality))

        weekly_summaries: list[WeeklyLatencySummary] = []
        for week_tag, entries in sorted(by_week.items()):
            tl = [t.total_latency_ms for t, _ in entries]
            ttl = sum(tl) / len(tl) if tl else 0.0
            mtl = float(statistics.median(tl)) if tl else 0.0
            mttft = sum(t.ttft_ms for t, _ in entries) / len(entries) if entries else 0.0
            mtpot = sum(t.tpot_ms for t, _ in entries) / len(entries) if entries else 0.0
            tps_list: list[float] = []
            sp_count = 0
            sg_count = 0
            for turn, _ in entries:
                latency_s = turn.total_latency_ms / 1000.0
                if latency_s > 0:
                    tps_list.append(turn.total_tokens / latency_s)
                if turn.ttft_ms > _TTFT_SLOW_THRESHOLD_MS:
                    sp_count += 1
                if turn.tpot_ms > _TPOT_SLOW_THRESHOLD_MS:
                    sg_count += 1
            weekly_summaries.append(
                WeeklyLatencySummary(
                    week_tag=week_tag,
                    n_turns=len(entries),
                    mean_total_latency_ms=ttl,
                    median_total_latency_ms=mtl,
                    mean_ttft_ms=mttft,
                    mean_tpot_ms=mtpot,
                    mean_tokens_per_second=sum(tps_list) / len(tps_list) if tps_list else 0.0,
                    slow_prompt_processing_count=sp_count,
                    slow_generation_count=sg_count,
                )
            )

        return LLMPerformanceResult(
            n_turns_analyzed=n_analyzed,
            n_turns_with_timing=n_timed,
            total_latency=total_lat_dist,
            ttft=ttft_dist,
            tpot=tpot_dist,
            slowest_turns=slowest_turns,
            slow_turns_slow_prompt_processing=slow_prompt_slow,
            slow_turns_slow_generation=slow_generation_slow,
            slow_turns_both_slow=both_slow,
            model_summaries=model_summaries,
            weekly_summaries=weekly_summaries,
            mean_tokens_per_second=mean_total_tps,
            mean_output_tokens_per_second=mean_output_tps,
            high_latency_error_count=high_latency_error_count,
            high_latency_error_rate=high_latency_error_rate,
            slow_prompt_processing_count=overall_slow_prompt,
            slow_generation_count=overall_slow_gen,
        )
