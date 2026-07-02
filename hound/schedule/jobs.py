# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Scheduled job functions called by ReportScheduler."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


def run_full_analysis(
    log_root: Path,
    max_weeks: int,
    qd_thresh: float,
    lift_thresh: float,
    skip_heartbeats: bool,
    output_dir: Path,
    baseline_store,
    label: str = "scheduled",
) -> None:
    """Run the full 13-analyzer pipeline and save results."""
    from analyzer.loader import TrajectoriesLoader
    from analyzer.report import TrajectoriesReport

    logger.info("hound: starting {} full analysis run", label)
    try:
        loader = TrajectoriesLoader(log_root, max_weeks=max_weeks, skip_heartbeats=skip_heartbeats)
        turns = loader.load()
        reporter = TrajectoriesReport(loader, quality_deficit_threshold=qd_thresh, correction_lift_threshold=lift_thresh)
        result = reporter.run()

        # Update baselines from fresh result
        if result.quality_trends.weeks:
            means = [w.mean_quality for w in result.quality_trends.weeks if w.n_turns > 0]
            if means:
                baseline_store.set("quality_mean", sum(means) / len(means))
        baseline_store.set("error_rate", result.error_categories.overall_error_rate)
        baseline_store.set("mean_tokens", result.token_usage.mean_tokens_per_turn)
        if result.llm_performance.total_latency.median > 0:
            baseline_store.set("median_latency_ms", result.llm_performance.total_latency.median)

        # Write text summary
        now = datetime.now(tz=timezone.utc)
        tag = f"{now.strftime('%Y%m%d_%H%M%S')}_{label}"
        output_dir.mkdir(parents=True, exist_ok=True)

        text_path = output_dir / f"report_{tag}.md"
        text_path.write_text(
            reporter.render_desktop(result), encoding="utf-8"
        )

        json_path = output_dir / f"report_{tag}.json"
        json_path.write_text(reporter.render_json(result), encoding="utf-8")

        logger.info("hound: {} analysis complete → {}", label, text_path)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("hound: {} analysis failed: {}", label, exc)
        return None


def write_session_summary(session_path: Path, turns, reporter) -> None:
    """Write a per-session tracehound_summary.md to the session directory."""
    if not turns:
        return
    try:
        from analyzer.report import TrajectoriesReport
        from analyzer.loader import TrajectoriesLoader
        summary_lines = [
            f"# TraceHound Session Summary",
            f"",
            f"**Session:** {session_path.parent.name}  ",
            f"**Turns:** {len(turns)}  ",
            f"**Generated:** {datetime.now(tz=timezone.utc).isoformat()}  ",
            "",
        ]
        errors = [t for t in turns if t.error_text]
        if errors:
            summary_lines += [
                "## Errors",
                "",
                *[f"- [{t.error_category}] {t.error_text[:80]}" for t in errors[:5]],
                "",
            ]
        summary_path = session_path.parent / "tracehound_summary.md"
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("hound: session summary failed: {}", exc)
