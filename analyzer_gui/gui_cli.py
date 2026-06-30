# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""GUI entry point argument parsing."""

from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="TraceHoundGUI",
        description="TraceHound graphical analysis dashboard.",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="PATH",
        help="Pre-populate the log directory field on launch.",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=30,
        metavar="N",
        help="Maximum number of sessions (weeks) to load (default: 30).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    from analyzer_gui.app import TraceHoundApp

    app = TraceHoundApp(
        initial_log_dir=Path(args.log_dir) if args.log_dir else None,
        initial_max_sessions=args.max_sessions,
    )
    app.mainloop()
