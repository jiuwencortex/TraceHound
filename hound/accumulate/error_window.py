# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ErrorRateWindow — rolling error rate over the last N turns."""

from __future__ import annotations


class ErrorRateWindow:
    """Maintains a boolean window (error / no-error) of the last ``size`` turns."""

    def __init__(self, size: int = 20) -> None:
        self._size = size
        self._window: list[bool] = []

    def update(self, has_error: bool) -> None:
        self._window.append(has_error)
        if len(self._window) > self._size:
            self._window.pop(0)

    @property
    def rate(self) -> float:
        if not self._window:
            return 0.0
        return sum(self._window) / len(self._window)

    @property
    def window(self) -> list[bool]:
        return list(self._window)

    def rate_over(self, n: int) -> float:
        """Error rate over the last ``n`` turns."""
        tail = self._window[-n:]
        return sum(tail) / len(tail) if tail else 0.0
