# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TokensView — token usage, LLM latency, tool success, content delivery."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from analyzer_gui.widgets.mpl_frame import MplFrame
from analyzer_gui.widgets.sortable_table import SortableTable
from analyzer_gui.widgets.stat_card import (
    COLOR_BAD, COLOR_GOOD, COLOR_NEUTRAL, COLOR_WARN, StatCard,
)


def _short(text: str, n: int = 48) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + "…" if len(text) > n else text


class TokensView(ctk.CTkFrame):
    """Four-tab view: Token Usage / LLM Latency / Tool Success / Content Delivery."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._navigate_callback: Callable[[str, str], None] | None = None
        self._turn_lookup: dict[str, Any] = {}

        ctk.CTkLabel(self, text="Tokens & LLM Performance", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        for name in ["Token Usage", "LLM Latency", "Tool Success", "Content Delivery"]:
            self._tabs.add(name)

        self._build_token_usage()
        self._build_llm_latency()
        self._build_tool_success()
        self._build_content_delivery()

    # ── Public ───────────────────────────────────────────────────────────────

    def set_navigate_callback(self, cb: Callable[[str, str], None]) -> None:
        self._navigate_callback = cb
        self._llm_slow_table.bind_row_click(self._on_llm_row_click)

    # ── Tab builders ─────────────────────────────────────────────────────────

    def _build_token_usage(self) -> None:
        tab = self._tabs.tab("Token Usage")
        tab.rowconfigure(2, weight=1)
        tab.columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_total_tok = StatCard(cards, "Total Tokens",      height=80, width=140)
        self._c_avg_tok   = StatCard(cards, "Avg/Turn",          height=80, width=130)
        self._c_ctx       = StatCard(cards, "Avg Context%",      height=80, width=130)
        self._c_near      = StatCard(cards, "Near-Limit Turns",  height=80, width=140)
        self._c_cost      = StatCard(cards, "Est. Cost",         height=80, width=120)
        for i, c in enumerate([self._c_total_tok, self._c_avg_tok,
                                self._c_ctx, self._c_near, self._c_cost]):
            c.grid(row=0, column=i, padx=4)

        self._token_model_table = SortableTable(
            tab,
            columns=["Model", "Turns", "Total Tokens", "Avg Tokens", "Avg Context%", "Est. Cost"],
            col_widths=[180, 60, 120, 110, 120, 100],
        )
        self._token_model_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))

        self._token_chart = MplFrame(tab, figsize=(9, 3))
        self._token_chart.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _build_llm_latency(self) -> None:
        tab = self._tabs.tab("LLM Latency")
        tab.rowconfigure(2, weight=1)
        tab.columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_lat_med    = StatCard(cards, "Median Latency",     height=80, width=140)
        self._c_lat_p90    = StatCard(cards, "p90 Latency",        height=80, width=130)
        self._c_tps        = StatCard(cards, "Throughput tok/s",   height=80, width=150)
        self._c_slow_prompt= StatCard(cards, "Slow Prompts (>5s)", height=80, width=150)
        self._c_slow_gen   = StatCard(cards, "Slow Gen (>100ms)",  height=80, width=150)
        for i, c in enumerate([self._c_lat_med, self._c_lat_p90, self._c_tps,
                                self._c_slow_prompt, self._c_slow_gen]):
            c.grid(row=0, column=i, padx=4)

        hint = ctk.CTkLabel(
            tab,
            text="Click a row to jump to that turn in Sessions →",
            font=("", 10), text_color="gray55",
        )
        hint.grid(row=1, column=0, sticky="w", padx=10, pady=(2, 0))

        self._llm_slow_table = SortableTable(
            tab,
            columns=["Query", "Session", "Latency(ms)", "TTFT(ms)", "TPOT(ms)",
                     "Model", "Status", "Request ID"],
            col_widths=[190, 110, 100, 90, 80, 140, 70, 160],
        )
        self._llm_slow_table.grid(row=2, column=0, sticky="nsew", padx=8, pady=(2, 4))

        self._llm_chart = MplFrame(tab, figsize=(9, 3))
        self._llm_chart.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _build_tool_success(self) -> None:
        tab = self._tabs.tab("Tool Success")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_total_calls = StatCard(cards, "Total Calls",       height=80, width=130)
        self._c_failures    = StatCard(cards, "Failures",          height=80, width=110)
        self._c_succ_rate   = StatCard(cards, "Success Rate",      height=80, width=120)
        self._c_recovery    = StatCard(cards, "Recovery Rate",     height=80, width=130)
        self._c_top_err     = StatCard(cards, "Top Error Msg",     height=80, width=220)
        for i, c in enumerate([self._c_total_calls, self._c_failures,
                                self._c_succ_rate, self._c_recovery, self._c_top_err]):
            c.grid(row=0, column=i, padx=4)

        self._tool_table = SortableTable(
            tab,
            columns=["Tool", "Calls", "Successes", "Failures", "Success Rate", "Avg Dur(s)"],
            col_widths=[180, 70, 90, 80, 110, 100],
        )
        self._tool_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    def _build_content_delivery(self) -> None:
        tab = self._tabs.tab("Content Delivery")
        tab.rowconfigure(2, weight=1)
        tab.columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self._c_productive  = StatCard(cards, "Productive Rate",       height=80, width=140)
        self._c_files       = StatCard(cards, "Files Delivered",       height=80, width=130)
        self._c_silent      = StatCard(cards, "Silent Successes",      height=80, width=140)
        self._c_tool_content= StatCard(cards, "Tool→No-Content Rate",  height=80, width=180)
        for i, c in enumerate([self._c_productive, self._c_files,
                                self._c_silent, self._c_tool_content]):
            c.grid(row=0, column=i, padx=4)

        self._content_table = SortableTable(
            tab,
            columns=["Bucket", "Char Range", "Turns", "Mean Quality"],
            col_widths=[110, 110, 70, 120],
        )
        self._content_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))

        self._content_chart = MplFrame(tab, figsize=(9, 3))
        self._content_chart.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

    # ── Refresh ──────────────────────────────────────────────────────────────

    def refresh(self, result, loader=None, reporter=None, *_) -> None:
        if result is None:
            return

        # Build turn lookup
        self._turn_lookup = {}
        if reporter is not None:
            for t in getattr(reporter, "_turns", []):
                self._turn_lookup[t.turn_id] = t

        self._fill_token_usage(result.token_usage)
        self._fill_llm_latency(result.llm_performance)
        self._fill_tool_success(result.tool_success)
        self._fill_content_delivery(result.content_delivery)

    # ── Fill helpers ─────────────────────────────────────────────────────────

    def _fill_token_usage(self, tu) -> None:
        self._c_total_tok.update(f"{tu.total_tokens:,}")
        self._c_avg_tok.update(f"{tu.mean_tokens_per_turn:,.0f}")
        ctx_pct = tu.mean_usage_percent
        self._c_ctx.update(
            f"{ctx_pct:.1f}%",
            StatCard.error_rate_color(ctx_pct / 100),
        )
        self._c_near.update(
            str(tu.turns_near_limit),
            COLOR_BAD if tu.turns_near_limit > 0 else COLOR_NEUTRAL,
        )
        self._c_cost.update(
            f"${tu.estimated_total_cost:.4f}" if tu.estimated_total_cost > 0 else "—"
        )

        rows = [
            [
                m.model_name,
                m.n_turns,
                f"{m.total_tokens:,}",
                f"{m.mean_total_tokens:,.0f}",
                f"{m.mean_usage_percent:.1f}%",
                f"${m.estimated_cost:.4f}",
            ]
            for m in tu.model_summary
        ]
        self._token_model_table.set_data(rows)

        weeks = tu.weekly_summary
        if not weeks:
            return
        tags    = [w.week_tag for w in weeks]
        totals  = [w.total_tokens for w in weeks]
        indices = list(range(len(weeks)))

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax.bar(indices, totals, color="#9b59b6", alpha=0.7)
            ax.set_xticks(indices)
            ax.set_xticklabels(tags, rotation=30, ha="right", fontsize=8)
            ax.set_ylabel("Total Tokens")
            ax.set_title("Weekly Token Consumption")

        self._token_chart.redraw(_draw)

    def _fill_llm_latency(self, lp) -> None:
        self._c_lat_med.update(f"{lp.total_latency.median:.0f}ms")
        self._c_lat_p90.update(f"{lp.total_latency.p90:.0f}ms")
        self._c_tps.update(f"{lp.mean_tokens_per_second:.0f}")
        self._c_slow_prompt.update(str(lp.slow_prompt_processing_count))
        self._c_slow_gen.update(str(lp.slow_generation_count))

        rows       = []
        highlights = []
        tags       = []

        for t in lp.slowest_turns:
            rec     = self._turn_lookup.get(t.turn_id)
            query   = _short(rec.user_query if rec else "", 48) or f"turn {t.turn_id[:20]}"
            session = _short((rec.session_title or rec.session_id) if rec else "", 20)
            sid     = rec.session_id if rec else ""

            rows.append([
                query,
                session,
                f"{t.total_latency_ms:.0f}",
                f"{t.ttft_ms:.0f}",
                f"{t.tpot_ms:.1f}",
                t.model_name,
                t.status,
                t.turn_id,
            ])
            highlights.append("#6b1a1a" if t.status == "error" else None)
            tags.append((sid, t.turn_id))

        self._llm_slow_table.set_data(rows, highlights, row_tags=tags)

        weeks = lp.weekly_summaries
        if not weeks:
            return
        tags_w  = [w.week_tag for w in weeks]
        means   = [w.mean_total_latency_ms for w in weeks]
        indices = list(range(len(weeks)))

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax.plot(indices, means, color="#e67e22", marker="o", linewidth=2)
            ax.set_xticks(indices)
            ax.set_xticklabels(tags_w, rotation=30, ha="right", fontsize=8)
            ax.set_ylabel("Mean Latency (ms)")
            ax.set_title("Weekly Mean LLM Latency")

        self._llm_chart.redraw(_draw)

    def _on_llm_row_click(self, row_data: list, tag) -> None:
        if self._navigate_callback and tag:
            session_id, turn_id = tag
            self._navigate_callback(session_id, turn_id)

    def _fill_tool_success(self, ts) -> None:
        self._c_total_calls.update(f"{ts.total_tool_calls:,}")
        self._c_failures.update(
            str(ts.total_tool_failures),
            "#6b1a1a" if ts.total_tool_failures > 0 else "#27ae60",
        )
        self._c_succ_rate.update(
            f"{ts.overall_success_rate:.1%}",
            "#27ae60" if ts.overall_success_rate >= 0.9
            else "#e67e22" if ts.overall_success_rate >= 0.7 else "#6b1a1a",
        )
        self._c_recovery.update(f"{ts.recovery_rate:.1%}")
        top_err = ts.top_error_messages[0][0][:30] if ts.top_error_messages else "—"
        self._c_top_err.update(top_err)

        rows = [
            [
                s.name,
                f"{s.total_calls:,}",
                f"{s.successes:,}",
                f"{s.failures:,}",
                f"{s.success_rate:.1%}",
                f"{s.avg_duration:.1f}",
            ]
            for s in ts.per_tool_stats
        ]
        highlights = ["#6b1a1a" if s.success_rate < 0.80 else None
                      for s in ts.per_tool_stats]
        self._tool_table.set_data(rows, highlights)

    def _fill_content_delivery(self, cd) -> None:
        self._c_productive.update(f"{cd.productivity_rate:.1%}")
        self._c_files.update(str(cd.total_files_delivered))
        self._c_silent.update(str(cd.silent_success_turns))
        self._c_tool_content.update(f"{cd.tool_to_content_rate:.1%}")

        rows = [
            [b.label, b.char_range, b.n_turns, f"{b.mean_quality:.4f}"]
            for b in cd.response_buckets
        ]
        self._content_table.set_data(rows)

        weeks = cd.weekly_summaries
        if not weeks:
            return
        tags    = [w.week_tag for w in weeks]
        lengths = [w.avg_response_length for w in weeks]
        indices = list(range(len(weeks)))

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax.bar(indices, lengths, color="#1abc9c", alpha=0.7)
            ax.set_xticks(indices)
            ax.set_xticklabels(tags, rotation=30, ha="right", fontsize=8)
            ax.set_ylabel("Avg Response Length (chars)")
            ax.set_title("Weekly Average Response Length")

        self._content_chart.redraw(_draw)
