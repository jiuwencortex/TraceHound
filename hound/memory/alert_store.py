# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AlertStore — SQLite-backed persistence for alert history and deduplication."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class AlertStore:
    """Persists alert lifecycle events (fired, resolved, acked).

    Used by AlertEngine to avoid re-firing alerts while a condition persists
    and to provide ``hound alerts`` CLI output.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_fired(self, rule_id: str, severity: str, payload: dict) -> int:
        """Insert a new fired alert and return its row id."""
        now = datetime.now(tz=timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO alerts (rule_id, severity, fired_at, payload) VALUES (?, ?, ?, ?)",
            (rule_id, severity, now, json.dumps(payload, default=str)),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def record_resolved(self, alert_id: int) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE alerts SET resolved_at = ? WHERE id = ?",
            (now, alert_id),
        )
        self._conn.commit()

    def record_acked(self, alert_id: int) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE alerts SET acked_at = ? WHERE id = ?",
            (now, alert_id),
        )
        self._conn.commit()

    def active_alerts(self) -> list[dict]:
        """Return alerts that have fired but not yet been resolved."""
        rows = self._conn.execute(
            """SELECT id, rule_id, severity, fired_at, payload
               FROM alerts
               WHERE resolved_at IS NULL
               ORDER BY fired_at DESC""",
        ).fetchall()
        return [
            {
                "id": r[0],
                "rule_id": r[1],
                "severity": r[2],
                "fired_at": r[3],
                "payload": json.loads(r[4]),
            }
            for r in rows
        ]

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        """Return the most recent ``limit`` alerts (any state)."""
        rows = self._conn.execute(
            """SELECT id, rule_id, severity, fired_at, resolved_at, acked_at, payload
               FROM alerts
               ORDER BY fired_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "rule_id": r[1],
                "severity": r[2],
                "fired_at": r[3],
                "resolved_at": r[4],
                "acked_at": r[5],
                "payload": json.loads(r[6]),
            }
            for r in rows
        ]

    def has_active(self, rule_id: str) -> bool:
        """Return True if there is already a firing (unresolved) alert for this rule."""
        row = self._conn.execute(
            "SELECT 1 FROM alerts WHERE rule_id = ? AND resolved_at IS NULL LIMIT 1",
            (rule_id,),
        ).fetchone()
        return row is not None

    def get_active_id(self, rule_id: str) -> int | None:
        """Return the row id of the active alert for this rule, or None."""
        row = self._conn.execute(
            "SELECT id FROM alerts WHERE rule_id = ? AND resolved_at IS NULL LIMIT 1",
            (rule_id,),
        ).fetchone()
        return row[0] if row else None

    def record_seen_error_category(self, category: str) -> bool:
        """Record a newly seen error category. Returns True if it was new."""
        row = self._conn.execute(
            "SELECT 1 FROM seen_error_categories WHERE category = ?",
            (category,),
        ).fetchone()
        if row:
            return False
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO seen_error_categories (category, first_seen) VALUES (?, ?)",
            (category, now),
        )
        self._conn.commit()
        return True
