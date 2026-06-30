# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tool execution success / failure analyzer.

Analyzes tool execution patterns from jiuwenswarm session logs:
  - Overall and per-tool success rates
  - Retry-loop detection (same tool called > 2 times in a turn)
  - Common error messages
  - Failure recovery (task_completed despite tool failures)
  - Weekly failure trends
  - Correlation between tool failure rate and turn duration
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

from ..loader import TurnRecord

_RETRY_THRESHOLD = 2  # more than this many calls of the same tool → retry loop


@dataclass(frozen=True)
class PerToolStats:
    name: str
    total_calls: int
    successes: int
    failures: int
    success_rate: float
    avg_duration: float
    common_errors: list[tuple[str, int]]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_calls": self.total_calls,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 4),
            "avg_duration": round(self.avg_duration, 2),
            "common_errors": [(err, cnt) for err, cnt in self.common_errors],
        }


@dataclass(frozen=True)
class RetryPattern:
    tool_name: str
    n_turns_with_retries: int
    avg_calls_per_retry_turn: float

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "n_turns_with_retries": self.n_turns_with_retries,
            "avg_calls_per_retry_turn": round(self.avg_calls_per_retry_turn, 2),
        }


@dataclass(frozen=True)
class WeeklyToolSummary:
    week_tag: str
    n_calls: int
    n_failures: int
    failure_rate: float

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "n_calls": self.n_calls,
            "n_failures": self.n_failures,
            "failure_rate": round(self.failure_rate, 4),
        }


@dataclass(frozen=True)
class ToolSuccessResult:
    total_turns: int
    total_tool_calls: int
    total_tool_failures: int
    overall_success_rate: float
    per_tool_stats: list[PerToolStats]              # sorted by failure rate desc
    most_failure_prone_tools: list[str]             # top 5 by failure count
    retry_patterns: list[RetryPattern]              # sorted by n_turns desc
    top_error_messages: list[tuple[str, int]]       # top 5 across all tools
    recovery_turns: int                             # task_completed=True despite failures
    recovery_rate: float
    weekly_summaries: list[WeeklyToolSummary]      # sorted by week_tag asc
    duration_correlation: dict                      # Pearson-like correlation stats

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "total_tool_calls": self.total_tool_calls,
            "total_tool_failures": self.total_tool_failures,
            "overall_success_rate": round(self.overall_success_rate, 4),
            "per_tool_stats": [s.to_dict() for s in self.per_tool_stats],
            "most_failure_prone_tools": self.most_failure_prone_tools,
            "retry_patterns": [r.to_dict() for r in self.retry_patterns],
            "top_error_messages": [(err, cnt) for err, cnt in self.top_error_messages],
            "recovery_turns": self.recovery_turns,
            "recovery_rate": round(self.recovery_rate, 4),
            "weekly_summaries": [w.to_dict() for w in self.weekly_summaries],
            "duration_correlation": self.duration_correlation,
        }


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Return Pearson correlation coefficient, or 0.0 on insufficient data."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (den_x * den_y)


class ToolSuccessAnalyzer:
    """Analyze tool execution success/failure patterns."""

    def __init__(
        self,
        turns: list[TurnRecord],
        retry_threshold: int = _RETRY_THRESHOLD,
    ) -> None:
        self._turns = [t for t in turns if not t.is_heartbeat]
        self._retry_threshold = retry_threshold

    def analyze(self) -> ToolSuccessResult:
        if not self._turns:
            return ToolSuccessResult(
                total_turns=0,
                total_tool_calls=0,
                total_tool_failures=0,
                overall_success_rate=0.0,
                per_tool_stats=[],
                most_failure_prone_tools=[],
                retry_patterns=[],
                top_error_messages=[],
                recovery_turns=0,
                recovery_rate=0.0,
                weekly_summaries=[],
                duration_correlation={
                    "failure_rate_vs_duration_pearson": 0.0,
                    "avg_duration_failed_turns": 0.0,
                    "avg_duration_successful_turns": 0.0,
                },
            )

        total_turns = len(self._turns)
        total_calls = sum(t.n_tool_calls for t in self._turns)
        total_failures = sum(t.n_tool_failures for t in self._turns)
        overall_success_rate = (
            (total_calls - total_failures) / total_calls if total_calls else 0.0
        )

        # Per-tool stats
        tool_calls: dict[str, int] = {}
        tool_failures: dict[str, int] = {}
        tool_durations: dict[str, list[float]] = {}
        tool_errors_counter: dict[str, Counter] = {}

        for turn in self._turns:
            # tool_calls and tool_failures per tool are derived from TurnRecord
            # tools_called is deduplicated, so we use n_tool_calls for total but
            # cannot attribute exact per-tool call counts unless we had raw messages.
            # We approximate: each listed tool gets an equal share of total calls
            # *and* we count failures proportionally (best effort from TurnRecord).
            names = turn.tools_called
            n_calls = turn.n_tool_calls
            n_fails = turn.n_tool_failures
            duration = turn.duration_seconds

            if names and n_calls:
                # distribute calls across tools uniformly
                per_tool_calls = n_calls / len(names)
                # same for failures (lower bound: at least one failure per failed tool)
                per_tool_fails = n_fails / len(names) if n_fails else 0.0
                for name in names:
                    tool_calls[name] = tool_calls.get(name, 0) + per_tool_calls
                    tool_failures[name] = tool_failures.get(name, 0) + per_tool_fails
                    tool_durations.setdefault(name, []).append(duration)

            # Aggregate tool errors by tool name heuristic: assign all errors to
            # every tool in the turn (since we don't have per-tool error mapping)
            for err in turn.tool_errors:
                for name in names:
                    tool_errors_counter.setdefault(name, Counter())[err] += 1

        per_tool_stats: list[PerToolStats] = []
        for name in sorted(tool_calls):
            calls = tool_calls[name]
            fails = tool_failures.get(name, 0.0)
            successes = max(0.0, calls - fails)
            success_rate = successes / calls if calls else 0.0
            durations = tool_durations.get(name, [])
            avg_dur = sum(durations) / len(durations) if durations else 0.0
            common = tool_errors_counter.get(name, Counter()).most_common(5)
            per_tool_stats.append(
                PerToolStats(
                    name=name,
                    total_calls=int(round(calls)),
                    successes=int(round(successes)),
                    failures=int(round(fails)),
                    success_rate=success_rate,
                    avg_duration=avg_dur,
                    common_errors=common,
                )
            )

        per_tool_stats.sort(key=lambda s: (1 - s.success_rate, s.failures), reverse=True)

        most_failure_prone_tools = [
            s.name for s in sorted(per_tool_stats, key=lambda s: s.failures, reverse=True)
        ][:5]

        # Retry loop detection: turns where a single tool was called > threshold times
        # TurnRecord does not preserve per-tool call counts, so we flag every tool
        # named in tools_called when n_tool_calls > threshold and only one unique tool.
        retry_turns: dict[str, list[int]] = {}  # tool_name -> list of call counts
        for turn in self._turns:
            names = turn.tools_called
            n_calls = turn.n_tool_calls
            if len(names) == 1 and n_calls > self._retry_threshold:
                name = names[0]
                retry_turns.setdefault(name, []).append(n_calls)

        retry_patterns: list[RetryPattern] = []
        for name, calls_list in retry_turns.items():
            retry_patterns.append(
                RetryPattern(
                    tool_name=name,
                    n_turns_with_retries=len(calls_list),
                    avg_calls_per_retry_turn=sum(calls_list) / len(calls_list),
                )
            )
        retry_patterns.sort(key=lambda r: r.n_turns_with_retries, reverse=True)

        # Top error messages across all tools
        all_errors: Counter = Counter()
        for turn in self._turns:
            for err in turn.tool_errors:
                all_errors[err] += 1
        top_error_messages = all_errors.most_common(5)

        # Recovery: task completed despite tool failures
        recovery_turns = sum(
            1 for t in self._turns if t.n_tool_failures > 0 and t.task_completed
        )
        turns_with_failures = sum(1 for t in self._turns if t.n_tool_failures > 0)
        recovery_rate = recovery_turns / turns_with_failures if turns_with_failures else 0.0

        # Weekly summaries
        weekly: dict[str, dict[str, int]] = {}
        for turn in self._turns:
            tag = turn.week_tag
            weekly.setdefault(tag, {"calls": 0, "failures": 0})
            weekly[tag]["calls"] += turn.n_tool_calls
            weekly[tag]["failures"] += turn.n_tool_failures

        weekly_summaries: list[WeeklyToolSummary] = []
        for tag in sorted(weekly):
            data = weekly[tag]
            calls = data["calls"]
            failures = data["failures"]
            weekly_summaries.append(
                WeeklyToolSummary(
                    week_tag=tag,
                    n_calls=calls,
                    n_failures=failures,
                    failure_rate=failures / calls if calls else 0.0,
                )
            )

        # Duration correlation: compare failure rate vs duration per turn
        failure_rates = []
        durations = []
        failed_durations = []
        successful_durations = []
        for turn in self._turns:
            if turn.n_tool_calls > 0:
                fr = turn.n_tool_failures / turn.n_tool_calls
                failure_rates.append(fr)
                durations.append(turn.duration_seconds)
                if turn.n_tool_failures > 0:
                    failed_durations.append(turn.duration_seconds)
                else:
                    successful_durations.append(turn.duration_seconds)

        duration_correlation = {
            "failure_rate_vs_duration_pearson": round(_pearson_r(failure_rates, durations), 4),
            "avg_duration_failed_turns": round(
                statistics.mean(failed_durations) if failed_durations else 0.0, 2
            ),
            "avg_duration_successful_turns": round(
                statistics.mean(successful_durations) if successful_durations else 0.0, 2
            ),
        }

        return ToolSuccessResult(
            total_turns=total_turns,
            total_tool_calls=total_calls,
            total_tool_failures=total_failures,
            overall_success_rate=overall_success_rate,
            per_tool_stats=per_tool_stats,
            most_failure_prone_tools=most_failure_prone_tools,
            retry_patterns=retry_patterns,
            top_error_messages=top_error_messages,
            recovery_turns=recovery_turns,
            recovery_rate=recovery_rate,
            weekly_summaries=weekly_summaries,
            duration_correlation=duration_correlation,
        )
