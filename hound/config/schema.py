# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AgentConfig — typed configuration schema for the hound agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WatchConfig:
    log_root: Path = field(default_factory=lambda: Path.home() / ".jiuwenswarm")
    debounce_ms: int = 500


@dataclass
class AnalysisConfig:
    max_weeks: int = 8
    quality_deficit_threshold: float = 0.15
    correction_lift_threshold: float = 1.5
    skip_heartbeats: bool = True


@dataclass
class AlertThresholds:
    quality_drop_delta: float = 0.15
    quality_drop_window_turns: int = 5
    quality_critical_value: float = 0.40
    error_spike_ratio: float = 2.0
    error_spike_window_turns: int = 20
    tool_failure_storm_count: int = 5
    tool_failure_storm_window: int = 10
    context_pressure_threshold: float = 0.80
    context_pressure_window_turns: int = 10
    context_critical_threshold: float = 0.95
    latency_regression_ratio: float = 1.5
    correction_loop_rate: float = 0.40
    correction_loop_window_turns: int = 15
    cost_daily_budget_usd: float = 5.00
    no_data_hours: float = 4.0


@dataclass
class AlertRulesConfig:
    quality_drop: bool = True
    quality_critical: bool = True
    error_spike: bool = True
    tool_failure_storm: bool = True
    context_pressure: bool = True
    context_critical: bool = True
    latency_regression: bool = True
    new_error_category: bool = True
    correction_loop: bool = True
    cost_threshold: bool = True
    no_data: bool = True
    thresholds: AlertThresholds = field(default_factory=AlertThresholds)


@dataclass
class MacOSNotifyConfig:
    enabled: bool = True
    min_severity: str = "WARNING"


@dataclass
class SlackConfig:
    enabled: bool = False
    webhook_url: str = ""
    min_severity: str = "WARNING"


@dataclass
class FeedbackConfig:
    enabled: bool = True
    update_interval_minutes: int = 30


@dataclass
class ActionsConfig:
    markdown_files: bool = True
    macos_notification: MacOSNotifyConfig = field(default_factory=MacOSNotifyConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    jiuwenswarm_feedback: FeedbackConfig = field(default_factory=FeedbackConfig)


@dataclass
class ScheduleConfig:
    hourly_check: bool = True
    daily_summary: str = "08:00"
    weekly_report: str = "Monday 07:00"
    on_session_end: bool = True
    session_end_idle_minutes: int = 30


@dataclass
class LLMAdvisorConfig:
    enabled: bool = False
    provider: str = "kimi"
    model: str = "moonshot-v1-8k"
    api_key_env: str = "MOONSHOT_API_KEY"
    trigger_on: list = field(default_factory=lambda: ["CRITICAL"])


@dataclass
class AgentConfig:
    watch: WatchConfig = field(default_factory=WatchConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    alerts: AlertRulesConfig = field(default_factory=AlertRulesConfig)
    actions: ActionsConfig = field(default_factory=ActionsConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    advisor: LLMAdvisorConfig = field(default_factory=LLMAdvisorConfig)
    working_hours: str = "09:00-22:00"

    @property
    def state_db_path(self) -> Path:
        return self.watch.log_root / "hound" / "state.db"

    @property
    def output_dir(self) -> Path:
        return self.watch.log_root / "hound"

    @property
    def feedback_path(self) -> Path:
        return self.watch.log_root / "tracehound_feedback.yaml"

    @property
    def events_log_path(self) -> Path:
        return self.output_dir / "events.jsonl"
