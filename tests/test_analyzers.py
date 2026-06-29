# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tests for all six trajectories_analyzer analyzers."""

from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.trajectories_analyzer.analyzers.budget_waste import BudgetWasteAnalyzer
from jiuwenswarm.trajectories_analyzer.analyzers.component_performance import (
    ComponentPerformanceAnalyzer,
)
from jiuwenswarm.trajectories_analyzer.analyzers.correction_patterns import (
    CorrectionPatternsAnalyzer,
)
from jiuwenswarm.trajectories_analyzer.analyzers.data_health import DataHealthAnalyzer
from jiuwenswarm.trajectories_analyzer.analyzers.exploration_analysis import ExplorationAnalyzer
from jiuwenswarm.trajectories_analyzer.analyzers.quality_trends import QualityTrendsAnalyzer
from jiuwenswarm.trajectories_analyzer.loader import TrajectoriesLoader
from jiuwenswarm.trajectories_analyzer.scorer import compute_qualities


@pytest.fixture
def loaded(log_dir: Path):
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()
    qualities = compute_qualities(turns)
    return loader, turns, qualities


# ---------------------------------------------------------------------------
# DataHealthAnalyzer
# ---------------------------------------------------------------------------


class TestDataHealthAnalyzer:
    def test_total_turns(self, loaded):
        loader, turns, _ = loaded
        result = DataHealthAnalyzer(turns, skipped_records=loader.skipped_records).analyze()
        assert result.total_turns == 8

    def test_skipped_records_counted(self, loaded):
        loader, turns, _ = loaded
        result = DataHealthAnalyzer(turns, skipped_records=loader.skipped_records).analyze()
        assert result.skipped_records >= 1

    def test_turns_per_week(self, loaded):
        _, turns, _ = loaded
        result = DataHealthAnalyzer(turns).analyze()
        assert "2025-W02" in result.turns_per_week
        assert "2025-W03" in result.turns_per_week
        assert result.turns_per_week["2025-W02"] == 5
        assert result.turns_per_week["2025-W03"] == 3

    def test_explicit_rating_coverage(self, loaded):
        _, turns, _ = loaded
        result = DataHealthAnalyzer(turns).analyze()
        # turns 1, 4, 5, 7 have explicit ratings → 4/8 = 0.5
        assert result.explicit_rating_coverage == pytest.approx(0.5)

    def test_date_range_set(self, loaded):
        _, turns, _ = loaded
        result = DataHealthAnalyzer(turns).analyze()
        assert result.date_range is not None
        start, end = result.date_range
        assert start < end

    def test_empty_turns(self):
        result = DataHealthAnalyzer([]).analyze()
        assert result.total_turns == 0
        assert result.date_range is None

    def test_to_dict_serializable(self, loaded):
        _, turns, _ = loaded
        result = DataHealthAnalyzer(turns).analyze()
        d = result.to_dict()
        assert isinstance(d["turns_per_week"], dict)
        assert isinstance(d["explicit_rating_coverage"], float)


# ---------------------------------------------------------------------------
# QualityTrendsAnalyzer
# ---------------------------------------------------------------------------


class TestQualityTrendsAnalyzer:
    def test_weeks_count(self, loaded):
        _, turns, qualities = loaded
        result = QualityTrendsAnalyzer(turns, qualities).analyze()
        assert len(result.weeks) == 2

    def test_overall_mean_in_range(self, loaded):
        _, turns, qualities = loaded
        result = QualityTrendsAnalyzer(turns, qualities).analyze()
        assert 0.0 <= result.overall_mean <= 1.0

    def test_best_and_worst_week_set(self, loaded):
        _, turns, qualities = loaded
        result = QualityTrendsAnalyzer(turns, qualities).analyze()
        assert result.best_week is not None
        assert result.worst_week is not None

    def test_insufficient_data_with_one_week(self, loaded):
        _, turns, qualities = loaded
        # Filter to only W02 turns
        w02_turns = [t for t in turns if t.week_tag == "2025-W02"]
        w02_q = [q for t, q in zip(turns, qualities) if t.week_tag == "2025-W02"]
        result = QualityTrendsAnalyzer(w02_turns, w02_q).analyze()
        assert result.trend_direction == "insufficient_data"

    def test_empty_turns_returns_insufficient_data(self):
        result = QualityTrendsAnalyzer([], []).analyze()
        assert result.trend_direction == "insufficient_data"
        assert result.overall_mean == 0.0

    def test_to_dict(self, loaded):
        _, turns, qualities = loaded
        result = QualityTrendsAnalyzer(turns, qualities).analyze()
        d = result.to_dict()
        assert "weeks" in d
        assert "trend_direction" in d


# ---------------------------------------------------------------------------
# ComponentPerformanceAnalyzer
# ---------------------------------------------------------------------------


class TestComponentPerformanceAnalyzer:
    def test_components_found(self, loaded):
        _, turns, qualities = loaded
        result = ComponentPerformanceAnalyzer(turns, qualities).analyze()
        names = [c.name for c in result.components]
        assert "bash-scripting" in names
        assert "python-dev" in names

    def test_global_mean_in_range(self, loaded):
        _, turns, qualities = loaded
        result = ComponentPerformanceAnalyzer(turns, qualities).analyze()
        assert 0.0 <= result.global_mean_quality <= 1.0

    def test_flagged_components_have_flags(self, loaded):
        _, turns, qualities = loaded
        result = ComponentPerformanceAnalyzer(turns, qualities, quality_deficit_threshold=0.0).analyze()
        for c in result.flagged_components:
            assert len(c.flags) > 0
            assert "insufficient_data" not in c.flags

    def test_low_turns_gets_insufficient_data_flag(self, loaded):
        """A component with < 5 turns should be flagged as insufficient_data, not bottleneck."""
        _, turns, qualities = loaded
        result = ComponentPerformanceAnalyzer(turns, qualities, min_turns_for_flag=100).analyze()
        for c in result.components:
            if "insufficient_data" in c.flags:
                assert "low_quality" not in c.flags

    def test_to_dict(self, loaded):
        _, turns, qualities = loaded
        result = ComponentPerformanceAnalyzer(turns, qualities).analyze()
        d = result.to_dict()
        assert "flagged_components" in d
        assert isinstance(d["components"], list)


# ---------------------------------------------------------------------------
# BudgetWasteAnalyzer
# ---------------------------------------------------------------------------


class TestBudgetWasteAnalyzer:
    def test_never_used_skill_detected(self, loaded):
        _, turns, qualities = loaded
        # "legacy-formatter" is in context_config.skills but never in skills_used
        result = BudgetWasteAnalyzer(turns, qualities, min_turns=1).analyze()
        # legacy-formatter appears in 2 turns but is never used
        assert "legacy-formatter" in result.never_used_skills

    def test_never_used_tool_detected(self, loaded):
        _, turns, qualities = loaded
        # "file_diff" is included but never called
        result = BudgetWasteAnalyzer(turns, qualities, min_turns=1).analyze()
        assert "file_diff" in result.never_used_tools

    def test_to_dict(self, loaded):
        _, turns, qualities = loaded
        result = BudgetWasteAnalyzer(turns, qualities).analyze()
        d = result.to_dict()
        assert "never_used_skills" in d
        assert "never_used_tools" in d
        assert "rarely_used_skills" in d

    def test_empty_turns(self):
        result = BudgetWasteAnalyzer([], []).analyze()
        assert result.never_used_skills == []
        assert result.never_used_tools == []


# ---------------------------------------------------------------------------
# CorrectionPatternsAnalyzer
# ---------------------------------------------------------------------------


class TestCorrectionPatternsAnalyzer:
    def test_baseline_rate_computed(self, loaded):
        _, turns, _ = loaded
        result = CorrectionPatternsAnalyzer(turns).analyze()
        # turns 2, 4, 7 have correction=True → 3/8 = 0.375
        assert result.baseline_correction_rate == pytest.approx(3 / 8)
        assert result.total_corrected_turns == 3

    def test_high_lift_components_sorted_descending(self, loaded):
        _, turns, _ = loaded
        result = CorrectionPatternsAnalyzer(turns, lift_threshold=1.0, min_turns=1).analyze()
        lifts = [p.lift for p in result.high_lift_components]
        assert lifts == sorted(lifts, reverse=True)

    def test_to_dict(self, loaded):
        _, turns, _ = loaded
        result = CorrectionPatternsAnalyzer(turns).analyze()
        d = result.to_dict()
        assert "high_lift_components" in d
        assert "baseline_correction_rate" in d

    def test_empty_turns(self):
        result = CorrectionPatternsAnalyzer([]).analyze()
        assert result.baseline_correction_rate == 0.0
        assert result.high_lift_components == []


# ---------------------------------------------------------------------------
# ExplorationAnalyzer
# ---------------------------------------------------------------------------


class TestExplorationAnalyzer:
    def test_explored_turns_counted(self, loaded):
        _, turns, qualities = loaded
        result = ExplorationAnalyzer(turns, qualities).analyze()
        assert result.n_explored == 2
        assert result.n_normal == 6

    def test_quality_delta_computed(self, loaded):
        _, turns, qualities = loaded
        result = ExplorationAnalyzer(turns, qualities).analyze()
        # Just verify it's a valid float
        assert isinstance(result.quality_delta, float)

    def test_promising_and_harmful_sorted(self, loaded):
        _, turns, qualities = loaded
        result = ExplorationAnalyzer(turns, qualities).analyze()
        if result.promising_additions:
            deltas = [a.mean_quality_delta for a in result.promising_additions]
            assert deltas == sorted(deltas, reverse=True)
        if result.harmful_additions:
            deltas = [a.mean_quality_delta for a in result.harmful_additions]
            assert deltas == sorted(deltas)

    def test_to_dict(self, loaded):
        _, turns, qualities = loaded
        result = ExplorationAnalyzer(turns, qualities).analyze()
        d = result.to_dict()
        assert "n_explored" in d
        assert "quality_delta" in d

    def test_no_exploration_turns(self, loaded):
        _, turns, qualities = loaded
        non_explored = [t for t in turns if not t.explored]
        non_explored_q = [q for t, q in zip(turns, qualities) if not t.explored]
        result = ExplorationAnalyzer(non_explored, non_explored_q).analyze()
        assert result.n_explored == 0
        assert result.quality_delta == 0.0
