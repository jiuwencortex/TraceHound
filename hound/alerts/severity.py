# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Severity — alert priority levels."""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    def __ge__(self, other: "Severity") -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]
        return order.index(self) >= order.index(other)

    def __gt__(self, other: "Severity") -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]
        return order.index(self) > order.index(other)
