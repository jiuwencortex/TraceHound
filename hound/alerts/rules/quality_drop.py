# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""QualityDropRule — fires when EMA quality drops significantly below baseline."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "quality_drop"


class QualityDropRule:
    rule_id = RULE_ID

    def __init__(self, delta: float = 0.15, window: int = 5) -> None:
        self._delta = delta
        self._window = window

    def _current(self, state: AnalyzerState) -> float:
        samples = state.quality_ema_window[-self._window:]
        return sum(samples) / len(samples) if samples else state.quality_ema

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        baseline = baselines.get("quality_mean", state.quality_ema)
        current = self._current(state)
        if baseline > 0 and (baseline - current) >= self._delta:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="Quality drop detected",
                description=(
                    f"Recent quality {current:.3f} is {baseline - current:.3f} "
                    f"below baseline {baseline:.3f}"
                ),
                payload={"current": current, "baseline": baseline, "delta": baseline - current},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        baseline = baselines.get("quality_mean", state.quality_ema)
        current = self._current(state)
        return (baseline - current) < self._delta * 0.8
