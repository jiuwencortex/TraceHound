"""Trajectories Analyzer for JiuwenSwarm.

Reads jiuwenswarm session-history JSONL files and surfaces actionable diagnostics.

Quick start::

    from . import TrajectoriesLoader, TrajectoriesReport

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))

CLI entry point::

    jiuwenswarm-analyze-trajectories --log-dir /path/to/online_logs
"""

from analyzer.analyzers import (
    ComponentInteractionsAnalyzer,
    ComponentInteractionsResult,
    ComponentPair,
)
from analyzer.analyzers import (
    ConversationLengthAnalyzer,
    ConversationLengthResult,
)
from analyzer.analyzers import (
    SignalDisagreementAnalyzer,
    SignalDisagreementResult,
)
from analyzer.loader import TrajectoriesLoader, TurnRecord
from analyzer.report import ReportResult, TrajectoriesReport
from analyzer.scorer import compute_qualities, compute_quality

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
