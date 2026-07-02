# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CostThresholdRule — fires when estimated daily cost exceeds budget."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "cost_threshold"


class CostThresholdRule:
    rule_id = RULE_ID

    def __init__(self, daily_budget_usd: float = 5.00) -> None:
        self._budget = daily_budget_usd

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        if self._budget > 0 and state.estimated_daily_cost_usd >= self._budget:
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.WARNING,
                title="Daily token budget exceeded",
                description=(
                    f"Estimated daily cost ${state.estimated_daily_cost_usd:.4f} "
                    f"≥ budget ${self._budget:.2f}"
                ),
                payload={
                    "daily_cost": state.estimated_daily_cost_usd,
                    "budget": self._budget,
                    "date": state.daily_cost_date,
                },
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        # Resolves at end of day (cost resets) or if date changes
        return state.estimated_daily_cost_usd < self._budget * 0.9
