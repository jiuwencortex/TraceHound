"""Trajectories Analyzer for JiuwenSwarm.

Reads jiuwenswarm session-history JSONL files and surfaces actionable diagnostics.

Quick start::

    from . import TrajectoriesLoader, TrajectoriesReport

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))

CLI entry point::

    python -m analyzer --log-dir /path/to/online_logs
"""

from analyzer.analyzers.content_delivery import (
    ContentDeliveryAnalyzer,
    ContentDeliveryResult,
)
from analyzer.analyzers.conversation_length import (
    ConversationLengthAnalyzer,
    ConversationLengthResult,
)
from analyzer.analyzers.data_health import (
    DataHealthAnalyzer,
    DataHealthResult,
)
from analyzer.analyzers.error_categories import (
    ErrorCategoryAnalyzer,
    ErrorCategoryResult,
)
from analyzer.analyzers.llm_performance import (
    LLMPerformanceAnalyzer,
    LLMPerformanceResult,
)
from analyzer.analyzers.session_flow import (
    SessionFlowAnalyzer,
    SessionFlowResult,
)
from analyzer.analyzers.time_bottlenecks import (
    TimeBottlenecksAnalyzer,
    TimeBottlenecksResult,
)
from analyzer.analyzers.token_usage import (
    TokenUsageAnalyzer,
    TokenUsageResult,
)
from analyzer.analyzers.tool_arguments import (
    ToolArgumentAnalyzer,
    ToolArgumentResult,
)
from analyzer.analyzers.tool_success import (
    ToolSuccessAnalyzer,
    ToolSuccessResult,
)
from analyzer.analyzers.user_queries import (
    UserQueryAnalyzer,
    UserQueryResult,
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
    "DataHealthAnalyzer",
    "DataHealthResult",
    "ConversationLengthAnalyzer",
    "ConversationLengthResult",
    "TimeBottlenecksAnalyzer",
    "TimeBottlenecksResult",
    "TokenUsageAnalyzer",
    "TokenUsageResult",
    "LLMPerformanceAnalyzer",
    "LLMPerformanceResult",
    "ToolSuccessAnalyzer",
    "ToolSuccessResult",
    "ErrorCategoryAnalyzer",
    "ErrorCategoryResult",
    "UserQueryAnalyzer",
    "UserQueryResult",
    "SessionFlowAnalyzer",
    "SessionFlowResult",
    "ToolArgumentAnalyzer",
    "ToolArgumentResult",
    "ContentDeliveryAnalyzer",
    "ContentDeliveryResult",
]
