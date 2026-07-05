# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ErrorsView — error category breakdown + individual error turns + user queries."""

from __future__ import annotations

import datetime
from typing import Any, Callable

import customtkinter as ctk

from analyzer_gui.widgets.mpl_frame import MplFrame
from analyzer_gui.widgets.sortable_table import SortableTable
from analyzer_gui.widgets.stat_card import StatCard


def _short(text: str, n: int = 55) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + "…" if len(text) > n else text


def _fmt_ts(ts) -> str:
    if ts is None:
        return ""
    if isinstance(ts, datetime.datetime):
        return ts.strftime("%m-%d %H:%M:%S")
    try:
        return datetime.datetime.fromtimestamp(float(ts),
               tz=datetime.timezone.utc).strftime("%m-%d %H:%M:%S")
    except Exception:
        return ""


class ErrorsView(ctk.CTkFrame):
    """Four-tab view: Error Summary / Error Turns / Weekly Errors / User Queries."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._navigate_callback: Callable[[str, str], None] | None = None

        ctk.CTkLabel(self, text="Errors & User Queries", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        for name in ["Error Summary", "Error Turns", "Weekly Errors", "User Queries"]:
            self._tabs.add(name)

        self._build_error_summary()
        self._build_error_turns()
        self._build_weekly_errors()
        self._build_user_queries()

    # ── Public ───────────────────────────────────────────────────────────────

    def set_navigate_callback(self, cb: Callable[[str, str], None]) -> None:
        """Register a callback(session_id, turn_id) that jumps to the Sessions tab."""
        self._navigate_callback = cb
        # Wire up to the error-turns table
        self._err_turns_table.bind_row_click(self._on_turn_row_click)

    # ── Tab builders ─────────────────────────────────────────────────────────

    def _build_error_summary(self) -> None:
        tab = self._tabs.tab("Error Summary")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_err_rate   = StatCard(cards, "Error Rate",        height=80, width=150)
        self._c_recovery   = StatCard(cards, "Recovery Rate",     height=80, width=150)
        self._c_persistent = StatCard(cards, "Persistent Errors", height=80, width=220)
        for i, c in enumerate([self._c_err_rate, self._c_recovery, self._c_persistent]):
            c.grid(row=0, column=i, padx=6)

        self._err_table = SortableTable(
            tab,
            columns=["Category", "Count", "% of Errors", "Affected Sessions", "Example Query"],
            col_widths=[120, 60, 100, 130, 220],
        )
        self._err_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    def _build_error_turns(self) -> None:
        tab = self._tabs.tab("Error Turns")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        hint = ctk.CTkLabel(
            tab,
            text="Click any row to jump to that turn in Sessions →",
            font=("", 11), text_color="gray60",
        )
        hint.grid(row=0, column=0, sticky="w", padx=12, pady=(6, 2))

        self._err_turns_table = SortableTable(
            tab,
            columns=["Time", "Session", "Session ID", "Request ID", "Query", "Category", "Error"],
            col_widths=[110, 120, 160, 160, 200, 100, 220],
        )
        self._err_turns_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _build_weekly_errors(self) -> None:
        tab = self._tabs.tab("Weekly Errors")
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)

        self._weekly_chart = MplFrame(tab, figsize=(9, 4))
        self._weekly_chart.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_user_queries(self) -> None:
        tab = self._tabs.tab("User Queries")
        tab.rowconfigure(2, weight=1)
        tab.columnconfigure(0, weight=1)

        stats_row = ctk.CTkFrame(tab, fg_color="transparent")
        stats_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_qlen_min  = StatCard(stats_row, "Min Length",        height=80, width=110)
        self._c_qlen_med  = StatCard(stats_row, "Median Length",     height=80, width=120)
        self._c_qlen_p90  = StatCard(stats_row, "p90 Length",        height=80, width=110)
        self._c_qlen_max  = StatCard(stats_row, "Max Length",        height=80, width=110)
        self._c_common_type = StatCard(stats_row, "Most Common Type",height=80, width=150)
        self._c_best_type   = StatCard(stats_row, "Best Quality Type",height=80,width=160)
        for i, c in enumerate([
            self._c_qlen_min, self._c_qlen_med, self._c_qlen_p90,
            self._c_qlen_max, self._c_common_type, self._c_best_type,
        ]):
            c.grid(row=0, column=i, padx=4)

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

    # ── Refresh ──────────────────────────────────────────────────────────────

    def refresh(self, result, loader=None, reporter=None, *_) -> None:
        if result is None:
            return

        # Build per-category example-query lookup from TurnRecord objects
        turns: list[Any] = []
        cat_examples: dict[str, str] = {}
        if reporter is not None:
            turns = getattr(reporter, "_turns", [])
            for t in turns:
                if t.error_category and t.error_category not in cat_examples:
                    cat_examples[t.error_category] = t.user_query or ""

        self._fill_error_summary(result.error_categories, cat_examples)
        self._draw_weekly_errors(result.error_categories)
        self._fill_user_queries(result.user_queries)
        self._fill_error_turns(turns)

    # ── Fill helpers ─────────────────────────────────────────────────────────

    def _fill_error_summary(self, ec, cat_examples: dict[str, str] | None = None) -> None:
        cat_examples = cat_examples or {}
        self._c_err_rate.update(
            f"{ec.overall_error_rate:.1%}",
            StatCard.error_rate_color(ec.overall_error_rate),
        )
        self._c_recovery.update(f"{ec.recovery_rate:.1%}")
        persistent = ", ".join(ec.persistent_error_categories) or "none"
        self._c_persistent.update(persistent)

        rows = []
        for c in ec.categories:
            if c.count == 0:
                continue
            example_q = _short(cat_examples.get(c.category, ""), 55)
            rows.append([
                c.category,
                c.count,
                f"{c.percentage_of_errors:.1f}%",
                c.affected_sessions,
                example_q if example_q else "—",
            ])
        highlights = ["#6b1a1a" if r[1] > 0 else None for r in rows]
        self._err_table.set_data(rows, highlights)

    def _fill_error_turns(self, turns: list) -> None:
        """Populate the Error Turns tab from TurnRecord objects."""
        error_turns = [
            t for t in turns
            if (t.error_text or t.error_category) and not t.is_heartbeat
        ]
        # Sort newest-first
        error_turns.sort(key=lambda t: t.timestamp, reverse=True)

        rows = []
        tags = []  # (session_id, turn_id) tuples for navigation
        highlights = []

        for t in error_turns:
            ts_str = _fmt_ts(t.timestamp)
            title  = (t.session_title or t.session_id or "")[:22]
            sid    = t.session_id
            rid    = t.turn_id
            query  = _short(t.user_query, 50)
            cat    = t.error_category or "unknown"
            err    = _short(t.error_text, 60)

            rows.append([ts_str, title, sid, rid, query, cat, err])
            tags.append((sid, rid))
            highlights.append("#6b1a1a")

        self._err_turns_table.set_data(rows, highlights, row_tags=tags)

    def _on_turn_row_click(self, row_data: list, tag) -> None:
        if self._navigate_callback and tag:
            session_id, turn_id = tag
            self._navigate_callback(session_id, turn_id)

    def _draw_weekly_errors(self, ec) -> None:
        weeks = ec.weekly_summaries
        if not weeks:
            return

        tags         = [w.week_tag for w in weeks]
        error_counts = [w.error_count for w in weeks]
        total_turns  = [w.total_turns for w in weeks]
        indices      = list(range(len(weeks)))

        def _draw(fig):
            ax  = fig.add_subplot(111)
            ax2 = ax.twinx()
            ax.bar(indices, error_counts, color="#e74c3c", alpha=0.7, label="Errors")
            ax2.plot(indices, total_turns, color="#3498db", marker="o",
                     linewidth=1.5, label="Total turns")
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
