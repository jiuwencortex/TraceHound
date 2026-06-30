# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""User query patterns analyzer.

Analyzes user query patterns from jiuwenswarm session logs:
- query length distribution and bucketing
- query type classification (coding, file_op, question, analysis, debug, general)
- quality and completion rates per bucket / type
- correlation between query length and duration / token usage
- tool usage by query type
- weekly average query length trends
- longest and shortest queries
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from ..loader import TurnRecord

_LENGTH_BUCKETS: list[tuple[str, int, int]] = [
    ("short", 0, 100),
    ("medium", 101, 300),
    ("long", 301, 800),
    ("very_long", 801, 1_000_000),
]

_FILE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".r",
    ".m",
    ".mm",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".pl",
    ".pm",
    ".lua",
    ".vim",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".xml",
    ".md",
    ".rst",
    ".dockerfile",
}

_QUESTION_WORDS = {"who", "what", "where", "when", "why", "how"}

_ANALYSIS_WORDS = {"analyze", "compare", "evaluate", "review", "summarize"}

_DEBUG_WORDS = {"error", "fix", "bug", "crash", "fails", "broken"}

_FILE_OP_WORDS = {"read", "write", "delete", "create file"}


@dataclass(frozen=True)
class LengthBucket:
    label: str
    min_chars: int
    max_chars: int
    n_turns: int
    mean_quality: float
    completion_rate: float

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "n_turns": self.n_turns,
            "mean_quality": round(self.mean_quality, 4),
            "completion_rate": round(self.completion_rate, 4),
        }


@dataclass(frozen=True)
class QueryTypeSummary:
    type_label: str
    count: int
    mean_quality: float
    mean_duration: float
    mean_tokens: float

    def to_dict(self) -> dict:
        return {
            "type_label": self.type_label,
            "count": self.count,
            "mean_quality": round(self.mean_quality, 4),
            "mean_duration": round(self.mean_duration, 2),
            "mean_tokens": round(self.mean_tokens, 2),
        }


@dataclass(frozen=True)
class WeeklyQuerySummary:
    week_tag: str
    avg_length: float
    n_queries: int

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "avg_length": round(self.avg_length, 2),
            "n_queries": self.n_queries,
        }


@dataclass(frozen=True)
class UserQueryResult:
    total_turns: int
    length_min: int
    length_median: float
    length_mean: float
    length_p90: float
    length_max: int
    length_buckets: list[LengthBucket]
    query_type_distribution: list[QueryTypeSummary]
    most_common_type: str | None
    best_quality_type: str | None
    length_vs_duration_correlation: float
    length_vs_tokens_correlation: float
    most_tool_heavy_type: str | None
    weekly_summaries: list[WeeklyQuerySummary]
    longest_queries: list[dict]
    shortest_queries: list[dict]

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "length_min": self.length_min,
            "length_median": round(self.length_median, 2),
            "length_mean": round(self.length_mean, 2),
            "length_p90": round(self.length_p90, 2),
            "length_max": self.length_max,
            "length_buckets": [b.to_dict() for b in self.length_buckets],
            "query_type_distribution": [t.to_dict() for t in self.query_type_distribution],
            "most_common_type": self.most_common_type,
            "best_quality_type": self.best_quality_type,
            "length_vs_duration_correlation": round(self.length_vs_duration_correlation, 4),
            "length_vs_tokens_correlation": round(self.length_vs_tokens_correlation, 4),
            "most_tool_heavy_type": self.most_tool_heavy_type,
            "weekly_summaries": [w.to_dict() for w in self.weekly_summaries],
            "longest_queries": self.longest_queries,
            "shortest_queries": self.shortest_queries,
        }


def _classify_query(query: str) -> str:
    """Classify a user query into one of several heuristic types."""
    text = query.lower()
    has_code_block = "```" in query
    has_file_ext = any(ext in text for ext in _FILE_EXTENSIONS)
    has_func_def = bool(re.search(r"\b(def\s+\w+|function\s+\w+|class\s+\w+)", text))
    has_file_path = bool(re.search(r"[\w\-./\\]+\.[a-zA-Z]{2,6}", query))

    # coding
    if has_code_block or has_file_ext or has_func_def:
        return "coding"

    # file_op
    if has_file_path or any(op in text for op in _FILE_OP_WORDS):
        return "file_op"

    # debug
    if any(word in text for word in _DEBUG_WORDS):
        return "debug"

    # analysis
    if any(word in text for word in _ANALYSIS_WORDS):
        return "analysis"

    # question
    stripped = text.strip()
    first_word = stripped.split()[0] if stripped else ""
    is_question = stripped.endswith("?") and first_word in _QUESTION_WORDS and not has_code_block
    if is_question:
        return "question"

    return "general"


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Return Pearson correlation coefficient, or 0.0 if undefined."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    if denom_x <= 0 or denom_y <= 0:
        return 0.0
    return num / (denom_x ** 0.5 * denom_y ** 0.5)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = (len(sorted_values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


class UserQueryAnalyzer:
    """Analyze user query patterns from jiuwenswarm session logs."""

    def __init__(self, turns: list[TurnRecord], qualities: list[float]) -> None:
        self._turns = turns
        self._qualities = qualities

    def analyze(self) -> UserQueryResult:
        # Filter out heartbeats
        pairs = [
            (turn, quality)
            for turn, quality in zip(self._turns, self._qualities)
            if not turn.is_heartbeat
        ]

        if not pairs:
            return UserQueryResult(
                total_turns=0,
                length_min=0,
                length_median=0.0,
                length_mean=0.0,
                length_p90=0.0,
                length_max=0,
                length_buckets=[],
                query_type_distribution=[],
                most_common_type=None,
                best_quality_type=None,
                length_vs_duration_correlation=0.0,
                length_vs_tokens_correlation=0.0,
                most_tool_heavy_type=None,
                weekly_summaries=[],
                longest_queries=[],
                shortest_queries=[],
            )

        turns = [t for t, _ in pairs]
        qualities = [q for _, q in pairs]
        lengths = [t.user_query_length for t in turns]
        sorted_lengths = sorted(float(x) for x in lengths)

        length_min = min(lengths)
        length_max = max(lengths)
        length_mean = sum(lengths) / len(lengths)
        length_median = statistics.median(lengths)
        length_p90 = _percentile(sorted_lengths, 90)

        # Length buckets
        bucket_data: dict[str, dict] = {
            label: {"qualities": [], "completions": 0, "n": 0}
            for label, _, _ in _LENGTH_BUCKETS
        }
        for turn, quality in pairs:
            ql = turn.user_query_length
            for label, lo, hi in _LENGTH_BUCKETS:
                if lo <= ql <= hi:
                    bucket_data[label]["qualities"].append(quality)
                    if turn.task_completed:
                        bucket_data[label]["completions"] += 1
                    bucket_data[label]["n"] += 1
                    break

        length_buckets: list[LengthBucket] = []
        for label, lo, hi in _LENGTH_BUCKETS:
            d = bucket_data[label]
            n = d["n"]
            qs = d["qualities"]
            length_buckets.append(
                LengthBucket(
                    label=label,
                    min_chars=lo,
                    max_chars=hi,
                    n_turns=n,
                    mean_quality=sum(qs) / len(qs) if qs else 0.0,
                    completion_rate=d["completions"] / n if n else 0.0,
                )
            )

        # Query type classification
        type_data: dict[str, dict] = {}
        for turn, quality in pairs:
            qtype = _classify_query(turn.user_query)
            d = type_data.setdefault(
                qtype,
                {"qualities": [], "durations": [], "tokens": [], "tool_counts": [], "n": 0},
            )
            d["qualities"].append(quality)
            d["durations"].append(turn.duration_seconds)
            d["tokens"].append(turn.total_tokens)
            d["tool_counts"].append(len(turn.tools_called))
            d["n"] += 1

        query_type_distribution: list[QueryTypeSummary] = []
        for qtype, d in sorted(type_data.items(), key=lambda x: x[1]["n"], reverse=True):
            n = d["n"]
            query_type_distribution.append(
                QueryTypeSummary(
                    type_label=qtype,
                    count=n,
                    mean_quality=sum(d["qualities"]) / n,
                    mean_duration=sum(d["durations"]) / n,
                    mean_tokens=sum(d["tokens"]) / n,
                )
            )

        most_common_type = (
            query_type_distribution[0].type_label if query_type_distribution else None
        )

        best_quality_type = None
        if query_type_distribution:
            best_quality_type = max(
                query_type_distribution, key=lambda t: t.mean_quality
            ).type_label

        # Correlations
        durations = [t.duration_seconds for t in turns]
        tokens = [t.total_tokens for t in turns]
        length_vs_duration_correlation = _pearson_r(sorted_lengths, durations)
        length_vs_tokens_correlation = _pearson_r(sorted_lengths, tokens)

        # Most tool-heavy type
        most_tool_heavy_type = None
        if type_data:
            most_tool_heavy_type = max(
                type_data.items(),
                key=lambda x: sum(x[1]["tool_counts"]) / x[1]["n"] if x[1]["n"] else 0.0,
            )[0]

        # Weekly summaries
        week_order: list[str] = []
        week_data: dict[str, list[int]] = {}
        for turn in turns:
            wt = turn.week_tag
            if wt not in week_data:
                week_order.append(wt)
                week_data[wt] = []
            week_data[wt].append(turn.user_query_length)

        weekly_summaries: list[WeeklyQuerySummary] = []
        for wt in week_order:
            qls = week_data[wt]
            weekly_summaries.append(
                WeeklyQuerySummary(
                    week_tag=wt,
                    avg_length=sum(qls) / len(qls),
                    n_queries=len(qls),
                )
            )

        # Longest / shortest queries
        sorted_by_length = sorted(pairs, key=lambda p: p[0].user_query_length)
        shortest_queries = [
            {
                "user_query": turn.user_query[:200],
                "length": turn.user_query_length,
                "type": _classify_query(turn.user_query),
                "quality": round(quality, 4),
            }
            for turn, quality in sorted_by_length[:5]
        ]
        longest_queries = [
            {
                "user_query": turn.user_query[:200],
                "length": turn.user_query_length,
                "type": _classify_query(turn.user_query),
                "quality": round(quality, 4),
            }
            for turn, quality in sorted_by_length[-5:][::-1]
        ]

        return UserQueryResult(
            total_turns=len(turns),
            length_min=length_min,
            length_median=length_median,
            length_mean=length_mean,
            length_p90=length_p90,
            length_max=length_max,
            length_buckets=length_buckets,
            query_type_distribution=query_type_distribution,
            most_common_type=most_common_type,
            best_quality_type=best_quality_type,
            length_vs_duration_correlation=length_vs_duration_correlation,
            length_vs_tokens_correlation=length_vs_tokens_correlation,
            most_tool_heavy_type=most_tool_heavy_type,
            weekly_summaries=weekly_summaries,
            longest_queries=longest_queries,
            shortest_queries=shortest_queries,
        )
