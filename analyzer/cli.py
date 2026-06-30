# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CLI entry point for the Trajectories Analyzer.

Usage::

    TraceHound --log-dir /path/to/online_logs
    TraceHound --log-dir /path/to/online_logs --format json --output report.json
    TraceHound --log-dir /path/to/online_logs --max-weeks 4
"""

# python -m analyzer --log-dir C:\Users\m00645993\.jiuwenswarm --max-weeks 30 -v
# python -m analyzer --log-dir /Users/mishka/.jiuwenswarm --max-weeks 30 -v

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger
from analyzer.loader import TrajectoriesLoader
from analyzer.report import TrajectoriesReport


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="TraceHound",
        description="Analyze jiuwenswarm turn-log trajectories and report bottlenecks.",
    )
    parser.add_argument(
        "--log-dir",
        required=True,
        metavar="PATH",
        help="Directory containing log files. Session histories at agent/sessions/*/history.jsonl are discovered automatically.",
    )
    parser.add_argument(
        "--max-weeks",
        type=int,
        default=8,
        metavar="N",
        help="Maximum number of most-recent session files to load (default: 8).",
    )
    parser.add_argument(
        "--raw-logs",
        action="store_true",
        help="Append per-session, per-turn trajectory detail after the analysis report.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed analysis with per-turn evidence, breakdowns, and calculations.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: 'text' (default) or 'json'.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Write report to FILE instead of stdout.",
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Generate a Desktop-style analysis report (saved to ~/Desktop/analysis.md). Overrides --output and --format.",
    )
    parser.add_argument(
        "--threshold-lift",
        type=float,
        default=1.5,
        metavar="FLOAT",
        help="Correction lift threshold for flagging high-correction-rate components (default: 1.5).",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        logger.error("trajectories_analyzer: log directory does not exist: {}", log_dir)
        sys.exit(1)

    loader = TrajectoriesLoader(
        log_dir,
        max_weeks=args.max_weeks,
    )
    reporter = TrajectoriesReport(
        loader,
        correction_lift_threshold=args.threshold_lift,
    )

    result = reporter.run()

    if args.desktop:
        # Desktop mode: generate structured analysis report
        desktop_path = Path.home() / "Desktop" / "analysis.md"
        output_text = reporter.render_desktop(result)
        desktop_path.write_text(output_text, encoding="utf-8")
        logger.info("trajectories_analyzer: Desktop report written to {}", desktop_path)
        return

    if args.format == "json":
        output_text = reporter.render_json(result)
    else:
        output_text = reporter.render_text(result, verbose=args.verbose)
        if args.raw_logs:
            output_text += "\n\n" + reporter.render_verbose(result, loader)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text, encoding="utf-8")
        logger.info("trajectories_analyzer: report written to {}", out_path)
    else:
        # force utf-8 output on Windows to avoid UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
        print(output_text)


if __name__ == "__main__":
    main()
