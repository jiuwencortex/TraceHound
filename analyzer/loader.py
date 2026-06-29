# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Turn-log loader.

Supports two source formats:

1. **Thalamus weekly logs** (default) — files named ``turns_YYYY-WNN.jsonl`` produced
   by the thalamus TurnLogger.
2. **JiuwenSwarm session histories** — ``history.jsonl`` files inside
   ``agent/sessions/{session_id}/`` directories produced by the
   jiuwenswarm runtime.

Format is auto-detected from the directory contents.  Pass ``source_type``
to force a specific parser.
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


def _detect_source_type(log_dir: Path) -> str:
    """Auto-detect whether ``log_dir`` contains thalamus or jiuwenswarm logs."""
    # JiuwenSwarm: agent/sessions/*/history.jsonl  (or sessions/*/history.jsonl)
    if (log_dir / "agent" / "sessions").is_dir():
        return "jiuwenswarm_sessions"
    if (log_dir / "sessions").is_dir():
        # sanity check: does it contain history.jsonl files?
        for sub in (log_dir / "sessions").iterdir():
            if sub.is_dir() and (sub / "history.jsonl").exists():
                return "jiuwenswarm_sessions"
    # Default to thalamus if turns_*.jsonl files exist or as fallback
    return "thalamus"


def _week_tag_from_mtime(path: Path) -> str:
    """Derive an ISO week tag from a file's last-modified time."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    iso_cal = dt.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"


def _parse_jiuwenswarm_turn(messages: list[dict], week_tag: str) -> TurnRecord | None:
    """Convert a group of jiuwenswarm session messages (same request_id) to a TurnRecord.

    Messages are expected to be raw dicts from ``history.jsonl`` with keys:
    ``id``, ``role``, ``request_id``, ``timestamp``, ``content``, ``event_type``,
    ``tool_call``, ``tool_name``, ``error``, etc.
    """
    if not messages:
        return None

    # Sort by timestamp ascending
    messages.sort(key=lambda m: float(m.get("timestamp", 0)))

    turn_id = str(messages[0].get("request_id", ""))
    if not turn_id:
        return None

    # Timestamp from the first message (usually the user message)
    ts_raw = messages[0].get("timestamp", 0)
    try:
        timestamp = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
    except (ValueError, TypeError):
        timestamp = datetime.fromtimestamp(0, tz=timezone.utc)

    # Heuristic: task_completed = True if no errors and assistant gave non-empty content
    has_error = any(m.get("event_type") == "chat.error" for m in messages)
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    has_content = any(
        bool(m.get("content")) for m in assistant_messages
        if m.get("event_type") not in ("chat.tool_call", "chat.tool_update", "chat.usage_metadata")
    )
    task_completed = not has_error and has_content

    # Tools called from chat.tool_call events
    tools_called: list[str] = []
    for m in messages:
        if m.get("event_type") == "chat.tool_call":
            tc = m.get("tool_call") or {}
            name = tc.get("name")
            if name:
                tools_called.append(str(name))

    # Deduplicate while preserving order
    seen = set()
    tools_called = [t for t in tools_called if not (t in seen or seen.add(t))]

    # Mode from first message (e.g. "team", "agent.plan")
    mode = str(messages[0].get("mode", ""))

    # conversation_length = number of messages in this turn
    conversation_length = len(messages)

    return TurnRecord(
        turn_id=turn_id,
        timestamp=timestamp,
        query_embedding=[],
        skills=[],
        memory_sections=[],
        tools=[],
        explicit_rating=None,
        follow_up_correction=has_error,
        task_completed=task_completed,
        conversation_length=conversation_length,
        skills_used=[],
        tools_called=tools_called,
        llm_judge_score=None,
        explored=False,
        exploration_additions={},
        week_tag=week_tag,
    )


class TrajectoriesLoader:
    """Load turn logs from thalamus weekly files or jiuwenswarm session histories.

    Args:
        log_dir: Directory containing log files.
        max_weeks: Maximum number of most-recent weekly files (thalamus) or
            session files (jiuwenswarm) to load.
        source_type: ``"auto"`` (default), ``"thalamus"``, or
            ``"jiuwenswarm_sessions"``.
    """

    def __init__(
        self,
        log_dir: str | Path,
        max_weeks: int = 8,
        source_type: str = "auto",
    ) -> None:
        self._log_dir = Path(log_dir)
        self._max_weeks = max_weeks
        self._source_type = (
            source_type if source_type != "auto" else _detect_source_type(self._log_dir)
        )
        self._skipped: int = 0
        self._raw_sessions: dict[Path, list[dict]] = {}

    @property
    def source_type(self) -> str:
        """The detected or configured source type."""
        return self._source_type

    @property
    def skipped_records(self) -> int:
        """Number of records skipped during the last ``load()`` call."""
        return self._skipped

    @property
    def raw_sessions(self) -> dict[Path, list[dict]]:
        """Raw session data from the last ``load()`` call.

        Maps file path -> list of raw message dicts (jiuwenswarm format)
        or list of raw turn dicts (thalamus format).
        Available only after ``load()`` has been called.
        """
        return self._raw_sessions

    def log_files(self) -> list[Path]:
        """Return matching log file paths sorted newest-first, up to max_weeks."""
        if self._source_type == "jiuwenswarm_sessions":
            # Look for agent/sessions/*/history.jsonl or sessions/*/history.jsonl
            sessions_dir = self._log_dir / "agent" / "sessions"
            if not sessions_dir.is_dir():
                sessions_dir = self._log_dir / "sessions"

            paths: list[Path] = []
            if sessions_dir.is_dir():
                for sub in sessions_dir.iterdir():
                    hist = sub / "history.jsonl"
                    if hist.exists():
                        paths.append(hist)

            # Sort by modification time (newest first)
            paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return paths[: self._max_weeks]

        # Thalamus default
        paths = sorted(self._log_dir.glob("turns_*.jsonl"), reverse=True)
        return paths[: self._max_weeks]

    def load(self) -> list[TurnRecord]:
        """Load and parse all turn records, sorted by timestamp ascending."""
        self._skipped = 0
        self._raw_sessions = {}
        records: list[TurnRecord] = []

        if self._source_type == "jiuwenswarm_sessions":
            records = self._load_jiuwenswarm_sessions()
        else:
            records = self._load_thalamus()

        records.sort(key=lambda r: r.timestamp)
        return records

    def _load_thalamus(self) -> list[TurnRecord]:
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
                self._raw_sessions.setdefault(path, []).append(raw)

        return records

    def _load_jiuwenswarm_sessions(self) -> list[TurnRecord]:
        records: list[TurnRecord] = []
        for path in self.log_files():
            week_tag = _week_tag_from_mtime(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("trajectories_analyzer: cannot read {}: {}", path, exc)
                continue

            # Group messages by request_id
            messages_by_request: dict[str, list[dict]] = {}
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    self._skipped += 1
                    continue

                req_id = raw.get("request_id")
                if not req_id:
                    self._skipped += 1
                    continue

                messages_by_request.setdefault(str(req_id), []).append(raw)

            for req_id, messages in messages_by_request.items():
                record = _parse_jiuwenswarm_turn(messages, week_tag)
                if record is None:
                    self._skipped += 1
                else:
                    records.append(record)
            self._raw_sessions[path] = [
                raw for raw in (json.loads(line) for line in text.splitlines() if line.strip())
                if isinstance(raw, dict)
            ]

        return records
