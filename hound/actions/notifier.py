# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""MacOSNotifier — sends macOS native notifications via osascript."""

from __future__ import annotations

import subprocess
import sys

from ..alerts.alert import Alert
from ..alerts.severity import Severity

_SEVERITY_ICONS = {
    Severity.INFO: "ℹ️",
    Severity.WARNING: "⚠️",
    Severity.CRITICAL: "🔴",
}


class MacOSNotifier:
    """Delivers macOS notifications for fired alerts using osascript.

    Only available on macOS; silently no-ops on other platforms.
    """

    def __init__(self, min_severity: Severity = Severity.WARNING) -> None:
        self._min_severity = min_severity

    def can_handle(self, alert: Alert) -> bool:
        return sys.platform == "darwin" and alert.severity >= self._min_severity

    def handle(self, alert: Alert) -> None:
        icon = _SEVERITY_ICONS.get(alert.severity, "")
        title = f"TraceHound {icon} {alert.severity.value}"
        body = f"{alert.title}\n{alert.description[:160]}"
        script = (
            f'display notification "{_esc(body)}" '
            f'with title "{_esc(title)}" '
            f'subtitle "hound"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _esc(s: str) -> str:
    """Escape a string for AppleScript double-quoted context."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
