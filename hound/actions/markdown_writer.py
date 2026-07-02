# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""MarkdownAlertWriter — writes one Markdown file per fired alert."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..alerts.alert import Alert


class MarkdownAlertWriter:
    """Writes alerts as Markdown files in ``output_dir``."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def can_handle(self, alert: Alert) -> bool:
        return True

    def handle(self, alert: Alert) -> None:
        now = datetime.now(tz=timezone.utc)
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{alert.rule_id}.md"
        path = self._output_dir / "alerts" / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# [{alert.severity.value}] {alert.title}",
            "",
            f"**Rule:** `{alert.rule_id}`  ",
            f"**Fired at:** {alert.fired_at.isoformat()}  ",
            f"**Severity:** {alert.severity.value}  ",
            "",
            "## Description",
            "",
            alert.description,
            "",
            "## Payload",
            "",
        ]
        for k, v in alert.payload.items():
            lines.append(f"- **{k}:** {v}")

        path.write_text("\n".join(lines), encoding="utf-8")
