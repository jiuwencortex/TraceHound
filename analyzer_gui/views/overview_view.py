# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""OverviewView — stat cards + text report preview."""

from __future__ import annotations

import customtkinter as ctk

from analyzer_gui.widgets.stat_card import (
    COLOR_BAD,
    COLOR_GOOD,
    COLOR_NEUTRAL,
    COLOR_WARN,
    StatCard,
)


def _fmt_date_range(dr) -> str:
    if dr is None:
        return "—"
    try:
        return f"{dr[0].strftime('%Y-%m-%d')} → {dr[1].strftime('%Y-%m-%d')}"
    except Exception:
        return "—"


def _trend_symbol(direction: str) -> str:
    return {
        "improving": "↑ improving",
        "degrading": "↓ degrading",
        "flat": "→ flat",
        "insufficient_data": "? insufficient data",
    }.get(direction, direction)


class OverviewView(ctk.CTkFrame):
    """One-glance summary screen."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # ----- Title -----
        ctk.CTkLabel(self, text="Overview", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        # ----- Scrollable body -----
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        scroll.columnconfigure(0, weight=1)

        # Cards area
        cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_frame.grid(row=0, column=0, sticky="ew", padx=8)

        CARD_W = 170
        card_opts = {"width": CARD_W, "height": 80}

        self._card_turns = StatCard(cards_frame, "Total Turns", **card_opts)
        self._card_dates = StatCard(cards_frame, "Date Range", width=260, height=80)
        self._card_quality = StatCard(cards_frame, "Mean Quality", **card_opts)
        self._card_trend = StatCard(cards_frame, "Quality Trend", **card_opts)
        self._card_sessions = StatCard(cards_frame, "Sessions (real/hb)", **card_opts)
        self._card_error_rate = StatCard(cards_frame, "Error Rate", **card_opts)
        self._card_correction = StatCard(cards_frame, "Correction Rate", **card_opts)
        self._card_duration = StatCard(cards_frame, "Median Duration", **card_opts)
        self._card_cost = StatCard(cards_frame, "Est. Cost", **card_opts)
        self._card_productive = StatCard(cards_frame, "Productive Sessions", **card_opts)

        all_cards = [
            self._card_turns, self._card_dates, self._card_quality,
            self._card_trend, self._card_sessions, self._card_error_rate,
            self._card_correction, self._card_duration, self._card_cost,
            self._card_productive,
        ]
        cols = 5
        for i, card in enumerate(all_cards):
            card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="ew")
        for c in range(cols):
            cards_frame.columnconfigure(c, weight=1)

        # Separator
        ctk.CTkLabel(scroll, text="Text Report Preview", font=("", 13, "bold")).grid(
            row=1, column=0, padx=16, pady=(16, 4), sticky="w"
        )

        # Text preview
        self._text_box = ctk.CTkTextbox(
            scroll,
            font=("Courier", 11),
            activate_scrollbars=True,
            wrap="none",
            height=420,
        )
        self._text_box.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._text_box.configure(state="disabled")

    # ------------------------------------------------------------------

    def refresh(self, result, loader, reporter) -> None:
        if result is None:
            return
        dh = result.data_health
        qt = result.quality_trends
        cp = result.correction_patterns
        tb = result.time_bottlenecks
        tu = result.token_usage
        ec = result.error_categories
        sf = result.session_flow

        self._card_turns.update(str(dh.total_turns))
        self._card_dates.update(_fmt_date_range(dh.date_range))

        q = qt.overall_mean
        self._card_quality.update(f"{q:.3f}", StatCard.quality_color(q))

        self._card_trend.update(_trend_symbol(qt.trend_direction))

        real = sf.total_real_sessions
        hb = sf.total_heartbeat_sessions
        self._card_sessions.update(f"{real} / {hb}")

        er = ec.overall_error_rate
        self._card_error_rate.update(
            f"{er:.1%}", StatCard.error_rate_color(er)
        )

        cr = cp.baseline_correction_rate
        self._card_correction.update(f"{cr:.1%}", StatCard.error_rate_color(cr))

        if tb.n_turns_with_timing > 0:
            self._card_duration.update(f"{tb.median_duration_s:.1f}s")
        else:
            self._card_duration.update("—")

        cost = tu.estimated_total_cost
        self._card_cost.update(f"${cost:.4f}" if cost > 0 else "—")

        pr = sf.productive_session_rate
        self._card_productive.update(
            f"{sf.productive_sessions}/{real} ({pr:.0%})",
        )

        # Text preview
        try:
            text = reporter.render_text(result)
        except Exception as exc:
            text = f"(render error: {exc})"

        self._text_box.configure(state="normal")
        self._text_box.delete("1.0", "end")
        self._text_box.insert("1.0", text)
        self._text_box.configure(state="disabled")
