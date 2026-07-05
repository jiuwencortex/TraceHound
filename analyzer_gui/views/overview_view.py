# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""OverviewView — compact stat-card strip + Report / Dashboard mode toggle."""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

from analyzer_gui.widgets.sortable_table import SortableTable
from analyzer_gui.widgets.stat_card import StatCard


def _fmt_date_range(dr) -> str:
    if dr is None:
        return "—"
    try:
        return f"{dr[0].strftime('%Y-%m-%d')}→{dr[1].strftime('%Y-%m-%d')}"
    except Exception:
        return "—"


def _trend_symbol(direction: str) -> str:
    return {
        "improving":        "↑ improving",
        "degrading":        "↓ degrading",
        "flat":             "→ flat",
        "insufficient_data":"? insufficient",
    }.get(direction, direction)


def _sec_label(parent, text: str, row: int) -> None:
    """Decorative section header with lines on both sides."""
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 4))
    f.columnconfigure(0, weight=0)
    f.columnconfigure(1, weight=1)
    f.columnconfigure(2, weight=0)
    ctk.CTkFrame(f, height=1, fg_color=("gray55", "gray35")).grid(
        row=0, column=0, sticky="ew", ipadx=20, padx=(0, 8))
    ctk.CTkLabel(f, text=text, font=("", 13, "bold"),
                 text_color=("#4a90d9", "#7ec8e3")).grid(row=0, column=1, sticky="w")
    ctk.CTkFrame(f, height=1, fg_color=("gray55", "gray35")).grid(
        row=0, column=2, sticky="ew", ipadx=40, padx=(8, 0))


def _sec_label_inline(parent, text: str, row: int) -> None:
    """Compact section label for a sub-column (no left line)."""
    ctk.CTkLabel(
        parent, text=text,
        font=("", 12, "bold"),
        text_color=("#4a90d9", "#7ec8e3"),
        anchor="w",
    ).grid(row=row, column=0, sticky="w", pady=(14, 4))


class OverviewView(ctk.CTkFrame):
    """One-glance summary: compact stat strip + Report / Dashboard toggle."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)

        self._reporter: Any = None
        self._result: Any   = None

        # ── Row 0: title bar + mode toggle ───────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        hdr.columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Overview", font=("", 20, "bold")).grid(
            row=0, column=0, sticky="w")

        self._mode_seg = ctk.CTkSegmentedButton(
            hdr,
            values=["Report", "Dashboard"],
            command=self._on_mode_change,
            width=220,
        )
        self._mode_seg.set("Report")
        self._mode_seg.grid(row=0, column=1)

        # ── Row 1: compact stat cards (single row, all equal weight) ─────────
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 0))

        _W, _H = 130, 62      # card width / height
        _DW    = 210           # date range card needs more room

        self._card_turns      = StatCard(cards_frame, "Total Turns",         width=_W,  height=_H)
        self._card_dates      = StatCard(cards_frame, "Date Range",          width=_DW, height=_H)
        self._card_quality    = StatCard(cards_frame, "Mean Quality",        width=_W,  height=_H)
        self._card_error_rate = StatCard(cards_frame, "Error Rate",          width=_W,  height=_H)
        self._card_sessions   = StatCard(cards_frame, "Sessions",            width=_W,  height=_H)
        self._card_duration   = StatCard(cards_frame, "Median Duration",     width=_W,  height=_H)
        self._card_trend      = StatCard(cards_frame, "Quality Trend",       width=_W,  height=_H)
        self._card_correction = StatCard(cards_frame, "Correction Rate",     width=_W,  height=_H)
        self._card_cost       = StatCard(cards_frame, "Est. Cost",           width=_W,  height=_H)
        self._card_productive = StatCard(cards_frame, "Productive Sessions", width=_W,  height=_H)

        _all_cards = [
            self._card_turns, self._card_dates, self._card_quality,
            self._card_error_rate, self._card_sessions, self._card_duration,
            self._card_trend, self._card_correction, self._card_cost,
            self._card_productive,
        ]
        for col, card in enumerate(_all_cards):
            card.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
            cards_frame.columnconfigure(col, weight=1)

        # ── Row 2: thin separator ─────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=("gray60", "gray30")).grid(
            row=2, column=0, sticky="ew", padx=16, pady=(0, 0)
        )

        # ── Row 3: content area (toggled) ────────────────────────────────────
        # -- Report mode (styled tk.Text) --
        self._report_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._report_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self._report_frame.rowconfigure(0, weight=1)
        self._report_frame.columnconfigure(0, weight=1)

        self._text_widget = tk.Text(
            self._report_frame,
            wrap="word",
            state="disabled",
            bg="#1a1a1a",
            fg="#d0d0d0",
            selectbackground="#4a90d9",
            selectforeground="white",
            padx=20,
            pady=14,
            font=("Consolas", 11),
            relief="flat",
            borderwidth=0,
        )
        self._text_widget.grid(row=0, column=0, sticky="nsew")
        _sb = ctk.CTkScrollbar(self._report_frame, command=self._text_widget.yview)
        _sb.grid(row=0, column=1, sticky="ns")
        self._text_widget.configure(yscrollcommand=_sb.set)
        self._configure_tags()

        # -- Dashboard mode (scrollable structured tables) --
        self._dash_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._dash_frame.columnconfigure(0, weight=1)
        # (gridded on demand)
        self._build_dashboard_widgets()

    # ── Widget factories ──────────────────────────────────────────────────────

    def _build_dashboard_widgets(self) -> None:
        """Create all table widgets inside _dash_frame once."""
        d = self._dash_frame

        # Sessions section
        _sec_label(d, "Sessions", 0)
        d.rowconfigure(0, weight=0)
        self._sess_table = SortableTable(
            d,
            columns=["Session ID", "Title / First Query", "Turns",
                     "Error Rate", "Tokens", "Files", "Mode", "Duration(s)"],
            col_widths=[170, 230, 55, 90, 80, 50, 100, 90],
        )
        self._sess_table.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        # Side-by-side: Errors | Quality
        mid = ctk.CTkFrame(d, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="ew", padx=8, pady=0)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)

        # Errors column
        err_col = ctk.CTkFrame(mid, fg_color="transparent")
        err_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        err_col.columnconfigure(0, weight=1)
        _sec_label_inline(err_col, "Error Breakdown", 0)
        self._err_table = SortableTable(
            err_col,
            columns=["Category", "Count", "% of Errors", "Sessions"],
            col_widths=[120, 60, 100, 80],
        )
        self._err_table.grid(row=1, column=0, sticky="ew")

        # Quality column
        qt_col = ctk.CTkFrame(mid, fg_color="transparent")
        qt_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        qt_col.columnconfigure(0, weight=1)
        _sec_label_inline(qt_col, "Quality by Week", 0)
        self._qt_table = SortableTable(
            qt_col,
            columns=["Week", "Turns", "Mean Quality", "Corrections"],
            col_widths=[100, 55, 110, 90],
        )
        self._qt_table.grid(row=1, column=0, sticky="ew")

        # Slowest turns section
        _sec_label(d, "Slowest Turns", 3)
        self._slow_table = SortableTable(
            d,
            columns=["Turn ID", "Query", "Duration(s)", "Status", "Quality", "Messages"],
            col_widths=[170, 280, 90, 70, 80, 75],
        )
        self._slow_table.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 12))

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _on_mode_change(self, mode: str) -> None:
        if mode == "Report":
            self._dash_frame.grid_remove()
            self._report_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        else:
            self._report_frame.grid_remove()
            self._dash_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self, result, loader, reporter) -> None:
        if result is None:
            return

        self._result   = result
        self._reporter = reporter

        dh = result.data_health
        qt = result.quality_trends
        cp = result.correction_patterns
        tb = result.time_bottlenecks
        tu = result.token_usage
        ec = result.error_categories
        sf = result.session_flow

        # ── Stat cards ───────────────────────────────────────────────
        self._card_turns.update(str(dh.total_turns))
        self._card_dates.update(_fmt_date_range(dh.date_range))

        q = qt.overall_mean
        self._card_quality.update(f"{q:.3f}", StatCard.quality_color(q))

        er = ec.overall_error_rate
        self._card_error_rate.update(f"{er:.1%}", StatCard.error_rate_color(er))

        real = sf.total_real_sessions
        hb   = sf.total_heartbeat_sessions
        self._card_sessions.update(f"{real} real / {hb} hb")

        if tb.n_turns_with_timing > 0:
            self._card_duration.update(f"{tb.median_duration_s:.1f}s")
        else:
            self._card_duration.update("—")

        self._card_trend.update(_trend_symbol(qt.trend_direction))

        cr = cp.baseline_correction_rate
        self._card_correction.update(f"{cr:.1%}", StatCard.error_rate_color(cr))

        cost = tu.estimated_total_cost
        self._card_cost.update(f"${cost:.4f}" if cost > 0 else "—")

        pr = sf.productive_session_rate
        self._card_productive.update(f"{sf.productive_sessions}/{real} ({pr:.0%})")

        # ── Report text ──────────────────────────────────────────────
        try:
            raw_text = reporter.render_text(result)
        except Exception as exc:
            raw_text = f"(render error: {exc})"
        self._render_text(raw_text)

        # ── Dashboard tables ─────────────────────────────────────────
        self._fill_sessions(sf)
        self._fill_errors(ec)
        self._fill_quality(qt)
        self._fill_slowest(tb, reporter)

    # ── Dashboard fill helpers ────────────────────────────────────────────────

    def _fill_sessions(self, sf) -> None:
        profiles = getattr(sf, "session_profiles", [])
        rows, highlights = [], []
        for p in profiles:
            sid      = getattr(p, "session_id",    "")
            title    = (getattr(p, "title", "") or sid)[:38]
            n_turns  = getattr(p, "n_turns",       0)
            err_rate = getattr(p, "error_rate",    0.0)
            tokens   = getattr(p, "total_tokens",  0)
            files    = getattr(p, "files_delivered", 0)
            mode     = getattr(p, "agent_mode",    "")
            dur      = getattr(p, "duration_s",    0.0)
            rows.append([
                sid, title, n_turns,
                f"{err_rate:.1%}",
                f"{tokens:,}" if tokens else "0",
                files, mode,
                f"{dur:.1f}",
            ])
            highlights.append(
                "#6b1a1a" if err_rate >= 0.5 else
                "#3a3300" if err_rate > 0   else None
            )
        if not rows:
            self._sess_table.set_data([["—"] * 8])
        else:
            self._sess_table.set_data(rows, highlights)

    def _fill_errors(self, ec) -> None:
        rows, highlights = [], []
        for c in ec.categories:
            if c.count == 0:
                continue
            rows.append([c.category, c.count,
                         f"{c.percentage_of_errors:.1%}", c.affected_sessions])
            highlights.append("#6b1a1a")
        if not rows:
            self._err_table.set_data([["—", "0", "—", "—"]])
        else:
            self._err_table.set_data(rows, highlights)

    def _fill_quality(self, qt) -> None:
        rows = []
        for w in qt.weeks:
            rows.append([
                w.week_tag,
                w.n_turns,
                f"{w.mean_quality:.3f}",
                w.n_follow_up_corrections,
            ])
        if not rows:
            self._qt_table.set_data([["—", "—", "—", "—"]])
        else:
            self._qt_table.set_data(rows)

    def _fill_slowest(self, tb, reporter) -> None:
        turn_lookup: dict = {}
        if reporter is not None:
            for t in getattr(reporter, "_turns", []):
                turn_lookup[t.turn_id] = t

        rows, highlights = [], []
        for t in tb.slowest_turns:
            rec   = turn_lookup.get(t.turn_id)
            query = (rec.user_query or "") if rec else ""
            query = (query[:40] + "…") if len(query) > 40 else query
            status = "ERR" if t.has_error else ("OK" if t.task_completed else "INC")
            rows.append([
                t.turn_id[:28],
                query or "—",
                f"{t.duration_seconds:.1f}",
                status,
                f"{t.quality:.3f}",
                t.n_messages,
            ])
            highlights.append("#6b1a1a" if t.has_error else None)
        if not rows:
            self._slow_table.set_data([["—"] * 6])
        else:
            self._slow_table.set_data(rows, highlights)

    # ── Report text rendering ─────────────────────────────────────────────────

    def _configure_tags(self) -> None:
        w = self._text_widget
        w.tag_configure("h1",    font=("Consolas", 16, "bold"), foreground="#ffffff",  spacing3=10)
        w.tag_configure("h2",    font=("Consolas", 13, "bold"), foreground="#7ec8e3",  spacing3=6)
        w.tag_configure("h3",    font=("Consolas", 11, "bold"), foreground="#a8d8a8",  spacing3=4)
        w.tag_configure("body",  font=("Consolas", 11),         foreground="#d0d0d0")
        w.tag_configure("key",   font=("Consolas", 11, "bold"), foreground="#ffffff")
        w.tag_configure("num",   font=("Consolas", 11, "bold"), foreground="#7ec8e3")
        w.tag_configure("sep",   font=("Consolas", 10),         foreground="#555555")
        w.tag_configure("err",   font=("Consolas", 11),         foreground="#e74c3c")
        w.tag_configure("good",  font=("Consolas", 11),         foreground="#27ae60")
        w.tag_configure("warn",  font=("Consolas", 11),         foreground="#e67e22")

    def _render_text(self, text: str) -> None:
        w = self._text_widget
        w.configure(state="normal")
        w.delete("1.0", "end")

        for line in text.splitlines():
            stripped = line.strip()

            # Section separators (--- Foo ---)
            if stripped.startswith("---") and stripped.endswith("---"):
                label = stripped.strip("-").strip()
                w.insert("end", f"\n  {label}\n", "h2")
                w.insert("end", "  " + "─" * 54 + "\n", "sep")
                continue

            # Main title (=== ... ===)
            if stripped.startswith("===") and stripped.endswith("==="):
                label = stripped.strip("=").strip()
                w.insert("end", f"\n{label}\n", "h1")
                continue

            # Blank line
            if not stripped:
                w.insert("end", "\n", "body")
                continue

            # Try to colorize key: value lines
            if ":" in stripped and not stripped.startswith("#"):
                colon = stripped.index(":")
                key_part = stripped[:colon + 1]
                val_part = stripped[colon + 1:]
                w.insert("end", "  " + key_part, "key")
                # Colour numeric / rate values
                v = val_part.strip()
                if any(bad in stripped.lower() for bad in ("error", "fail", "0.0%", "0/", "100%")):
                    tag = "err"
                elif any(kw in key_part.lower() for kw in ("quality", "rate", "productivity")):
                    tag = "num"
                else:
                    tag = "body"
                w.insert("end", val_part + "\n", tag)
                continue

            # Indent + bullet lines
            w.insert("end", line + "\n", "body")

        w.configure(state="disabled")

