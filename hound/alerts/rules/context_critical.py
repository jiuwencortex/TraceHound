# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ContextCriticalRule — fires on any single turn exceeding the context limit."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "context_critical"


class ContextCriticalRule:
    rule_id = RULE_ID

    def __init__(self, threshold: float = 0.95) -> None:
        self._threshold = threshold
        self._last_triggered = False

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if state.max_usage_percent >= self._threshold and not self._last_triggered:
            self._last_triggered = True
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.CRITICAL,
                title="Context window nearly full",
                description=f"A turn used {state.max_usage_percent:.1%} of the context window",
                payload={"max_usage": state.max_usage_percent, "threshold": self._threshold},
            )
        if state.max_usage_percent < self._threshold:
            self._last_triggered = False
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return state.max_usage_percent < self._threshold
