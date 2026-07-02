# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TurnIngester — reads new log lines and emits TurnRecord objects."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from analyzer.loader import TurnRecord

from ..memory.offset_store import IngestionOffsetStore
from ..watch.event import NewDataEvent
from .parser import parse_new_turns


class TurnIngester:
    """Processes NewDataEvent objects from the WatchAgent.

    For each event, reads only the new bytes in the file (from the stored
    offset), parses complete turns, updates the offset in IngestionOffsetStore,
    and calls ``on_turns`` with the new TurnRecord list.
    """

    def __init__(
        self,
        offset_store: IngestionOffsetStore,
        on_turns: Callable[[list[TurnRecord]], None],
        loop: asyncio.AbstractEventLoop | None = None,
        executor=None,
    ) -> None:
        self._offsets = offset_store
        self._on_turns = on_turns
        self._loop = loop or asyncio.get_event_loop()
        self._executor = executor

    async def process(self, event: NewDataEvent) -> None:
        """Handle one NewDataEvent: parse new turns and invoke callback."""
        turns, new_offset = await self._loop.run_in_executor(
            self._executor,
            parse_new_turns,
            event.file_path,
            event.known_offset,
        )
        if new_offset > event.known_offset:
            self._offsets.set_offset(
                event.session_id, event.file_path, new_offset
            )
        if turns:
            self._on_turns(turns)
