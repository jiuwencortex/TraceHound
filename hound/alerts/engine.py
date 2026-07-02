# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AlertEngine — evaluates all rules and manages the alert lifecycle."""

from __future__ import annotations

from typing import Callable

from ..accumulate.state import AnalyzerState
from ..memory.alert_store import AlertStore
from ..memory.baseline_store import BaselineStore
from .alert import Alert
from .severity import Severity


class AlertEngine:
    """Evaluates registered rules against the current AnalyzerState.

    Maintains the alert lifecycle:
      DETECTED → FIRING (persisted) → RESOLVED (or ACKNOWLEDGED)

    Each rule fires at most once per violation; it does not re-fire while
    the condition persists. It fires again after the condition resolves and
    then re-violates.
    """

    def __init__(
        self,
        rules: list,
        alert_store: AlertStore,
        baseline_store: BaselineStore,
        on_alert: Callable[[Alert], None],
    ) -> None:
        self._rules = rules
        self._store = alert_store
        self._baselines = baseline_store
        self._on_alert = on_alert

    def evaluate(self, state: AnalyzerState) -> list[Alert]:
        """Evaluate all rules; fire new alerts and resolve stale ones."""
        fired: list[Alert] = []

        for rule in self._rules:
            already_active = self._store.has_active(rule.rule_id)

            if already_active:
                # Check if condition has cleared
                if rule.check_resolved(state, self._baselines):
                    alert_id = self._store.get_active_id(rule.rule_id)
                    if alert_id is not None:
                        self._store.record_resolved(alert_id)
            else:
                # Evaluate rule
                alert = rule.evaluate(state, self._baselines)
                if alert is not None:
                    db_id = self._store.record_fired(
                        rule_id=alert.rule_id,
                        severity=alert.severity.value,
                        payload=alert.payload,
                    )
                    alert.db_id = db_id
                    fired.append(alert)
                    self._on_alert(alert)

        return fired
