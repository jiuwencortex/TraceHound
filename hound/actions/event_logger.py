# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""EventLogger — appends all agent events to events.jsonl."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..alerts.alert import Alert


class EventLogger:
    """Appends a JSON line for every alert to ``events_path``."""

    def __init__(self, events_path: Path) -> None:
        self._path = events_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def can_handle(self, alert: Alert) -> bool:
        return True

    def handle(self, alert: Alert) -> None:
        entry = {
            "type": "alert_fired",
            "rule_id": alert.rule_id,
            "severity": alert.severity.value,
            "title": alert.title,
            "description": alert.description,
            "payload": alert.payload,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def log_info(self, message: str, **kwargs) -> None:
        """Log a non-alert informational event."""
        entry = {
            "type": "info",
            "message": message,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            **kwargs,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
