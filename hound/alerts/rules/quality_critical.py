# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""QualityCriticalRule — fires when EMA quality falls below absolute floor."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "quality_critical"


class QualityCriticalRule:
    rule_id = RULE_ID

    def __init__(self, threshold: float = 0.40) -> None:
        self._threshold = threshold

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if state.quality_ema < self._threshold:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.CRITICAL,
                title="Quality critically low",
                description=f"EMA quality {state.quality_ema:.3f} < threshold {self._threshold:.2f}",
                payload={"quality_ema": state.quality_ema, "threshold": self._threshold},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return state.quality_ema >= self._threshold + 0.05
