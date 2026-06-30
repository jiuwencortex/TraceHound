# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tool arguments analyzer.

Inspects raw session messages to understand how tools are actually being
invoked in practice:

- File access patterns: which paths/directories are touched most often,
  read vs write ratios, most common file extensions.
- Command execution: for ``bash``/``code`` tools, extracts and classifies
  the commands / code being run.
- Dangerous pattern detection: flags destructive commands (``rm -rf``,
  ``format``, ``DROP TABLE``, broad wildcards, etc.).
- Argument complexity: number of keys per tool call arguments dict.
- Tool retry patterns: same tool with same/similar arguments called
  multiple times within one turn.

This analyzer requires **raw message data** (``raw_sessions``) because
argument details are not preserved in the summarised ``TurnRecord``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..loader import TurnRecord

# -- heuristics --
_READ_TOOLS = frozenset(
    {
        "read_file",
        "glob",
        "view",
        "cat",
        "head",
        "tail",
        "find",
        "search_file",
        "grep",
    }
)
_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "edit",
        "apply_edit",
        "replace",
        "create_file",
        "mkdir",
        "touch",
    }
)
_DANGEROUS_PATTERNS = [
    ("rm -rf", "dangerous_delete"),
    ("del /f", "dangerous_delete"),
    ("del /q", "dangerous_delete"),
    ("format ", "system_format"),
    ("drop table", "sql_injection"),
    ("sudo ", "privilege_escalation"),
]

_MAX_FILE_PATH_LENGTH = 512
_TOP_N_ARGS = 3
_TOP_N_ACCESS = 10
_TOP_N_EXTENSIONS = 10


def _looks_like_path(value: str) -> bool:
    """Heuristic: string value looks like a file path."""
    if len(value) > _MAX_FILE_PATH_LENGTH:
        return False
    # Must not be a URL
    if value.startswith(("http://", "https://", "ftp://", "file://")):
        return False
    has_sep = "/" in value or "\\" in value
    has_dot = "." in value
    has_space = " " in value
    # Real paths have separators. Simple filenames have no spaces.
    if has_sep:
        return True
    if has_dot and not has_space:
        return True
    return False


def _extract_file_paths(obj) -> list[str]:
    """Recursively extract string values that look like file paths from a dict/list."""
    paths: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            paths.extend(_extract_file_paths(v))
    elif isinstance(obj, list):
        for item in obj:
            paths.extend(_extract_file_paths(item))
    elif isinstance(obj, str) and _looks_like_path(obj):
        paths.append(obj)
    return paths


def _file_operation_type(tool_name: str) -> str:
    """Classify a tool call as 'read', 'write', or 'unknown'."""
    t = tool_name.lower()
    if t in _READ_TOOLS:
        return "read"
    if t in _WRITE_TOOLS:
        return "write"
    return "unknown"


def _get_extension(path: str) -> str:
    """Return the file extension (e.g. '.py') or empty string."""
    # Handle paths like 'dir/.gitignore' gracefully
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name[1:]:  # skip leading dot for hidden files
        return name.rsplit(".", 1)[-1].lower()
    return ""


def _command_base(cmd: str) -> str:
    """Extract the base command (first word) from a shell command."""
    cmd = cmd.strip()
    if not cmd:
        return ""
    # Handle common prefixes like 'python -m', 'python3', etc.
    first = cmd.split(None, 1)[0].lower()
    # Normalise python variants
    if first in ("python", "python3", "python2"):
        return "python"
    return first


def _is_dangerous_command(cmd: str) -> tuple[bool, str]:
    """Check if a command contains a dangerous pattern.

    Returns (is_dangerous, flag_reason).
    """
    lower = cmd.lower()
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern in lower:
            return True, reason
    # Broad wildcard delete: rm/del paired with "*"
    if any(c in lower for c in ("rm ", "del ", "rmdir ", "rd ")):
        if "*" in lower or " -r " in lower or " -rf " in lower or " /s " in lower:
            return True, "dangerous_delete"
    return False, ""


def _arg_signature(arguments: dict) -> str:
    """Create a simplified signature for comparing argument similarity."""
    # Sort keys and stringify primitive values for fuzzy comparison
    parts: list[str] = []
    for k in sorted(arguments.keys()):
        v = arguments[k]
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
        elif isinstance(v, list) and len(v) <= 3:
            parts.append(f"{k}={tuple(v)}")
        else:
            parts.append(k)
    return "|".join(parts)


def _similar_args(args1: dict, args2: dict) -> bool:
    """Quick similarity check: same keys and at least one matching value."""
    if set(args1.keys()) != set(args2.keys()):
        return False
    matching = sum(1 for k in args1 if args1[k] == args2[k])
    return matching > 0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileAccessStat:
    path_pattern: str
    access_count: int
    read_count: int
    write_count: int
    tools_that_accessed: list[str]

    def to_dict(self) -> dict:
        return {
            "path_pattern": self.path_pattern,
            "access_count": self.access_count,
            "read_count": self.read_count,
            "write_count": self.write_count,
            "tools_that_accessed": list(self.tools_that_accessed),
        }


@dataclass(frozen=True)
class CommandStat:
    command_base: str
    count: int
    dangerous_flag: bool

    def to_dict(self) -> dict:
        return {
            "command_base": self.command_base,
            "count": self.count,
            "dangerous_flag": self.dangerous_flag,
        }


@dataclass(frozen=True)
class ToolArgPattern:
    tool_name: str
    most_common_args: list[str]
    arg_complexity_score: float

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "most_common_args": list(self.most_common_args),
            "arg_complexity_score": round(self.arg_complexity_score, 4),
        }


@dataclass(frozen=True)
class RetryPattern:
    tool_name: str
    turn_id: str
    repeat_count: int
    similar_args: bool

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "turn_id": self.turn_id,
            "repeat_count": self.repeat_count,
            "similar_args": self.similar_args,
        }


@dataclass(frozen=True)
class ToolArgumentResult:
    total_tool_calls: int
    total_tool_results: int
    # file access
    most_accessed_paths: list[FileAccessStat]
    read_count: int
    write_count: int
    read_write_ratio: float
    most_common_extensions: list[tuple[str, int]]
    # commands
    command_stats: list[CommandStat]
    dangerous_commands_found: int
    # argument complexity
    tool_arg_patterns: list[ToolArgPattern]
    overall_avg_arg_keys: float
    # retry patterns
    retry_patterns: list[RetryPattern]

    def to_dict(self) -> dict:
        return {
            "total_tool_calls": self.total_tool_calls,
            "total_tool_results": self.total_tool_results,
            "most_accessed_paths": [p.to_dict() for p in self.most_accessed_paths],
            "read_count": self.read_count,
            "write_count": self.write_count,
            "read_write_ratio": round(self.read_write_ratio, 4),
            "most_common_extensions": [
                {"extension": ext, "count": cnt}
                for ext, cnt in self.most_common_extensions
            ],
            "command_stats": [c.to_dict() for c in self.command_stats],
            "dangerous_commands_found": self.dangerous_commands_found,
            "tool_arg_patterns": [t.to_dict() for t in self.tool_arg_patterns],
            "overall_avg_arg_keys": round(self.overall_avg_arg_keys, 4),
            "retry_patterns": [r.to_dict() for r in self.retry_patterns],
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ToolArgumentAnalyzer:
    """Analyze tool call arguments from raw session messages."""

    def __init__(
        self,
        turns: list[TurnRecord],
        raw_sessions: dict[Path, list[dict]],
    ) -> None:
        self._turns = turns
        self._raw_sessions = raw_sessions

    def analyze(self) -> ToolArgumentResult:
        if not self._raw_sessions:
            return ToolArgumentResult(
                total_tool_calls=0,
                total_tool_results=0,
                most_accessed_paths=[],
                read_count=0,
                write_count=0,
                read_write_ratio=0.0,
                most_common_extensions=[],
                command_stats=[],
                dangerous_commands_found=0,
                tool_arg_patterns=[],
                overall_avg_arg_keys=0.0,
                retry_patterns=[],
            )

        # Aggregate raw messages from all sessions
        all_messages: list[dict] = []
        for msgs in self._raw_sessions.values():
            all_messages.extend(msgs)

        # -- tool calls & results --
        tool_call_events: list[dict] = [
            m for m in all_messages if m.get("event_type") == "chat.tool_call"
        ]
        tool_result_events: list[dict] = [
            m for m in all_messages if m.get("event_type") == "chat.tool_result"
        ]

        # -- file access tracking --
        path_stats: dict[str, dict] = {}
        ext_counter: Counter = Counter()
        read_count = 0
        write_count = 0

        # -- command tracking --
        command_counter: Counter = Counter()
        dangerous_command_count = 0

        # -- argument complexity --
        tool_arg_keys: dict[str, list[int]] = {}
        tool_arg_signatures: dict[str, list[str]] = {}

        # -- retry tracking (grouped by turn/request_id) --
        turn_tool_calls: dict[str, list[dict]] = {}  # request_id -> [(tool_name, args_dict), ...]

        for m in tool_call_events:
            tc = m.get("tool_call") or {}
            tool_name = str(tc.get("name", ""))
            if not tool_name:
                continue

            # Parse arguments JSON string
            args_raw = tc.get("arguments")
            args_dict: dict = {}
            if isinstance(args_raw, str):
                try:
                    args_dict = json.loads(args_raw)
                except json.JSONDecodeError:
                    args_dict = {}
            elif isinstance(args_raw, dict):
                args_dict = args_raw

            # Normalize to dict
            if not isinstance(args_dict, dict):
                args_dict = {}

            # -- file paths --
            file_paths = _extract_file_paths(args_dict)
            op_type = _file_operation_type(tool_name)
            for path in file_paths:
                if path not in path_stats:
                    path_stats[path] = {
                        "access_count": 0,
                        "read_count": 0,
                        "write_count": 0,
                        "tools": set(),
                    }
                path_stats[path]["access_count"] += 1
                if op_type == "read":
                    path_stats[path]["read_count"] += 1
                    read_count += 1
                elif op_type == "write":
                    path_stats[path]["write_count"] += 1
                    write_count += 1
                path_stats[path]["tools"].add(tool_name)

                ext = _get_extension(path)
                if ext:
                    ext_counter[ext] += 1

            # -- commands (bash / code tools) --
            lower_name = tool_name.lower()
            if lower_name in ("bash", "shell", "command", "exec"):
                cmd = str(args_dict.get("command", args_dict.get("cmd", "")))
                if cmd:
                    base = _command_base(cmd)
                    if base:
                        command_counter[base] += 1
                        is_danger, _ = _is_dangerous_command(cmd)
                        if is_danger:
                            dangerous_command_count += 1
            elif lower_name in ("code", "python", "run_code", "execute"):
                code = str(args_dict.get("code", args_dict.get("source", "")))
                if code:
                    command_counter["python"] += 1

            # -- argument complexity --
            n_keys = len(args_dict)
            tool_arg_keys.setdefault(tool_name, []).append(n_keys)

            # -- arg patterns --
            sig = _arg_signature(args_dict)
            if sig:
                tool_arg_signatures.setdefault(tool_name, []).append(sig)

            # -- retry tracking (group by request_id) --
            req_id = str(m.get("request_id", ""))
            if req_id:
                turn_tool_calls.setdefault(req_id, []).append(
                    {"tool_name": tool_name, "args": args_dict}
                )

        # Build most_accessed_paths (top N by access_count)
        sorted_paths = sorted(
            path_stats.items(), key=lambda x: x[1]["access_count"], reverse=True
        )[:_TOP_N_ACCESS]
        most_accessed_paths: list[FileAccessStat] = []
        for path, s in sorted_paths:
            most_accessed_paths.append(
                FileAccessStat(
                    path_pattern=path,
                    access_count=s["access_count"],
                    read_count=s["read_count"],
                    write_count=s["write_count"],
                    tools_that_accessed=sorted(s["tools"]),
                )
            )

        # Read/write ratio (reads per write; inf if no writes but reads exist)
        if read_count == 0 and write_count == 0:
            read_write_ratio = 0.0
        elif write_count == 0:
            read_write_ratio = float("inf")
        else:
            read_write_ratio = read_count / write_count

        # Most common extensions
        most_common_extensions = ext_counter.most_common(_TOP_N_EXTENSIONS)

        # Command stats
        command_stats: list[CommandStat] = []
        for cmd_base, cnt in command_counter.most_common():
            # Re-check danger on the most common occurrence? We just flag if any dangerous
            # patterns existed; here we approximate by checking if the base itself is
            # commonly dangerous. For simplicity, dangerous_flag = False in aggregate
            # because we already counted dangerous_command_count separately.
            command_stats.append(
                CommandStat(
                    command_base=cmd_base,
                    count=cnt,
                    dangerous_flag=False,
                )
            )

        # Tool arg patterns & complexity
        tool_arg_patterns: list[ToolArgPattern] = []
        total_keys = 0
        total_calls = 0
        for tool_name, keys_list in tool_arg_keys.items():
            avg_keys = sum(keys_list) / len(keys_list)
            sigs = tool_arg_signatures.get(tool_name, [])
            top_sigs = [
                sig for sig, _ in Counter(sigs).most_common(_TOP_N_ARGS)
            ]
            tool_arg_patterns.append(
                ToolArgPattern(
                    tool_name=tool_name,
                    most_common_args=top_sigs,
                    arg_complexity_score=avg_keys,
                )
            )
            total_keys += sum(keys_list)
            total_calls += len(keys_list)
        tool_arg_patterns.sort(key=lambda t: t.arg_complexity_score, reverse=True)
        overall_avg_arg_keys = total_keys / total_calls if total_calls > 0 else 0.0

        # Retry patterns: same tool called >1 time in same turn with same/similar args
        retry_patterns: list[RetryPattern] = []
        for req_id, calls in turn_tool_calls.items():
            if len(calls) < 2:
                continue
            # Count occurrences of each tool in this turn
            tool_counts: dict[str, list[dict]] = {}
            for c in calls:
                tool_counts.setdefault(c["tool_name"], []).append(c["args"])
            for tool_name, arg_list in tool_counts.items():
                if len(arg_list) < 2:
                    continue
                # Check if any pair has similar args
                has_similar = False
                for i in range(len(arg_list)):
                    for j in range(i + 1, len(arg_list)):
                        if _similar_args(arg_list[i], arg_list[j]):
                            has_similar = True
                            break
                    if has_similar:
                        break
                retry_patterns.append(
                    RetryPattern(
                        tool_name=tool_name,
                        turn_id=req_id,
                        repeat_count=len(arg_list),
                        similar_args=has_similar,
                    )
                )
        # Sort by repeat_count desc
        retry_patterns.sort(key=lambda r: r.repeat_count, reverse=True)

        return ToolArgumentResult(
            total_tool_calls=len(tool_call_events),
            total_tool_results=len(tool_result_events),
            most_accessed_paths=most_accessed_paths,
            read_count=read_count,
            write_count=write_count,
            read_write_ratio=read_write_ratio,
            most_common_extensions=most_common_extensions,
            command_stats=command_stats,
            dangerous_commands_found=dangerous_command_count,
            tool_arg_patterns=tool_arg_patterns,
            overall_avg_arg_keys=overall_avg_arg_keys,
            retry_patterns=retry_patterns,
        )
