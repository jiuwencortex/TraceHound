# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""parse_new_turns — incremental JSONL parser that reuses loader.py logic."""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.loader import TurnRecord, _parse_jiuwenswarm_turn, _week_tag_from_mtime, _load_session_metadata


def parse_new_turns(
    file_path: Path,
    start_offset: int,
) -> tuple[list[TurnRecord], int]:
    """Read new lines from ``file_path`` starting at ``start_offset`` bytes.

    Returns:
        turns: parsed TurnRecord objects (only complete turns — where a
               request_id group has at least one message)
        new_offset: the byte position after the last fully-consumed newline
    """
    try:
        raw_bytes = file_path.read_bytes()
    except OSError:
        return [], start_offset

    new_bytes = raw_bytes[start_offset:]
    if not new_bytes:
        return [], start_offset

    # Find the last complete line (ends with newline)
    last_nl = new_bytes.rfind(b"\n")
    if last_nl == -1:
        # No complete line yet — wait for more data
        return [], start_offset

    complete_chunk = new_bytes[: last_nl + 1]
    new_offset = start_offset + len(complete_chunk)

    session_dir = file_path.parent
    week_tag = _week_tag_from_mtime(file_path)
    metadata = _load_session_metadata(session_dir)
    session_id = str(metadata.get("session_id", session_dir.name))
    session_title = str(metadata.get("title", ""))

    messages_by_request: dict[str, list[dict]] = {}
    for line in complete_chunk.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        req_id = raw.get("request_id")
        if req_id:
            messages_by_request.setdefault(str(req_id), []).append(raw)

    turns: list[TurnRecord] = []
    for msgs in messages_by_request.values():
        record, _ = _parse_jiuwenswarm_turn(
            msgs, week_tag, session_id=session_id, session_title=session_title
        )
        if record is not None:
            turns.append(record)

    turns.sort(key=lambda t: t.timestamp)
    return turns, new_offset
