# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""load_config — read agent_config.yaml and return an AgentConfig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .defaults import DEFAULT_CONFIG_PATH, write_default_config
from .schema import (
    ActionsConfig,
    AgentConfig,
    AlertRulesConfig,
    AlertThresholds,
    AnalysisConfig,
    FeedbackConfig,
    LLMAdvisorConfig,
    MacOSNotifyConfig,
    ScheduleConfig,
    SlackConfig,
    WatchConfig,
)


def _get(d: dict, key: str, default: Any) -> Any:
    return d.get(key, default)


def load_config(path: Path | None = None) -> AgentConfig:
    """Parse the YAML config file and return a typed AgentConfig.

    If ``path`` is None, uses the default location.
    If the file does not exist, the default config is written and defaults are used.
    """
    import yaml  # optional at runtime; required for full config support

    config_path = path or DEFAULT_CONFIG_PATH
    write_default_config(config_path)

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        raw = {}

    def _expand_home(s: str) -> Path:
        return Path(s).expanduser()

    # watch
    w = raw.get("watch", {})
    watch = WatchConfig(
        log_root=_expand_home(str(w.get("log_root", "~/.jiuwenswarm"))),
        debounce_ms=int(w.get("debounce_ms", 500)),
    )

    # analysis
    a = raw.get("analysis", {})
    analysis = AnalysisConfig(
        max_weeks=int(a.get("max_weeks", 8)),
        quality_deficit_threshold=float(a.get("quality_deficit_threshold", 0.15)),
        correction_lift_threshold=float(a.get("correction_lift_threshold", 1.5)),
        skip_heartbeats=bool(a.get("skip_heartbeats", True)),
    )

    # alerts
    al = raw.get("alerts", {})
    thr_raw = al.get("thresholds", {})
    thresholds = AlertThresholds(
        quality_drop_delta=float(thr_raw.get("quality_drop_delta", 0.15)),
        quality_drop_window_turns=int(thr_raw.get("quality_drop_window_turns", 5)),
        quality_critical_value=float(thr_raw.get("quality_critical_value", 0.40)),
        error_spike_ratio=float(thr_raw.get("error_spike_ratio", 2.0)),
        error_spike_window_turns=int(thr_raw.get("error_spike_window_turns", 20)),
        tool_failure_storm_count=int(thr_raw.get("tool_failure_storm_count", 5)),
        tool_failure_storm_window=int(thr_raw.get("tool_failure_storm_window", 10)),
        context_pressure_threshold=float(thr_raw.get("context_pressure_threshold", 0.80)),
        context_pressure_window_turns=int(thr_raw.get("context_pressure_window_turns", 10)),
        context_critical_threshold=float(thr_raw.get("context_critical_threshold", 0.95)),
        latency_regression_ratio=float(thr_raw.get("latency_regression_ratio", 1.5)),
        correction_loop_rate=float(thr_raw.get("correction_loop_rate", 0.40)),
        correction_loop_window_turns=int(thr_raw.get("correction_loop_window_turns", 15)),
        cost_daily_budget_usd=float(thr_raw.get("cost_daily_budget_usd", 5.00)),
        no_data_hours=float(thr_raw.get("no_data_hours", 4.0)),
        session_dead_hours=float(thr_raw.get("session_dead_hours", 2.0)),
    )
    alerts = AlertRulesConfig(
        quality_drop=bool(al.get("quality_drop", True)),
        quality_critical=bool(al.get("quality_critical", True)),
        error_spike=bool(al.get("error_spike", True)),
        tool_failure_storm=bool(al.get("tool_failure_storm", True)),
        context_pressure=bool(al.get("context_pressure", True)),
        context_critical=bool(al.get("context_critical", True)),
        latency_regression=bool(al.get("latency_regression", True)),
        new_error_category=bool(al.get("new_error_category", True)),
        correction_loop=bool(al.get("correction_loop", True)),
        cost_threshold=bool(al.get("cost_threshold", True)),
        no_data=bool(al.get("no_data", True)),
        session_dead=bool(al.get("session_dead", True)),
        thresholds=thresholds,
    )

    # actions
    ac = raw.get("actions", {})
    mn = ac.get("macos_notification", {})
    sl = ac.get("slack", {})
    fb = ac.get("jiuwenswarm_feedback", {})
    actions = ActionsConfig(
        markdown_files=bool(ac.get("markdown_files", True)),
        macos_notification=MacOSNotifyConfig(
            enabled=bool(mn.get("enabled", True)),
            min_severity=str(mn.get("min_severity", "WARNING")),
        ),
        slack=SlackConfig(
            enabled=bool(sl.get("enabled", False)),
            webhook_url=str(sl.get("webhook_url", "")),
            min_severity=str(sl.get("min_severity", "WARNING")),
        ),
        jiuwenswarm_feedback=FeedbackConfig(
            enabled=bool(fb.get("enabled", True)),
            update_interval_minutes=int(fb.get("update_interval_minutes", 30)),
        ),
    )

    # schedule
    sc = raw.get("schedule", {})
    schedule = ScheduleConfig(
        hourly_check=bool(sc.get("hourly_check", True)),
        daily_summary=str(sc.get("daily_summary", "08:00")),
        weekly_report=str(sc.get("weekly_report", "Monday 07:00")),
        on_session_end=bool(sc.get("on_session_end", True)),
        session_end_idle_minutes=int(sc.get("session_end_idle_minutes", 30)),
    )

    # advisor
    adv = raw.get("advisor", {})
    advisor = LLMAdvisorConfig(
        enabled=bool(adv.get("enabled", False)),
        provider=str(adv.get("provider", "kimi")),
        model=str(adv.get("model", "moonshot-v1-8k")),
        api_key_env=str(adv.get("api_key_env", "MOONSHOT_API_KEY")),
        trigger_on=list(adv.get("trigger_on", ["CRITICAL"])),
    )

    return AgentConfig(
        watch=watch,
        analysis=analysis,
        alerts=alerts,
        actions=actions,
        schedule=schedule,
        advisor=advisor,
        working_hours=str(raw.get("working_hours", "09:00-22:00")),
    )
