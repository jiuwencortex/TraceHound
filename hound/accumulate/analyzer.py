# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""IncrementalAnalyzer — updates all accumulators on each new TurnRecord."""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from analyzer.loader import TurnRecord
from analyzer.scorer import compute_quality

from .cost_tracker import CostTracker
from .error_window import ErrorRateWindow
from .quality_ema import QualityEMA
from .state import AnalyzerState
from .token_stats import TokenStats
from .tool_failure import ToolFailureWindow


class IncrementalAnalyzer:
    """Maintains live metric accumulators updated in O(1) per turn.

    Call ``ingest(turns)`` whenever the TurnIngester delivers new turns.
    Read ``state`` to get the current snapshot for AlertEngine evaluation.
    """

    def __init__(self, config_thresholds=None) -> None:
        self._quality_ema = QualityEMA(alpha=0.1, window_size=20)
        self._error_window = ErrorRateWindow(size=20)
        self._token_stats = TokenStats(usage_window=10)
        self._tool_failure = ToolFailureWindow(window_size=10)
        self._cost = CostTracker()
        self._correction_window: list[bool] = []
        self._correction_window_size = 15
        self._latency_samples: list[float] = []
        self._latency_cap = 100
        self._state = AnalyzerState()

    def ingest(self, turns: list[TurnRecord]) -> None:
        """Process a batch of new turns and update all accumulators."""
        for turn in turns:
            if turn.is_heartbeat:
                continue
            self._process_turn(turn)

    def _process_turn(self, turn: TurnRecord) -> None:
        quality = compute_quality(turn)

        self._quality_ema.update(quality)
        self._error_window.update(bool(turn.error_text))
        self._token_stats.update(turn.total_tokens, turn.usage_percent)
        self._tool_failure.update(turn.tools_called, turn.n_tool_failures)
        self._cost.update(turn.input_tokens, turn.output_tokens)

        self._correction_window.append(turn.follow_up_correction)
        if len(self._correction_window) > self._correction_window_size:
            self._correction_window.pop(0)

        if turn.total_latency_ms > 0:
            self._latency_samples.append(turn.total_latency_ms)
            if len(self._latency_samples) > self._latency_cap:
                self._latency_samples.pop(0)

        if turn.error_category:
            self._state.recent_error_categories.append(turn.error_category)
            if len(self._state.recent_error_categories) > 50:
                self._state.recent_error_categories.pop(0)

        # Rebuild state snapshot
        self._state.quality_ema = self._quality_ema.ema
        self._state.quality_ema_window = self._quality_ema.window
        self._state.error_rate = self._error_window.rate
        self._state.recent_errors = self._error_window.window
        self._state.mean_tokens_per_turn = self._token_stats.mean_tokens
        self._state.mean_usage_percent = self._token_stats.mean_usage_percent
        self._state.max_usage_percent = self._token_stats.max_usage_percent
        self._state.tool_failure_windows = {
            k: list(v)
            for k, v in self._tool_failure._windows.items()
        }
        self._state.estimated_daily_cost_usd = self._cost.daily_cost
        self._state.daily_cost_date = self._cost.current_date
        self._state.correction_rate = (
            sum(self._correction_window) / len(self._correction_window)
            if self._correction_window else 0.0
        )
        self._state.recent_corrections = list(self._correction_window)
        self._state.median_latency_ms = (
            statistics.median(self._latency_samples) if self._latency_samples else 0.0
        )
        self._state.latency_samples = list(self._latency_samples[-20:])
        self._state.turn_count += 1
        self._state.last_turn_at = turn.timestamp

    @property
    def state(self) -> AnalyzerState:
        return self._state

    def tool_failure_candidates(self, min_failures: int) -> list[str]:
        return self._tool_failure.storm_candidates(min_failures)
