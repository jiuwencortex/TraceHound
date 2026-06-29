# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Shared fixtures for trajectories_analyzer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Raw turn dicts used across multiple test modules
# ---------------------------------------------------------------------------

TURN_POSITIVE = {
    "turn_id": "aaaa0001-0000-0000-0000-000000000001",
    "timestamp": "2025-01-06T10:00:00Z",
    "query_embedding": [0.1, 0.2, 0.3],
    "context_config": {
        "skills": ["bash-scripting", "debugging-tools"],
        "memory_sections": ["project.md::Architecture"],
        "tools": ["bash_exec", "file_reader"],
    },
    "outcome": {
        "explicit_rating": "positive",
        "implicit_signals": {
            "follow_up_correction": False,
            "task_completed": True,
            "conversation_length": 2,
        },
        "component_usage": {
            "skills_used": ["bash-scripting"],
            "tools_called": ["bash_exec"],
        },
    },
}

TURN_NEGATIVE_WITH_CORRECTION = {
    "turn_id": "aaaa0004-0000-0000-0000-000000000004",
    "timestamp": "2025-01-09T14:00:00Z",
    "query_embedding": [0.4, 0.2, 0.1],
    "context_config": {
        "skills": ["bash-scripting", "legacy-formatter"],
        "memory_sections": ["user.md::Preferences"],
        "tools": ["bash_exec", "file_diff"],
    },
    "outcome": {
        "explicit_rating": "negative",
        "implicit_signals": {
            "follow_up_correction": True,
            "task_completed": False,
            "conversation_length": 8,
        },
        "component_usage": {
            "skills_used": ["bash-scripting"],
            "tools_called": ["bash_exec"],
        },
    },
}

TURN_EXPLORED_GOOD = {
    "turn_id": "aaaa0006-0000-0000-0000-000000000006",
    "timestamp": "2025-01-13T09:00:00Z",
    "query_embedding": [0.5, 0.1, 0.3],
    "context_config": {
        "skills": ["bash-scripting", "debugging-tools"],
        "memory_sections": ["project.md::Architecture"],
        "tools": ["bash_exec"],
    },
    "outcome": {
        "explicit_rating": None,
        "implicit_signals": {
            "follow_up_correction": False,
            "task_completed": True,
            "conversation_length": 3,
        },
        "component_usage": {
            "skills_used": ["bash-scripting", "debugging-tools"],
            "tools_called": ["bash_exec"],
        },
    },
    "exploration": {
        "explored": True,
        "exploration_rate": 0.1,
        "explored_additions": {"skills": ["debugging-tools"], "memory": [], "tools": []},
    },
}

TURN_EXPLORED_BAD = {
    "turn_id": "aaaa0007-0000-0000-0000-000000000007",
    "timestamp": "2025-01-14T10:00:00Z",
    "query_embedding": [0.2, 0.5, 0.1],
    "context_config": {
        "skills": ["legacy-formatter"],
        "memory_sections": ["user.md::Preferences"],
        "tools": ["file_diff"],
    },
    "outcome": {
        "explicit_rating": "negative",
        "implicit_signals": {
            "follow_up_correction": True,
            "task_completed": False,
            "conversation_length": 7,
        },
        "component_usage": {
            "skills_used": [],
            "tools_called": [],
        },
    },
    "exploration": {
        "explored": True,
        "exploration_rate": 0.1,
        "explored_additions": {"skills": ["legacy-formatter"], "memory": [], "tools": []},
    },
}

ALL_TURNS = [
    TURN_POSITIVE,
    {
        "turn_id": "aaaa0002-0000-0000-0000-000000000002",
        "timestamp": "2025-01-07T11:00:00Z",
        "query_embedding": [0.2, 0.3, 0.4],
        "context_config": {
            "skills": ["bash-scripting"],
            "memory_sections": ["project.md::Architecture", "user.md::Preferences"],
            "tools": ["file_reader"],
        },
        "outcome": {
            "explicit_rating": None,
            "implicit_signals": {
                "follow_up_correction": True,
                "task_completed": False,
                "conversation_length": 5,
            },
            "component_usage": {
                "skills_used": [],
                "tools_called": ["file_reader"],
            },
            "llm_judge_score": 0.35,
        },
    },
    {
        "turn_id": "aaaa0003-0000-0000-0000-000000000003",
        "timestamp": "2025-01-08T09:00:00Z",
        "query_embedding": [0.3, 0.1, 0.2],
        "context_config": {
            "skills": ["python-dev", "debugging-tools"],
            "memory_sections": ["project.md::Architecture"],
            "tools": ["python_exec", "file_reader"],
        },
        "outcome": {
            "explicit_rating": None,
            "implicit_signals": {
                "follow_up_correction": False,
                "task_completed": True,
                "conversation_length": 1,
            },
            "component_usage": {
                "skills_used": ["python-dev"],
                "tools_called": ["python_exec"],
            },
            "llm_judge_score": 0.82,
        },
    },
    TURN_NEGATIVE_WITH_CORRECTION,
    {
        "turn_id": "aaaa0005-0000-0000-0000-000000000005",
        "timestamp": "2025-01-10T15:00:00Z",
        "query_embedding": [0.1, 0.4, 0.2],
        "context_config": {
            "skills": ["python-dev"],
            "memory_sections": ["project.md::Architecture"],
            "tools": ["python_exec"],
        },
        "outcome": {
            "explicit_rating": "positive",
            "implicit_signals": {
                "follow_up_correction": False,
                "task_completed": True,
                "conversation_length": 1,
            },
            "component_usage": {
                "skills_used": ["python-dev"],
                "tools_called": ["python_exec"],
            },
        },
    },
    TURN_EXPLORED_GOOD,
    TURN_EXPLORED_BAD,
    {
        "turn_id": "aaaa0008-0000-0000-0000-000000000008",
        "timestamp": "2025-01-15T11:00:00Z",
        "query_embedding": [0.3, 0.3, 0.3],
        "context_config": {
            "skills": ["python-dev", "debugging-tools"],
            "memory_sections": ["project.md::Architecture"],
            "tools": ["python_exec", "file_reader"],
        },
        "outcome": {
            "explicit_rating": None,
            "implicit_signals": {
                "follow_up_correction": False,
                "task_completed": True,
                "conversation_length": 2,
            },
            "component_usage": {
                "skills_used": ["python-dev", "debugging-tools"],
                "tools_called": ["python_exec", "file_reader"],
            },
            "llm_judge_score": 0.75,
        },
    },
]


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    """Create a temporary log directory with sample JSONL files."""
    # Week 02: turns 1–5 (sorted by timestamp they're all in same week W02)
    w02_turns = ALL_TURNS[:5]
    w02_file = tmp_path / "turns_2025-W02.jsonl"
    lines = [json.dumps(t, ensure_ascii=False) for t in w02_turns]
    # add a truly malformed line to test skipping
    lines.append("{bad json here{{")
    w02_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Week 03: turns 6–8
    w03_turns = ALL_TURNS[5:]
    w03_file = tmp_path / "turns_2025-W03.jsonl"
    w03_file.write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in w03_turns) + "\n",
        encoding="utf-8",
    )

    return tmp_path
