# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ErrorsView — error category breakdown + user query analysis."""

from __future__ import annotations

import customtkinter as ctk

from analyzer_gui.widgets.mpl_frame import MplFrame
from analyzer_gui.widgets.sortable_table import SortableTable
from analyzer_gui.widgets.stat_card import StatCard


class ErrorsView(ctk.CTkFrame):
    """Three-tab view: Error Breakdown / Weekly Errors / User Queries."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Errors & User Queries", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        for name in ["Error Breakdown", "Weekly Errors", "User Queries"]:
            self._tabs.add(name)

        self._build_error_breakdown()
        self._build_weekly_errors()
        self._build_user_queries()

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_error_breakdown(self) -> None:
        tab = self._tabs.tab("Error Breakdown")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        # Stat cards
        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_err_rate = StatCard(cards, "Error Rate", height=70, width=150)
        self._c_recovery = StatCard(cards, "Recovery Rate", height=70, width=150)
        self._c_persistent = StatCard(cards, "Persistent Errors", height=70, width=200)
        for i, c in enumerate([self._c_err_rate, self._c_recovery, self._c_persistent]):
            c.grid(row=0, column=i, padx=6)

        self._err_table = SortableTable(
            tab,
            columns=["Category", "Count", "% of Errors", "Affected Sessions"],
            col_widths=[120, 70, 110, 140],
        )
        self._err_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    def _build_weekly_errors(self) -> None:
        tab = self._tabs.tab("Weekly Errors")
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)

        self._weekly_chart = MplFrame(tab, figsize=(9, 4))
        self._weekly_chart.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_user_queries(self) -> None:
        tab = self._tabs.tab("User Queries")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        # Stat cards row
        stats_row = ctk.CTkFrame(tab, fg_color="transparent")
        stats_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_qlen_min = StatCard(stats_row, "Min Length", height=70, width=110)
        self._c_qlen_med = StatCard(stats_row, "Median Length", height=70, width=120)
        self._c_qlen_p90 = StatCard(stats_row, "p90 Length", height=70, width=110)
        self._c_qlen_max = StatCard(stats_row, "Max Length", height=70, width=110)
        self._c_common_type = StatCard(stats_row, "Most Common Type", height=70, width=150)
        self._c_best_type = StatCard(stats_row, "Best Quality Type", height=70, width=160)
        for i, c in enumerate([
            self._c_qlen_min, self._c_qlen_med, self._c_qlen_p90,
            self._c_qlen_max, self._c_common_type, self._c_best_type,
        ]):
            c.grid(row=0, column=i, padx=4)

        # Correlation cards
        corr_row = ctk.CTkFrame(tab, fg_color="transparent")
        corr_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 4))
        ctk.CTkLabel(corr_row, text="Correlations:", font=("", 11)).pack(side="left", padx=4)
        self._corr_dur_lbl = ctk.CTkLabel(corr_row, text="Len vs Duration: —", font=("", 11))
        self._corr_dur_lbl.pack(side="left", padx=8)
        self._corr_tok_lbl = ctk.CTkLabel(corr_row, text="Len vs Tokens: —", font=("", 11))
        self._corr_tok_lbl.pack(side="left", padx=8)

        self._query_table = SortableTable(
            tab,
            columns=["Query Type", "Count", "Mean Quality", "Mean Duration(s)", "Mean Tokens"],
            col_widths=[120, 70, 120, 140, 120],
        )
        self._query_table.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self, result, *_) -> None:
        if result is None:
            return
        self._fill_error_breakdown(result.error_categories)
        self._draw_weekly_errors(result.error_categories)
        self._fill_user_queries(result.user_queries)

    # ------------------------------------------------------------------

    def _fill_error_breakdown(self, ec) -> None:
        self._c_err_rate.update(
            f"{ec.overall_error_rate:.1%}",
            StatCard.error_rate_color(ec.overall_error_rate),
        )
        self._c_recovery.update(f"{ec.recovery_rate:.1%}")
        persistent = ", ".join(ec.persistent_error_categories) or "none"
        self._c_persistent.update(persistent)

        rows = [
            [
                c.category,
                c.count,
                f"{c.percentage_of_errors:.1f}%",
                c.affected_sessions,
            ]
            for c in ec.categories
            if c.count > 0
        ]
        highlights = ["#6b1a1a" if r[1] > 0 else None for r in rows]
        self._err_table.set_data(rows, highlights)

    def _draw_weekly_errors(self, ec) -> None:
        weeks = ec.weekly_summaries
        if not weeks:
            return

        tags = [w.week_tag for w in weeks]
        error_counts = [w.error_count for w in weeks]
        total_turns = [w.total_turns for w in weeks]
        indices = list(range(len(weeks)))

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax2 = ax.twinx()

            ax.bar(indices, error_counts, color="#e74c3c", alpha=0.7, label="Errors")
            ax2.plot(indices, total_turns, color="#3498db", marker="o", linewidth=1.5,
                     label="Total turns")
            ax2.set_ylabel("Total Turns", color="#3498db", fontsize=9)
            ax2.tick_params(axis="y", colors="#3498db")

            ax.set_xticks(indices)
            ax.set_xticklabels(tags, rotation=30, ha="right", fontsize=8)
            ax.set_ylabel("Error Count")
            ax.set_title("Errors by Week")
            ax.legend(loc="upper left", fontsize=8)

        self._weekly_chart.redraw(_draw)

    def _fill_user_queries(self, uq) -> None:
        self._c_qlen_min.update(str(uq.length_min))
        self._c_qlen_med.update(f"{uq.length_median:.0f}")
        self._c_qlen_p90.update(f"{uq.length_p90:.0f}")
        self._c_qlen_max.update(str(uq.length_max))
        self._c_common_type.update(uq.most_common_type or "—")
        self._c_best_type.update(uq.best_quality_type or "—")

        self._corr_dur_lbl.configure(
            text=f"Len vs Duration: r={uq.length_vs_duration_correlation:.3f}"
        )
        self._corr_tok_lbl.configure(
            text=f"Len vs Tokens: r={uq.length_vs_tokens_correlation:.3f}"
        )

        rows = [
            [
                qt.type_label,
                qt.count,
                f"{qt.mean_quality:.4f}",
                f"{qt.mean_duration:.1f}",
                f"{qt.mean_tokens:.0f}",
            ]
            for qt in uq.query_type_distribution
        ]
        self._query_table.set_data(rows)
