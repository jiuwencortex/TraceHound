# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TrajectoriesReport: orchestrates all analyzers and renders output.

Usage::

    from .report import TrajectoriesReport
    from .loader import TrajectoriesLoader

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from .analyzers.content_delivery import (
    ContentDeliveryAnalyzer,
    ContentDeliveryResult,
)
from .analyzers.conversation_length import (
    ConversationLengthAnalyzer,
    ConversationLengthResult,
)
from .analyzers.correction_patterns import (
    CorrectionPatternsAnalyzer,
    CorrectionPatternsResult,
)
from .analyzers.data_health import (
    DataHealthAnalyzer,
    DataHealthResult,
)
from .analyzers.error_categories import (
    ErrorCategoryAnalyzer,
    ErrorCategoryResult,
)
from .analyzers.llm_performance import (
    LLMPerformanceAnalyzer,
    LLMPerformanceResult,
)
from .analyzers.quality_trends import (
    QualityTrendsAnalyzer,
    QualityTrendsResult,
)
from .analyzers.session_flow import (
    SessionFlowAnalyzer,
    SessionFlowResult,
)
from .analyzers.time_bottlenecks import (
    TimeBottlenecksAnalyzer,
    TimeBottlenecksResult,
)
from .analyzers.token_usage import (
    TokenUsageAnalyzer,
    TokenUsageResult,
)
from .analyzers.tool_arguments import (
    ToolArgumentAnalyzer,
    ToolArgumentResult,
)
from .analyzers.tool_success import (
    ToolSuccessAnalyzer,
    ToolSuccessResult,
)
from .analyzers.user_queries import (
    UserQueryAnalyzer,
    UserQueryResult,
)
from .loader import TrajectoriesLoader, TurnRecord
from .scorer import compute_qualities


@dataclass(frozen=True)
class ReportResult:
    generated_at: datetime
    data_health: DataHealthResult
    quality_trends: QualityTrendsResult
    correction_patterns: CorrectionPatternsResult
    conversation_length: ConversationLengthResult
    time_bottlenecks: TimeBottlenecksResult
    token_usage: TokenUsageResult
    llm_performance: LLMPerformanceResult
    tool_success: ToolSuccessResult
    error_categories: ErrorCategoryResult
    user_queries: UserQueryResult
    session_flow: SessionFlowResult
    tool_arguments: ToolArgumentResult
    content_delivery: ContentDeliveryResult

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "data_health": self.data_health.to_dict(),
            "quality_trends": self.quality_trends.to_dict(),
            "correction_patterns": self.correction_patterns.to_dict(),
            "conversation_length": self.conversation_length.to_dict(),
            "time_bottlenecks": self.time_bottlenecks.to_dict(),
            "token_usage": self.token_usage.to_dict(),
            "llm_performance": self.llm_performance.to_dict(),
            "tool_success": self.tool_success.to_dict(),
            "error_categories": self.error_categories.to_dict(),
            "user_queries": self.user_queries.to_dict(),
            "session_flow": self.session_flow.to_dict(),
            "tool_arguments": self.tool_arguments.to_dict(),
            "content_delivery": self.content_delivery.to_dict(),
        }


class TrajectoriesReport:
    """Run all analyzers over loaded turns and render results."""

    def __init__(
        self,
        loader: TrajectoriesLoader,
        quality_deficit_threshold: float = 0.15,
        correction_lift_threshold: float = 1.5,
    ) -> None:
        self._loader = loader
        self._quality_deficit = quality_deficit_threshold
        self._correction_lift = correction_lift_threshold
        self._turns: list[TurnRecord] = []
        self._qualities: list[float] = []

    def run(self) -> ReportResult:
        """Load turns and run all analyzers."""
        self._turns = self._loader.load()
        self._qualities = compute_qualities(self._turns)
        turns = self._turns
        qualities = self._qualities
        log_files = self._loader.log_files()

        data_health = DataHealthAnalyzer(
            turns,
            skipped_records=self._loader.skipped_records,
            log_files=log_files,
        ).analyze()

        quality_trends = QualityTrendsAnalyzer(turns, qualities).analyze()

        correction_patterns = CorrectionPatternsAnalyzer(
            turns,
            lift_threshold=self._correction_lift,
        ).analyze()

        conversation_length = ConversationLengthAnalyzer(turns, qualities).analyze()

        time_bottlenecks = TimeBottlenecksAnalyzer(
            turns,
            qualities,
            tool_call_timings=self._loader.tool_call_timings,
        ).analyze()

        token_usage = TokenUsageAnalyzer(turns).analyze()

        llm_performance = LLMPerformanceAnalyzer(turns, qualities).analyze()

        tool_success = ToolSuccessAnalyzer(turns).analyze()

        error_categories = ErrorCategoryAnalyzer(turns).analyze()

        user_queries = UserQueryAnalyzer(turns, qualities).analyze()

        session_flow = SessionFlowAnalyzer(turns).analyze()

        tool_arguments = ToolArgumentAnalyzer(
            turns, raw_sessions=self._loader.raw_sessions
        ).analyze()

        content_delivery = ContentDeliveryAnalyzer(turns, qualities).analyze()

        return ReportResult(
            generated_at=datetime.now(tz=timezone.utc),
            data_health=data_health,
            quality_trends=quality_trends,
            correction_patterns=correction_patterns,
            conversation_length=conversation_length,
            time_bottlenecks=time_bottlenecks,
            token_usage=token_usage,
            llm_performance=llm_performance,
            tool_success=tool_success,
            error_categories=error_categories,
            user_queries=user_queries,
            session_flow=session_flow,
            tool_arguments=tool_arguments,
            content_delivery=content_delivery,
        )

    def render_json(self, result: ReportResult) -> str:
        """Return machine-readable JSON."""
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    def render_text(self, result: ReportResult, verbose: bool = False) -> str:
        """Return a human-readable text report."""
        lines: list[str] = []

        def h(title: str) -> None:
            lines.append(f"\n--- {title} ---")

        def v(title: str) -> None:
            if verbose:
                lines.append(f"\n  >>> {title}")

        dh = result.data_health
        qt = result.quality_trends
        crp = result.correction_patterns
        cl = result.conversation_length
        tb = result.time_bottlenecks
        tu = result.token_usage
        lp = result.llm_performance
        ts = result.tool_success
        ec = result.error_categories
        uq = result.user_queries
        sf = result.session_flow
        ta = result.tool_arguments
        cd = result.content_delivery

        lines.append("=== TraceHound Analyzer Report ===")
        lines.append(f"Generated: {result.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        if verbose:
            lines.append("Mode: VERBOSE")
        lines.append("")

        h("Data Health")
        lines.append(f"  Total turns: {dh.total_turns}")
        if dh.date_range:
            lines.append(f"  Date range: {dh.date_range[0].strftime('%Y-%m-%d')} → {dh.date_range[1].strftime('%Y-%m-%d')}")

        n_log_files = len(dh.log_files_found)
        unique_names = sorted(set(dh.log_files_found))
        if len(unique_names) == 1 and unique_names[0] == "history.jsonl":
            session_ids = [p.parent.name for p in self._loader.log_files()]
            lines.append(f"  Sessions loaded: {n_log_files}")
            if session_ids:
                preview = session_ids[:5]
                suffix = f"  (+ {len(session_ids) - 5} more)" if len(session_ids) > 5 else ""
                lines.append(f"  Session IDs: {', '.join(preview)}{suffix}")
        else:
            lines.append(f"  Log files: {n_log_files} ({', '.join(unique_names) or 'none'})")

        lines.append(f"  Skipped (malformed): {dh.skipped_records}")
        if dh.weeks_with_low_data:
            lines.append(f"  Low-data weeks: {', '.join(dh.weeks_with_low_data)}")
        else:
            lines.append("  Low-data weeks: none")

        v("Data Health Evidence")
        if verbose and self._loader.raw_sessions:
            for path, msgs in self._loader.raw_sessions.items():
                sz = path.stat().st_size
                sz_str = f"{sz/1024:.1f} KB" if sz > 1024 else f"{sz} B"
                lines.append(f"    {path.parent.name}: {len(msgs)} messages, {sz_str}")

        h("Session Overview")
        lines.append(f"  Total sessions: {sf.total_sessions} (real: {sf.total_real_sessions}, heartbeat: {sf.total_heartbeat_sessions})")
        sz = sf.session_size_distribution
        lines.append(f"  Turns per session: min={sz.get('min', 0)} median={sz.get('median', 0):.1f} mean={sz.get('mean', 0):.1f} max={sz.get('max', 0)}")
        if sf.agent_mode_distribution:
            lines.append("  Agent modes:")
            for mode, count in sf.agent_mode_distribution.items():
                lines.append(f"    {mode}: {count}")
        if sf.session_profiles:
            productive = sum(1 for p in sf.session_profiles if p.files_delivered > 0)
            lines.append(f"  Productive sessions: {productive}/{sf.total_real_sessions}")
            error_sessions = sum(1 for p in sf.session_profiles if p.error_count > 0)
            lines.append(f"  Sessions with errors: {error_sessions}/{sf.total_real_sessions}")
        if sf.n_error_cascades:
            lines.append(f"  Error cascades: {sf.n_error_cascades} ({sf.n_recovery_sessions} recovered)")
        if sf.persistent_errors:
            lines.append(f"  Persistent errors: {', '.join(pe.error_category for pe in sf.persistent_errors)}")

        h(f"Quality Trend: {qt.trend_direction}")
        lines.append(f"  Overall mean quality: {qt.overall_mean:.3f}")
        if qt.best_week:
            best = next((w for w in qt.weeks if w.week_tag == qt.best_week), None)
            if best:
                lines.append(f"  Best week: {qt.best_week} (mean={best.mean_quality:.3f}, n={best.n_turns})")
        if qt.worst_week:
            worst = next((w for w in qt.weeks if w.week_tag == qt.worst_week), None)
            if worst:
                lines.append(f"  Worst week: {qt.worst_week} (mean={worst.mean_quality:.3f}, n={worst.n_turns})")
        lines.append(f"  Per-week breakdown ({len(qt.weeks)} weeks):")
        for w in qt.weeks:
            lines.append(f"    {w.week_tag}: mean={w.mean_quality:.3f} n={w.n_turns} completed={w.n_task_completed} corrections={w.n_follow_up_corrections}")

        v("Quality Evidence")
        if verbose and self._turns:
            turn_q = sorted(
                [(t, q) for t, q in zip(self._turns, self._qualities) if not t.is_heartbeat],
                key=lambda x: x[1], reverse=True
            )
            lines.append("  Top 5 highest-quality turns:")
            for t, q in turn_q[:5]:
                status = "OK" if t.task_completed else ("ERR" if t.follow_up_correction else "?")
                lines.append(f"    {t.turn_id[:28]:28s} q={q:.3f} [{status}] len={t.conversation_length}")
            lines.append("  Bottom 5 lowest-quality turns:")
            for t, q in turn_q[-5:]:
                status = "OK" if t.task_completed else ("ERR" if t.follow_up_correction else "?")
                lines.append(f"    {t.turn_id[:28]:28s} q={q:.3f} [{status}] len={t.conversation_length}")

        h("Token Usage")
        if tu.total_tokens == 0:
            lines.append("  No token data available.")
        else:
            lines.append(f"  Total tokens: {tu.total_tokens:,} (in={tu.total_input_tokens:,} out={tu.total_output_tokens:,})")
            lines.append(f"  Per turn: avg={tu.mean_tokens_per_turn:.0f} median={tu.median_tokens_per_turn:.0f} max={tu.max_tokens_per_turn:,}")
            if tu.failure_turns > 0:
                lines.append(f"  Efficiency: success={tu.mean_tokens_per_success:.0f} failure={tu.mean_tokens_per_failure:.0f} ratio={tu.token_efficiency_ratio:.2f}")
            else:
                lines.append(f"  Efficiency: success={tu.mean_tokens_per_success:.0f} (no failures)")
            lines.append(f"  Context: avg={tu.mean_usage_percent:.1%} p90={tu.p90_usage_percent:.1%}")
            if tu.turns_near_limit > 0:
                lines.append(f"  Near-limit turns: {tu.turns_near_limit}")
            if tu.estimated_total_cost > 0:
                lines.append(f"  Est. cost: ${tu.estimated_total_cost:.4f}")
            if tu.weekly_summary:
                for w in tu.weekly_summary:
                    lines.append(f"    {w.week_tag}: total={w.total_tokens:,} avg={w.mean_total_tokens:.0f} near-limit={w.turns_near_limit}")
            if tu.model_summary:
                for m in tu.model_summary:
                    lines.append(f"    {m.model_name or 'unknown':20s} turns={m.n_turns} total={m.total_tokens:,} avg={m.mean_total_tokens:.0f}")
            if tu.tool_summary:
                for t_tool in tu.tool_summary[:5]:
                    lines.append(f"    {t_tool.tool_name:20s} avg={t_tool.mean_total_tokens:.0f} n={t_tool.n_turns}")

        h("LLM Performance")
        if lp.n_turns_with_timing == 0:
            lines.append("  No LLM timing data.")
        else:
            lines.append(f"  Timed turns: {lp.n_turns_with_timing}")
            d = lp.total_latency
            lines.append(f"  Total latency: min={d.min:.0f}ms median={d.median:.0f}ms p90={d.p90:.0f}ms max={d.max:.0f}ms")
            d_ttft = lp.ttft
            lines.append(f"  TTFT: min={d_ttft.min:.0f}ms median={d_ttft.median:.0f}ms p90={d_ttft.p90:.0f}ms")
            d_tpot = lp.tpot
            lines.append(f"  TPOT: min={d_tpot.min:.0f}ms median={d_tpot.median:.0f}ms p90={d_tpot.p90:.0f}ms")
            lines.append(f"  Throughput: {lp.mean_tokens_per_second:.1f} tok/s")
            if lp.slowest_turns:
                lines.append(f"  Slowest turns:")
                for st in lp.slowest_turns[:5]:
                    lines.append(f"    {st.turn_id[:28]:28s} lat={st.total_latency_ms:7.0f}ms ttft={st.ttft_ms:6.0f}ms tpot={st.tpot_ms:6.1f}ms [{st.status}]")
            if lp.weekly_summaries:
                for w in lp.weekly_summaries:
                    lines.append(f"    {w.week_tag}: avg={w.mean_total_latency_ms:.0f}ms slow_prompt={w.slow_prompt_processing_count} slow_gen={w.slow_generation_count}")
            if lp.model_summaries:
                for m in lp.model_summaries:
                    lines.append(f"    {m.model_name or 'unknown':20s} avg={m.total_latency.mean:.0f}ms ttft={m.ttft.mean:.0f}ms throughput={m.mean_tokens_per_second:.1f}t/s")

        h("Tool Success Rate")
        lines.append(f"  Total calls: {ts.total_tool_calls} Failures: {ts.total_tool_failures} Success: {ts.overall_success_rate:.1%}")
        if ts.per_tool_stats:
            lines.append("  Per-tool:")
            for pts in ts.per_tool_stats[:8]:
                marker = " ⚠" if pts.success_rate < 0.8 else ""
                lines.append(f"    {pts.name:20s} {pts.success_rate:6.1%} ({pts.successes}/{pts.total_calls}){marker}")
        if ts.retry_patterns:
            lines.append(f"  Repeated tool calls: {len(ts.retry_patterns)}")
            for rp in ts.retry_patterns[:3]:
                lines.append(f"    {rp.tool_name}: {rp.n_turns_with_retries} turns, avg {rp.avg_calls_per_retry_turn:.1f} calls/turn")
        if ts.recovery_turns > 0:
            failure_turns = sum(1 for t in self._turns if t.n_tool_failures > 0 and not t.is_heartbeat)
            lines.append(f"  Recovery: {ts.recovery_turns}/{failure_turns} turns ({ts.recovery_rate:.1%})")
        if ts.top_error_messages:
            lines.append("  Common errors:")
            for msg, count in ts.top_error_messages[:5]:
                lines.append(f"    ({count}x) {msg[:80]}{'...' if len(msg) > 80 else ''}")

        h("Error Categorization")
        lines.append(f"  Rate: {ec.overall_error_rate:.1%} ({ec.error_turns}/{ec.total_turns} turns)")
        if ec.categories:
            lines.append("  By category:")
            for cat in ec.categories:
                lines.append(f"    {cat.category:15s} {cat.count:3d} ({cat.percentage_of_errors:.1%})")
                if verbose and cat.example_messages:
                    for ex in cat.example_messages[:2]:
                        lines.append(f"      e.g. {ex[:100]}{'...' if len(ex) > 100 else ''}")
        if ec.session_profiles:
            lines.append("  Error-prone sessions:")
            for se in sorted(ec.session_profiles, key=lambda x: x.error_count, reverse=True)[:3]:
                lines.append(f"    {se.session_id[:32]:32s} errors={se.error_count}")
        if ec.persistent_error_categories:
            lines.append(f"  Persistent: {', '.join(ec.persistent_error_categories)}")
        if ec.recovery_rate is not None:
            lines.append(f"  Recovery: {ec.recovery_rate:.1%}")
        if ec.weekly_summaries:
            for w in ec.weekly_summaries:
                lines.append(f"    {w.week_tag}: {w.error_count}/{w.total_turns} top={w.top_category}")

        h("User Query Analysis")
        lines.append(f"  Length: min={uq.length_min} median={uq.length_median:.0f} mean={uq.length_mean:.0f} p90={uq.length_p90:.0f} max={uq.length_max}")
        if uq.length_buckets:
            lines.append("  Length vs quality:")
            for b in uq.length_buckets:
                if b.n_turns > 0:
                    lines.append(f"    {b.label:12s} ({b.min_chars:4d}-{b.max_chars:4d}ch): n={b.n_turns} qual={b.mean_quality:.3f}")
        if uq.query_type_distribution:
            lines.append("  Types:")
            for qt_summary in uq.query_type_distribution:
                lines.append(f"    {qt_summary.type_label:12s}: {qt_summary.count:3d} qual={qt_summary.mean_quality:.3f}")
        if uq.length_vs_duration_correlation is not None:
            lines.append(f"  Len vs duration: r={uq.length_vs_duration_correlation:.3f}")
        if uq.length_vs_tokens_correlation is not None:
            lines.append(f"  Len vs tokens: r={uq.length_vs_tokens_correlation:.3f}")
        if verbose and uq.longest_queries:
            lines.append("  Longest queries:")
            for q in uq.longest_queries[:3]:
                text = q["user_query"]
                preview = text[:80] + "..." if len(text) > 80 else text
                lines.append(f"    [{q['type']}] len={q['length']} {preview}")

        h("Content Delivery")
        lines.append(f"  Response length: min={cd.response_length_min} median={cd.response_length_median:.0f} mean={cd.response_length_mean:.0f} p90={cd.response_length_p90:.0f} max={cd.response_length_max}")
        lines.append(f"  Productive: {cd.productive_turns}/{cd.total_turns} ({cd.productivity_rate:.1%})")
        lines.append(f"  Files: {cd.total_files_delivered} ({cd.avg_files_per_turn:.2f}/turn)")
        if cd.silent_success_turns > 0:
            lines.append(f"  Silent successes: {cd.silent_success_turns}")
        if cd.response_buckets:
            for b in cd.response_buckets:
                if b.n_turns > 0:
                    lines.append(f"    {b.label:12s}: n={b.n_turns} qual={b.mean_quality:.3f}")
        if cd.weekly_summaries:
            for w in cd.weekly_summaries:
                lines.append(f"    {w.week_tag}: avg_len={w.avg_response_length:.0f} files={w.n_files}")

        h("Time Bottlenecks")
        if tb.n_turns_with_timing == 0:
            lines.append(f"  No timing data ({tb.n_turns_total} turns total).")
        else:
            lines.append(f"  Timed: {tb.n_turns_with_timing}/{tb.n_turns_total}")
            lines.append(f"  Duration: min={tb.min_duration_s:.1f}s median={tb.median_duration_s:.1f}s mean={tb.mean_duration_s:.1f}s p90={tb.p90_duration_s:.1f}s max={tb.max_duration_s:.1f}s")
            lines.append(f"  Total wall time: {tb.total_time_s:.1f}s ({tb.total_time_s/60:.1f} min)")
            verdict = tb.speed_quality_verdict
            lines.append(f"  Speed/quality: {verdict} (slow_q={tb.slow_quartile_mean_quality:.3f} fast_q={tb.fast_half_mean_quality:.3f})")
            if tb.slowest_turns:
                lines.append("  Slowest turns:")
                for rec in tb.slowest_turns:
                    status = "ERR" if rec.has_error else ("OK" if rec.task_completed else "?")
                    tools_str = ", ".join(rec.tools_called[:4])
                    if len(rec.tools_called) > 4:
                        tools_str += f" +{len(rec.tools_called) - 4}"
                    lines.append(f"    {rec.turn_id[:28]:28s} {rec.duration_seconds:7.1f}s [{status}] q={rec.quality:.3f} msgs={rec.n_messages} [{tools_str}]")
            if tb.tool_turn_correlation:
                lines.append("  Tool-duration correlation:")
                for tc in tb.tool_turn_correlation[:10]:
                    marker = " <-- SLOW" if tc.duration_ratio >= 1.5 else ""
                    lines.append(f"    {tc.tool_name:30s} ratio={tc.duration_ratio:.2f}x mean={tc.mean_turn_duration_s:.1f}s n={tc.n_turns}{marker}")
            if tb.tool_call_timing:
                lines.append("  Per-tool timing:")
                for ts_t in tb.tool_call_timing[:10]:
                    lines.append(f"    {ts_t.tool_name:30s} mean={ts_t.mean_duration_s:.2f}s median={ts_t.median_duration_s:.2f}s p90={ts_t.p90_duration_s:.2f}s max={ts_t.max_duration_s:.2f}s n={ts_t.n_timed_calls}")
            if tb.hourly_distribution:
                lines.append("  Hourly activity:")
                for hb in tb.hourly_distribution:
                    bar = "#" * min(hb.n_turns, 20)
                    lines.append(f"    {hb.hour:02d}:00 {bar:<20s} n={hb.n_turns:3d} q={hb.mean_quality:.3f} dur={hb.mean_duration_s:.1f}s err={hb.error_rate:.0%}")

        if self._turns:
            all_tools: list[str] = []
            for t in self._turns:
                all_tools.extend(t.tools_called)
            if all_tools:
                h("Tool Call Frequency")
                tool_counts = Counter(all_tools)
                for tool, count in tool_counts.most_common(20):
                    bar = "#" * min(count, 30)
                    lines.append(f"  {tool:35s} {bar:<30s} {count:4d}")

        h("Tool Arguments & File Access")
        if ta.total_tool_calls == 0:
            lines.append("  No tool argument data.")
        else:
            lines.append(f"  Tool calls analyzed: {ta.total_tool_calls}")
            if ta.most_accessed_paths:
                lines.append("  Accessed paths:")
                for fa in ta.most_accessed_paths[:8]:
                    rw = f"R={fa.read_count} W={fa.write_count}"
                    lines.append(f"    {fa.path_pattern[:50]:50s} [{rw}]")
            if ta.dangerous_commands_found > 0:
                lines.append(f"  Dangerous commands: {ta.dangerous_commands_found}")
                for dc in [c for c in ta.command_stats if c.dangerous_flag][:3]:
                    lines.append(f"    {dc.command:20s} ({dc.count}x)")
            if ta.command_stats:
                lines.append("  Commands:")
                for cs in ta.command_stats[:5]:
                    lines.append(f"    {cs.command_base:20s} {cs.count:3d}")
            if ta.retry_patterns:
                lines.append(f"  Multi-call patterns: {len(ta.retry_patterns)}")
            if ta.read_write_ratio == float("inf"):
                lines.append("  Read/write ratio: ∞ (reads only)")
            elif ta.read_write_ratio == 0.0 and ta.read_count == 0 and ta.write_count == 0:
                lines.append("  Read/write ratio: n/a (no file access)")
            else:
                lines.append(f"  Read/write ratio: {ta.read_write_ratio:.2f}")
            if ta.most_common_extensions:
                ext_strs = [f"{ext}({count})" for ext, count in ta.most_common_extensions[:5]]
                lines.append(f"  Extensions: {', '.join(ext_strs)}")

        h("Correction Patterns")
        lines.append(f"  Rate: {crp.baseline_correction_rate:.1%} ({crp.total_corrected_turns}/{crp.total_turns})")
        if crp.high_lift_components:
            for p in crp.high_lift_components[:5]:
                lines.append(f"    {p.component_type}: {p.component} correction={p.correction_rate:.1%} lift={p.lift:.2f}x")
        else:
            lines.append("  No high-lift patterns.")

        v("Correction Evidence")
        if verbose and self._turns:
            error_turns = [(t, q) for t, q in zip(self._turns, self._qualities) if t.follow_up_correction and not t.is_heartbeat]
            if error_turns:
                lines.append(f"  All {len(error_turns)} error turns:")
                error_turns.sort(key=lambda x: x[1])
                for t, q in error_turns:
                    lines.append(f"    {t.turn_id[:32]:32s} q={q:.3f} len={t.conversation_length} err={t.error_category or 'other'}")

        h("Conversation Length")
        if cl.total_turns > 0:
            lines.append(f"  Range: min={cl.min_length} median={cl.median_length:.1f} p90={cl.p90_length:.1f} max={cl.max_length}")
            lines.append(f"  Long turns (>=4): {cl.n_long_successful} OK / {cl.n_long_failed} failed")
            lines.append("  Quality by bucket:")
            for b in cl.buckets:
                if b.n_turns > 0:
                    lines.append(f"    {b.label:10s} (len {b.min_length}-{b.max_length}): n={b.n_turns} qual={b.mean_quality:.3f} complete={b.task_completion_rate:.1%}")
            v("Conversation Evidence")
            if verbose:
                lengths = sorted(
                    [(t.turn_id, t.conversation_length, q)
                     for t, q in zip(self._turns, self._qualities)
                     if not t.is_heartbeat],
                    key=lambda x: x[1], reverse=True
                )
                lines.append("  Longest turns:")
                for tid, ln, q in lengths[:10]:
                    lines.append(f"    {tid[:32]:32s} len={ln:3d} q={q:.3f}")
                if len(lengths) > 20:
                    lines.append("  Shortest:")
                    for tid, ln, q in lengths[-5:]:
                        lines.append(f"    {tid[:32]:32s} len={ln:3d} q={q:.3f}")
        else:
            lines.append("  No turn data.")

        return "\n".join(lines)

    def render_verbose(self, result: ReportResult, loader) -> str:
        """Return detailed per-session, per-turn report."""
        lines: list[str] = []

        def h(title: str) -> None:
            lines.append(f"\n=== {title} ===")

        lines.append("=== TraceHound Session Detail ===")
        lines.append(f"Generated: {result.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        lines.append(f"Sessions loaded: {len(loader.raw_sessions)}")
        lines.append(f"Total turns: {result.data_health.total_turns}")

        h("Quick Summary")
        qt = result.quality_trends
        dh = result.data_health
        cl = result.conversation_length
        crp = result.correction_patterns
        tb = result.time_bottlenecks
        lines.append(f"  Mean quality: {qt.overall_mean:.3f}")
        lines.append(f"  Completed: {dh.total_turns - crp.total_corrected_turns}/{dh.total_turns} Corrections: {crp.total_corrected_turns}")
        if cl.total_turns > 0:
            lines.append(f"  Length range: {cl.min_length}-{cl.max_length} median={cl.median_length:.1f}")
        if tb.n_turns_with_timing > 0:
            lines.append(f"  Duration: median={tb.median_duration_s:.1f}s p90={tb.p90_duration_s:.1f}s total={tb.total_time_s:.0f}s")

        h("Session Details")
        for path, raw_messages in loader.raw_sessions.items():
            session_name = path.parent.name
            n_messages = len(raw_messages)
            by_req: dict[str, list[dict]] = {}
            for m in raw_messages:
                req = str(m.get("request_id", ""))
                if req:
                    by_req.setdefault(req, []).append(m)
            n_turns = len(by_req)
            lines.append(f"\n  [SESSION] {session_name}")
            lines.append(f"    Messages: {n_messages} Turns: {n_turns}")
            for req_id, messages in sorted(by_req.items(), key=lambda x: float(x[1][0].get("timestamp", 0))):
                messages.sort(key=lambda m: float(m.get("timestamp", 0)))
                user_msgs = [m for m in messages if m.get("role") == "user"]
                user_content = user_msgs[0].get("content", "") if user_msgs else ""
                user_preview = user_content[:180] + ("..." if len(user_content) > 180 else "")
                error_msgs = [m for m in messages if m.get("event_type") == "chat.error"]
                has_error = bool(error_msgs)
                error_text = ""
                if error_msgs:
                    err = error_msgs[0].get("error", "")
                    error_text = err[:180] + ("..." if len(err) > 180 else "")
                tools: list[str] = []
                for m in messages:
                    if m.get("event_type") == "chat.tool_call":
                        tc = m.get("tool_call") or {}
                        name = tc.get("name")
                        if name and name not in tools:
                            tools.append(name)
                final_content = ""
                for m in messages:
                    if m.get("role") == "assistant" and m.get("event_type") not in ("chat.tool_call", "chat.tool_update", "chat.usage_metadata", "chat.tool_result"):
                        c = m.get("content", "")
                        if c:
                            final_content = c[:180] + ("..." if len(c) > 180 else "")
                            break
                try:
                    t0 = float(messages[0].get("timestamp", 0))
                    t1 = float(messages[-1].get("timestamp", 0))
                    duration = f"{t1 - t0:.1f}s"
                except (ValueError, TypeError):
                    duration = "?"
                status = "ERROR" if has_error else ("OK" if final_content else "NO_CONTENT")
                lines.append(f"\n    Turn: {req_id[:28]} Status: {status} Duration: {duration} Msgs: {len(messages)}")
                lines.append(f"      User: {user_preview}")
                if tools:
                    lines.append(f"      Tools: {', '.join(tools)}")
                if has_error:
                    lines.append(f"      Error: {error_text}")
                if final_content and not has_error:
                    lines.append(f"      Result: {final_content}")
        lines.append("")
        return "\n".join(lines)
