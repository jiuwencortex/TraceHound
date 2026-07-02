# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""BaselineStore — persists named metric baselines for regression detection."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class BaselineStore:
    """Store and retrieve named metric baselines (floats).

    Baselines are recomputed periodically from full analysis runs and used
    by the AlertEngine to detect regressions.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, metric_name: str, value: float) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO baselines (metric_name, value, computed_at)
               VALUES (?, ?, ?)
               ON CONFLICT(metric_name) DO UPDATE SET
                   value = excluded.value,
                   computed_at = excluded.computed_at""",
            (metric_name, value, now),
        )
        self._conn.commit()

    def get(self, metric_name: str, default: float = 0.0) -> float:
        row = self._conn.execute(
            "SELECT value FROM baselines WHERE metric_name = ?",
            (metric_name,),
        ).fetchone()
        return float(row[0]) if row else default

    def all(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT metric_name, value FROM baselines").fetchall()
        return {r[0]: float(r[1]) for r in rows}
