# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Trajectories Analyzer for JiuwenSwarm.

Reads thalamus weekly turn-log JSONL files and surfaces actionable diagnostics:

- **Data health**: turn counts, date range, feedback coverage, skipped records.
- **Quality trends**: week-over-week mean quality with trend direction detection.
- **Component bottlenecks**: skills, memory sections, and tools with low quality,
  high correction rates, or low task-completion rates — each ranked by severity score.
- **Budget waste**: components included in context but rarely or never invoked.
- **Correction patterns**: components whose presence correlates with follow-up corrections.
- **Exploration analysis**: whether off-policy exploration is net beneficial and which
  randomly-added components help vs. hurt quality.
- **Conversation length**: distribution, quality by length bucket, and components that
  consistently inflate conversation length.
- **Signal disagreement**: turns where the quality formula disagrees with the user's
  explicit rating — identifies formula calibration issues and hard-to-judge components.
- **Component interactions**: pairwise quality delta analysis that surfaces toxic
  combinations (A+B worse than either alone) and synergistic combinations.

Quick start::

    from jiuwenswarm.trajectories_analyzer import TrajectoriesLoader, TrajectoriesReport

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))

CLI entry point::

    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs
"""

from .analyzers.component_interactions import (
    ComponentInteractionsAnalyzer,
    ComponentInteractionsResult,
    ComponentPair,
)
from .analyzers.conversation_length import (
    ConversationLengthAnalyzer,
    ConversationLengthResult,
)
from .analyzers.signal_disagreement import (
    SignalDisagreementAnalyzer,
    SignalDisagreementResult,
)
from loader import TrajectoriesLoader, TurnRecord
from report import ReportResult, TrajectoriesReport
from scorer import compute_qualities, compute_quality

__all__ = [
    # Core
    "TrajectoriesLoader",
    "TurnRecord",
    "TrajectoriesReport",
    "ReportResult",
    "compute_quality",
    "compute_qualities",
    # New analyzers
    "ConversationLengthAnalyzer",
    "ConversationLengthResult",
    "SignalDisagreementAnalyzer",
    "SignalDisagreementResult",
    "ComponentInteractionsAnalyzer",
    "ComponentInteractionsResult",
    "ComponentPair",
]
