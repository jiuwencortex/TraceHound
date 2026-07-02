# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TokenStats — running token and context-window usage statistics."""

from __future__ import annotations

import statistics


class TokenStats:
    """Tracks mean tokens/turn and context window utilisation."""

    def __init__(self, usage_window: int = 10) -> None:
        self._usage_window = usage_window
        self._total_tokens: int = 0
        self._count: int = 0
        self._usage_samples: list[float] = []   # recent usage_percent values
        self._max_usage: float = 0.0

    def update(self, total_tokens: int, usage_percent: float) -> None:
        self._total_tokens += total_tokens
        self._count += 1
        if usage_percent > 0:
            self._usage_samples.append(usage_percent)
            if len(self._usage_samples) > self._usage_window:
                self._usage_samples.pop(0)
            self._max_usage = max(self._max_usage, usage_percent)

    @property
    def mean_tokens(self) -> float:
        return self._total_tokens / self._count if self._count else 0.0

    @property
    def mean_usage_percent(self) -> float:
        return statistics.mean(self._usage_samples) if self._usage_samples else 0.0

    @property
    def max_usage_percent(self) -> float:
        return self._max_usage
