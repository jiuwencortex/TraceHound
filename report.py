# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TrajectoriesReport: orchestrates all analyzers and renders output.

Usage::

    from jiuwenswarm.trajectories_analyzer.report import TrajectoriesReport
    from jiuwenswarm.trajectories_analyzer.loader import TrajectoriesLoader

    loader = TrajectoriesLoader("/path/to/online_logs", max_weeks=8)
    report = TrajectoriesReport(loader)
    result = report.run()
    print(report.render_text(result))
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from analyzers.budget_waste import (
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
from loader import TrajectoriesLoader
from scorer import compute_qualities


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

    def run(self) -> ReportResult:
        """Load turns and run all analyzers."""
        turns = self._loader.load()
        qualities = compute_qualities(turns)
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
        )

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def render_json(self, result: ReportResult) -> str:
        """Return machine-readable JSON."""
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    def render_text(self, result: ReportResult) -> str:  # noqa: C901
        """Return a human-readable text report."""
        lines: list[str] = []

        def h(title: str) -> None:
            lines.append(f"\n--- {title} ---")

        dh = result.data_health
        qt = result.quality_trends
        cp = result.component_performance
        bw = result.budget_waste
        crp = result.correction_patterns
        ex = result.exploration
        cl = result.conversation_length
        sd = result.signal_disagreement
        ci = result.component_interactions

        lines.append("=== Trajectories Analyzer Report ===")
        lines.append(f"Generated: {result.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")

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
        lines.append(
            f"  Log files:   {len(dh.log_files_found)} ({', '.join(dh.log_files_found) or 'none'})"
        )
        lines.append(f"  Explicit rating coverage: {dh.explicit_rating_coverage:.1%}")
        lines.append(f"  LLM judge coverage:       {dh.llm_judge_coverage:.1%}")
        lines.append(f"  Skipped (malformed):      {dh.skipped_records}")
        if dh.weeks_with_low_data:
            lines.append(f"  Low-data weeks:  {', '.join(dh.weeks_with_low_data)}")
        else:
            lines.append("  Low-data weeks:  none")

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

        # ------------------------------------------------------------------
        # Component bottlenecks (with severity + type breakdown)
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

        if cp.flagged_components and len(cp.flagged_components) > len(cp.top_priority_fixes):
            lines.append(
                f"  (+ {len(cp.flagged_components) - len(cp.top_priority_fixes)} more flagged)"
            )

        if cp.type_breakdown:
            lines.append("  Context budget by type:")
            for tb in cp.type_breakdown:
                lines.append(
                    f"    {tb.component_type:8s}  {tb.n_components} components"
                    f"  budget={tb.budget_fraction:.1%}"
                    f"  quality={tb.mean_quality:.3f}"
                    f"  completion={tb.mean_task_completion:.1%}"
                    f"  flagged={tb.n_flagged}"
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

        # ------------------------------------------------------------------
        # Correction patterns
        # ------------------------------------------------------------------
        h(f"Correction Patterns (top {min(5, len(crp.high_lift_components))})")
        lines.append(
            f"  Baseline correction rate: {crp.baseline_correction_rate:.1%}  "
            f"({crp.total_corrected_turns}/{crp.total_turns} turns)"
        )
        if crp.high_lift_components:
            for p in crp.high_lift_components[:5]:
                lines.append(
                    f"  {p.component_type}: {p.component}"
                    f"  correction={p.correction_rate:.1%}  lift={p.lift:.2f}×"
                    f"  n={p.n_turns_included}"
                )
        else:
            lines.append("  No high-lift correction patterns detected.")

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
                f"  Long turns (≥4):  {cl.n_long_successful} successful"
                f"  / {cl.n_long_failed} failed"
            )
            lines.append("  Quality by length bucket:")
            for b in cl.buckets:
                if b.n_turns > 0:
                    lines.append(
                        f"    {b.label:10s} (len {b.min_length}–{'∞' if b.max_length > 100 else b.max_length}):"
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
                        f"  median_len={c.median_length:.1f}  ratio={c.length_ratio:.2f}×"
                    )
            else:
                lines.append("  No components consistently inflate conversation length.")
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
                        f"    {d.turn_id[:16]}…  explicit={d.explicit_rating}"
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
                lines.append(f"  Toxic combinations ({n_toxic}) — avoid pairing these:")
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
                lines.append(f"  Synergistic combinations ({n_synergy}) — these work well together:")
                for p in ci.synergistic_pairs[:3]:
                    lines.append(
                        f"    {p.type_a}:{p.component_a}  +  {p.type_b}:{p.component_b}"
                        f"  expected={p.expected_quality:.3f}  actual={p.actual_quality:.3f}"
                        f"  delta={p.interaction_delta:+.3f}  n={p.n_cooccurrence}"
                    )
            else:
                lines.append("  No synergistic combinations detected.")

        return "\n".join(lines)
