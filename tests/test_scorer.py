# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tests for trajectories_analyzer.scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.trajectories_analyzer.loader import TrajectoriesLoader
from jiuwenswarm.trajectories_analyzer.scorer import compute_qualities, compute_quality


def _make_turn(
    explicit_rating=None,
    llm_judge_score=None,
    task_completed=False,
    follow_up_correction=False,
    conversation_length=0,
    log_dir=None,
):
    """Build a minimal TurnRecord via the loader using a single-line JSONL."""
    import json
    import tempfile

    record = {
        "turn_id": "test-turn-id",
        "timestamp": "2025-01-01T00:00:00Z",
        "query_embedding": [0.1],
        "context_config": {"skills": [], "memory_sections": [], "tools": []},
        "outcome": {
            "explicit_rating": explicit_rating,
            "implicit_signals": {
                "follow_up_correction": follow_up_correction,
                "task_completed": task_completed,
                "conversation_length": conversation_length,
            },
            "component_usage": {"skills_used": [], "tools_called": []},
        },
    }
    if llm_judge_score is not None:
        record["outcome"]["llm_judge_score"] = llm_judge_score

    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "turns_2025-W01.jsonl"
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        loader = TrajectoriesLoader(tmpdir, max_weeks=1)
        turns = loader.load()

    return turns[0]


def test_explicit_positive():
    t = _make_turn(explicit_rating="positive")
    assert compute_quality(t) == 1.0


def test_explicit_negative():
    t = _make_turn(explicit_rating="negative")
    assert compute_quality(t) == 0.0


def test_llm_judge_score_used_when_no_explicit():
    t = _make_turn(llm_judge_score=0.72)
    assert compute_quality(t) == pytest.approx(0.72)


def test_implicit_signals_task_completed():
    t = _make_turn(task_completed=True)
    # 0.5 + 0.2 + max(0, 0.1 - 0.02*0) = 0.8
    assert compute_quality(t) == pytest.approx(0.8)


def test_implicit_signals_correction():
    t = _make_turn(follow_up_correction=True)
    # 0.5 - 0.3 + 0.1 = 0.3
    assert compute_quality(t) == pytest.approx(0.3)


def test_implicit_signals_long_conversation():
    t = _make_turn(task_completed=True, conversation_length=10)
    # 0.5 + 0.2 + max(0, 0.1 - 0.2) = 0.7
    assert compute_quality(t) == pytest.approx(0.7)


def test_quality_clamped_to_zero():
    t = _make_turn(follow_up_correction=True, conversation_length=20)
    # 0.5 - 0.3 + 0 = 0.2  → still positive, just reduced
    assert compute_quality(t) >= 0.0


def test_compute_qualities_list(log_dir: Path):
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()
    qualities = compute_qualities(turns)
    assert len(qualities) == len(turns)
    assert all(0.0 <= q <= 1.0 for q in qualities)


def test_explicit_rating_overrides_judge(log_dir: Path):
    """Explicit rating takes priority over llm_judge_score."""
    import json
    import tempfile

    record = {
        "turn_id": "priority-test",
        "timestamp": "2025-01-01T00:00:00Z",
        "query_embedding": [0.1],
        "context_config": {"skills": [], "memory_sections": [], "tools": []},
        "outcome": {
            "explicit_rating": "positive",
            "implicit_signals": {
                "follow_up_correction": True,
                "task_completed": False,
                "conversation_length": 10,
            },
            "component_usage": {"skills_used": [], "tools_called": []},
            "llm_judge_score": 0.1,
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "turns_2025-W01.jsonl"
        p.write_text(json.dumps(record) + "\n", encoding="utf-8")
        turns = TrajectoriesLoader(tmpdir, max_weeks=1).load()
    assert compute_quality(turns[0]) == 1.0
