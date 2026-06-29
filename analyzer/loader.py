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

    # Wall-clock duration of the turn in seconds.
    # Populated from jiuwenswarm message timestamps (last_msg.ts - first_msg.ts).
    # 0.0 for thalamus turns where per-message timing is unavailable.
    duration_seconds: float = 0.0

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
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class ToolCallTiming:
    """Timing record for a single tool call extracted from session messages."""

    turn_id: str
    tool_name: str
    call_timestamp: float    # Unix epoch of the chat.tool_call message
    result_timestamp: float  # Unix epoch of the matching result message; 0 if unknown
    duration_seconds: float  # result_timestamp - call_timestamp; 0 if unmatched


def _parse_timestamp(raw: str) -> datetime:
    """Parse ISO 8601 UTC timestamp into a timezone-aware datetime."""
    try:
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
        duration_seconds=0.0,
    )


def _detect_source_type(log_dir: Path) -> str:
    """Auto-detect whether ``log_dir`` contains thalamus or jiuwenswarm logs."""
    if (log_dir / "agent" / "sessions").is_dir():
        return "jiuwenswarm_sessions"
    if (log_dir / "sessions").is_dir():
        for sub in (log_dir / "sessions").iterdir():
            if sub.is_dir() and (sub / "history.jsonl").exists():
                return "jiuwenswarm_sessions"
    return "thalamus"


def _week_tag_from_mtime(path: Path) -> str:
    """Derive an ISO week tag from a file's last-modified time."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    iso_cal = dt.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"


def _extract_tool_timings(turn_id: str, messages: list[dict]) -> list[ToolCallTiming]:
    """Extract per-tool-call timing from a sorted list of session messages.

    Matches ``chat.tool_call`` events with subsequent ``chat.tool_result`` /
    ``chat.tool_update`` events by tool name.  The first result timestamp that
    is >= the call timestamp is consumed.  If no match is found, duration is 0.
    """
    timings: list[ToolCallTiming] = []

    # Index result/update timestamps by tool name (sorted ascending)
    result_events: dict[str, list[float]] = {}
    for m in messages:
        evt = m.get("event_type", "")
        if evt in ("chat.tool_result", "chat.tool_update"):
            name = str(
                m.get("tool_name")
                or (m.get("tool_call") or {}).get("name", "")
            )
            if name:
                try:
                    result_events.setdefault(name, []).append(float(m.get("timestamp", 0)))
                except (ValueError, TypeError):
                    pass

    for name in result_events:
        result_events[name].sort()

    consumed: dict[str, int] = {}  # tool_name → next index to consume

    for m in messages:
        if m.get("event_type") != "chat.tool_call":
            continue
        tc = m.get("tool_call") or {}
        name = str(tc.get("name", ""))
        if not name:
            continue
        try:
            call_ts = float(m.get("timestamp", 0))
        except (ValueError, TypeError):
            continue

        idx = consumed.get(name, 0)
        candidates = result_events.get(name, [])
        result_ts = 0.0
        for ri in range(idx, len(candidates)):
            if candidates[ri] >= call_ts:
                result_ts = candidates[ri]
                consumed[name] = ri + 1
                break

        duration = max(0.0, result_ts - call_ts) if result_ts else 0.0
        timings.append(
            ToolCallTiming(
                turn_id=turn_id,
                tool_name=name,
                call_timestamp=call_ts,
                result_timestamp=result_ts,
                duration_seconds=duration,
            )
        )

    return timings


def _parse_jiuwenswarm_turn(
    messages: list[dict], week_tag: str
) -> tuple[TurnRecord | None, list[ToolCallTiming]]:
    """Convert a group of jiuwenswarm session messages (same request_id) to a TurnRecord.

    Returns ``(TurnRecord | None, list[ToolCallTiming])``.
    """
    if not messages:
        return None, []

    messages.sort(key=lambda m: float(m.get("timestamp", 0)))

    turn_id = str(messages[0].get("request_id", ""))
    if not turn_id:
        return None, []

    ts_raw = messages[0].get("timestamp", 0)
    try:
        timestamp = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
    except (ValueError, TypeError):
        timestamp = datetime.fromtimestamp(0, tz=timezone.utc)

    # Wall-clock duration
    try:
        t_start = float(messages[0].get("timestamp", 0))
        t_end = float(messages[-1].get("timestamp", 0))
        duration_seconds = max(0.0, t_end - t_start)
    except (ValueError, TypeError):
        duration_seconds = 0.0

    has_error = any(m.get("event_type") == "chat.error" for m in messages)
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    has_content = any(
        bool(m.get("content")) for m in assistant_messages
        if m.get("event_type") not in (
            "chat.tool_call", "chat.tool_update", "chat.usage_metadata"
        )
    )
    task_completed = not has_error and has_content

    tools_called: list[str] = []
    for m in messages:
        if m.get("event_type") == "chat.tool_call":
            tc = m.get("tool_call") or {}
            name = tc.get("name")
            if name:
                tools_called.append(str(name))

    seen: set[str] = set()
    tools_called = [t for t in tools_called if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    record = TurnRecord(
        turn_id=turn_id,
        timestamp=timestamp,
        query_embedding=[],
        skills=[],
        memory_sections=[],
        tools=[],
        explicit_rating=None,
        follow_up_correction=has_error,
        task_completed=task_completed,
        conversation_length=len(messages),
        skills_used=[],
        tools_called=tools_called,
        llm_judge_score=None,
        explored=False,
        exploration_additions={},
        week_tag=week_tag,
        duration_seconds=duration_seconds,
    )

    tool_timings = _extract_tool_timings(turn_id, messages)
    return record, tool_timings


class TrajectoriesLoader:
    """Load turn logs from thalamus weekly files or jiuwenswarm session histories."""

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
        self._tool_call_timings: list[ToolCallTiming] = []

    @property
    def source_type(self) -> str:
        return self._source_type

    @property
    def skipped_records(self) -> int:
        return self._skipped

    @property
    def raw_sessions(self) -> dict[Path, list[dict]]:
        return self._raw_sessions

    @property
    def tool_call_timings(self) -> list[ToolCallTiming]:
        """Per-tool-call timing records (jiuwenswarm only; empty for thalamus)."""
        return self._tool_call_timings

    def log_files(self) -> list[Path]:
        """Return matching log file paths sorted newest-first, up to max_weeks."""
        if self._source_type == "jiuwenswarm_sessions":
            sessions_dir = self._log_dir / "agent" / "sessions"
            if not sessions_dir.is_dir():
                sessions_dir = self._log_dir / "sessions"

            paths: list[Path] = []
            if sessions_dir.is_dir():
                for sub in sessions_dir.iterdir():
                    hist = sub / "history.jsonl"
                    if hist.exists():
                        paths.append(hist)

            paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return paths[: self._max_weeks]

        paths = sorted(self._log_dir.glob("turns_*.jsonl"), reverse=True)
        return paths[: self._max_weeks]

    def load(self) -> list[TurnRecord]:
        """Load and parse all turn records, sorted by timestamp ascending."""
        self._skipped = 0
        self._raw_sessions = {}
        self._tool_call_timings = []
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
                record, tool_timings = _parse_jiuwenswarm_turn(messages, week_tag)
                if record is None:
                    self._skipped += 1
                else:
                    records.append(record)
                    self._tool_call_timings.extend(tool_timings)

            self._raw_sessions[path] = [
                raw
                for raw in (
                    json.loads(line) for line in text.splitlines() if line.strip()
                )
                if isinstance(raw, dict)
            ]

        return records
