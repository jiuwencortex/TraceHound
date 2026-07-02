# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CorrectionLoopRule — fires when follow-up corrections become frequent."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "correction_loop"


class CorrectionLoopRule:
    rule_id = RULE_ID

    def __init__(self, rate: float = 0.40) -> None:
        self._rate = rate

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if state.correction_rate >= self._rate:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="Correction loop detected",
                description=f"Follow-up correction rate {state.correction_rate:.1%} ≥ {self._rate:.0%}",
                payload={"correction_rate": state.correction_rate, "threshold": self._rate},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return state.correction_rate < self._rate * 0.75
