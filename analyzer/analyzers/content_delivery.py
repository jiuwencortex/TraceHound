# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content delivery analyzer.

Analyzes content delivered by the agent (final responses and files) from
jiuwenswarm session logs.

Produces:
  - Response length distribution (min / median / mean / p90 / max characters)
  - Response buckets ("terse"/"normal"/"verbose"/"essay") and their quality scores
  - File delivery frequency (files per turn, files per session)
  - Productive turns and productivity rate
  - Response length correlation with token usage and user query length
  - Tool-to-content ratio: turns with many tools but short responses
  - Per-week content delivery trends
  - Sessions with highest file delivery counts
  - Silent successes: zero response length but task_completed=True
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass

from ..loader import TurnRecord

_RESPONSE_BUCKETS: list[tuple[str, int, int]] = [
    ("terse", 0, 99),
    ("normal", 100, 499),
    ("verbose", 500, 1499),
    ("essay", 1500, 1_000_000),
]
_SHORT_RESPONSE_TOOL_THRESHOLD = 3  # n_tool_calls > this with final_response_length < 100


@dataclass(frozen=True)
class ResponseBucket:
    label: str
    char_range: str
    n_turns: int
    mean_quality: float

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "char_range": self.char_range,
            "n_turns": self.n_turns,
            "mean_quality": round(self.mean_quality, 4),
        }


@dataclass(frozen=True)
class WeeklyDeliverySummary:
    week_tag: str
    avg_response_length: float
    n_files: int
    n_productive_turns: int

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "avg_response_length": round(self.avg_response_length, 2),
            "n_files": self.n_files,
            "n_productive_turns": self.n_productive_turns,
        }


@dataclass(frozen=True)
class SessionDeliveryProfile:
    session_id: str
    total_response_chars: int
    total_files: int
    n_turns: int

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "total_response_chars": self.total_response_chars,
            "total_files": self.total_files,
            "n_turns": self.n_turns,
        }


@dataclass(frozen=True)
class ContentDeliveryResult:
    total_turns: int

    # Response length distribution
    response_length_min: int
    response_length_median: float
    response_length_mean: float
    response_length_p90: float
    response_length_max: int

    # Response buckets
    response_buckets: list[ResponseBucket]

    # File delivery
    total_files_delivered: int
    avg_files_per_turn: float
    avg_files_per_session: float
    sessions_with_files: int

    # Productivity
    productive_turns: int
    productivity_rate: float

    # Silent success
    silent_success_turns: int

    # Tool-to-content
    tool_to_content_flagged: int
    tool_to_content_rate: float

    # Correlations
    response_token_correlation: float
    response_query_length_correlation: float

    # Per-week
    weekly_summaries: list[WeeklyDeliverySummary]

    # Sessions
    top_file_sessions: list[SessionDeliveryProfile]

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "response_length_min": self.response_length_min,
            "response_length_median": round(self.response_length_median, 2),
            "response_length_mean": round(self.response_length_mean, 2),
            "response_length_p90": round(self.response_length_p90, 2),
            "response_length_max": self.response_length_max,
            "response_buckets": [b.to_dict() for b in self.response_buckets],
            "total_files_delivered": self.total_files_delivered,
            "avg_files_per_turn": round(self.avg_files_per_turn, 4),
            "avg_files_per_session": round(self.avg_files_per_session, 4),
            "sessions_with_files": self.sessions_with_files,
            "productive_turns": self.productive_turns,
            "productivity_rate": round(self.productivity_rate, 4),
            "silent_success_turns": self.silent_success_turns,
            "tool_to_content_flagged": self.tool_to_content_flagged,
            "tool_to_content_rate": round(self.tool_to_content_rate, 4),
            "response_token_correlation": round(self.response_token_correlation, 4),
            "response_query_length_correlation": round(self.response_query_length_correlation, 4),
            "weekly_summaries": [w.to_dict() for w in self.weekly_summaries],
            "top_file_sessions": [s.to_dict() for s in self.top_file_sessions],
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


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = (len(sorted_values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


class ContentDeliveryAnalyzer:
    """Analyze agent content delivery patterns."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
    ) -> None:
        pairs = [(t, q) for t, q in zip(turns, qualities) if not t.is_heartbeat]
        self._turns = [t for t, _ in pairs]
        self._qualities = [q for _, q in pairs]

    def analyze(self) -> ContentDeliveryResult:
        if not self._turns:
            return self._empty_result()

        n_total = len(self._turns)

        all_qualities = self._qualities

        # --- Response length distribution ---
        response_lengths = [t.final_response_length for t in self._turns]
        sorted_lengths = sorted(float(x) for x in response_lengths)

        response_length_min = min(response_lengths)
        response_length_max = max(response_lengths)
        response_length_mean = sum(response_lengths) / n_total
        response_length_median = statistics.median(response_lengths)
        response_length_p90 = _percentile(sorted_lengths, 90)

        # --- Response buckets ---
        bucket_data: dict[str, dict] = {
            label: {"qualities": [], "n": 0}
            for label, _, _ in _RESPONSE_BUCKETS
        }
        for turn, quality in zip(self._turns, all_qualities):
            rl = turn.final_response_length
            for label, lo, hi in _RESPONSE_BUCKETS:
                if lo <= rl <= hi:
                    bucket_data[label]["qualities"].append(quality)
                    bucket_data[label]["n"] += 1
                    break

        response_buckets: list[ResponseBucket] = []
        for label, lo, hi in _RESPONSE_BUCKETS:
            d = bucket_data[label]
            qs = d["qualities"]
            char_range = f"{lo}-{hi}" if hi < 1_000_000 else f"{lo}+"
            response_buckets.append(
                ResponseBucket(
                    label=label,
                    char_range=char_range,
                    n_turns=d["n"],
                    mean_quality=sum(qs) / len(qs) if qs else 0.0,
                )
            )

        # --- File delivery ---
        total_files = sum(t.files_delivered for t in self._turns)
        avg_files_per_turn = total_files / n_total if n_total else 0.0

        session_files: Counter = Counter()
        for t in self._turns:
            if t.files_delivered:
                session_files[t.session_id] += t.files_delivered
        n_sessions = len({t.session_id for t in self._turns})
        sessions_with_files = len(session_files)
        avg_files_per_session = total_files / n_sessions if n_sessions else 0.0

        # --- Productive turns ---
        productive_turns = 0
        for t in self._turns:
            if t.files_delivered > 0 or t.final_response_length > 100:
                productive_turns += 1
        productivity_rate = productive_turns / n_total if n_total else 0.0

        # --- Silent success: zero response length but task_completed=True ---
        silent_success_turns = sum(
            1
            for t in self._turns
            if t.final_response_length == 0 and t.task_completed
        )

        # --- Tool-to-content ratio ---
        tool_to_content_flagged = sum(
            1
            for t in self._turns
            if t.n_tool_calls > _SHORT_RESPONSE_TOOL_THRESHOLD
            and t.final_response_length < 100
        )
        tool_to_content_rate = (
            tool_to_content_flagged / n_total if n_total else 0.0
        )

        # --- Correlations ---
        # Response length vs total_tokens
        valid_token_pairs = [
            (float(t.final_response_length), float(t.total_tokens))
            for t in self._turns
            if t.total_tokens > 0
        ]
        response_token_correlation = (
            _pearson_r([x for x, _ in valid_token_pairs], [y for _, y in valid_token_pairs])
            if len(valid_token_pairs) >= 2
            else 0.0
        )

        # Response length vs user_query_length
        valid_query_pairs = [
            (float(t.final_response_length), float(t.user_query_length))
            for t in self._turns
        ]
        response_query_length_correlation = (
            _pearson_r([x for x, _ in valid_query_pairs], [y for _, y in valid_query_pairs])
            if len(valid_query_pairs) >= 2
            else 0.0
        )

        # --- Per-week summaries ---
        week_order: list[str] = []
        week_data: dict[str, dict] = {}
        for t in self._turns:
            wt = t.week_tag
            if wt not in week_data:
                week_order.append(wt)
                week_data[wt] = {
                    "response_lengths": [],
                    "files": 0,
                    "productive": 0,
                }
            d = week_data[wt]
            d["response_lengths"].append(t.final_response_length)
            d["files"] += t.files_delivered
            if t.files_delivered > 0 or t.final_response_length > 100:
                d["productive"] += 1

        weekly_summaries: list[WeeklyDeliverySummary] = []
        for wt in week_order:
            d = week_data[wt]
            rls = d["response_lengths"]
            weekly_summaries.append(
                WeeklyDeliverySummary(
                    week_tag=wt,
                    avg_response_length=sum(rls) / len(rls) if rls else 0.0,
                    n_files=d["files"],
                    n_productive_turns=d["productive"],
                )
            )

        # --- Session profiles: top by file delivery ---
        session_profiles: dict[str, dict] = {}
        for t in self._turns:
            sid = t.session_id
            session_profiles.setdefault(
                sid,
                {"total_response_chars": 0, "total_files": 0, "n_turns": 0},
            )
            sp = session_profiles[sid]
            sp["total_response_chars"] += t.final_response_length
            sp["total_files"] += t.files_delivered
            sp["n_turns"] += 1

        profiles: list[SessionDeliveryProfile] = [
            SessionDeliveryProfile(
                session_id=sid,
                total_response_chars=d["total_response_chars"],
                total_files=d["total_files"],
                n_turns=d["n_turns"],
            )
            for sid, d in session_profiles.items()
        ]
        profiles.sort(key=lambda p: p.total_files, reverse=True)
        top_file_sessions = profiles[:10]

        return ContentDeliveryResult(
            total_turns=n_total,
            response_length_min=response_length_min,
            response_length_median=response_length_median,
            response_length_mean=response_length_mean,
            response_length_p90=response_length_p90,
            response_length_max=response_length_max,
            response_buckets=response_buckets,
            total_files_delivered=total_files,
            avg_files_per_turn=avg_files_per_turn,
            avg_files_per_session=avg_files_per_session,
            sessions_with_files=sessions_with_files,
            productive_turns=productive_turns,
            productivity_rate=productivity_rate,
            silent_success_turns=silent_success_turns,
            tool_to_content_flagged=tool_to_content_flagged,
            tool_to_content_rate=tool_to_content_rate,
            response_token_correlation=response_token_correlation,
            response_query_length_correlation=response_query_length_correlation,
            weekly_summaries=weekly_summaries,
            top_file_sessions=top_file_sessions,
        )

    def _empty_result(self) -> ContentDeliveryResult:
        return ContentDeliveryResult(
            total_turns=0,
            response_length_min=0,
            response_length_median=0.0,
            response_length_mean=0.0,
            response_length_p90=0.0,
            response_length_max=0,
            response_buckets=[
                ResponseBucket(
                    label=label,
                    char_range=f"{lo}-{hi}" if hi < 1_000_000 else f"{lo}+",
                    n_turns=0,
                    mean_quality=0.0,
                )
                for label, lo, hi in _RESPONSE_BUCKETS
            ],
            total_files_delivered=0,
            avg_files_per_turn=0.0,
            avg_files_per_session=0.0,
            sessions_with_files=0,
            productive_turns=0,
            productivity_rate=0.0,
            silent_success_turns=0,
            tool_to_content_flagged=0,
            tool_to_content_rate=0.0,
            response_token_correlation=0.0,
            response_query_length_correlation=0.0,
            weekly_summaries=[],
            top_file_sessions=[],
        )
