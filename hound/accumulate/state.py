# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AnalyzerState — snapshot of all live accumulator values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AnalyzerState:
    """Live metric state maintained by IncrementalAnalyzer.

    All values are updated in O(1) per new TurnRecord.
    """

    # Quality
    quality_ema: float = 0.5          # exponential moving average
    quality_ema_window: list[float] = field(default_factory=list)

    # Error rate
    recent_errors: list[bool] = field(default_factory=list)   # window of has_error flags
    error_rate: float = 0.0

    # Token usage
    token_turn_count: int = 0
    token_sum: float = 0.0
    mean_tokens_per_turn: float = 0.0

    # Context pressure
    recent_usage_pcts: list[float] = field(default_factory=list)
    mean_usage_percent: float = 0.0
    max_usage_percent: float = 0.0

    # Tool failure window: tool_name -> recent call results (bool success)
    tool_failure_windows: dict[str, list[bool]] = field(default_factory=dict)

    # Latency
    latency_samples: list[float] = field(default_factory=list)
    median_latency_ms: float = 0.0

    # Correction rate
    recent_corrections: list[bool] = field(default_factory=list)
    correction_rate: float = 0.0

    # Cost estimate (running total for current calendar day)
    estimated_daily_cost_usd: float = 0.0
    daily_cost_date: str = ""

    # Timing
    turn_count: int = 0
    last_turn_at: datetime = field(
        default_factory=lambda: datetime.fromtimestamp(0, tz=timezone.utc)
    )

    # Error category tracking (for new_error_category rule)
    recent_error_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "quality_ema": self.quality_ema,
            "error_rate": self.error_rate,
            "mean_tokens_per_turn": self.mean_tokens_per_turn,
            "mean_usage_percent": self.mean_usage_percent,
            "max_usage_percent": self.max_usage_percent,
            "median_latency_ms": self.median_latency_ms,
            "correction_rate": self.correction_rate,
            "estimated_daily_cost_usd": self.estimated_daily_cost_usd,
            "turn_count": self.turn_count,
            "last_turn_at": self.last_turn_at.isoformat(),
        }
