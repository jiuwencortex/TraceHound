# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ToolFailureWindow — per-tool sliding window of recent call success/failure."""

from __future__ import annotations

from collections import defaultdict


class ToolFailureWindow:
    """Tracks success/failure for each tool over the last ``window_size`` calls."""

    def __init__(self, window_size: int = 10) -> None:
        self._window_size = window_size
        # tool_name -> list of bool (True = success)
        self._windows: dict[str, list[bool]] = defaultdict(list)

    def update(self, tools_called: list[str], n_tool_failures: int) -> None:
        """Record outcomes for tools used in a single turn.

        We distribute failures evenly (pessimistic: first N tools failed).
        """
        if not tools_called:
            return
        failures_left = n_tool_failures
        for tool in tools_called:
            success = failures_left <= 0
            if not success:
                failures_left -= 1
            window = self._windows[tool]
            window.append(success)
            if len(window) > self._window_size:
                window.pop(0)

    def failure_counts(self) -> dict[str, tuple[int, int]]:
        """Return {tool: (failures_in_window, window_size)} for each tool."""
        return {
            name: (window.count(False), len(window))
            for name, window in self._windows.items()
        }

    def storm_candidates(self, min_failures: int) -> list[str]:
        """Return tools whose recent failure count >= ``min_failures``."""
        return [
            name
            for name, window in self._windows.items()
            if window.count(False) >= min_failures
        ]
