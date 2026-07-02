# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CostTracker — estimates token cost per calendar day."""

from __future__ import annotations

from datetime import datetime, timezone


# Rough cost per 1M tokens (USD) — Kimi defaults
_COST_PER_1M_INPUT = 0.12
_COST_PER_1M_OUTPUT = 0.12


class CostTracker:
    """Accumulates estimated USD cost for the current calendar day."""

    def __init__(self) -> None:
        self._date = ""
        self._daily_cost: float = 0.0

    def update(self, input_tokens: int, output_tokens: int) -> None:
        today = datetime.now(tz=timezone.utc).date().isoformat()
        if today != self._date:
            self._date = today
            self._daily_cost = 0.0
        self._daily_cost += (
            input_tokens * _COST_PER_1M_INPUT / 1_000_000
            + output_tokens * _COST_PER_1M_OUTPUT / 1_000_000
        )

    @property
    def daily_cost(self) -> float:
        return self._daily_cost

    @property
    def current_date(self) -> str:
        return self._date
