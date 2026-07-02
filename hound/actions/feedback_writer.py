# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""JiuwenswarmFeedbackWriter — writes tracehound_feedback.yaml for jiuwenswarm."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..accumulate.state import AnalyzerState


class JiuwenswarmFeedbackWriter:
    """Writes a YAML file that jiuwenswarm can optionally read to adjust behaviour.

    This file is written on schedule (not per-alert) by the ReportScheduler.
    """

    def __init__(self, feedback_path: Path) -> None:
        self._path = feedback_path

    def write(self, state: AnalyzerState) -> None:
        """Serialise the current AnalyzerState into tracehound_feedback.yaml."""
        import yaml  # optional dependency

        quality_trend = (
            "improving" if state.quality_ema > 0.65
            else "degrading" if state.quality_ema < 0.45
            else "stable"
        )

        token_pressure = (
            "high" if state.mean_usage_percent > 0.75
            else "moderate" if state.mean_usage_percent > 0.50
            else "low"
        )

        # Build per-tool failure summary
        problem_tools = []
        for tool, calls in state.tool_failure_windows.items():
            if not calls:
                continue
            failure_rate = calls.count(False) / len(calls)
            if failure_rate >= 0.30:
                problem_tools.append({
                    "name": tool,
                    "failure_rate": round(failure_rate, 3),
                    "recommendation": "Consider adding retry logic or checking tool configuration",
                })

        data = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "quality_ema": round(state.quality_ema, 4),
            "quality_trend": quality_trend,
            "error_rate": round(state.error_rate, 4),
            "correction_rate": round(state.correction_rate, 4),
            "token_pressure": token_pressure,
            "mean_usage_percent": round(state.mean_usage_percent, 4),
            "estimated_daily_cost_usd": round(state.estimated_daily_cost_usd, 4),
            "problem_tools": problem_tools,
            "turn_count": state.turn_count,
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
