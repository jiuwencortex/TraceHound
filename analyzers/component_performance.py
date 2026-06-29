# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Component performance analyzer.

For every skill, memory section, and tool found across all turns, computes:
  - mean quality when the component was included in context
  - task completion rate
  - follow-up correction rate

Components that fall below configurable thresholds are flagged as bottlenecks.

Each flagged component receives a **severity score** (0–1) that combines how
bad it is with how many users it affects, so developers can triage what to fix
first.  Components are also aggregated by type (skill / memory / tool) to give
a high-level view of where context budget is being spent effectively.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord

_DEFAULT_QUALITY_DEFICIT = 0.15   # component mean quality > global_mean - threshold → flagged
_DEFAULT_CORRECTION_RATE = 0.30   # correction rate above this → flagged
_DEFAULT_COMPLETION_RATE = 0.50   # task completion below this → flagged
_MIN_TURNS_FOR_FLAG = 5            # don't flag components with fewer turns


@dataclass(frozen=True)
class ComponentStats:
    name: str
    component_type: str    # "skill" | "memory" | "tool"
    n_turns_included: int
    mean_quality: float
    task_completion_rate: float
    correction_rate: float
    flags: list[str]       # e.g. ["low_quality", "high_correction_rate"]
    severity_score: float  # 0–1; higher = fix this first (only non-zero when flagged)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "n_turns_included": self.n_turns_included,
            "mean_quality": round(self.mean_quality, 4),
            "task_completion_rate": round(self.task_completion_rate, 4),
            "correction_rate": round(self.correction_rate, 4),
            "flags": list(self.flags),
            "severity_score": round(self.severity_score, 4),
        }


@dataclass(frozen=True)
class TypeBreakdown:
    """Aggregate statistics for one component type (skill / memory / tool)."""

    component_type: str
    n_components: int          # distinct components of this type
    total_inclusions: int      # sum of n_turns_included across all components of this type
    budget_fraction: float     # total_inclusions / grand_total_inclusions
    mean_quality: float        # weighted mean quality (weighted by n_turns_included)
    mean_task_completion: float
    mean_correction_rate: float
    n_flagged: int             # how many components of this type are flagged

    def to_dict(self) -> dict:
        return {
            "component_type": self.component_type,
            "n_components": self.n_components,
            "total_inclusions": self.total_inclusions,
            "budget_fraction": round(self.budget_fraction, 4),
            "mean_quality": round(self.mean_quality, 4),
            "mean_task_completion": round(self.mean_task_completion, 4),
            "mean_correction_rate": round(self.mean_correction_rate, 4),
            "n_flagged": self.n_flagged,
        }


@dataclass(frozen=True)
class ComponentPerformanceResult:
    global_mean_quality: float
    components: list[ComponentStats]          # all components, sorted by mean_quality asc
    flagged_components: list[ComponentStats]  # subset with at least one flag
    top_priority_fixes: list[ComponentStats]  # top-5 flagged by severity_score desc
    type_breakdown: list[TypeBreakdown]       # one entry per component type

    def to_dict(self) -> dict:
        return {
            "global_mean_quality": round(self.global_mean_quality, 4),
            "components": [c.to_dict() for c in self.components],
            "flagged_components": [c.to_dict() for c in self.flagged_components],
            "top_priority_fixes": [c.to_dict() for c in self.top_priority_fixes],
            "type_breakdown": [t.to_dict() for t in self.type_breakdown],
        }


def _get_component_names(turn: TurnRecord) -> list[tuple[str, str]]:
    """Return (name, type) pairs for all components included in a turn's context."""
    result: list[tuple[str, str]] = []
    for s in turn.skills:
        result.append((s, "skill"))
    for m in turn.memory_sections:
        result.append((m, "memory"))
    for t in turn.tools:
        result.append((t, "tool"))
    return result


def _compute_severity(
    mean_quality: float,
    global_mean: float,
    correction_rate: float,
    task_completion_rate: float,
    n_turns: int,
) -> float:
    """Raw (un-normalised) severity score for a flagged component.

    Combines quality deficit × exposure, correction load, and task failures.
    Weights:
      quality deficit: 2.0  — quality gap felt by every affected user
      correction load: 1.5  — follow-up corrections are high user frustration
      completion miss: 1.0  — incomplete tasks are bad but already captured by quality
    """
    quality_deficit = max(0.0, global_mean - mean_quality)
    return (
        quality_deficit * n_turns * 2.0
        + correction_rate * n_turns * 1.5
        + (1.0 - task_completion_rate) * n_turns * 1.0
    )


class ComponentPerformanceAnalyzer:
    """Analyze per-component quality, completion, and correction rates."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
        quality_deficit_threshold: float = _DEFAULT_QUALITY_DEFICIT,
        correction_rate_threshold: float = _DEFAULT_CORRECTION_RATE,
        completion_rate_threshold: float = _DEFAULT_COMPLETION_RATE,
        min_turns_for_flag: int = _MIN_TURNS_FOR_FLAG,
    ) -> None:
        self._turns = turns
        self._qualities = qualities
        self._quality_deficit = quality_deficit_threshold
        self._correction_threshold = correction_rate_threshold
        self._completion_threshold = completion_rate_threshold
        self._min_turns = min_turns_for_flag

    def analyze(self) -> ComponentPerformanceResult:
        global_mean = sum(self._qualities) / len(self._qualities) if self._qualities else 0.0

        # Accumulate per-component data
        data: dict[tuple[str, str], dict] = {}  # (name, type) → stats dict

        for turn, quality in zip(self._turns, self._qualities):
            for name, ctype in _get_component_names(turn):
                key = (name, ctype)
                if key not in data:
                    data[key] = {"qualities": [], "completed": 0, "corrections": 0}
                d = data[key]
                d["qualities"].append(quality)
                if turn.task_completed:
                    d["completed"] += 1
                if turn.follow_up_correction:
                    d["corrections"] += 1

        quality_floor = global_mean - self._quality_deficit

        # First pass: build ComponentStats without normalised severity
        raw_stats: list[tuple[ComponentStats, float]] = []  # (stats, raw_severity)

        for (name, ctype), d in data.items():
            qs = d["qualities"]
            n = len(qs)
            mean_q = sum(qs) / n
            completion_rate = d["completed"] / n
            correction_rate = d["corrections"] / n

            flags: list[str] = []
            if n < self._min_turns:
                flags.append("insufficient_data")
            else:
                if mean_q < quality_floor:
                    flags.append("low_quality")
                if correction_rate > self._correction_threshold:
                    flags.append("high_correction_rate")
                if completion_rate < self._completion_threshold:
                    flags.append("low_task_completion")

            is_flagged_real = flags and "insufficient_data" not in flags
            raw_sev = (
                _compute_severity(mean_q, global_mean, correction_rate, completion_rate, n)
                if is_flagged_real
                else 0.0
            )
            raw_stats.append(
                (
                    ComponentStats(
                        name=name,
                        component_type=ctype,
                        n_turns_included=n,
                        mean_quality=mean_q,
                        task_completion_rate=completion_rate,
                        correction_rate=correction_rate,
                        flags=flags,
                        severity_score=0.0,  # placeholder; replaced below
                    ),
                    raw_sev,
                )
            )

        # Normalise severity scores to [0, 1]
        max_raw = max((rs for _, rs in raw_stats), default=1.0) or 1.0

        components: list[ComponentStats] = []
        for stats, raw_sev in raw_stats:
            normalised = raw_sev / max_raw
            components.append(
                ComponentStats(
                    name=stats.name,
                    component_type=stats.component_type,
                    n_turns_included=stats.n_turns_included,
                    mean_quality=stats.mean_quality,
                    task_completion_rate=stats.task_completion_rate,
                    correction_rate=stats.correction_rate,
                    flags=stats.flags,
                    severity_score=normalised,
                )
            )

        components.sort(key=lambda c: c.mean_quality)
        flagged = [c for c in components if c.flags and "insufficient_data" not in c.flags]
        top_priority = sorted(flagged, key=lambda c: c.severity_score, reverse=True)[:5]

        # Type breakdown
        type_breakdown = _build_type_breakdown(components, flagged)

        return ComponentPerformanceResult(
            global_mean_quality=global_mean,
            components=components,
            flagged_components=flagged,
            top_priority_fixes=top_priority,
            type_breakdown=type_breakdown,
        )


def _build_type_breakdown(
    all_components: list[ComponentStats],
    flagged: list[ComponentStats],
) -> list[TypeBreakdown]:
    type_data: dict[str, dict] = {}
    flagged_set = {(c.name, c.component_type) for c in flagged}

    grand_total = sum(c.n_turns_included for c in all_components) or 1

    for c in all_components:
        t = c.component_type
        if t not in type_data:
            type_data[t] = {
                "n": 0,
                "inclusions": 0,
                "quality_weighted": 0.0,
                "completion_weighted": 0.0,
                "correction_weighted": 0.0,
                "n_flagged": 0,
            }
        d = type_data[t]
        d["n"] += 1
        d["inclusions"] += c.n_turns_included
        d["quality_weighted"] += c.mean_quality * c.n_turns_included
        d["completion_weighted"] += c.task_completion_rate * c.n_turns_included
        d["correction_weighted"] += c.correction_rate * c.n_turns_included
        if (c.name, c.component_type) in flagged_set:
            d["n_flagged"] += 1

    breakdown: list[TypeBreakdown] = []
    for ctype in ("skill", "memory", "tool"):
        if ctype not in type_data:
            continue
        d = type_data[ctype]
        inc = d["inclusions"] or 1
        breakdown.append(
            TypeBreakdown(
                component_type=ctype,
                n_components=d["n"],
                total_inclusions=d["inclusions"],
                budget_fraction=d["inclusions"] / grand_total,
                mean_quality=d["quality_weighted"] / inc,
                mean_task_completion=d["completion_weighted"] / inc,
                mean_correction_rate=d["correction_weighted"] / inc,
                n_flagged=d["n_flagged"],
            )
        )

    return breakdown
