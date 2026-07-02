# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""WatchAgent — monitors the jiuwenswarm log tree for new JSONL content."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .event import NewDataEvent


class _Handler(FileSystemEventHandler):
    """Watchdog event handler that queues debounced NewDataEvent objects."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue,
        debounce_ms: int,
        offset_getter,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue
        self._debounce_s = debounce_ms / 1000.0
        self._offset_getter = offset_getter
        self._pending: dict[Path, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        self._handle(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        self._handle(event.src_path)

    def _handle(self, src_path: str) -> None:
        path = Path(src_path)
        if path.name != "history.jsonl":
            return
        with self._lock:
            self._pending[path] = time.monotonic()
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for path in paths:
            session_id = path.parent.name
            offset = self._offset_getter(session_id)
            event = NewDataEvent(file_path=path, session_id=session_id, known_offset=offset)
            asyncio.run_coroutine_threadsafe(self._queue.put(event), self._loop)


class WatchAgent:
    """Watches ``log_root`` for new/modified history.jsonl files.

    Emits :class:`NewDataEvent` objects into ``event_queue`` (asyncio.Queue).
    Debounces rapid filesystem bursts to avoid reading mid-write files.
    """

    def __init__(
        self,
        log_root: Path,
        event_queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        debounce_ms: int = 500,
        offset_getter=None,
    ) -> None:
        self._log_root = log_root
        self._queue = event_queue
        self._loop = loop
        self._debounce_ms = debounce_ms
        self._offset_getter = offset_getter or (lambda _session_id: 0)
        self._observer: Observer | None = None

    def _watch_dirs(self) -> list[Path]:
        candidates = [
            self._log_root / "agent" / "sessions",
            self._log_root / "sessions",
        ]
        return [d for d in candidates if d.is_dir()]

    def start(self) -> None:
        """Start the watchdog observer thread."""
        handler = _Handler(
            loop=self._loop,
            queue=self._queue,
            debounce_ms=self._debounce_ms,
            offset_getter=self._offset_getter,
        )
        self._observer = Observer()
        for watch_dir in self._watch_dirs():
            self._observer.schedule(handler, str(watch_dir), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """Stop the watchdog observer thread."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
