# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Token usage analyzer.

Analyzes token consumption patterns from jiuwenswarm session logs.
Produces aggregate metrics, per-week trends, per-model breakdowns, per-tool
cost attribution, context-window utilization stats, and crude cost estimates.

Heartbeat turns (``is_heartbeat=True``) are excluded from all token analysis
because they carry trivial usage.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from ..loader import TurnRecord

_CONTEXT_LIMIT_THRESHOLD = 80.0  # usage_percent above this are "approaching limit"


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - idx + lo) + sorted_vals[hi] * (idx - lo)


def _cost_estimate(input_tokens: int, output_tokens: int, model_name: str) -> float:
    """Return a rough USD cost for the given token counts.

    Kimi-family models are priced differently from the default fallback.
    """
    if "kimi" in model_name.lower():
        input_rate = 0.0015
        output_rate = 0.006
    else:
        input_rate = 0.002
        output_rate = 0.008
    return (input_tokens / 1000.0) * input_rate + (output_tokens / 1000.0) * output_rate


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WeeklyTokenSummary:
    """Token aggregates for a single week."""

    week_tag: str
    n_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    mean_total_tokens: float
    max_total_tokens: int
    mean_usage_percent: float
    turns_near_limit: int

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "n_turns": self.n_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "mean_total_tokens": round(self.mean_total_tokens, 2),
            "max_total_tokens": self.max_total_tokens,
            "mean_usage_percent": round(self.mean_usage_percent, 4),
            "turns_near_limit": self.turns_near_limit,
        }


@dataclass(frozen=True)
class ModelTokenSummary:
    """Token aggregates for a single model."""

    model_name: str
    n_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    mean_total_tokens: float
    max_total_tokens: int
    mean_usage_percent: float
    turns_near_limit: int
    estimated_cost: float

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "n_turns": self.n_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "mean_total_tokens": round(self.mean_total_tokens, 2),
            "max_total_tokens": self.max_total_tokens,
            "mean_usage_percent": round(self.mean_usage_percent, 4),
            "turns_near_limit": self.turns_near_limit,
            "estimated_cost": round(self.estimated_cost, 4),
        }


@dataclass(frozen=True)
class ToolTokenSummary:
    """Average token consumption for turns where a specific tool was called."""

    tool_name: str
    n_turns: int
    mean_total_tokens: float
    mean_input_tokens: float
    mean_output_tokens: float
    mean_usage_percent: float

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "n_turns": self.n_turns,
            "mean_total_tokens": round(self.mean_total_tokens, 2),
            "mean_input_tokens": round(self.mean_input_tokens, 2),
            "mean_output_tokens": round(self.mean_output_tokens, 2),
            "mean_usage_percent": round(self.mean_usage_percent, 4),
        }


@dataclass(frozen=True)
class TokenUsageResult:
    """Complete token usage analysis."""

    # --- overall counts ---
    n_turns: int
    n_heartbeat_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    mean_tokens_per_turn: float
    median_tokens_per_turn: float
    max_tokens_per_turn: int

    # --- success vs failure ---
    success_turns: int
    failure_turns: int
    mean_tokens_per_success: float
    mean_tokens_per_failure: float
    token_efficiency_ratio: float  # success_mean / failure_mean; 0 if no failures

    # --- context window utilization ---
    mean_usage_percent: float
    median_usage_percent: float
    p90_usage_percent: float
    max_usage_percent: float
    turns_near_limit: int            # > _CONTEXT_LIMIT_THRESHOLD

    # --- cost estimate ---
    estimated_total_cost: float

    # --- per-week trends ---
    weekly_summary: list[WeeklyTokenSummary]

    # --- per-model breakdown ---
    model_summary: list[ModelTokenSummary]

    # --- per-tool averages ---
    tool_summary: list[ToolTokenSummary]

    def to_dict(self) -> dict:
        return {
            "n_turns": self.n_turns,
            "n_heartbeat_turns": self.n_heartbeat_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "mean_tokens_per_turn": round(self.mean_tokens_per_turn, 2),
            "median_tokens_per_turn": round(self.median_tokens_per_turn, 2),
            "max_tokens_per_turn": self.max_tokens_per_turn,
            "success_turns": self.success_turns,
            "failure_turns": self.failure_turns,
            "mean_tokens_per_success": round(self.mean_tokens_per_success, 2),
            "mean_tokens_per_failure": round(self.mean_tokens_per_failure, 2),
            "token_efficiency_ratio": round(self.token_efficiency_ratio, 4),
            "mean_usage_percent": round(self.mean_usage_percent, 4),
            "median_usage_percent": round(self.median_usage_percent, 4),
            "p90_usage_percent": round(self.p90_usage_percent, 4),
            "max_usage_percent": round(self.max_usage_percent, 4),
            "turns_near_limit": self.turns_near_limit,
            "estimated_total_cost": round(self.estimated_total_cost, 4),
            "weekly_summary": [w.to_dict() for w in self.weekly_summary],
            "model_summary": [m.to_dict() for m in self.model_summary],
            "tool_summary": [t.to_dict() for t in self.tool_summary],
        }


class TokenUsageAnalyzer:
    """Analyze token consumption patterns across agent turns."""

    def __init__(
        self,
        turns: list[TurnRecord],
    ) -> None:
        self._turns = turns

    def analyze(self) -> TokenUsageResult:
        all_turns = self._turns
        n_heartbeat = sum(1 for t in all_turns if t.is_heartbeat)
        turns = [t for t in all_turns if not t.is_heartbeat]
        n = len(turns)

        if not turns:
            return TokenUsageResult(
                n_turns=0,
                n_heartbeat_turns=n_heartbeat,
                total_input_tokens=0,
                total_output_tokens=0,
                total_tokens=0,
                mean_tokens_per_turn=0.0,
                median_tokens_per_turn=0.0,
                max_tokens_per_turn=0,
                success_turns=0,
                failure_turns=0,
                mean_tokens_per_success=0.0,
                mean_tokens_per_failure=0.0,
                token_efficiency_ratio=0.0,
                mean_usage_percent=0.0,
                median_usage_percent=0.0,
                p90_usage_percent=0.0,
                max_usage_percent=0.0,
                turns_near_limit=0,
                estimated_total_cost=0.0,
                weekly_summary=[],
                model_summary=[],
                tool_summary=[],
            )

        # ----------------------------------------------------------------
        # Overall aggregates
        # ----------------------------------------------------------------
        total_input = sum(t.input_tokens for t in turns)
        total_output = sum(t.output_tokens for t in turns)
        total_tokens = sum(t.total_tokens for t in turns)
        total_tokens_sorted = sorted(t.total_tokens for t in turns)
        mean_total = total_tokens / n
        median_total = float(statistics.median(total_tokens_sorted))
        max_total = max(total_tokens_sorted)

        # ----------------------------------------------------------------
        # Success vs failure
        # ----------------------------------------------------------------
        success_turns = [t for t in turns if t.task_completed]
        failure_turns = [t for t in turns if not t.task_completed]
        n_success = len(success_turns)
        n_failure = len(failure_turns)

        mean_success = (
            sum(t.total_tokens for t in success_turns) / n_success if n_success else 0.0
        )
        mean_failure = (
            sum(t.total_tokens for t in failure_turns) / n_failure if n_failure else 0.0
        )
        efficiency_ratio = mean_success / mean_failure if mean_failure > 0 else 0.0

        # ----------------------------------------------------------------
        # Context window utilization
        # ----------------------------------------------------------------
        usage_vals = sorted(t.usage_percent for t in turns)
        mean_usage = sum(usage_vals) / n
        median_usage = float(statistics.median(usage_vals))
        p90_usage = _percentile(usage_vals, 90)
        max_usage = max(usage_vals)
        near_limit = sum(1 for u in usage_vals if u > _CONTEXT_LIMIT_THRESHOLD)

        # ----------------------------------------------------------------
        # Cost estimate
        # ----------------------------------------------------------------
        # Use per-turn model name for best accuracy; fallback to empty string
        est_cost = sum(
            _cost_estimate(t.input_tokens, t.output_tokens, t.model_name) for t in turns
        )

        # ----------------------------------------------------------------
        # Per-week trends
        # ----------------------------------------------------------------
        weekly = self._build_weekly_summary(turns)

        # ----------------------------------------------------------------
        # Per-model breakdown
        # ----------------------------------------------------------------
        model = self._build_model_summary(turns)

        # ----------------------------------------------------------------
        # Per-tool averages
        # ----------------------------------------------------------------
        tool = self._build_tool_summary(turns)

        return TokenUsageResult(
            n_turns=n,
            n_heartbeat_turns=n_heartbeat,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_tokens,
            mean_tokens_per_turn=mean_total,
            median_tokens_per_turn=median_total,
            max_tokens_per_turn=max_total,
            success_turns=n_success,
            failure_turns=n_failure,
            mean_tokens_per_success=mean_success,
            mean_tokens_per_failure=mean_failure,
            token_efficiency_ratio=efficiency_ratio,
            mean_usage_percent=mean_usage,
            median_usage_percent=median_usage,
            p90_usage_percent=p90_usage,
            max_usage_percent=max_usage,
            turns_near_limit=near_limit,
            estimated_total_cost=est_cost,
            weekly_summary=weekly,
            model_summary=model,
            tool_summary=tool,
        )

    def _build_weekly_summary(
        self, turns: list[TurnRecord]
    ) -> list[WeeklyTokenSummary]:
        by_week: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in turns:
            by_week[t.week_tag].append(t)

        summaries: list[WeeklyTokenSummary] = []
        for week_tag, wturns in sorted(by_week.items()):
            n = len(wturns)
            total_input = sum(t.input_tokens for t in wturns)
            total_output = sum(t.output_tokens for t in wturns)
            total = sum(t.total_tokens for t in wturns)
            max_total = max(t.total_tokens for t in wturns)
            mean_usage = sum(t.usage_percent for t in wturns) / n
            near = sum(1 for t in wturns if t.usage_percent > _CONTEXT_LIMIT_THRESHOLD)
            summaries.append(
                WeeklyTokenSummary(
                    week_tag=week_tag,
                    n_turns=n,
                    total_input_tokens=total_input,
                    total_output_tokens=total_output,
                    total_tokens=total,
                    mean_total_tokens=total / n,
                    max_total_tokens=max_total,
                    mean_usage_percent=mean_usage,
                    turns_near_limit=near,
                )
            )
        return summaries

    def _build_model_summary(
        self, turns: list[TurnRecord]
    ) -> list[ModelTokenSummary]:
        by_model: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in turns:
            model = t.model_name if t.model_name else "unknown"
            by_model[model].append(t)

        summaries: list[ModelTokenSummary] = []
        for model_name, mturns in sorted(by_model.items()):
            n = len(mturns)
            total_input = sum(t.input_tokens for t in mturns)
            total_output = sum(t.output_tokens for t in mturns)
            total = sum(t.total_tokens for t in mturns)
            max_total = max(t.total_tokens for t in mturns)
            mean_usage = sum(t.usage_percent for t in mturns) / n
            near = sum(1 for t in mturns if t.usage_percent > _CONTEXT_LIMIT_THRESHOLD)
            cost = sum(
                _cost_estimate(t.input_tokens, t.output_tokens, t.model_name)
                for t in mturns
            )
            summaries.append(
                ModelTokenSummary(
                    model_name=model_name,
                    n_turns=n,
                    total_input_tokens=total_input,
                    total_output_tokens=total_output,
                    total_tokens=total,
                    mean_total_tokens=total / n,
                    max_total_tokens=max_total,
                    mean_usage_percent=mean_usage,
                    turns_near_limit=near,
                    estimated_cost=cost,
                )
            )
        # Sort by total token consumption descending
        summaries.sort(key=lambda s: s.total_tokens, reverse=True)
        return summaries

    def _build_tool_summary(
        self, turns: list[TurnRecord]
    ) -> list[ToolTokenSummary]:
        by_tool: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in turns:
            for tool in t.tools_called:
                by_tool[tool].append(t)

        summaries: list[ToolTokenSummary] = []
        for tool_name, tturns in sorted(by_tool.items()):
            n = len(tturns)
            total = sum(t.total_tokens for t in tturns)
            total_input = sum(t.input_tokens for t in tturns)
            total_output = sum(t.output_tokens for t in tturns)
            mean_usage = sum(t.usage_percent for t in tturns) / n
            summaries.append(
                ToolTokenSummary(
                    tool_name=tool_name,
                    n_turns=n,
                    mean_total_tokens=total / n,
                    mean_input_tokens=total_input / n,
                    mean_output_tokens=total_output / n,
                    mean_usage_percent=mean_usage,
                )
            )
        # Sort by mean total tokens descending ("which tools burn the most tokens")
        summaries.sort(key=lambda s: s.mean_total_tokens, reverse=True)
        return summaries
