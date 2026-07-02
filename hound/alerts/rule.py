# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AlertRule — protocol that all rule classes must implement."""

from __future__ import annotations

from typing import Protocol

from ..accumulate.state import AnalyzerState
from ..memory.baseline_store import BaselineStore
from .alert import Alert


class AlertRule(Protocol):
    """Each rule evaluates the current AnalyzerState and optionally fires an Alert."""

    rule_id: str

    def evaluate(
        self,
        state: AnalyzerState,
        baselines: BaselineStore,
    ) -> Alert | None:
        """Return an Alert if the rule is triggered, else None."""
        ...

    def check_resolved(
        self,
        state: AnalyzerState,
        baselines: BaselineStore,
    ) -> bool:
        """Return True if the previously-fired condition is no longer active."""
        ...
