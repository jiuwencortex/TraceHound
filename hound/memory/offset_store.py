# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""IngestionOffsetStore — persists per-session byte offsets for tail-reading."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class IngestionOffsetStore:
    """Stores and retrieves the byte offset up to which each session file
    has been processed by the TurnIngester."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_offset(self, session_id: str) -> int:
        """Return the number of bytes already consumed for this session (0 if new)."""
        row = self._conn.execute(
            "SELECT bytes_read FROM ingestion_state WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def set_offset(self, session_id: str, file_path: Path, bytes_read: int) -> None:
        """Upsert the byte offset for a session."""
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO ingestion_state (session_id, file_path, bytes_read, last_turn)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   file_path = excluded.file_path,
                   bytes_read = excluded.bytes_read,
                   last_turn = excluded.last_turn""",
            (session_id, str(file_path), bytes_read, now),
        )
        self._conn.commit()

    def all_sessions(self) -> list[dict]:
        """Return all tracked sessions with their current offsets."""
        rows = self._conn.execute(
            "SELECT session_id, file_path, bytes_read, last_turn FROM ingestion_state"
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "file_path": r[1],
                "bytes_read": r[2],
                "last_turn": r[3],
            }
            for r in rows
        ]
