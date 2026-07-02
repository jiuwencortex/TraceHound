# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""do_report — triggers an immediate full analysis."""

from __future__ import annotations

from pathlib import Path


def do_report(config_path: Path | None) -> None:
    from ..config.loader import load_config
    from ..memory.db import Database
    from ..memory.baseline_store import BaselineStore
    from ..schedule.jobs import run_full_analysis

    cfg = load_config(config_path)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    db = Database(cfg.state_db_path)
    conn = db.connect()
    baselines = BaselineStore(conn)

    print("Running full analysis…")
    run_full_analysis(
        log_root=cfg.watch.log_root,
        max_weeks=cfg.analysis.max_weeks,
        qd_thresh=cfg.analysis.quality_deficit_threshold,
        lift_thresh=cfg.analysis.correction_lift_threshold,
        skip_heartbeats=cfg.analysis.skip_heartbeats,
        output_dir=cfg.output_dir,
        baseline_store=baselines,
        label="manual",
    )
    print(f"Done. Reports saved to: {cfg.output_dir}")
