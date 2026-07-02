# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""NoDataRule — fires when no new turns have been processed for a long time."""

from __future__ import annotations

from datetime import datetime, timezone

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "no_data"


class NoDataRule:
    rule_id = RULE_ID

    def __init__(self, hours: float = 4.0) -> None:
        self._hours = hours

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if state.turn_count == 0:
            return None
        now = datetime.now(tz=timezone.utc)
        elapsed_h = (now - state.last_turn_at).total_seconds() / 3600
        if elapsed_h >= self._hours:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="No new log data",
                description=f"No new turns received in the last {elapsed_h:.1f} h (threshold: {self._hours} h)",
                payload={"elapsed_hours": elapsed_h, "threshold_hours": self._hours},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        now = datetime.now(tz=timezone.utc)
        elapsed_h = (now - state.last_turn_at).total_seconds() / 3600
        return elapsed_h < self._hours
