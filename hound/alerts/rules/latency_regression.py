# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""LatencyRegressionRule — fires when median LLM latency exceeds baseline by a ratio."""

from __future__ import annotations

import statistics

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "latency_regression"

# Minimum number of latency samples needed before the rule is meaningful
_MIN_SAMPLES = 10


class LatencyRegressionRule:
    rule_id = RULE_ID

    def __init__(self, ratio: float = 1.5) -> None:
        self._ratio = ratio

    def _current_median(self, state: AnalyzerState) -> float | None:
        samples = state.latency_samples
        if len(samples) < _MIN_SAMPLES:
            return None
        return statistics.median(samples)

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        baseline = baselines.get("median_latency_ms", 0.0)
        if baseline <= 0:
            return None  # No baseline established yet

        current = self._current_median(state)
        if current is None:
            return None  # Not enough samples

        if current >= baseline * self._ratio:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="LLM latency regression",
                description=(
                    f"Median latency {current:.0f} ms is {current / baseline:.1f}× "
                    f"above baseline {baseline:.0f} ms"
                ),
                payload={
                    "current_median_ms": round(current, 1),
                    "baseline_ms": round(baseline, 1),
                    "ratio": round(current / baseline, 2),
                    "threshold_ratio": self._ratio,
                    "sample_count": len(state.latency_samples),
                },
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        baseline = baselines.get("median_latency_ms", 0.0)
        if baseline <= 0:
            return True
        current = self._current_median(state)
        if current is None:
            return True
        return current < baseline * (self._ratio * 0.8)
