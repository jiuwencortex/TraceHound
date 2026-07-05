# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Turn-log loader.

Reads jiuwenswarm session-history JSONL files from
``agent/sessions/{session_id}/history.jsonl`` and returns typed TurnRecord
objects sorted by timestamp ascending.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class TurnRecord:
    """Parsed representation of one agent turn log entry.

    For jiuwenswarm session logs, many legacy fields (skills, memory_sections,
    tools context, explicit_rating, llm_judge_score, explored) remain present
    on the dataclass for backward compatibility but are always empty/None.

    New jiuwenswarm-specific fields capture token usage, LLM timing, tool
    results, user query content, and session metadata.
    """

    # --- identity ---
    turn_id: str
    timestamp: datetime
    week_tag: str

    # --- legacy context fields (always empty for jiuwenswarm) ---
    query_embedding: list[float]
    skills: list[str]
    memory_sections: list[str]
    tools: list[str]

    # --- outcome (jiuwenswarm-derived heuristics) ---
    explicit_rating: str | None
    follow_up_correction: bool
    task_completed: bool
    conversation_length: int
    skills_used: list[str]
    tools_called: list[str]
    llm_judge_score: float | None

    # --- exploration (always False/empty for jiuwenswarm) ---
    explored: bool
    exploration_additions: dict

    # --- wall-clock duration ---
    duration_seconds: float = 0.0

    # === NEW jiuwenswarm-specific fields ===

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    context_window_tokens: int = 0
    usage_percent: float = 0.0

    # LLM performance timing (milliseconds)
    total_latency_ms: float = 0.0
    ttft_ms: float = 0.0
    tpot_ms: float = 0.0

    # Model
    model_name: str = ""

    # Tool execution
    n_tool_calls: int = 0
    n_tool_failures: int = 0
    tool_errors: list[str] = None  # type: ignore[assignment]

    # User query
    user_query: str = ""
    user_query_length: int = 0

    # Session metadata
    session_id: str = ""
    session_title: str = ""
    is_heartbeat: bool = False
    agent_mode: str = ""

    # Content delivery
    final_response_length: int = 0
    files_delivered: int = 0

    # Error categorization
    error_text: str = ""
    error_category: str = ""

    def __post_init__(self):
        # dataclass(frozen=True) with mutable defaults workaround
        object.__setattr__(self, "tool_errors", self.tool_errors or [])

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp.isoformat(),
            "week_tag": self.week_tag,
            "follow_up_correction": self.follow_up_correction,
            "task_completed": self.task_completed,
            "conversation_length": self.conversation_length,
            "tools_called": self.tools_called,
            "duration_seconds": self.duration_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "context_window_tokens": self.context_window_tokens,
            "usage_percent": self.usage_percent,
            "total_latency_ms": self.total_latency_ms,
            "ttft_ms": self.ttft_ms,
            "tpot_ms": self.tpot_ms,
            "model_name": self.model_name,
            "n_tool_calls": self.n_tool_calls,
            "n_tool_failures": self.n_tool_failures,
            "tool_errors": self.tool_errors,
            "user_query_length": self.user_query_length,
            "session_id": self.session_id,
            "session_title": self.session_title,
            "is_heartbeat": self.is_heartbeat,
            "agent_mode": self.agent_mode,
            "final_response_length": self.final_response_length,
            "files_delivered": self.files_delivered,
            "error_category": self.error_category,
        }


@dataclass(frozen=True)
class ToolCallTiming:
    """Timing record for a single tool call extracted from session messages."""

    turn_id: str
    tool_name: str
    call_timestamp: float
    result_timestamp: float
    duration_seconds: float


def _week_tag_from_mtime(path: Path) -> str:
    """Derive an ISO week tag from a file's last-modified time."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    iso_cal = dt.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"


def _extract_tool_timings(turn_id: str, messages: list[dict]) -> list[ToolCallTiming]:
    """Extract per-tool-call timing from a sorted list of session messages."""
    timings: list[ToolCallTiming] = []
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
    consumed: dict[str, int] = {}
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


def _categorize_error(error_text: str) -> str:
    """Classify an error message into a category."""
    text = (error_text or "").lower()
    if not text:
        return ""
    # Import / module errors
    if any(x in text for x in ("importerror", "modulenotfounderror", "no module named", "cannot import")):
        return "import"
    # Syntax / compilation errors
    if any(x in text for x in ("syntaxerror", "indentationerror", "unexpected token", "parse error")):
        return "syntax"
    # API / balance / authentication
    if any(x in text for x in ("api", "insufficient balance", "payment required", "402", "401", "authentication", "unauthorized")):
        return "api_auth"
    # Timeout / rate limit
    if any(x in text for x in ("timeout", "timed out", "rate limit", "too many requests", "429", "deadline")):
        return "timeout"
    # File system
    if any(x in text for x in ("filenotfounderror", "no such file", "permission denied", "is a directory", "not a directory")):
        return "filesystem"
    # Model / LLM call failures
    if any(x in text for x in ("model", "llm", "generation failed", "invalid model", "context length exceeded")):
        return "model"
    # Network
    if any(x in text for x in ("connection", "network", "unreachable", "dns", "refused")):
        return "network"
    # Code execution
    if any(x in text for x in ("runtimeerror", "execution failed", "process exited", "command failed", "returned non-zero")):
        return "execution"
    return "other"


def _load_session_metadata(session_dir: Path) -> dict:
    """Load metadata.json from a session directory if present."""
    meta_path = session_dir / "metadata.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _parse_jiuwenswarm_turn(
    messages: list[dict],
    week_tag: str,
    session_id: str = "",
    session_title: str = "",
) -> tuple[TurnRecord | None, list[ToolCallTiming]]:
    """Convert a group of jiuwenswarm session messages (same request_id) to a TurnRecord."""
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

    # Wall-clock duration — stop at the first large intra-turn gap so that
    # late-arriving stale messages (e.g. session-summary records logged minutes
    # later under the same request_id) don't inflate the turn duration.
    _MAX_GAP_S = 120.0  # gaps > 2 min are assumed to be stale log entries
    try:
        timestamps = [float(m.get("timestamp", 0)) for m in messages]
        t_start = timestamps[0]
        t_end = t_start
        for ts in timestamps[1:]:
            if ts - t_end > _MAX_GAP_S:
                break
            t_end = ts
        duration_seconds = max(0.0, t_end - t_start)
    except (ValueError, TypeError):
        duration_seconds = 0.0

    has_error = any(m.get("event_type") == "chat.error" for m in messages)
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    has_content = any(
        bool(m.get("content")) for m in assistant_messages
        if m.get("event_type") not in ("chat.tool_call", "chat.tool_update", "chat.usage_metadata")
    )
    task_completed = not has_error and has_content

    # Collect errors
    error_text = ""
    tool_errors: list[str] = []
    for m in messages:
        if m.get("event_type") == "chat.error":
            err = str(m.get("error", ""))
            if err and not error_text:
                error_text = err
        # Also look for tool failure indicators
        if m.get("event_type") == "chat.tool_result":
            result = m.get("result")
            raw = m.get("raw_output")
            success = m.get("success")
            # If success is explicitly False or result contains error
            if success is False:
                err_detail = str(result) if result else "tool failure"
                tool_errors.append(err_detail[:200])
            elif isinstance(result, dict) and result.get("error"):
                tool_errors.append(str(result["error"])[:200])
            elif isinstance(raw, dict) and raw.get("error"):
                tool_errors.append(str(raw["error"])[:200])

    # Tools called
    tools_called: list[str] = []
    n_tool_calls = 0
    for m in messages:
        if m.get("event_type") == "chat.tool_call":
            n_tool_calls += 1
            tc = m.get("tool_call") or {}
            name = tc.get("name")
            if name:
                tools_called.append(str(name))
    seen: set[str] = set()
    tools_called = [t for t in tools_called if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    # Token usage (aggregate from chat.usage_summary and chat.usage_metadata)
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    context_window_tokens = 0
    usage_percent = 0.0

    # LLM timing (best values from chat.usage_metadata)
    total_latency_ms = 0.0
    ttft_ms = 0.0
    tpot_ms = 0.0
    model_name = ""

    # Count tool failures
    n_tool_failures = len(tool_errors)

    # User query
    user_query = ""
    user_query_length = 0
    for m in messages:
        if m.get("role") == "user":
            content = str(m.get("content", ""))
            if content:
                user_query = content
                user_query_length = len(content)
                break

    # Heartbeat detection
    channel_id = str(messages[0].get("channel_id", ""))
    is_heartbeat = channel_id == "__heartbeat__"

    # Agent mode
    agent_mode = str(messages[0].get("mode", ""))

    # Content delivery
    final_response_length = 0
    files_delivered = 0
    for m in messages:
        evt = m.get("event_type", "")
        if evt == "chat.final":
            content = str(m.get("content", ""))
            if content:
                final_response_length = len(content)
        elif evt == "chat.file":
            files = m.get("files") or []
            files_delivered += len(files)

    # Process usage_metadata and usage_summary
    for m in messages:
        evt = m.get("event_type", "")
        if evt == "chat.usage_summary":
            usage = m.get("usage") or {}
            input_tokens = max(input_tokens, int(usage.get("input_tokens") or 0))
            output_tokens = max(output_tokens, int(usage.get("output_tokens") or 0))
            total_tokens = max(total_tokens, int(usage.get("total_tokens") or 0))
            model_name = str(m.get("model", model_name)) or model_name
            usage_percent = max(usage_percent, float(m.get("usage_percent") or 0.0)) / 100.0
            context_window_tokens = max(context_window_tokens, int(m.get("context_window_tokens") or 0))
        elif evt == "chat.usage_metadata":
            meta = m.get("metadata") or {}
            um = meta.get("usage_metadata") or {}
            # Extract timing
            total_latency_ms = max(total_latency_ms, float(meta.get("total_latency_ms") or 0.0))
            ttft_ms = max(ttft_ms, float(meta.get("ttft_ms") or 0.0))
            tpot_ms = max(tpot_ms, float(meta.get("tpot_ms") or 0.0))
            # Extract model
            model_name = str(um.get("model_name", model_name)) or model_name
            # Fallback token extraction from usage_metadata
            if not total_tokens:
                input_tokens = max(input_tokens, int(um.get("input_tokens") or 0))
                output_tokens = max(output_tokens, int(um.get("output_tokens") or 0))
                total_tokens = max(total_tokens, int(um.get("total_tokens") or 0))

    # Error categorization
    error_category = _categorize_error(error_text) if has_error else ""

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
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        context_window_tokens=context_window_tokens,
        usage_percent=usage_percent,
        total_latency_ms=total_latency_ms,
        ttft_ms=ttft_ms,
        tpot_ms=tpot_ms,
        model_name=model_name,
        n_tool_calls=n_tool_calls,
        n_tool_failures=n_tool_failures,
        tool_errors=tool_errors,
        user_query=user_query,
        user_query_length=user_query_length,
        session_id=session_id,
        session_title=session_title,
        is_heartbeat=is_heartbeat,
        agent_mode=agent_mode,
        final_response_length=final_response_length,
        files_delivered=files_delivered,
        error_text=error_text,
        error_category=error_category,
    )

    tool_timings = _extract_tool_timings(turn_id, messages)
    return record, tool_timings


class TrajectoriesLoader:
    """Load jiuwenswarm session-history JSONL files."""

    def __init__(
        self,
        log_dir: str | Path,
        max_weeks: int = 8,
        skip_heartbeats: bool = True,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._max_weeks = max_weeks
        self._skip_heartbeats = skip_heartbeats
        self._skipped: int = 0
        self._raw_sessions: dict[Path, list[dict]] = {}
        self._tool_call_timings: list[ToolCallTiming] = []

    @property
    def skipped_records(self) -> int:
        return self._skipped

    @property
    def raw_sessions(self) -> dict[Path, list[dict]]:
        return self._raw_sessions

    @property
    def tool_call_timings(self) -> list[ToolCallTiming]:
        """Per-tool-call timing records extracted from session messages."""
        return self._tool_call_timings

    def log_files(self) -> list[Path]:
        """Return matching log file paths sorted newest-first, up to max_weeks."""
        sessions_dir = self._log_dir / "agent" / "sessions"
        if not sessions_dir.is_dir():
            sessions_dir = self._log_dir / "sessions"

        paths: list[Path] = []
        if sessions_dir.is_dir():
            for sub in sessions_dir.iterdir():
                hist = sub / "history.jsonl"
                if not hist.exists():
                    continue
                # Skip heartbeat sessions by directory name heuristic
                if self._skip_heartbeats and sub.name.lower().startswith("heartbeat"):
                    continue
                paths.append(hist)

        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return paths[: self._max_weeks]

    def load(self) -> list[TurnRecord]:
        """Load and parse all turn records, sorted by timestamp ascending."""
        self._skipped = 0
        self._raw_sessions = {}
        self._tool_call_timings = []
        records: list[TurnRecord] = []

        for path in self.log_files():
            week_tag = _week_tag_from_mtime(path)
            session_dir = path.parent
            metadata = _load_session_metadata(session_dir)
            session_id = str(metadata.get("session_id", session_dir.name))
            session_title = str(metadata.get("title", ""))

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
                record, tool_timings = _parse_jiuwenswarm_turn(
                    messages, week_tag, session_id=session_id, session_title=session_title
                )
                if record is None:
                    self._skipped += 1
                    continue
                # Safety-net: skip heartbeat turns even if session dir wasn't caught
                if self._skip_heartbeats and record.is_heartbeat:
                    self._skipped += 1
                    continue
                records.append(record)
                self._tool_call_timings.extend(tool_timings)

            self._raw_sessions[path] = [
                raw
                for raw in (
                    json.loads(line) for line in text.splitlines() if line.strip()
                )
                if isinstance(raw, dict)
            ]

        records.sort(key=lambda r: r.timestamp)
        return records
