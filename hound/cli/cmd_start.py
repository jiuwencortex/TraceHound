# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""do_start — launches the HoundAgent event loop."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger


def do_start(config_path: Path | None, daemon: bool) -> None:
    from ..config.loader import load_config
    from ..agent import HoundAgent

    cfg = load_config(config_path)

    if daemon:
        _daemonise(cfg.output_dir)

    logger.info("hound: starting agent — log_root={}", cfg.watch.log_root)
    agent = HoundAgent(cfg)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("hound: stopped by user")


def _daemonise(output_dir: Path) -> None:
    """Fork into background and redirect stdio."""
    import os

    pid = os.fork()
    if pid > 0:
        print(f"hound: daemon started (PID {pid})")
        sys.exit(0)

    os.setsid()
    output_dir.mkdir(parents=True, exist_ok=True)
    pid_file = output_dir / "hound.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    devnull = open(os.devnull, "r")
    sys.stdin = devnull
