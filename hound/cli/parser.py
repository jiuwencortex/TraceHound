# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CLI argument parser for the hound agent."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hound",
        description="TraceHound Hound Agent — autonomous jiuwenswarm log monitor.",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        metavar="PATH",
        help="Path to agent_config.yaml (default: ~/.jiuwenswarm/hound/agent_config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # start
    start = sub.add_parser("start", help="Start the agent (foreground by default)")
    start.add_argument("--daemon", action="store_true", help="Run as background daemon")

    # stop
    sub.add_parser("stop", help="Stop a running daemon")

    # status
    sub.add_parser("status", help="Show live metric snapshot")

    # alerts
    alerts_p = sub.add_parser("alerts", help="List alerts")
    alerts_p.add_argument("--all", action="store_true", help="Include resolved alerts")

    # ack
    ack = sub.add_parser("ack", help="Acknowledge an alert by ID")
    ack.add_argument("alert_id", type=int, help="Alert database ID")

    # report
    sub.add_parser("report", help="Trigger an immediate full analysis and save report")

    # baseline
    sub.add_parser("baseline", help="Recompute baselines from recent data")

    # gate
    gate = sub.add_parser("gate", help="Exit 0 if quality OK, else exit 1 (for CI use)")
    gate.add_argument("--min-quality", type=float, default=0.65, metavar="Q")
    gate.add_argument("--last-turns", type=int, default=20, metavar="N")

    return parser
