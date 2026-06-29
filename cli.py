# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""CLI entry point for the Trajectories Analyzer.

Usage::

    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs
    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs --format json --output report.json
    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs --max-weeks 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jiuwenswarm-analyze-trajectories",
        description="Analyze thalamus turn-log trajectories and report bottlenecks.",
    )
    parser.add_argument(
        "--log-dir",
        required=True,
        metavar="PATH",
        help="Directory containing thalamus turns_YYYY-WNN.jsonl files.",
    )
    parser.add_argument(
        "--max-weeks",
        type=int,
        default=8,
        metavar="N",
        help="Number of most-recent weekly log files to load (default: 8).",
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
        "--threshold-quality",
        type=float,
        default=0.15,
        metavar="FLOAT",
        help=(
            "Quality deficit threshold for component bottleneck flags "
            "(default: 0.15, meaning components more than 0.15 below global mean are flagged)."
        ),
    )
    parser.add_argument(
        "--threshold-utilization",
        type=float,
        default=0.20,
        metavar="FLOAT",
        help="Utilization rate below which a component is flagged as rarely-used (default: 0.20).",
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

    from loader import TrajectoriesLoader
    from report import TrajectoriesReport

    loader = TrajectoriesLoader(log_dir, max_weeks=args.max_weeks)
    reporter = TrajectoriesReport(
        loader,
        quality_deficit_threshold=args.threshold_quality,
        utilization_threshold=args.threshold_utilization,
        correction_lift_threshold=args.threshold_lift,
    )

    result = reporter.run()

    if args.format == "json":
        output_text = reporter.render_json(result)
    else:
        output_text = reporter.render_text(result)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text, encoding="utf-8")
        logger.info("trajectories_analyzer: report written to {}", out_path)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
