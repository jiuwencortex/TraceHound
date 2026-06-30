# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Error categories and trends analyzer.

Categorizes and trends errors from jiuwenswarm session logs, producing:

- Overall error rate and distribution by category
- Most common error messages per category
- Session-level error profiles and recovery rates
- Per-week error trends
- Tool-specific error associations
- Persistent (systemic) error detection

Heartbeat turns are excluded from analysis.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from ..loader import TurnRecord

_KNOWN_CATEGORIES: list[str] = [
    "import",
    "syntax",
    "api_auth",
    "timeout",
    "filesystem",
    "model",
    "network",
    "execution",
    "other",
]
_TOP_EXAMPLES = 3
_MIN_TURNS_FOR_TOOL_ERR_RATE = 5


@dataclass(frozen=True)
class CategoryStats:
    """Aggregate statistics for a single error category."""

    category: str
    count: int
    percentage_of_errors: float
    example_messages: list[str]
    affected_sessions: int

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "count": self.count,
            "percentage_of_errors": round(self.percentage_of_errors, 4),
            "example_messages": self.example_messages,
            "affected_sessions": self.affected_sessions,
        }


@dataclass(frozen=True)
class SessionErrorProfile:
    """Error profile for a single session."""

    session_id: str
    error_count: int
    error_categories: list[str]
    recovery_rate: float

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "error_count": self.error_count,
            "error_categories": self.error_categories,
            "recovery_rate": round(self.recovery_rate, 4),
        }


@dataclass(frozen=True)
class WeeklyErrorSummary:
    """Error summary for a single week."""

    week_tag: str
    total_turns: int
    error_count: int
    top_category: str

    def to_dict(self) -> dict:
        return {
            "week_tag": self.week_tag,
            "total_turns": self.total_turns,
            "error_count": self.error_count,
            "top_category": self.top_category,
        }


@dataclass(frozen=True)
class ErrorCategoryResult:
    """Top-level result of the error categories analyzer."""

    total_turns: int
    error_turns: int
    overall_error_rate: float
    categories: list[CategoryStats]
    session_profiles: list[SessionErrorProfile]
    recovery_rate: float
    weekly_summaries: list[WeeklyErrorSummary]
    tool_error_associations: list[dict]
    persistent_error_categories: list[str]

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "error_turns": self.error_turns,
            "overall_error_rate": round(self.overall_error_rate, 4),
            "categories": [c.to_dict() for c in self.categories],
            "session_profiles": [s.to_dict() for s in self.session_profiles],
            "recovery_rate": round(self.recovery_rate, 4),
            "weekly_summaries": [w.to_dict() for w in self.weekly_summaries],
            "tool_error_associations": self.tool_error_associations,
            "persistent_error_categories": self.persistent_error_categories,
        }


class ErrorCategoryAnalyzer:
    """Analyze error categories and trends from session logs."""

    def __init__(
        self,
        turns: list[TurnRecord],
        top_examples: int = _TOP_EXAMPLES,
        min_turns_for_tool: int = _MIN_TURNS_FOR_TOOL_ERR_RATE,
    ) -> None:
        self._turns = [t for t in turns if not t.is_heartbeat]
        self._top_examples = top_examples
        self._min_turns_for_tool = min_turns_for_tool

    def analyze(self) -> ErrorCategoryResult:
        total_turns = len(self._turns)
        error_turns = [t for t in self._turns if t.follow_up_correction]
        n_errors = len(error_turns)
        overall_error_rate = n_errors / total_turns if total_turns else 0.0

        # --- category distribution ---
        cat_counter: Counter[str] = Counter()
        cat_messages: dict[str, list[str]] = defaultdict(list)
        cat_sessions: dict[str, set[str]] = defaultdict(set)

        for t in error_turns:
            cat = t.error_category or "other"
            if not cat:
                cat = "other"
            cat_counter[cat] += 1
            if t.error_text:
                cat_messages[cat].append(t.error_text)
            if t.session_id:
                cat_sessions[cat].add(t.session_id)

        # Ensure all known categories appear (with zeros if absent)
        categories: list[CategoryStats] = []
        for cat in _KNOWN_CATEGORIES:
            count = cat_counter.get(cat, 0)
            pct = (count / n_errors * 100.0) if n_errors else 0.0
            msgs = cat_messages.get(cat, [])
            # Top N most common distinct messages
            msg_counter = Counter(msgs)
            top_msgs = [m for m, _ in msg_counter.most_common(self._top_examples)]
            categories.append(
                CategoryStats(
                    category=cat,
                    count=count,
                    percentage_of_errors=pct,
                    example_messages=top_msgs,
                    affected_sessions=len(cat_sessions.get(cat, set())),
                )
            )
        # Sort by count descending
        categories.sort(key=lambda c: c.count, reverse=True)

        # --- session profiles ---
        session_errors: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in error_turns:
            if t.session_id:
                session_errors[t.session_id].append(t)

        session_profiles: list[SessionErrorProfile] = []
        for sid, err_turns in session_errors.items():
            cats = sorted({(t.error_category or "other") for t in err_turns})
            # Recovery: at least one error turn in the session has task_completed=True
            recovered = any(t.task_completed for t in err_turns)
            recovery_rate = 1.0 if recovered else 0.0
            session_profiles.append(
                SessionErrorProfile(
                    session_id=sid,
                    error_count=len(err_turns),
                    error_categories=cats,
                    recovery_rate=recovery_rate,
                )
            )
        session_profiles.sort(key=lambda p: p.error_count, reverse=True)

        # --- overall recovery rate ---
        # Among sessions that had errors, what fraction recovered?
        recovered_sessions = sum(1 for p in session_profiles if p.recovery_rate > 0)
        recovery_rate = (
            recovered_sessions / len(session_profiles) if session_profiles else 0.0
        )

        # --- weekly summaries ---
        week_turns: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in self._turns:
            week_turns[t.week_tag].append(t)

        weekly_summaries: list[WeeklyErrorSummary] = []
        for week, wturns in sorted(week_turns.items()):
            werrors = [t for t in wturns if t.follow_up_correction]
            wcat_counter: Counter[str] = Counter()
            for t in werrors:
                cat = t.error_category or "other"
                wcat_counter[cat] += 1
            top_cat = wcat_counter.most_common(1)[0][0] if wcat_counter else ""
            weekly_summaries.append(
                WeeklyErrorSummary(
                    week_tag=week,
                    total_turns=len(wturns),
                    error_count=len(werrors),
                    top_category=top_cat,
                )
            )

        # --- tool-specific errors ---
        tool_turns: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "errors": 0})
        for t in self._turns:
            has_err = t.follow_up_correction
            for tool in t.tools_called:
                tool_turns[tool]["total"] += 1
                if has_err:
                    tool_turns[tool]["errors"] += 1

        tool_error_associations: list[dict] = []
        for tool, counts in sorted(tool_turns.items(), key=lambda x: x[1]["errors"], reverse=True):
            total = counts["total"]
            errs = counts["errors"]
            if total < self._min_turns_for_tool:
                continue
            err_rate = errs / total if total else 0.0
            tool_error_associations.append(
                {
                    "tool": tool,
                    "total_turns": total,
                    "error_turns": errs,
                    "error_rate": round(err_rate, 4),
                }
            )

        # --- persistent errors (appear in >1 session) ---
        persistent_error_categories = [
            cat for cat, sess in cat_sessions.items() if len(sess) > 1
        ]
        persistent_error_categories.sort()

        return ErrorCategoryResult(
            total_turns=total_turns,
            error_turns=n_errors,
            overall_error_rate=overall_error_rate,
            categories=categories,
            session_profiles=session_profiles,
            recovery_rate=recovery_rate,
            weekly_summaries=weekly_summaries,
            tool_error_associations=tool_error_associations,
            persistent_error_categories=persistent_error_categories,
        )
