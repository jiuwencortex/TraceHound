# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""do_gate — quality gate for CI/CD pipeline integration."""

from __future__ import annotations

import sys
from pathlib import Path


def do_gate(config_path: Path | None, min_quality: float, last_turns: int) -> None:
    from ..config.loader import load_config
    from ..memory.db import Database
    from ..memory.snapshot_store import SnapshotStore

    cfg = load_config(config_path)
    db = Database(cfg.state_db_path)
    conn = db.connect()
    snap = SnapshotStore(conn).latest()

    if snap is None:
        print("ERROR: No snapshot found. Run the agent first.", file=sys.stderr)
        sys.exit(2)

    quality = snap.get("quality_ema", 0.0)
    turn_count = snap.get("turn_count", 0)

    print(f"Quality gate: EMA={quality:.4f}, min={min_quality}, turns={turn_count}")

    if turn_count < last_turns:
        print(f"WARNING: only {turn_count} turns seen (need {last_turns}); passing gate anyway.")
        sys.exit(0)

    if quality >= min_quality:
        print("PASS")
        sys.exit(0)
    else:
        print(f"FAIL — quality {quality:.4f} < {min_quality}")
        sys.exit(1)
