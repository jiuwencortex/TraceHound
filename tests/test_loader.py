# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tests for trajectories_analyzer.loader."""

from __future__ import annotations

from pathlib import Path

from jiuwenswarm.trajectories_analyzer.loader import TrajectoriesLoader, TurnRecord


def test_load_returns_sorted_turns(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()

    assert len(turns) == 8  # 8 valid turns (1 malformed line skipped)
    # sorted by timestamp ascending
    timestamps = [t.timestamp for t in turns]
    assert timestamps == sorted(timestamps)


def test_load_skips_malformed_json(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    loader.load()
    assert loader.skipped_records >= 1


def test_load_respects_max_weeks(log_dir: Path) -> None:
    # With max_weeks=1 we should only get the most recent file (W03 = 3 turns)
    loader = TrajectoriesLoader(log_dir, max_weeks=1)
    turns = loader.load()
    assert len(turns) == 3


def test_turn_record_fields(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()

    # First turn by timestamp = TURN_POSITIVE (2025-01-06)
    first = turns[0]
    assert first.turn_id == "aaaa0001-0000-0000-0000-000000000001"
    assert first.explicit_rating == "positive"
    assert first.task_completed is True
    assert first.follow_up_correction is False
    assert "bash-scripting" in first.skills
    assert "bash_exec" in first.tools
    assert "bash_exec" in first.tools_called
    assert first.explored is False
    assert first.week_tag == "2025-W02"


def test_exploration_fields_parsed(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()

    explored = [t for t in turns if t.explored]
    assert len(explored) == 2

    good = next(t for t in explored if t.turn_id == "aaaa0006-0000-0000-0000-000000000006")
    assert "debugging-tools" in good.exploration_additions.get("skills", [])


def test_missing_log_dir_returns_empty(tmp_path: Path) -> None:
    loader = TrajectoriesLoader(tmp_path / "nonexistent", max_weeks=8)
    turns = loader.load()
    assert turns == []


def test_log_files_sorted_newest_first(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    files = loader.log_files()
    names = [f.name for f in files]
    # W03 > W02 alphabetically and chronologically
    assert names[0] == "turns_2025-W03.jsonl"
    assert names[1] == "turns_2025-W02.jsonl"


def test_turn_record_to_dict(log_dir: Path) -> None:
    loader = TrajectoriesLoader(log_dir, max_weeks=8)
    turns = loader.load()
    d = turns[0].to_dict()
    assert d["turn_id"] == turns[0].turn_id
    assert isinstance(d["timestamp"], str)
    assert "skills" in d
