# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default agent_config.yaml content and path resolution."""

from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".jiuwenswarm" / "hound" / "agent_config.yaml"

DEFAULT_YAML = """\
# TraceHound Hound Agent — configuration
# Generated automatically. Edit as needed.

watch:
  log_root: ~/.jiuwenswarm
  debounce_ms: 500

analysis:
  max_weeks: 8
  quality_deficit_threshold: 0.15
  correction_lift_threshold: 1.5
  skip_heartbeats: true

alerts:
  quality_drop: true
  quality_critical: true
  error_spike: true
  tool_failure_storm: true
  context_pressure: true
  context_critical: true
  latency_regression: true
  new_error_category: true
  correction_loop: true
  cost_threshold: true
  no_data: true
  thresholds:
    quality_drop_delta: 0.15
    quality_drop_window_turns: 5
    quality_critical_value: 0.40
    error_spike_ratio: 2.0
    error_spike_window_turns: 20
    tool_failure_storm_count: 5
    tool_failure_storm_window: 10
    context_pressure_threshold: 0.80
    context_pressure_window_turns: 10
    context_critical_threshold: 0.95
    latency_regression_ratio: 1.5
    correction_loop_rate: 0.40
    correction_loop_window_turns: 15
    cost_daily_budget_usd: 5.00
    no_data_hours: 4.0

actions:
  markdown_files: true
  macos_notification:
    enabled: true
    min_severity: WARNING
  slack:
    enabled: false
    webhook_url: ""
    min_severity: WARNING
  jiuwenswarm_feedback:
    enabled: true
    update_interval_minutes: 30

schedule:
  hourly_check: true
  daily_summary: "08:00"
  weekly_report: "Monday 07:00"
  on_session_end: true
  session_end_idle_minutes: 30

advisor:
  enabled: false
  provider: kimi
  model: moonshot-v1-8k
  api_key_env: MOONSHOT_API_KEY
  trigger_on:
    - CRITICAL

working_hours: "09:00-22:00"
"""


def write_default_config(path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Write the default config file if it does not already exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_YAML, encoding="utf-8")
