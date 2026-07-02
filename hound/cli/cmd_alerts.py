# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""do_alerts — lists active (or all) alerts."""

from __future__ import annotations

from pathlib import Path


def do_alerts(config_path: Path | None, show_all: bool) -> None:
    from ..config.loader import load_config
    from ..memory.db import Database
    from ..memory.alert_store import AlertStore

    cfg = load_config(config_path)
    db = Database(cfg.state_db_path)
    conn = db.connect()
    store = AlertStore(conn)

    if show_all:
        alerts = store.recent_alerts(limit=50)
        print(f"Recent alerts (last 50):")
    else:
        alerts = store.active_alerts()
        print(f"Active alerts ({len(alerts)}):")

    print("=" * 60)
    if not alerts:
        print("  (none)")
        return

    for a in alerts:
        status = "ACTIVE" if a.get("resolved_at") is None else "resolved"
        acked = " [acked]" if a.get("acked_at") else ""
        print(f"  [{a['id']}] {a['severity']:<10} {a['rule_id']:<30} {status}{acked}")
        print(f"       fired: {a['fired_at']}")
        if a.get("resolved_at"):
            print(f"       resolved: {a['resolved_at']}")
        print()
