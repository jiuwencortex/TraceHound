# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Factory that builds the list of enabled AlertRule instances from config."""

from __future__ import annotations

from ...config.schema import AgentConfig, AlertRulesConfig
from ...memory.alert_store import AlertStore
from .context_critical import ContextCriticalRule
from .context_pressure import ContextPressureRule
from .correction_loop import CorrectionLoopRule
from .cost_threshold import CostThresholdRule
from .error_spike import ErrorSpikeRule
from .new_error_category import NewErrorCategoryRule
from .no_data import NoDataRule
from .quality_critical import QualityCriticalRule
from .quality_drop import QualityDropRule
from .tool_failure_storm import ToolFailureStormRule


def build_rules(cfg: AgentConfig, alert_store: AlertStore) -> list:
    """Return a list of enabled rule instances based on configuration."""
    thr = cfg.alerts.thresholds
    rules = []
    if cfg.alerts.quality_drop:
        rules.append(QualityDropRule(delta=thr.quality_drop_delta, window=thr.quality_drop_window_turns))
    if cfg.alerts.quality_critical:
        rules.append(QualityCriticalRule(threshold=thr.quality_critical_value))
    if cfg.alerts.error_spike:
        rules.append(ErrorSpikeRule(ratio=thr.error_spike_ratio, window=thr.error_spike_window_turns))
    if cfg.alerts.tool_failure_storm:
        rules.append(ToolFailureStormRule(min_failures=thr.tool_failure_storm_count, window=thr.tool_failure_storm_window))
    if cfg.alerts.context_pressure:
        rules.append(ContextPressureRule(threshold=thr.context_pressure_threshold))
    if cfg.alerts.context_critical:
        rules.append(ContextCriticalRule(threshold=thr.context_critical_threshold))
    if cfg.alerts.correction_loop:
        rules.append(CorrectionLoopRule(rate=thr.correction_loop_rate))
    if cfg.alerts.cost_threshold:
        rules.append(CostThresholdRule(daily_budget_usd=thr.cost_daily_budget_usd))
    if cfg.alerts.new_error_category:
        rules.append(NewErrorCategoryRule(alert_store=alert_store))
    if cfg.alerts.no_data:
        rules.append(NoDataRule(hours=thr.no_data_hours))
    return rules
