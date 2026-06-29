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

from .analyzers.budget_waste import (
    BudgetWasteAnalyzer,
    BudgetWasteResult,
)
from .analyzers.component_interactions import (
    ComponentInteractionsAnalyzer,
    ComponentInteractionsResult,
)
from .analyzers.component_performance import (
    ComponentPerformanceAnalyzer,
    ComponentPerformanceResult,
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
from .analyzers.exploration_analysis import (
    ExplorationAnalyzer,
    ExplorationAnalysisResult,
)
from .analyzers.quality_trends import (
    QualityTrendsAnalyzer,
    QualityTrendsResult,
)
from .analyzers.signal_disagreement import (
    SignalDisagreementAnalyzer,
    SignalDisagreementResult,
)
from .analyzers.time_bottlenecks import (
    TimeBottlenecksAnalyzer,
    TimeBottlenecksResult,
)
from .loader import TrajectoriesLoader, TurnRecord
from .scorer import compute_qualities


@dataclass(frozen=True)
class ReportResult:
    generated_at: datetime
    data_health: DataHealthResult
    quality_trends: QualityTrendsResult
    component_performance: ComponentPerformanceResult
    budget_waste: BudgetWasteResult
    correction_patterns: CorrectionPatternsResult
    exploration: ExplorationAnalysisResult
    conversation_length: ConversationLengthResult
    signal_disagreement: SignalDisagreementResult
    component_interactions: ComponentInteractionsResult
    time_bottlenecks: TimeBottlenecksResult

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "data_health": self.data_health.to_dict(),
            "quality_trends": self.quality_trends.to_dict(),
            "component_performance": self.component_performance.to_dict(),
            "budget_waste": self.budget_waste.to_dict(),
            "correction_patterns": self.correction_patterns.to_dict(),
            "exploration": self.exploration.to_dict(),
            "conversation_length": self.conversation_length.to_dict(),
            "signal_disagreement": self.signal_disagreement.to_dict(),
            "component_interactions": self.component_interactions.to_dict(),
            "time_bottlenecks": self.time_bottlenecks.to_dict(),
        }


class TrajectoriesReport:
    """Run all analyzers over loaded turns and render results."""

    def __init__(
        self,
        loader: TrajectoriesLoader,
        quality_deficit_threshold: float = 0.15,
        utilization_threshold: float = 0.20,
        correction_lift_threshold: float = 1.5,
    ) -> None:
        self._loader = loader
        self._quality_deficit = quality_deficit_threshold
        self._utilization_threshold = utilization_threshold
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

        component_performance = ComponentPerformanceAnalyzer(
            turns,
            qualities,
            quality_deficit_threshold=self._quality_deficit,
        ).analyze()

        budget_waste = BudgetWasteAnalyzer(
            turns,
            qualities,
            utilization_threshold=self._utilization_threshold,
        ).analyze()

        correction_patterns = CorrectionPatternsAnalyzer(
            turns,
            lift_threshold=self._correction_lift,
        ).analyze()

        exploration = ExplorationAnalyzer(turns, qualities).analyze()

        conversation_length = ConversationLengthAnalyzer(turns, qualities).analyze()

        signal_disagreement = SignalDisagreementAnalyzer(turns).analyze()

        component_interactions = ComponentInteractionsAnalyzer(turns, qualities).analyze()

        time_bottlenecks = TimeBottlenecksAnalyzer(
            turns,
            qualities,
            tool_call_timings=self._loader.tool_call_timings,
        ).analyze()

        return ReportResult(
            generated_at=datetime.now(tz=timezone.utc),
            data_health=data_health,
            quality_trends=quality_trends,
            component_performance=component_performance,
            budget_waste=budget_waste,
            correction_patterns=correction_patterns,
            exploration=exploration,
            conversation_length=conversation_length,
            signal_disagreement=signal_disagreement,
            component_interactions=component_interactions,
            time_bottlenecks=time_bottlenecks,
        )

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def render_json(self, result: ReportResult) -> str:
        """Return machine-readable JSON."""
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    def render_text(self, result: ReportResult, verbose: bool = False) -> str:  # noqa: C901
        """Return a human-readable text report."""
        lines: list[str] = []

        def h(title: str) -> None:
            lines.append(f"\n--- {title} ---")

        def v(title: str) -> None:
            if verbose:
                lines.append(f"\n  >>> {title}")

        dh = result.data_health
        qt = result.quality_trends
        cp = result.component_performance
        bw = result.budget_waste
        crp = result.correction_patterns
        ex = result.exploration
        cl = result.conversation_length
        sd = result.signal_disagreement
        ci = result.component_interactions
        tb = result.time_bottlenecks

        lines.append("=== Trajectories Analyzer Report ===")
        lines.append(f"Generated: {result.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        if verbose:
            lines.append("Mode: VERBOSE (showing per-turn evidence and calculations)")
        lines.append("")

        # ------------------------------------------------------------------
        # Data health
        # ------------------------------------------------------------------
        h("Data Health")
        lines.append(f"  Total turns: {dh.total_turns}")
        if dh.date_range:
            lines.append(
                f"  Date range:  {dh.date_range[0].strftime('%Y-%m-%d')} → "
                f"{dh.date_range[1].strftime('%Y-%m-%d')}"
            )

        # For jiuwenswarm sessions all files are named "history.jsonl" — show
        # the count and the distinct session IDs instead of repeating the filename.
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
            lines.append(
                f"  Log files:   {n_log_files} ({', '.join(unique_names) or 'none'})"
            )

        lines.append(f"  Explicit rating coverage: {dh.explicit_rating_coverage:.1%}")
        lines.append(f"  LLM judge coverage:       {dh.llm_judge_coverage:.1%}")
        lines.append(f"  Skipped (malformed):      {dh.skipped_records}")
        if dh.weeks_with_low_data:
            lines.append(f"  Low-data weeks:  {', '.join(dh.weeks_with_low_data)}")
        else:
            lines.append("  Low-data weeks:  none")

        v("Data Health Evidence")
        if verbose and self._loader.raw_sessions:
            lines.append("  Per-session file details:")
            for path, msgs in self._loader.raw_sessions.items():
                sz = path.stat().st_size
                sz_str = f"{sz/1024:.1f} KB" if sz > 1024 else f"{sz} B"
                lines.append(f"    {path.parent.name}: {len(msgs)} messages, {sz_str}")
        elif verbose and dh.log_files_found:
            lines.append("  Per-log file details:")
            for fname in dh.log_files_found:
                lines.append(f"    {fname}")

        # ------------------------------------------------------------------
        # Quality trends
        # ------------------------------------------------------------------
        trend_arrow = {
            "improving": "↑ IMPROVING",
            "degrading": "↓ DEGRADING",
            "flat": "→ FLAT",
            "insufficient_data": "? INSUFFICIENT DATA",
        }.get(qt.trend_direction, qt.trend_direction)

        h(f"Quality Trend: {trend_arrow}")
        lines.append(f"  Overall mean quality: {qt.overall_mean:.3f}")
        if qt.best_week:
            best = next((w for w in qt.weeks if w.week_tag == qt.best_week), None)
            if best:
                lines.append(
                    f"  Best week:  {qt.best_week} (mean={best.mean_quality:.3f}, n={best.n_turns})"
                )
        if qt.worst_week:
            worst = next((w for w in qt.weeks if w.week_tag == qt.worst_week), None)
            if worst:
                lines.append(
                    f"  Worst week: {qt.worst_week} (mean={worst.mean_quality:.3f}, n={worst.n_turns})"
                )
        lines.append(f"  Per-week breakdown ({len(qt.weeks)} weeks):")
        for w in qt.weeks:
            lines.append(
                f"    {w.week_tag}: mean={w.mean_quality:.3f}  n={w.n_turns}"
                f"  +{w.n_explicit_positive}/-{w.n_explicit_negative} explicit"
                f"  completed={w.n_task_completed}  corrections={w.n_follow_up_corrections}"
            )

        v("Quality Evidence")
        if verbose and self._turns:
            turn_q = list(zip(self._turns, self._qualities))
            turn_q.sort(key=lambda x: x[1], reverse=True)
            lines.append("  Top 5 highest-quality turns:")
            for t, q in turn_q[:5]:
                status = "OK" if t.task_completed else ("ERR" if t.follow_up_correction else "?")
                lines.append(f"    {t.turn_id[:28]:28s}  q={q:.3f}  [{status}]  len={t.conversation_length}")
            lines.append("  Bottom 5 lowest-quality turns:")
            for t, q in turn_q[-5:]:
                status = "OK" if t.task_completed else ("ERR" if t.follow_up_correction else "?")
                lines.append(f"    {t.turn_id[:28]:28s}  q={q:.3f}  [{status}]  len={t.conversation_length}")
            lines.append(f"  Quality formula: 0.5 + 0.20*task_completed - 0.30*correction + max(0, 0.10 - 0.02*length)")
            lines.append(f"  (LLM judge score or explicit rating overrides the formula when available)")

        # ------------------------------------------------------------------
        # Time bottlenecks
        # ------------------------------------------------------------------
        h("Time Bottlenecks")
        if tb.n_turns_with_timing == 0:
            lines.append(
                f"  No timing data available ({tb.n_turns_total} turns total)."
            )
        else:
            lines.append(f"  Timed turns: {tb.n_turns_with_timing} / {tb.n_turns_total}")
            lines.append(
                f"  Duration:  min={tb.min_duration_s:.1f}s"
                f"  median={tb.median_duration_s:.1f}s"
                f"  mean={tb.mean_duration_s:.1f}s"
                f"  p90={tb.p90_duration_s:.1f}s"
                f"  max={tb.max_duration_s:.1f}s"
            )
            lines.append(
                f"  Total wall-clock time: {tb.total_time_s:.1f}s"
                f" ({tb.total_time_s / 60:.1f} min)"
            )

            verdict_label = {
                "slower_is_better": "slower turns have HIGHER quality (+delta)",
                "slower_is_worse":  "slower turns have LOWER quality (possible timeout/overload)",
                "no_correlation":   "no meaningful correlation between speed and quality",
            }.get(tb.speed_quality_verdict, tb.speed_quality_verdict)
            lines.append(
                f"  Speed/quality: {verdict_label}"
                f"  (slow_q={tb.slow_quartile_mean_quality:.3f}"
                f"  fast_q={tb.fast_half_mean_quality:.3f})"
            )

            if tb.slowest_turns:
                lines.append(f"  Slowest turns (top {len(tb.slowest_turns)}):")
                for rec in tb.slowest_turns:
                    status = "ERR" if rec.has_error else ("OK" if rec.task_completed else "?")
                    tools_str = ", ".join(rec.tools_called[:4])
                    if len(rec.tools_called) > 4:
                        tools_str += f" +{len(rec.tools_called) - 4}"
                    lines.append(
                        f"    {rec.turn_id[:28]:28s}  {rec.duration_seconds:7.1f}s"
                        f"  [{status}]  q={rec.quality:.3f}  msgs={rec.n_messages}"
                        + (f"  [{tools_str}]" if tools_str else "")
                    )

            if tb.tool_turn_correlation:
                lines.append(
                    f"  Tool turn-duration correlation"
                    f" ({len(tb.tool_turn_correlation)} tools, sorted by slowdown ratio):"
                )
                for tc in tb.tool_turn_correlation[:10]:
                    marker = " <-- SLOW" if tc.duration_ratio >= 1.5 else ""
                    lines.append(
                        f"    {tc.tool_name:30s}  ratio={tc.duration_ratio:.2f}x"
                        f"  mean={tc.mean_turn_duration_s:.1f}s  n={tc.n_turns}{marker}"
                    )

            if tb.tool_call_timing:
                lines.append(
                    f"  Per-tool call timing"
                    f" ({len(tb.tool_call_timing)} tools with timed calls, sorted by mean):"
                )
                for ts in tb.tool_call_timing[:10]:
                    lines.append(
                        f"    {ts.tool_name:30s}  mean={ts.mean_duration_s:.2f}s"
                        f"  median={ts.median_duration_s:.2f}s"
                        f"  p90={ts.p90_duration_s:.2f}s"
                        f"  max={ts.max_duration_s:.2f}s"
                        f"  n={ts.n_timed_calls}"
                        f"  total={ts.total_time_s:.1f}s"
                    )

            if tb.hourly_distribution:
                lines.append(
                    f"  Hourly activity (UTC) — {len(tb.hourly_distribution)} active hours:"
                )
                for hb in tb.hourly_distribution:
                    bar = "#" * min(hb.n_turns, 20)
                    lines.append(
                        f"    {hb.hour:02d}:00  {bar:<20s}  n={hb.n_turns:3d}"
                        f"  mean_q={hb.mean_quality:.3f}"
                        f"  mean_dur={hb.mean_duration_s:.1f}s"
                        f"  err={hb.error_rate:.0%}"
                    )

        # ------------------------------------------------------------------
        # Tool call frequency (always shown, not verbose-only)
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Component bottlenecks (with severity + type breakdown)
        # Note: empty for jiuwenswarm sessions — no skills/memory/tools config
        # in session format; only tool_calls are available.
        # ------------------------------------------------------------------
        n_flagged = len(cp.flagged_components)
        h(f"Component Bottlenecks ({n_flagged} flagged)")
        lines.append(f"  Global mean quality: {cp.global_mean_quality:.3f}")

        if cp.top_priority_fixes:
            lines.append(f"  Top priority fixes (by severity):")
            for c in cp.top_priority_fixes:
                flags_str = ", ".join(c.flags)
                lines.append(
                    f"    [{flags_str}] {c.component_type}: {c.name}"
                    f"  severity={c.severity_score:.2f}"
                    f"  quality={c.mean_quality:.3f}  n={c.n_turns_included}"
                )
        elif not cp.flagged_components:
            lines.append("  No bottleneck components detected.")
            if self._loader.source_type == "jiuwenswarm_sessions":
                lines.append(
                    "  (jiuwenswarm session logs do not carry skills/memory/tools context;"
                    " only tool_calls are available for analysis)"
                )

        if cp.flagged_components and len(cp.flagged_components) > len(cp.top_priority_fixes):
            lines.append(
                f"  (+ {len(cp.flagged_components) - len(cp.top_priority_fixes)} more flagged)"
            )

        if cp.type_breakdown:
            lines.append("  Context budget by type:")
            for tb_row in cp.type_breakdown:
                lines.append(
                    f"    {tb_row.component_type:8s}  {tb_row.n_components} components"
                    f"  budget={tb_row.budget_fraction:.1%}"
                    f"  quality={tb_row.mean_quality:.3f}"
                    f"  completion={tb_row.mean_task_completion:.1%}"
                    f"  flagged={tb_row.n_flagged}"
                )

        # ------------------------------------------------------------------
        # Budget waste
        # ------------------------------------------------------------------
        total_waste = (
            len(bw.never_used_skills)
            + len(bw.rarely_used_skills)
            + len(bw.never_used_tools)
            + len(bw.rarely_used_tools)
            + len(bw.potentially_wasteful_memory)
        )
        h(f"Budget Waste ({total_waste} items)")
        if bw.never_used_skills:
            lines.append(
                f"  Never-used skills ({len(bw.never_used_skills)}): {', '.join(bw.never_used_skills)}"
            )
        if bw.rarely_used_skills:
            for c in bw.rarely_used_skills:
                lines.append(
                    f"  Rarely-used skill: {c.name} "
                    f"(utilization={c.utilization_rate:.1%}, included={c.times_included},"
                    f" used={c.times_used})"
                )
        if bw.never_used_tools:
            lines.append(
                f"  Never-used tools ({len(bw.never_used_tools)}): {', '.join(bw.never_used_tools)}"
            )
        if bw.rarely_used_tools:
            for c in bw.rarely_used_tools:
                lines.append(
                    f"  Rarely-used tool: {c.name} "
                    f"(utilization={c.utilization_rate:.1%}, included={c.times_included},"
                    f" called={c.times_used})"
                )
        if bw.potentially_wasteful_memory:
            lines.append(
                f"  Wasteful memory ({len(bw.potentially_wasteful_memory)}): "
                f"{', '.join(bw.potentially_wasteful_memory)}"
            )
        if total_waste == 0:
            lines.append("  No budget waste detected.")
            if self._loader.source_type == "jiuwenswarm_sessions":
                lines.append(
                    "  (jiuwenswarm session logs do not carry context configuration;"
                    " budget analysis requires thalamus turn logs)"
                )

        # ------------------------------------------------------------------
        # Correction patterns
        # ------------------------------------------------------------------
        h("Correction Patterns")
        lines.append(
            f"  Baseline correction rate: {crp.baseline_correction_rate:.1%}  "
            f"({crp.total_corrected_turns}/{crp.total_turns} turns)"
        )
        if crp.high_lift_components:
            n_high_lift = len(crp.high_lift_components)
            lines.append(f"  High-lift patterns (top {min(5, n_high_lift)}):")
            for p in crp.high_lift_components[:5]:
                lines.append(
                    f"    {p.component_type}: {p.component}"
                    f"  correction={p.correction_rate:.1%}  lift={p.lift:.2f}×"
                    f"  n={p.n_turns_included}"
                )
        else:
            lines.append("  No high-lift correction patterns detected.")

        v("Correction Evidence")
        if verbose and self._turns:
            error_turns = [(t, q) for t, q in zip(self._turns, self._qualities) if t.follow_up_correction]
            if error_turns:
                lines.append(f"  All {len(error_turns)} error turns (sorted by quality):")
                error_turns.sort(key=lambda x: x[1])
                for t, q in error_turns:
                    lines.append(f"    {t.turn_id[:32]:32s}  q={q:.3f}  len={t.conversation_length}")

        # ------------------------------------------------------------------
        # Exploration
        # ------------------------------------------------------------------
        h("Exploration Analysis")
        lines.append(f"  Explored turns: {ex.n_explored} / {ex.n_explored + ex.n_normal}")
        if ex.n_explored > 0:
            delta_str = f"{ex.quality_delta:+.3f}"
            verdict = (
                "net beneficial"
                if ex.quality_delta > 0.02
                else ("net harmful" if ex.quality_delta < -0.02 else "net neutral")
            )
            lines.append(
                f"  Explored mean quality: {ex.mean_quality_explored:.3f}  "
                f"vs normal: {ex.mean_quality_normal:.3f}  "
                f"(delta={delta_str}, {verdict})"
            )
            if ex.promising_additions:
                lines.append(f"  Promising additions ({len(ex.promising_additions)}):")
                for a in ex.promising_additions[:3]:
                    lines.append(
                        f"    {a.component_type}: {a.name}  "
                        f"delta={a.mean_quality_delta:+.3f}  n={a.n_times_explored}"
                    )
            if ex.harmful_additions:
                lines.append(f"  Harmful additions ({len(ex.harmful_additions)}):")
                for a in ex.harmful_additions[:3]:
                    lines.append(
                        f"    {a.component_type}: {a.name}  "
                        f"delta={a.mean_quality_delta:+.3f}  n={a.n_times_explored}"
                    )
        else:
            lines.append("  No exploration turns found in loaded data.")

        # ------------------------------------------------------------------
        # Conversation length
        # ------------------------------------------------------------------
        h("Conversation Length")
        if cl.total_turns > 0:
            lines.append(
                f"  Length distribution: min={cl.min_length}  median={cl.median_length:.1f}"
                f"  p90={cl.p90_length:.1f}  max={cl.max_length}"
            )
            lines.append(
                f"  Long turns (>=4):  {cl.n_long_successful} successful"
                f"  / {cl.n_long_failed} failed"
            )
            lines.append("  Quality by length bucket:")
            for b in cl.buckets:
                if b.n_turns > 0:
                    lines.append(
                        f"    {b.label:10s} (len {b.min_length}-{'inf' if b.max_length > 100 else b.max_length}):"
                        f"  n={b.n_turns}  quality={b.mean_quality:.3f}"
                        f"  completion={b.task_completion_rate:.1%}"
                    )
            if cl.components_flagged_long:
                lines.append(
                    f"  Components inflating conversation length"
                    f" ({len(cl.components_flagged_long)}):"
                )
                for c in cl.components_flagged_long[:5]:
                    lines.append(
                        f"    {c.component_type}: {c.name}"
                        f"  median_len={c.median_length:.1f}  ratio={c.length_ratio:.2f}x"
                    )
            else:
                lines.append("  No components consistently inflate conversation length.")

            v("Conversation Length Evidence")
            if verbose and self._turns:
                lengths = [(t.turn_id, t.conversation_length, q) for t, q in zip(self._turns, self._qualities)]
                lengths.sort(key=lambda x: x[1], reverse=True)
                lines.append("  Longest turns (top 10):")
                for tid, ln, q in lengths[:10]:
                    lines.append(f"    {tid[:32]:32s}  len={ln:3d}  q={q:.3f}")
                if len(lengths) > 20:
                    lines.append("  ...")
                    lines.append("  Shortest turns (bottom 5):")
                    for tid, ln, q in lengths[-5:]:
                        lines.append(f"    {tid[:32]:32s}  len={ln:3d}  q={q:.3f}")
        else:
            lines.append("  No turn data.")

        # ------------------------------------------------------------------
        # Signal disagreement
        # ------------------------------------------------------------------
        h("Signal Disagreement (formula vs explicit rating)")
        if sd.n_rated_turns == 0:
            lines.append("  No explicitly rated turns to compare.")
        else:
            lines.append(
                f"  Rated turns: {sd.n_rated_turns}  "
                f"disagreements: {sd.n_disagreements} ({sd.disagreement_rate:.1%})"
            )
            lines.append(
                f"  Over-optimistic formula: {sd.n_over_optimistic}"
                f"  (formula says OK, user said NO)"
            )
            lines.append(
                f"  Over-pessimistic formula: {sd.n_over_pessimistic}"
                f"  (formula says BAD, user said OK)"
            )
            if sd.worst_disagreements:
                lines.append(f"  Worst disagreements (top {min(3, len(sd.worst_disagreements))}):")
                for d in sd.worst_disagreements[:3]:
                    lines.append(
                        f"    {d.turn_id[:16]}...  explicit={d.explicit_rating}"
                        f"  formula={d.formula_score:.2f}  delta={d.delta:.2f}"
                        f"  [{d.disagreement_type}]"
                    )
            if sd.components_by_disagreement_rate:
                lines.append("  Most disagreement-prone components (top 3):")
                for c in sd.components_by_disagreement_rate[:3]:
                    lines.append(
                        f"    {c.component_type}: {c.name}"
                        f"  disagree_rate={c.disagreement_rate:.1%}"
                        f"  ({c.n_disagreement_turns}/{c.n_turns_with_rating})"
                    )

        # ------------------------------------------------------------------
        # Component interactions
        # ------------------------------------------------------------------
        n_toxic = len(ci.toxic_pairs)
        n_synergy = len(ci.synergistic_pairs)
        h(f"Component Interactions ({ci.n_pairs_evaluated} pairs evaluated)")
        if ci.n_pairs_evaluated == 0:
            lines.append("  Not enough co-occurrence data to evaluate pairs.")
        else:
            if ci.toxic_pairs:
                lines.append(f"  Toxic combinations ({n_toxic}) -- avoid pairing these:")
                for p in ci.toxic_pairs[:3]:
                    lines.append(
                        f"    {p.type_a}:{p.component_a}  +  {p.type_b}:{p.component_b}"
                        f"  expected={p.expected_quality:.3f}  actual={p.actual_quality:.3f}"
                        f"  delta={p.interaction_delta:+.3f}  n={p.n_cooccurrence}"
                    )
                if n_toxic > 3:
                    lines.append(f"    (+ {n_toxic - 3} more toxic pairs)")
            else:
                lines.append("  No toxic combinations detected.")

            if ci.synergistic_pairs:
                lines.append(f"  Synergistic combinations ({n_synergy}) -- these work well together:")
                for p in ci.synergistic_pairs[:3]:
                    lines.append(
                        f"    {p.type_a}:{p.component_a}  +  {p.type_b}:{p.component_b}"
                        f"  expected={p.expected_quality:.3f}  actual={p.actual_quality:.3f}"
                        f"  delta={p.interaction_delta:+.3f}  n={p.n_cooccurrence}"
                    )
            else:
                lines.append("  No synergistic combinations detected.")

        return "\n".join(lines)

    def render_verbose(self, result: ReportResult, loader) -> str:
        """Return a detailed per-session, per-turn report showing actual trajectory content."""
        lines: list[str] = []

        def h(title: str) -> None:
            lines.append(f"\n=== {title} ===")

        lines.append("=== TraceHound Session Detail ===")
        lines.append(f"Generated: {result.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        lines.append(f"Source type: {loader.source_type}")
        lines.append(f"Sessions loaded: {len(loader.raw_sessions)}")
        lines.append(f"Total turns: {result.data_health.total_turns}")

        # Quick summary
        h("Quick Summary")
        qt = result.quality_trends
        dh = result.data_health
        cl = result.conversation_length
        crp = result.correction_patterns
        tb = result.time_bottlenecks
        lines.append(f"  Mean quality: {qt.overall_mean:.3f}")
        lines.append(
            f"  Completed: {dh.total_turns - crp.total_corrected_turns}/{dh.total_turns}"
            f"   Corrections: {crp.total_corrected_turns}"
        )
        if cl.total_turns > 0:
            lines.append(
                f"  Length range: {cl.min_length}-{cl.max_length}   median={cl.median_length:.1f}"
            )
        if tb.n_turns_with_timing > 0:
            lines.append(
                f"  Duration: median={tb.median_duration_s:.1f}s"
                f"  p90={tb.p90_duration_s:.1f}s"
                f"  total={tb.total_time_s:.0f}s ({tb.total_time_s / 60:.1f} min)"
            )

        # Per-session detail
        h("Session Details")
        for path, raw_messages in loader.raw_sessions.items():
            session_name = path.parent.name
            n_messages = len(raw_messages)

            # Group by request_id
            by_req: dict[str, list[dict]] = {}
            for m in raw_messages:
                req = str(m.get("request_id", ""))
                if req:
                    by_req.setdefault(req, []).append(m)

            n_turns = len(by_req)
            lines.append(f"\n  [SESSION] {session_name}")
            lines.append(f"    File: {path}")
            lines.append(f"    Messages: {n_messages}   Turns: {n_turns}")

            for req_id, messages in sorted(
                by_req.items(), key=lambda x: float(x[1][0].get("timestamp", 0))
            ):
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
                    if m.get("role") == "assistant" and m.get("event_type") not in (
                        "chat.tool_call",
                        "chat.tool_update",
                        "chat.usage_metadata",
                        "chat.tool_result",
                    ):
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
                lines.append(
                    f"\n    Turn: {req_id[:28]}   Status: {status}"
                    f"   Duration: {duration}   Msgs: {len(messages)}"
                )
                lines.append(f"      User: {user_preview}")
                if tools:
                    lines.append(f"      Tools: {', '.join(tools)}")
                if has_error:
                    lines.append(f"      Error: {error_text}")
                if final_content and not has_error:
                    lines.append(f"      Result: {final_content}")

        lines.append("")
        return "\n".join(lines)
