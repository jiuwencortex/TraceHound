# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""QualityEMA — exponential moving average over quality scores."""

from __future__ import annotations


class QualityEMA:
    """Tracks a windowed EMA of quality scores.

    ``alpha`` controls smoothing: lower = smoother, slower to react.
    The ``window`` stores the last N raw scores for short-window stats.
    """

    def __init__(self, alpha: float = 0.1, window_size: int = 20) -> None:
        self._alpha = alpha
        self._window_size = window_size
        self._ema: float | None = None
        self._window: list[float] = []

    def update(self, quality: float) -> None:
        if self._ema is None:
            self._ema = quality
        else:
            self._ema = self._alpha * quality + (1 - self._alpha) * self._ema
        self._window.append(quality)
        if len(self._window) > self._window_size:
            self._window.pop(0)

    @property
    def ema(self) -> float:
        return self._ema if self._ema is not None else 0.5

    def window_mean(self, n: int | None = None) -> float:
        """Mean of the last ``n`` samples (defaults to full window)."""
        samples = self._window[-n:] if n else self._window
        return sum(samples) / len(samples) if samples else 0.5

    @property
    def window(self) -> list[float]:
        return list(self._window)
