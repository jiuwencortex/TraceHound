"""Trajectories Analyzer for JiuwenSwarm.

Reads thalamus weekly turn-log JSONL files and surfaces actionable diagnostics.

Quick start::

    from jiuwenswarm.trajectories_analyzer import TrajectoriesLoader, TrajectoriesReport

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))

CLI entry point::

    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs
"""

from .analyzers import (
    ComponentInteractionsAnalyzer,
    ComponentInteractionsResult,
    ComponentPair,
)
from .analyzers import (
    ConversationLengthAnalyzer,
    ConversationLengthResult,
)
from .analyzers import (
    SignalDisagreementAnalyzer,
    SignalDisagreementResult,
)
from .loader import TrajectoriesLoader, TurnRecord
from .report import ReportResult, TrajectoriesReport
from .scorer import compute_qualities, compute_quality

__all__ = [
    "TrajectoriesLoader",
    "TurnRecord",
    "TrajectoriesReport",
    "ReportResult",
    "compute_quality",
    "compute_qualities",
    "ConversationLengthAnalyzer",
    "ConversationLengthResult",
    "SignalDisagreementAnalyzer",
    "SignalDisagreementResult",
    "ComponentInteractionsAnalyzer",
    "ComponentInteractionsResult",
    "ComponentPair",
]
