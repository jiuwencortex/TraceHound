# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""NewErrorCategoryRule — fires when a previously-unseen error category appears."""

from __future__ import annotations

from ...accumulate.state import AnalyzerState
from ...memory.alert_store import AlertStore
from ...memory.baseline_store import BaselineStore
from ..alert import Alert
from ..severity import Severity

RULE_ID = "new_error_category"


class NewErrorCategoryRule:
    """Fires INFO alert when an error category appears that hasn't been seen before.

    Requires ``alert_store`` to persist seen categories across restarts.
    """

    rule_id = RULE_ID

    def __init__(self, alert_store: AlertStore) -> None:
        self._store = alert_store
        self._last_new: str | None = None

    def evaluate(self, state: AnalyzerState, baselines: BaselineStore) -> Alert | None:
        for cat in state.recent_error_categories[-5:]:
            if cat and self._store.record_seen_error_category(cat):
                self._last_new = cat
                return Alert(
                    rule_id=RULE_ID,
                    severity=Severity.INFO,
                    title=f"New error category: {cat}",
                    description=f"Error category '{cat}' has not been seen in previous logs",
                    payload={"category": cat},
                )
        return None

    def check_resolved(self, state: AnalyzerState, baselines: BaselineStore) -> bool:
        return True  # INFO-level, auto-resolve immediately
