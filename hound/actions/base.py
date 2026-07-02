# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ActionHandler — protocol for all output channel handlers."""

from __future__ import annotations

from typing import Protocol

from ..alerts.alert import Alert


class ActionHandler(Protocol):
    """Interface for action channel handlers.

    Implementations must be safe to call from a thread pool executor.
    """

    def handle(self, alert: Alert) -> None:
        """Execute the action for the given alert."""
        ...

    def can_handle(self, alert: Alert) -> bool:
        """Return True if this handler should process the given alert."""
        ...
