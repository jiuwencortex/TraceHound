# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TimingView — turn duration analysis with tabbed detail panels."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from analyzer_gui.widgets.mpl_frame import MplFrame
from analyzer_gui.widgets.sortable_table import SortableTable
from analyzer_gui.widgets.stat_card import StatCard


def _short(text: str, n: int = 50) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + "…" if len(text) > n else text


class TimingView(ctk.CTkFrame):
    """Duration histogram, stat cards, and four detail tabs."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._navigate_callback: Callable[[str, str], None] | None = None
        self._turn_lookup: dict[str, Any] = {}

        ctk.CTkLabel(self, text="Time Bottlenecks", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        # Main split: left histogram, right tabs
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)

        # Left column
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=0)
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        # Stat cards
        cards = ctk.CTkFrame(left, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._c_min   = StatCard(cards, "Min",    height=70, width=90)
        self._c_med   = StatCard(cards, "Median", height=70, width=90)
        self._c_p90   = StatCard(cards, "p90",    height=70, width=90)
        self._c_max   = StatCard(cards, "Max",    height=70, width=90)
        self._c_total = StatCard(cards, "Total",  height=70, width=100)
        for i, c in enumerate([self._c_min, self._c_med, self._c_p90,
                                self._c_max, self._c_total]):
            c.grid(row=0, column=i, padx=3)

        # Clarification note
        ctk.CTkLabel(
            left,
            text="Duration = per-request latency only (send→response).\n"
                 "Idle time between turns is not counted.",
            font=("", 9), text_color="gray50", justify="left", anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 4))

        self._histogram = MplFrame(left, figsize=(5, 3.5))
        self._histogram.grid(row=2, column=0, sticky="nsew")

        self._verdict_lbl = ctk.CTkLabel(left, text="", font=("", 11))
        self._verdict_lbl.grid(row=3, column=0, pady=(4, 0))

        # Right column: tabs
        self._tabs = ctk.CTkTabview(body)
        self._tabs.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=0)

        for tab_name in ["Slowest Turns", "Tool Turn Corr.", "Per-Tool Timing", "Hourly Dist."]:
            self._tabs.add(tab_name)

        # Slowest turns — query-first layout, clickable
        slow_tab = self._tabs.tab("Slowest Turns")
        slow_tab.rowconfigure(1, weight=1)
        slow_tab.columnconfigure(0, weight=1)
        hint = ctk.CTkLabel(
            slow_tab,
            text="Click a row to jump to that turn in Sessions →",
            font=("", 10), text_color="gray55",
        )
        hint.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))
        self._slow_table = SortableTable(
            slow_tab,
            columns=["Query", "Session", "Status", "Duration(s)", "Tools", "Request ID"],
            col_widths=[200, 120, 60, 90, 130, 160],
        )
        self._slow_table.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        # Tool turn correlation
        self._tool_corr_table = SortableTable(
            self._tabs.tab("Tool Turn Corr."),
            columns=["Tool", "Turns", "Mean Dur(s)", "Global(s)", "Ratio"],
            col_widths=[160, 60, 100, 80, 70],
        )
        self._tool_corr_table.pack(fill="both", expand=True, padx=4, pady=4)

        # Per-tool call timing
        self._call_timing_table = SortableTable(
            self._tabs.tab("Per-Tool Timing"),
            columns=["Tool", "Calls", "Mean(s)", "Median(s)", "p90(s)", "Max(s)", "Total(s)"],
            col_widths=[160, 60, 80, 80, 80, 80, 80],
        )
        self._call_timing_table.pack(fill="both", expand=True, padx=4, pady=4)

        # Hourly distribution chart
        self._hourly_chart = MplFrame(
            self._tabs.tab("Hourly Dist."), figsize=(6, 3.5)
        )
        self._hourly_chart.pack(fill="both", expand=True, padx=4, pady=4)

        self._no_data_lbl = ctk.CTkLabel(
            self, text="No timing data available.", font=("", 14), text_color="gray60"
        )

    # ── Public ───────────────────────────────────────────────────────────────

    def set_navigate_callback(self, cb: Callable[[str, str], None]) -> None:
        self._navigate_callback = cb
        self._slow_table.bind_row_click(self._on_slow_row_click)

    # ── Refresh ──────────────────────────────────────────────────────────────

    def refresh(self, result, loader=None, reporter=None, *_) -> None:
        if result is None:
            return

        # Build turn lookup for cross-referencing
        self._turn_lookup = {}
        if reporter is not None:
            for t in getattr(reporter, "_turns", []):
                self._turn_lookup[t.turn_id] = t

        tb = result.time_bottlenecks

        if tb.n_turns_with_timing == 0:
            self._no_data_lbl.place(relx=0.5, rely=0.5, anchor="center")
            return
        self._no_data_lbl.place_forget()

        self._c_min.update(f"{tb.min_duration_s:.1f}s")
        self._c_med.update(f"{tb.median_duration_s:.1f}s")
        self._c_p90.update(f"{tb.p90_duration_s:.1f}s",
                           StatCard.error_rate_color(min(tb.p90_duration_s / 30, 1.0)))
        self._c_max.update(f"{tb.max_duration_s:.1f}s")
        total_min = tb.total_time_s / 60
        self._c_total.update(f"{total_min:.1f}min")

        verdict_map = {
            "slower_is_worse":  ("Slower = worse quality",        "#e74c3c"),
            "slower_is_better": ("Slower = better quality",       "#2ecc71"),
            "no_correlation":   ("No speed/quality correlation",  "#95a5a6"),
        }
        vtext, vcol = verdict_map.get(tb.speed_quality_verdict,
                                      (tb.speed_quality_verdict, "gray"))
        self._verdict_lbl.configure(text=vtext, text_color=vcol)

        self._draw_histogram(tb)
        self._fill_slow_table(tb)
        self._fill_corr_table(tb)
        self._fill_timing_table(tb)
        self._draw_hourly_chart(tb)

    # ── Internals ────────────────────────────────────────────────────────────

    def _draw_histogram(self, tb) -> None:
        med = tb.median_duration_s
        p90 = tb.p90_duration_s

        def _draw(fig):
            ax = fig.add_subplot(111)
            durations = [t.duration_seconds for t in tb.slowest_turns]
            if not durations:
                ax.text(0.5, 0.5, "No per-turn data", transform=ax.transAxes, ha="center")
                return
            ax.hist(durations, bins=min(20, len(durations)), color="#3498db", alpha=0.7)
            ax.axvline(med, linestyle="--", color="orange", label=f"median {med:.1f}s")
            ax.axvline(p90, linestyle=":", color="red",    label=f"p90 {p90:.1f}s")
            ax.set_xlabel("Duration (s)")
            ax.set_ylabel("Turns")
            ax.set_title("Turn Duration Distribution")
            ax.legend(fontsize=8)

        self._histogram.redraw(_draw)

    def _fill_slow_table(self, tb) -> None:
        rows = []
        highlights = []
        tags = []

        for t in tb.slowest_turns:
            rec = self._turn_lookup.get(t.turn_id)
            query   = _short(rec.user_query  if rec else "", 50) or f"turn {t.turn_id[:20]}"
            session = _short((rec.session_title or rec.session_id) if rec else "", 22)
            sid     = rec.session_id if rec else ""
            status  = "ERR" if t.has_error else ("OK" if t.task_completed else "INC")
            tools   = ", ".join(t.tools_called[:3])
            if len(t.tools_called) > 3:
                tools += "…"

            rows.append([
                query,
                session,
                status,
                f"{t.duration_seconds:.1f}",
                tools,
                t.turn_id,
            ])
            highlights.append("#6b1a1a" if t.has_error else None)
            tags.append((sid, t.turn_id))

        self._slow_table.set_data(rows, highlights, row_tags=tags)

    def _on_slow_row_click(self, row_data: list, tag) -> None:
        if self._navigate_callback and tag:
            session_id, turn_id = tag
            self._navigate_callback(session_id, turn_id)

    def _fill_corr_table(self, tb) -> None:
        rows = []
        highlights = []
        for tc in tb.tool_turn_correlation:
            rows.append([
                tc.tool_name,
                tc.n_turns,
                f"{tc.mean_turn_duration_s:.1f}",
                f"{tc.global_mean_duration_s:.1f}",
                f"{tc.duration_ratio:.2f}x",
            ])
            highlights.append("#6b1a1a" if tc.duration_ratio >= 1.5 else None)
        self._tool_corr_table.set_data(rows, highlights)

    def _fill_timing_table(self, tb) -> None:
        rows = [
            [
                tc.tool_name,
                tc.n_timed_calls,
                f"{tc.mean_duration_s:.2f}",
                f"{tc.median_duration_s:.2f}",
                f"{tc.p90_duration_s:.2f}",
                f"{tc.max_duration_s:.2f}",
                f"{tc.total_time_s:.1f}",
            ]
            for tc in tb.tool_call_timing
        ]
        self._call_timing_table.set_data(rows)

    def _draw_hourly_chart(self, tb) -> None:
        hours_data = tb.hourly_distribution
        if not hours_data:
            return

        hours     = [h.hour for h in hours_data]
        counts    = [h.n_turns for h in hours_data]
        qualities = [h.mean_quality for h in hours_data]

        def _color(q):
            if q >= 0.70: return "#2ecc71"
            if q >= 0.50: return "#f39c12"
            return "#e74c3c"

        colors = [_color(q) for q in qualities]

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax.bar(hours, counts, color=colors)
            ax.set_xlabel("Hour (UTC)")
            ax.set_ylabel("Turns")
            ax.set_title("Activity by Hour")
            ax.set_xticks(range(0, 24, 2))

        self._hourly_chart.redraw(_draw)
