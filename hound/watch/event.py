# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""NewDataEvent — emitted by WatchAgent when a session file has new content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NewDataEvent:
    """Signals that ``file_path`` has grown since it was last processed.

    ``session_id`` is derived from the parent directory name.
    ``known_offset`` is the byte position already consumed; the ingester
    should read from this offset onwards.
    """

    file_path: Path
    session_id: str
    known_offset: int = 0
