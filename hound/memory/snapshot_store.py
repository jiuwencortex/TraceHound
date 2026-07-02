# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SnapshotStore — persists AnalyzerState snapshots as JSON for crash recovery."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class SnapshotStore:
    """Persists AnalyzerState snapshots to SQLite.

    Keeps only the last ``keep`` snapshots to avoid unbounded growth.
    """

    def __init__(self, conn: sqlite3.Connection, keep: int = 20) -> None:
        self._conn = conn
        self._keep = keep

    def save(self, data: dict) -> None:
        """Serialise ``data`` as JSON and store with current timestamp."""
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO accumulator_snapshots (snapshot_at, data) VALUES (?, ?)",
            (now, json.dumps(data, default=str)),
        )
        # Prune old rows
        self._conn.execute(
            """DELETE FROM accumulator_snapshots
               WHERE id NOT IN (
                   SELECT id FROM accumulator_snapshots
                   ORDER BY id DESC LIMIT ?
               )""",
            (self._keep,),
        )
        self._conn.commit()

    def latest(self) -> dict | None:
        """Return the most recently saved snapshot, or None."""
        row = self._conn.execute(
            "SELECT data FROM accumulator_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None
        return None
