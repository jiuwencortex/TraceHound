# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Conversation length analyzer.

``conversation_length`` is available on every turn but is only used as a
minor penalty term in the quality formula.  This analyzer treats it as a
first-class diagnostic signal:

- Distribution: min / median / p90 / max
- Quality by length bucket: short (1) / medium (2-3) / long (4-5) / very long (6+)
- Per-component: which components correlate with longer conversations
- Flags components whose presence consistently inflates conversation length
  (> 1.5× the global median)
- Separates "long but successful" from "long and failed" so the developer can
  distinguish between complex-but-fine turns and genuinely broken ones.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from jiuwenswarm.trajectories_analyzer.loader import TurnRecord

_LENGTH_BUCKETS: list[tuple[str, int, int]] = [
    ("short", 1, 1),
    ("medium", 2, 3),
    ("long", 4, 5),
    ("very_long", 6, 10_000),
]
_LONG_CONV_MULTIPLIER = 1.5   # flag if component median > this × global median
_MIN_TURNS_FOR_COMPONENT = 5


@dataclass(frozen=True)
class LengthBucketStats:
    label: str           # "short" | "medium" | "long" | "very_long"
    min_length: int
    max_length: int
    n_turns: int
    mean_quality: float
    task_completion_rate: float

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "n_turns": self.n_turns,
            "mean_quality": round(self.mean_quality, 4),
            "task_completion_rate": round(self.task_completion_rate, 4),
        }


@dataclass(frozen=True)
class ComponentLengthProfile:
    name: str
    component_type: str
    n_turns: int
    median_length: float        # median conversation length when included
    global_median_length: float
    length_ratio: float         # median_length / global_median_length
    flagged_long: bool          # True if ratio > _LONG_CONV_MULTIPLIER

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "n_turns": self.n_turns,
            "median_length": round(self.median_length, 2),
            "global_median_length": round(self.global_median_length, 2),
            "length_ratio": round(self.length_ratio, 3),
            "flagged_long": self.flagged_long,
        }


@dataclass(frozen=True)
class ConversationLengthResult:
    total_turns: int
    min_length: int
    max_length: int
    mean_length: float
    median_length: float
    p90_length: float           # 90th percentile
    # long-but-successful: task_completed=True AND length >= 4
    n_long_successful: int
    n_long_failed: int
    buckets: list[LengthBucketStats]
    components_flagged_long: list[ComponentLengthProfile]   # sorted by length_ratio desc

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "mean_length": round(self.mean_length, 2),
            "median_length": round(self.median_length, 2),
            "p90_length": round(self.p90_length, 2),
            "n_long_successful": self.n_long_successful,
            "n_long_failed": self.n_long_failed,
            "buckets": [b.to_dict() for b in self.buckets],
            "components_flagged_long": [c.to_dict() for c in self.components_flagged_long],
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = (len(sorted_values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _iter_components(turn: TurnRecord):
    for s in turn.skills:
        yield s, "skill"
    for m in turn.memory_sections:
        yield m, "memory"
    for t in turn.tools:
        yield t, "tool"


class ConversationLengthAnalyzer:
    """Profile conversation length and its relationship to quality and components."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
        long_conv_multiplier: float = _LONG_CONV_MULTIPLIER,
        min_turns: int = _MIN_TURNS_FOR_COMPONENT,
    ) -> None:
        self._turns = turns
        self._qualities = qualities
        self._long_multiplier = long_conv_multiplier
        self._min_turns = min_turns

    def analyze(self) -> ConversationLengthResult:
        if not self._turns:
            return ConversationLengthResult(
                total_turns=0,
                min_length=0,
                max_length=0,
                mean_length=0.0,
                median_length=0.0,
                p90_length=0.0,
                n_long_successful=0,
                n_long_failed=0,
                buckets=[],
                components_flagged_long=[],
            )

        lengths = [t.conversation_length for t in self._turns]
        sorted_lengths = sorted(float(x) for x in lengths)

        global_median = statistics.median(lengths)
        p90 = _percentile(sorted_lengths, 90)

        n_long_successful = sum(
            1 for t in self._turns if t.conversation_length >= 4 and t.task_completed
        )
        n_long_failed = sum(
            1 for t in self._turns if t.conversation_length >= 4 and not t.task_completed
        )

        # Bucket analysis
        bucket_data: dict[str, dict] = {
            label: {"qualities": [], "completions": 0, "n": 0}
            for label, _, _ in _LENGTH_BUCKETS
        }
        for turn, quality in zip(self._turns, self._qualities):
            cl = turn.conversation_length
            for label, lo, hi in _LENGTH_BUCKETS:
                if lo <= cl <= hi:
                    bucket_data[label]["qualities"].append(quality)
                    if turn.task_completed:
                        bucket_data[label]["completions"] += 1
                    bucket_data[label]["n"] += 1
                    break

        buckets: list[LengthBucketStats] = []
        for label, lo, hi in _LENGTH_BUCKETS:
            d = bucket_data[label]
            n = d["n"]
            qs = d["qualities"]
            buckets.append(
                LengthBucketStats(
                    label=label,
                    min_length=lo,
                    max_length=hi,
                    n_turns=n,
                    mean_quality=sum(qs) / len(qs) if qs else 0.0,
                    task_completion_rate=d["completions"] / n if n else 0.0,
                )
            )

        # Per-component median length
        comp_lengths: dict[tuple[str, str], list[int]] = {}
        for turn in self._turns:
            for name, ctype in _iter_components(turn):
                comp_lengths.setdefault((name, ctype), []).append(turn.conversation_length)

        flagged: list[ComponentLengthProfile] = []
        for (name, ctype), comp_lens in comp_lengths.items():
            if len(comp_lens) < self._min_turns:
                continue
            comp_median = statistics.median(comp_lens)
            ratio = comp_median / global_median if global_median > 0 else 1.0
            if ratio >= self._long_multiplier:
                flagged.append(
                    ComponentLengthProfile(
                        name=name,
                        component_type=ctype,
                        n_turns=len(comp_lens),
                        median_length=float(comp_median),
                        global_median_length=float(global_median),
                        length_ratio=ratio,
                        flagged_long=True,
                    )
                )

        flagged.sort(key=lambda c: c.length_ratio, reverse=True)

        return ConversationLengthResult(
            total_turns=len(self._turns),
            min_length=min(lengths),
            max_length=max(lengths),
            mean_length=sum(lengths) / len(lengths),
            median_length=float(global_median),
            p90_length=p90,
            n_long_successful=n_long_successful,
            n_long_failed=n_long_failed,
            buckets=buckets,
            components_flagged_long=flagged,
        )
