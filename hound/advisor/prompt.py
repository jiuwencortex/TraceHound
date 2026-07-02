# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""build_prompt — assembles the LLM context bundle for advisor calls."""

from __future__ import annotations

from ..accumulate.state import AnalyzerState
from ..alerts.alert import Alert


def build_prompt(alert: Alert, state: AnalyzerState) -> str:
    """Build a compact system+user prompt for the LLMAdvisor."""
    system = (
        "You are TraceHound Hound, an AI assistant that analyses jiuwenswarm "
        "multi-agent system logs and provides concise, actionable diagnostics. "
        "Respond in plain text with three sections: "
        "'## What happened', '## Most likely root cause', '## Suggested next steps'. "
        "Keep each section to 2-4 sentences or a short numbered list."
    )

    context_lines = [
        f"Alert rule: {alert.rule_id}",
        f"Severity: {alert.severity.value}",
        f"Title: {alert.title}",
        f"Description: {alert.description}",
        "",
        "Current metrics:",
        f"  - Quality EMA: {state.quality_ema:.3f}",
        f"  - Error rate (recent): {state.error_rate:.1%}",
        f"  - Correction rate: {state.correction_rate:.1%}",
        f"  - Mean tokens/turn: {state.mean_tokens_per_turn:.0f}",
        f"  - Mean context usage: {state.mean_usage_percent:.1%}",
        f"  - Median latency: {state.median_latency_ms:.0f} ms",
        f"  - Estimated daily cost: ${state.estimated_daily_cost_usd:.4f}",
        "",
        "Alert payload:",
    ]
    for k, v in alert.payload.items():
        context_lines.append(f"  - {k}: {v}")

    # Add recent error categories if any
    if state.recent_error_categories:
        cats = list(dict.fromkeys(state.recent_error_categories[-10:]))
        context_lines += ["", f"Recent error categories: {', '.join(cats)}"]

    user = "\n".join(context_lines)
    return f"SYSTEM: {system}\n\nUSER:\n{user}"
