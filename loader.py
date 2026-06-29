# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Turn-log loader.

Reads weekly-rotated JSONL files written by the thalamus TurnLogger and
returns a list of typed TurnRecord objects sorted by timestamp ascending.

File naming convention: ``turns_YYYY-WNN.jsonl``
One JSON object per line; blank lines and malformed records are skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class TurnRecord:
    """Parsed representation of one agent turn log entry."""

    turn_id: str
    timestamp: datetime
    query_embedding: list[float]

    # context_config
    skills: list[str]
    memory_sections: list[str]
    tools: list[str]

    # outcome
    explicit_rating: str | None  # "positive" | "negative" | None
    follow_up_correction: bool
    task_completed: bool
    conversation_length: int
    skills_used: list[str]
    tools_called: list[str]
    llm_judge_score: float | None

    # exploration (present only when the turn used off-policy exploration)
    explored: bool
    exploration_additions: dict  # {"skills": [...], "memory": [...], "tools": [...]}

    # ISO week tag derived from the file name, e.g. "2025-W03"
    week_tag: str

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp.isoformat(),
            "query_embedding": self.query_embedding,
            "skills": self.skills,
            "memory_sections": self.memory_sections,
            "tools": self.tools,
            "explicit_rating": self.explicit_rating,
            "follow_up_correction": self.follow_up_correction,
            "task_completed": self.task_completed,
            "conversation_length": self.conversation_length,
            "skills_used": self.skills_used,
            "tools_called": self.tools_called,
            "llm_judge_score": self.llm_judge_score,
            "explored": self.explored,
            "exploration_additions": self.exploration_additions,
            "week_tag": self.week_tag,
        }


def _parse_timestamp(raw: str) -> datetime:
    """Parse ISO 8601 UTC timestamp into a timezone-aware datetime."""
    try:
        # Handle both "Z" suffix and "+00:00"
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except (ValueError, AttributeError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _week_tag_from_path(path: Path) -> str:
    """Extract week tag from filename, e.g. turns_2025-W03.jsonl → '2025-W03'."""
    stem = path.stem  # turns_2025-W03
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else stem


def _parse_record(raw: dict, week_tag: str) -> TurnRecord | None:
    """Convert a raw dict to a TurnRecord.  Returns None if required fields are absent."""
    turn_id = raw.get("turn_id")
    if not turn_id:
        return None

    timestamp_raw = raw.get("timestamp", "1970-01-01T00:00:00Z")
    timestamp = _parse_timestamp(str(timestamp_raw))

    embedding = raw.get("query_embedding") or []

    ctx = raw.get("context_config") or {}
    skills: list[str] = list(ctx.get("skills") or [])
    memory_sections: list[str] = list(ctx.get("memory_sections") or [])
    tools: list[str] = list(ctx.get("tools") or [])

    outcome = raw.get("outcome") or {}
    explicit_rating = outcome.get("explicit_rating")
    implicit = outcome.get("implicit_signals") or {}
    follow_up_correction: bool = bool(implicit.get("follow_up_correction", False))
    task_completed: bool = bool(implicit.get("task_completed", False))
    conversation_length: int = int(implicit.get("conversation_length") or 0)

    usage = outcome.get("component_usage") or {}
    skills_used: list[str] = list(usage.get("skills_used") or [])
    tools_called: list[str] = list(usage.get("tools_called") or [])

    llm_judge_raw = outcome.get("llm_judge_score")
    llm_judge_score: float | None = float(llm_judge_raw) if llm_judge_raw is not None else None

    exploration_block = raw.get("exploration") or {}
    explored: bool = bool(exploration_block.get("explored", False))
    exploration_additions: dict = dict(exploration_block.get("explored_additions") or {})

    return TurnRecord(
        turn_id=str(turn_id),
        timestamp=timestamp,
        query_embedding=list(embedding),
        skills=skills,
        memory_sections=memory_sections,
        tools=tools,
        explicit_rating=explicit_rating if explicit_rating in ("positive", "negative") else None,
        follow_up_correction=follow_up_correction,
        task_completed=task_completed,
        conversation_length=conversation_length,
        skills_used=skills_used,
        tools_called=tools_called,
        llm_judge_score=llm_judge_score,
        explored=explored,
        exploration_additions=exploration_additions,
        week_tag=week_tag,
    )


class TrajectoriesLoader:
    """Load thalamus turn-log JSONL files from a directory.

    Args:
        log_dir: Directory containing ``turns_YYYY-WNN.jsonl`` files.
        max_weeks: Maximum number of most-recent weekly files to load.
    """

    def __init__(self, log_dir: str | Path, max_weeks: int = 8) -> None:
        self._log_dir = Path(log_dir)
        self._max_weeks = max_weeks
        self._skipped: int = 0

    @property
    def skipped_records(self) -> int:
        """Number of records skipped during the last ``load()`` call."""
        return self._skipped

    def log_files(self) -> list[Path]:
        """Return matching log file paths sorted newest-first, up to max_weeks."""
        paths = sorted(self._log_dir.glob("turns_*.jsonl"), reverse=True)
        return paths[: self._max_weeks]

    def load(self) -> list[TurnRecord]:
        """Load and parse all turn records, sorted by timestamp ascending."""
        self._skipped = 0
        records: list[TurnRecord] = []

        for path in self.log_files():
            week_tag = _week_tag_from_path(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("trajectories_analyzer: cannot read {}: {}", path, exc)
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    self._skipped += 1
                    continue

                record = _parse_record(raw, week_tag)
                if record is None:
                    self._skipped += 1
                else:
                    records.append(record)

        records.sort(key=lambda r: r.timestamp)
        return records
