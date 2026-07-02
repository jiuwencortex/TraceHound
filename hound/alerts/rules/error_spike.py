# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ErrorSpikeRule — fires when recent error rate exceeds baseline by a ratio."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "error_spike"


class ErrorSpikeRule:
    rule_id = RULE_ID

    def __init__(self, ratio: float = 2.0, window: int = 20) -> None:
        self._ratio = ratio
        self._window = window

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        baseline = baselines.get("error_rate", 0.10)
        recent = len([e for e in state.recent_errors[-self._window:] if e])
        recent_rate = recent / min(self._window, len(state.recent_errors)) if state.recent_errors else 0.0
        if baseline > 0 and recent_rate >= baseline * self._ratio and recent_rate > 0.15:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="Error rate spike",
                description=f"Recent error rate {recent_rate:.1%} is {recent_rate/baseline:.1f}× baseline {baseline:.1%}",
                payload={"recent_rate": recent_rate, "baseline": baseline, "ratio": recent_rate / baseline},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        baseline = baselines.get("error_rate", 0.10)
        return state.error_rate < baseline * (self._ratio * 0.7)
