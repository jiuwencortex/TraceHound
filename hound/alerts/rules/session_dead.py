# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SessionDeadRule — fires when a session has been idle too long during working hours."""

from __future__ import annotations

from datetime import datetime, timezone

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ...memory.offset_store import IngestionOffsetStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "session_dead"


def _parse_working_hours(spec: str) -> tuple[int, int]:
    """Parse 'HH:MM-HH:MM' → (start_hour, end_hour).  Defaults to (9, 22)."""
    try:
        start_s, end_s = spec.split("-", 1)
        return int(start_s.split(":")[0]), int(end_s.split(":")[0])
    except Exception:  # noqa: BLE001
        return 9, 22


def _is_working_hours(working_hours_spec: str) -> bool:
    """Return True if the current UTC hour falls within the configured range."""
    start_h, end_h = _parse_working_hours(working_hours_spec)
    current_h = datetime.now(tz=timezone.utc).hour
    if start_h <= end_h:
        return start_h <= current_h < end_h
    # Overnight range (e.g. 22-06)
    return current_h >= start_h or current_h < end_h


class SessionDeadRule:
    """Fires INFO when a known session has had no new turns for ``hours`` during working hours.

    Unlike ``no_data`` (which triggers globally), this rule checks individual
    sessions that have previously been active and gone quiet — suggesting the
    jiuwenswarm agent may have stalled mid-task.

    Requires ``offset_store`` so it can read per-session ``last_turn`` timestamps.
    """

    rule_id = RULE_ID

    def __init__(
        self,
        offset_store: IngestionOffsetStore,
        hours: float = 2.0,
        working_hours: str = "09:00-22:00",
    ) -> None:
        self._offsets = offset_store
        self._hours = hours
        self._working_hours = working_hours
        self._last_dead_session: str | None = None

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if not _is_working_hours(self._working_hours):
            return None

        now = datetime.now(tz=timezone.utc)
        sessions = self._offsets.all_sessions()

        for s in sessions:
            last_turn_str = s.get("last_turn")
            if not last_turn_str:
                continue
            try:
                last_turn = datetime.fromisoformat(last_turn_str)
            except ValueError:
                continue

            # Make sure last_turn is timezone-aware
            if last_turn.tzinfo is None:
                last_turn = last_turn.replace(tzinfo=timezone.utc)

            elapsed_h = (now - last_turn).total_seconds() / 3600
            if elapsed_h >= self._hours:
                self._last_dead_session = s["session_id"]
                return Alert(
                    rule_id=RULE_ID,
                    severity=Severity.INFO,
                    title=f"Session idle: {s['session_id'][:20]}",
                    description=(
                        f"Session '{s['session_id'][:32]}' has had no new turns "
                        f"for {elapsed_h:.1f} h (threshold: {self._hours} h)"
                    ),
                    payload={
                        "session_id": s["session_id"],
                        "elapsed_hours": round(elapsed_h, 2),
                        "threshold_hours": self._hours,
                        "last_turn": last_turn_str,
                    },
                )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        # Resolves as soon as the session gets a new turn (offset_store last_turn updates)
        if self._last_dead_session is None:
            return True
        sessions = {s["session_id"]: s for s in self._offsets.all_sessions()}
        s = sessions.get(self._last_dead_session)
        if not s or not s.get("last_turn"):
            return True
        try:
            last_turn = datetime.fromisoformat(s["last_turn"])
        except ValueError:
            return True
        if last_turn.tzinfo is None:
            last_turn = last_turn.replace(tzinfo=timezone.utc)
        elapsed_h = (datetime.now(tz=timezone.utc) - last_turn).total_seconds() / 3600
        return elapsed_h < self._hours * 0.8
