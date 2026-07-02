# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ToolFailureStormRule — fires when any single tool has many recent failures."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "tool_failure_storm"


class ToolFailureStormRule:
    rule_id = RULE_ID

    def __init__(self, min_failures: int = 5, window: int = 10) -> None:
        self._min_failures = min_failures
        self._window = window

    def _worst_tool(self, state: AnalyzerState) -> tuple[str, int] | None:
        worst = None
        worst_count = 0
        for tool, calls in state.tool_failure_windows.items():
            failures = calls[-self._window:].count(False)
            if failures >= self._min_failures and failures > worst_count:
                worst = tool
                worst_count = failures
        return (worst, worst_count) if worst else None

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        result = self._worst_tool(state)
        if result:
            tool, count = result
            return Alert(
                rule_id=RULE_ID,
                severity=Severity.CRITICAL,
                title=f"Tool failure storm: {tool}",
                description=f"{tool} failed {count} times in last {self._window} calls",
                payload={"tool": tool, "failure_count": count, "window": self._window},
            )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return self._worst_tool(state) is None
