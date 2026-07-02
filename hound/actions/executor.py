# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ActionExecutor — dispatches fired alerts to all registered handlers."""

from __future__ import annotations

import concurrent.futures

from ..alerts.alert import Alert


class ActionExecutor:
    """Receives fired Alert objects and dispatches them to all registered handlers.

    Each handler is invoked in a thread-pool executor so that slow I/O
    (HTTP, file writes) does not block the main asyncio event loop.
    """

    def __init__(self, handlers: list, max_workers: int = 4) -> None:
        self._handlers = handlers
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="hound-action"
        )

    def dispatch(self, alert: Alert) -> None:
        """Submit all eligible handlers to the thread pool."""
        for handler in self._handlers:
            if handler.can_handle(alert):
                self._pool.submit(self._run, handler, alert)

    @staticmethod
    def _run(handler, alert: Alert) -> None:
        try:
            handler.handle(alert)
        except Exception:  # noqa: BLE001
            pass  # Action failures must never crash the main loop

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
