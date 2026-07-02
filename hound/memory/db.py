# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Database — SQLite connection factory with schema initialisation."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Manages a SQLite database file and provides connection access.

    Thread safety: call ``connect()`` once per thread; SQLite connections must
    not be shared between threads.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS ingestion_state (
        session_id  TEXT PRIMARY KEY,
        file_path   TEXT NOT NULL,
        bytes_read  INTEGER NOT NULL DEFAULT 0,
        last_turn   TEXT
    );

    CREATE TABLE IF NOT EXISTS baselines (
        metric_name TEXT PRIMARY KEY,
        value       REAL NOT NULL,
        computed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS accumulator_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_at TEXT NOT NULL,
        data        TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id     TEXT NOT NULL,
        severity    TEXT NOT NULL,
        fired_at    TEXT NOT NULL,
        resolved_at TEXT,
        acked_at    TEXT,
        payload     TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS seen_error_categories (
        category    TEXT PRIMARY KEY,
        first_seen  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS annotations (
        turn_id     TEXT NOT NULL,
        note        TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Return a new SQLite connection with WAL mode and schema applied."""
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(self._DDL)
        conn.commit()
        return conn

    @property
    def path(self) -> Path:
        return self._path
