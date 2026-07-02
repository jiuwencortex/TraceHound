# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SlackPoster — POSTs alert notifications to a Slack incoming webhook."""

from __future__ import annotations

import json
import urllib.request

from ..alerts.alert import Alert
from ..alerts.severity import Severity

_COLORS = {
    Severity.INFO: "#36a64f",
    Severity.WARNING: "#ffa500",
    Severity.CRITICAL: "#cc0000",
}


class SlackPoster:
    """Sends formatted Slack messages for fired alerts."""

    def __init__(self, webhook_url: str, min_severity: Severity = Severity.WARNING) -> None:
        self._url = webhook_url
        self._min_severity = min_severity

    def can_handle(self, alert: Alert) -> bool:
        return bool(self._url) and alert.severity >= self._min_severity

    def handle(self, alert: Alert) -> None:
        color = _COLORS.get(alert.severity, "#888888")
        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"[{alert.severity.value}] {alert.title}",
                    "text": alert.description,
                    "footer": f"TraceHound hound • rule={alert.rule_id}",
                    "ts": int(alert.fired_at.timestamp()),
                }
            ]
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except OSError:
            pass
