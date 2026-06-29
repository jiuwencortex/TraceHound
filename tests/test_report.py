# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""End-to-end tests for TrajectoriesReport."""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.loader import TrajectoriesLoader
from analyzer.report import TrajectoriesReport


def test_report_run_produces_result(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()

    assert result.data_health.total_turns == 8
    assert result.quality_trends.overall_mean > 0.0
    assert result.data_health.date_range is not None


def test_render_text_non_empty(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    text = report.render_text(result)

    assert "Trajectories Analyzer Report" in text
    assert "Data Health" in text
    assert "Quality Trend" in text
    assert "Component Bottlenecks" in text
    assert "Budget Waste" in text
    assert "Correction Patterns" in text
    assert "Exploration Analysis" in text


def test_render_json_valid(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    json_output = report.render_json(result)

    parsed = json.loads(json_output)
    assert "generated_at" in parsed
    assert "data_health" in parsed
    assert "quality_trends" in parsed
    assert "component_performance" in parsed
    assert "budget_waste" in parsed
    assert "correction_patterns" in parsed
    assert "exploration" in parsed


def test_report_on_empty_log_dir(tmp_path: Path) -> None:
    loader = TrajectoriesLoader(tmp_path, max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()

    assert result.data_health.total_turns == 0
    assert result.quality_trends.trend_direction == "insufficient_data"
    text = report.render_text(result)
    assert "Trajectories Analyzer Report" in text


def test_result_to_dict_is_json_serializable(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    # Should not raise
    as_dict = result.to_dict()
    json.dumps(as_dict)
