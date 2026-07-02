# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ContextPressureRule — fires when mean context utilisation is high."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "context_pressure"


class ContextPressureRule:
    rule_id = RULE_ID

    def __init__(self, threshold: float = 0.80) -> None:
        self._threshold = threshold

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if state.mean_usage_percent >= self._threshold:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="Context window pressure",
                description=f"Mean context usage {state.mean_usage_percent:.1%} ≥ {self._threshold:.0%}",
                payload={"mean_usage": state.mean_usage_percent, "threshold": self._threshold},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return state.mean_usage_percent < self._threshold * 0.85
