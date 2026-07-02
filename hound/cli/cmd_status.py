# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""do_status — prints the latest AnalyzerState snapshot."""

from __future__ import annotations

import json
from pathlib import Path


def do_status(config_path: Path | None) -> None:
    from ..config.loader import load_config
    from ..memory.db import Database
    from ..memory.snapshot_store import SnapshotStore

    cfg = load_config(config_path)
    db = Database(cfg.state_db_path)
    conn = db.connect()
    store = SnapshotStore(conn)
    snap = store.latest()

    if snap is None:
        print("No snapshot available. Is the agent running?")
        return

    print("TraceHound Hound — Live Status")
    print("=" * 40)
    for k, v in snap.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.4f}")
        else:
            print(f"  {k:<30} {v}")
