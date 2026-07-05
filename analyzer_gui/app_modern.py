# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ModernApp — consumer-friendly agent analytics dashboard.

Opens as a CTkToplevel over the main TraceHound window.
Shows the same data in plain language with large visuals.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from typing import Any

import customtkinter as ctk

# ── Colour palette ────────────────────────────────────────────────────────────
BG       = "#0d1117"   # near-black canvas
SURFACE  = "#161b22"   # panel background
CARD     = "#1c2128"   # card background
BORDER   = "#30363d"   # subtle border / divider
BLUE     = "#58a6ff"   # primary accent
GREEN    = "#3fb950"   # success
AMBER    = "#d29922"   # warning
RED      = "#f85149"   # error / danger
PURPLE   = "#bc8cff"   # neutral accent
TEXT     = "#e6edf3"   # primary text
MUTED    = "#8b949e"   # secondary text
DIM      = "#484f58"   # very muted

NAV_W    = 110          # sidebar width
NAV_BG   = "#0d1117"
NAV_ACT  = "#1c2128"   # active nav item bg


# ── Plain-language translations ───────────────────────────────────────────────

_ERROR_PLAIN: dict[str, str] = {
    "api_auth":   "💳 Payment / API key issues",
    "timeout":    "⏱ Server took too long",
    "network":    "📡 Connection problems",
    "model":      "🤖 AI model errors",
    "filesystem": "📁 File access errors",
    "syntax":     "🔧 Code syntax errors",
    "import":     "📦 Missing package",
    "execution":  "⚡ Code run errors",
    "other":      "❓ Unknown errors",
}

_ERROR_DETAIL: dict[str, str] = {
    "api_auth":   "Your agent's API balance ran out or the key is invalid. It couldn't make any AI calls.",
    "timeout":    "The AI server was too slow to respond. Requests timed out before completion.",
    "network":    "The agent lost its connection to the internet or to the AI service.",
    "model":      "The AI model returned an unexpected error or was temporarily unavailable.",
    "filesystem": "The agent couldn't read or write files it needed.",
    "syntax":     "Code that the agent wrote had syntax errors and couldn't run.",
    "import":     "A required Python package was missing from the environment.",
    "execution":  "Code ran but crashed with a runtime error.",
    "other":      "An error occurred that doesn't fit a known category.",
}

_ERROR_FIX: dict[str, str] = {
    "api_auth":   "Add credit to your API account or replace the API key in your config.",
    "timeout":    "Check your internet speed, or switch to a faster AI model endpoint.",
    "network":    "Verify your network connection and firewall settings.",
    "model":      "Retry the request. If persistent, contact your AI provider.",
    "filesystem": "Check file paths and permissions in your agent configuration.",
    "syntax":     "Review the agent's code generation prompts for clarity.",
    "import":     "Run `pip install <package>` to add the missing dependency.",
    "execution":  "Add error handling to the agent's execution loop.",
    "other":      "Review the raw error logs for more details.",
}


def _health_score(result) -> int:
    """0–100 composite health score."""
    qt  = getattr(result, "quality_trends",    None)
    ec  = getattr(result, "error_categories",  None)
    sf  = getattr(result, "session_flow",       None)
    q   = getattr(qt, "overall_mean",           0.0) if qt else 0.0
    er  = getattr(ec, "overall_error_rate",     0.0) if ec else 0.0
    pr  = getattr(sf, "productive_session_rate", 0.0) if sf else 0.0
    raw = (q * 50) + ((1 - er) * 40) + (pr * 10)
    return max(0, min(100, int(raw)))


def _grade(score: int) -> tuple[str, str]:
    """Return (label, colour) for a health score."""
    if score >= 80: return "GREAT",  GREEN
    if score >= 60: return "GOOD",   BLUE
    if score >= 40: return "FAIR",   AMBER
    return "POOR", RED


def _fmt_dur(s: float) -> str:
    if s < 1:   return f"{s*1000:.0f} ms"
    if s < 60:  return f"{s:.1f}s"
    if s < 3600: return f"{s/60:.1f} min"
    return f"{s/3600:.1f}h"


def _status_pill(error_rate: float) -> tuple[str, str]:
    """(text, color) for a session status pill."""
    if error_rate == 0:   return "✓  All good",      GREEN
    if error_rate < 0.5:  return "⚠  Some issues",   AMBER
    return "✗  Failed",  RED


def _today_str() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%B %d, %Y")


# ── Widgets ───────────────────────────────────────────────────────────────────

class _DonutGauge(tk.Canvas):
    """Canvas-based circular health gauge."""

    SIZE = 200
    TRACK_W = 18

    def __init__(self, parent, **kw) -> None:
        super().__init__(
            parent,
            width=self.SIZE, height=self.SIZE,
            bg=CARD, highlightthickness=0,
            **kw,
        )
        self._score = 0

    def set_score(self, score: int) -> None:
        self._score = score
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s    = self.SIZE
        pad  = 24
        x0, y0, x1, y1 = pad, pad, s - pad, s - pad
        hw   = self.TRACK_W

        # Background track
        self.create_arc(x0, y0, x1, y1, start=0, extent=360,
                        outline=BORDER, width=hw, style="arc")

        # Score arc
        if self._score > 0:
            label, color = _grade(self._score)
            extent = self._score / 100 * 359.9   # avoid full-circle artefact
            self.create_arc(x0, y0, x1, y1,
                            start=90, extent=-extent,
                            outline=color, width=hw, style="arc")

        # Center score
        cx, cy = s // 2, s // 2
        label, color = _grade(self._score)
        self.create_text(cx, cy - 14, text=str(self._score),
                         fill=TEXT, font=("", 34, "bold"))
        self.create_text(cx, cy + 18, text="/ 100",
                         fill=MUTED, font=("", 11))
        self.create_text(cx, cy + 36, text=label,
                         fill=color, font=("", 10, "bold"))


class _HeroCard(ctk.CTkFrame):
    """Large stat tile: big number + label."""

    def __init__(self, parent, title: str, color: str = BLUE, **kw) -> None:
        super().__init__(parent, fg_color=CARD, corner_radius=10, **kw)
        self.columnconfigure(0, weight=1)

        # Accent stripe at top
        ctk.CTkFrame(self, height=3, fg_color=color,
                     corner_radius=0).grid(row=0, column=0, sticky="ew")

        self._val = ctk.CTkLabel(self, text="—",
                                  font=("", 28, "bold"), text_color=TEXT,
                                  anchor="center")
        self._val.grid(row=1, column=0, pady=(12, 2))

        ctk.CTkLabel(self, text=title, font=("", 10), text_color=MUTED,
                     anchor="center").grid(row=2, column=0, pady=(0, 14))

    def set(self, value: str) -> None:
        self._val.configure(text=value)


class _AlertBanner(ctk.CTkFrame):
    """One-line coloured banner for a key issue."""

    def __init__(self, parent, icon: str, headline: str,
                 body: str, color: str = RED, **kw) -> None:
        super().__init__(parent, fg_color=CARD,
                         corner_radius=10, border_width=1,
                         border_color=color, **kw)
        self.columnconfigure(2, weight=1)   # headline/body column expands

        # Left color bar
        ctk.CTkFrame(self, width=4, fg_color=color,
                     corner_radius=0).grid(row=0, column=0, sticky="ns",
                                           rowspan=2, padx=(0, 0), pady=1)

        ctk.CTkLabel(self, text=icon, font=("", 22),
                     anchor="w").grid(row=0, column=1, padx=(12, 4),
                                      pady=(12, 2), rowspan=2, sticky="nw")

        ctk.CTkLabel(self, text=headline, font=("", 13, "bold"),
                     text_color=TEXT, anchor="w").grid(
            row=0, column=2, sticky="w", padx=(0, 12), pady=(12, 0))

        ctk.CTkLabel(self, text=body, font=("", 10), text_color=MUTED,
                     anchor="w", wraplength=480, justify="left").grid(
            row=1, column=2, sticky="w", padx=(0, 12), pady=(0, 12))


class _SessionCard(ctk.CTkFrame):
    """A session summary card with status pill."""

    def __init__(self, parent, title: str, subtitle: str,
                 pill_text: str, pill_color: str,
                 turns: int, mode: str, **kw) -> None:
        super().__init__(parent, fg_color=CARD, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(1, weight=1)

        # Status indicator dot
        dot = ctk.CTkFrame(self, width=10, height=10, fg_color=pill_color,
                           corner_radius=5)
        dot.grid(row=0, column=0, padx=(14, 8), pady=(16, 0), sticky="n")
        dot.grid_propagate(False)

        # Title
        ctk.CTkLabel(self, text=title, font=("", 13, "bold"), text_color=TEXT,
                     anchor="w").grid(row=0, column=1, sticky="w", pady=(14, 2))

        # Subtitle row
        sub = ctk.CTkFrame(self, fg_color="transparent")
        sub.grid(row=1, column=1, sticky="w", pady=(0, 14))

        ctk.CTkLabel(sub, text=subtitle, font=("", 10), text_color=MUTED).pack(
            side="left", padx=(0, 10))

        # Pill
        pill = ctk.CTkFrame(sub, fg_color=_hex_20(pill_color),
                             corner_radius=8)
        pill.pack(side="left")
        ctk.CTkLabel(pill, text=pill_text, font=("", 9, "bold"),
                     text_color=pill_color).pack(padx=8, pady=2)

        # turns + mode chips
        for txt in (f"{turns} turn{'s' if turns != 1 else ''}", mode):
            chip = ctk.CTkFrame(sub, fg_color=SURFACE, corner_radius=6)
            chip.pack(side="left", padx=(6, 0))
            ctk.CTkLabel(chip, text=txt, font=("", 9),
                         text_color=MUTED).pack(padx=7, pady=2)


class _ProblemCard(ctk.CTkFrame):
    """Card describing one error category in plain language."""

    def __init__(self, parent, category: str, count: int,
                 example_msg: str = "", **kw) -> None:
        col  = RED if count > 1 else AMBER
        name = _ERROR_PLAIN.get(category, category)
        detail = _ERROR_DETAIL.get(category, "")
        fix    = _ERROR_FIX.get(category, "")
        subtitle = f"Happened {count} time{'s' if count != 1 else ''}"

        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=col, **kw)
        self.columnconfigure(0, weight=1)

        # Header strip
        hdr = ctk.CTkFrame(self, fg_color=_hex_12(col), corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text=name, font=("", 13, "bold"),
                     text_color=TEXT, anchor="w").grid(
            row=0, column=0, padx=14, pady=10, sticky="w")

        ctk.CTkLabel(hdr, text=subtitle, font=("", 10),
                     text_color=col, anchor="e").grid(
            row=0, column=1, padx=14, pady=10, sticky="e")

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 14))
        body.columnconfigure(0, weight=1)

        ctk.CTkLabel(body, text=detail, font=("", 11), text_color=MUTED,
                     wraplength=560, justify="left", anchor="w").grid(
            row=0, column=0, sticky="w")

        # Fix row
        fix_frame = ctk.CTkFrame(body, fg_color=_hex_08(GREEN),
                                  corner_radius=8)
        fix_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ctk.CTkLabel(fix_frame, text="💡  " + fix, font=("", 11),
                     text_color=GREEN, wraplength=530,
                     justify="left", anchor="w").grid(padx=12, pady=8,
                                                       sticky="w")

        # Example message (truncated)
        if example_msg:
            em = example_msg[:120] + ("…" if len(example_msg) > 120 else "")
            ctk.CTkLabel(body, text=f'Error: "{em}"',
                         font=("Consolas", 9), text_color=DIM,
                         wraplength=560, justify="left", anchor="w").grid(
                row=2, column=0, sticky="w", pady=(6, 0))


class _TipCard(ctk.CTkFrame):
    """Single action-card for a recommendation."""

    _PRI_LABEL = {"P0": ("Must fix",   RED),
                  "P1": ("Should fix", AMBER),
                  "P2": ("Nice to",    BLUE)}

    def __init__(self, parent, priority: str, fix: str,
                 effort: str = "", impact: str = "", **kw) -> None:
        lbl, col = self._PRI_LABEL.get(priority, ("Action", BLUE))

        super().__init__(parent, fg_color=CARD, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(1, weight=1)

        # Priority badge
        badge = ctk.CTkFrame(self, fg_color=col, corner_radius=8,
                              width=64, height=64)
        badge.grid(row=0, column=0, rowspan=2, padx=(14, 12),
                   pady=14, sticky="n")
        badge.grid_propagate(False)
        ctk.CTkLabel(badge, text=priority, font=("", 14, "bold"),
                     text_color=BG).place(relx=0.5, rely=0.35, anchor="center")
        ctk.CTkLabel(badge, text=lbl, font=("", 7, "bold"),
                     text_color=BG).place(relx=0.5, rely=0.72, anchor="center")

        ctk.CTkLabel(self, text=fix, font=("", 12), text_color=TEXT,
                     wraplength=480, justify="left", anchor="w").grid(
            row=0, column=1, sticky="w", pady=(14, 2), padx=(0, 14))

        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.grid(row=1, column=1, sticky="w", pady=(0, 14))
        for tag, val in (("Effort", effort), ("Impact", impact)):
            if val:
                ch = ctk.CTkFrame(chips, fg_color=SURFACE, corner_radius=6)
                ch.pack(side="left", padx=(0, 6))
                ctk.CTkLabel(ch, text=f"{tag}: {val}", font=("", 9),
                             text_color=MUTED).pack(padx=8, pady=3)


# ── Views ─────────────────────────────────────────────────────────────────────

class _SummaryView(ctk.CTkFrame):
    """Home: health gauge + 6 hero cards + mini stat panel + alerts + sessions."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, fg_color=BG, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Title bar
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        tb.columnconfigure(0, weight=1)
        self._title_lbl = ctk.CTkLabel(
            tb, text="Your AI Agent — Loading…",
            font=("", 20, "bold"), text_color=TEXT, anchor="w")
        self._title_lbl.grid(row=0, column=0, sticky="w")
        self._date_lbl = ctk.CTkLabel(
            tb, text="", font=("", 11), text_color=MUTED, anchor="e")
        self._date_lbl.grid(row=0, column=1, sticky="e")

        # ── Main body: left (gauge + mini-stats) + right (heroes + alerts) ─
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=(14, 12))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left column: donut + compact stats panel
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12), ipadx=16)
        left.columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Agent Health",
                     font=("", 11, "bold"), text_color=MUTED).grid(
            row=0, column=0, pady=(18, 6))

        self._gauge = _DonutGauge(left)
        self._gauge.grid(row=1, column=0, padx=20, pady=(0, 4))

        self._gauge_sub = ctk.CTkLabel(
            left, text="", font=("", 9), text_color=MUTED)
        self._gauge_sub.grid(row=2, column=0, pady=(0, 10))

        ctk.CTkFrame(left, height=1, fg_color=BORDER).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(0, 6))

        # Mini stat panel
        sp = ctk.CTkFrame(left, fg_color="transparent")
        sp.grid(row=4, column=0, sticky="ew", padx=6, pady=(0, 14))
        sp.columnconfigure(1, weight=1)
        self._mini: dict[str, ctk.CTkLabel] = {}
        for i, key in enumerate(["Quality Score", "Quality Trend",
                                   "Correction Rate", "Productive Sessions",
                                   "Total Tokens", "Est. Cost",
                                   "Tool Calls", "Tool Success Rate"]):
            ctk.CTkLabel(sp, text=key, font=("", 8), text_color=DIM,
                         anchor="w").grid(row=i, column=0, padx=(8, 4),
                                          pady=1, sticky="w")
            lbl = ctk.CTkLabel(sp, text="—", font=("", 8, "bold"),
                               text_color=MUTED, anchor="e")
            lbl.grid(row=i, column=1, padx=(0, 8), pady=1, sticky="e")
            self._mini[key] = lbl

        # Right column
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure((0, 1, 2), weight=1)
        right.rowconfigure(3, weight=1)

        # Hero row 1: Conversations | Error Rate | Mean Quality
        self._h_convos  = _HeroCard(right, "Conversations",  BLUE)
        self._h_errors  = _HeroCard(right, "Hit Errors",     RED)
        self._h_quality = _HeroCard(right, "Mean Quality",   GREEN)
        self._h_convos .grid(row=0, column=0, padx=(0, 5), pady=(0, 5), sticky="ew")
        self._h_errors .grid(row=0, column=1, padx=5,       pady=(0, 5), sticky="ew")
        self._h_quality.grid(row=0, column=2, padx=(5, 0), pady=(0, 5), sticky="ew")

        # Hero row 2: Avg Duration | Correction Rate | Total Tokens
        self._h_duration   = _HeroCard(right, "Avg Duration",    PURPLE)
        self._h_correction = _HeroCard(right, "Correction Rate", AMBER)
        self._h_tokens     = _HeroCard(right, "Total Tokens",    DIM)
        self._h_duration  .grid(row=1, column=0, padx=(0, 5), pady=(0, 10), sticky="ew")
        self._h_correction.grid(row=1, column=1, padx=5,       pady=(0, 10), sticky="ew")
        self._h_tokens    .grid(row=1, column=2, padx=(5, 0), pady=(0, 10), sticky="ew")

        # Alerts
        ctk.CTkLabel(right, text="What went wrong",
                     font=("", 11, "bold"), text_color=MUTED, anchor="w").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(2, 4))
        self._alert_scroll = ctk.CTkScrollableFrame(
            right, fg_color="transparent", height=120)
        self._alert_scroll.columnconfigure(0, weight=1)
        self._alert_scroll.grid(row=3, column=0, columnspan=3,
                                 sticky="nsew", pady=(0, 8))

        # Recent sessions
        ctk.CTkLabel(right, text="Recent conversations",
                     font=("", 11, "bold"), text_color=MUTED, anchor="w").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(2, 4))
        self._sessions_scroll = ctk.CTkScrollableFrame(
            right, fg_color="transparent", height=140)
        self._sessions_scroll.columnconfigure(0, weight=1)
        self._sessions_scroll.grid(row=5, column=0, columnspan=3, sticky="ew")

    def fill(self, result, reporter) -> None:
        if result is None:
            return

        dh  = result.data_health
        qt  = result.quality_trends
        ec  = result.error_categories
        sf  = result.session_flow
        tb  = result.time_bottlenecks
        tu  = result.token_usage
        cp  = result.correction_patterns
        ts  = result.tool_success

        # Title / date
        start  = dh.date_range[0].strftime("%b %d") if dh.date_range else "Today"
        end    = dh.date_range[1].strftime("%b %d") if dh.date_range else ""
        period = f"{start} → {end}" if start != end else start
        self._title_lbl.configure(text=f"Your AI Agent  ·  {period}")
        self._date_lbl.configure(text=_today_str())

        # Gauge
        score = _health_score(result)
        self._gauge.set_score(score)
        self._gauge_sub.configure(
            text=f"{sf.total_real_sessions} sessions  ·  {dh.total_turns} turns")

        # Mini stat panel
        q  = qt.overall_mean
        cr = cp.baseline_correction_rate
        pr = sf.productive_session_rate
        tk = tu.total_tokens
        cost = tu.estimated_total_cost
        t_calls = ts.total_tool_calls
        t_sr    = ts.overall_success_rate if t_calls > 0 else None
        trend_map = {"improving": "↑ Improving", "degrading": "↓ Degrading",
                     "flat": "→ Flat", "insufficient_data": "? Not enough data"}
        mini = {
            "Quality Score":       (f"{q:.3f}", GREEN if q >= 0.7 else AMBER if q >= 0.4 else RED),
            "Quality Trend":       (trend_map.get(qt.trend_direction, "—"), MUTED),
            "Correction Rate":     (f"{cr:.1%}", AMBER if cr > 0.2 else MUTED),
            "Productive Sessions": (f"{sf.productive_sessions}/{sf.total_real_sessions} ({pr:.0%})",
                                    GREEN if pr > 0.5 else MUTED),
            "Total Tokens":        (f"{tk:,}" if tk else "0", MUTED),
            "Est. Cost":           (f"${cost:.4f}" if cost > 0 else "—", MUTED),
            "Tool Calls":          (str(t_calls), MUTED),
            "Tool Success Rate":   (f"{t_sr:.1%}" if t_sr is not None else "—",
                                    GREEN if t_sr and t_sr >= 0.9 else AMBER),
        }
        for key, (val, col) in mini.items():
            if key in self._mini:
                self._mini[key].configure(text=val, text_color=col)

        # Hero cards
        self._h_convos.set(str(sf.total_real_sessions))
        er = ec.overall_error_rate
        self._h_errors.set(f"{er:.0%}")
        self._h_quality.set(f"{q:.3f}")
        dur = tb.mean_duration_s if tb.n_turns_with_timing > 0 else 0
        self._h_duration.set(_fmt_dur(dur))
        self._h_correction.set(f"{cr:.1%}")
        self._h_tokens.set(f"{tk:,}" if tk else "—")

        # Alerts
        for w in self._alert_scroll.winfo_children():
            w.destroy()
        active_cats = [c for c in ec.categories if c.count > 0]
        if active_cats:
            for i, cat in enumerate(active_cats):
                name  = _ERROR_PLAIN.get(cat.category, cat.category)
                fix   = _ERROR_FIX.get(cat.category, "Review logs.")
                parts = name.split(" ", 1)
                _AlertBanner(
                    self._alert_scroll,
                    icon=parts[0],
                    headline=f"{parts[1] if len(parts) > 1 else name}  ({cat.count}×)",
                    body=fix,
                    color=RED if cat.count > 1 else AMBER,
                ).grid(row=i, column=0, sticky="ew", pady=(0, 6))
        else:
            ctk.CTkLabel(self._alert_scroll,
                          text="✓  No errors detected. Everything ran smoothly.",
                          font=("", 12), text_color=GREEN).grid(
                row=0, column=0, sticky="w", padx=4, pady=8)

        # Recent sessions
        for w in self._sessions_scroll.winfo_children():
            w.destroy()
        profiles = getattr(sf, "session_profiles", [])
        for i, p in enumerate(sorted(profiles,
                                      key=lambda x: getattr(x, "duration_s", 0),
                                      reverse=True)):
            er2   = getattr(p, "error_rate",  0.0)
            title = getattr(p, "title", "") or getattr(p, "session_id", "—")
            mode  = getattr(p, "agent_mode", "")
            turns = getattr(p, "n_turns", 0)
            dur2  = getattr(p, "duration_s", 0.0)
            pill_text, pill_col = _status_pill(er2)
            _SessionCard(
                self._sessions_scroll,
                title=title[:50], subtitle=_fmt_dur(dur2),
                pill_text=pill_text, pill_color=pill_col,
                turns=turns, mode=mode,
            ).grid(row=i, column=0, sticky="ew", pady=(0, 6))


class _ConversationsView(ctk.CTkScrollableFrame):
    """All sessions as expandable story cards."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, fg_color=BG, **kw)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Your Conversations",
                     font=("", 20, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 4))

        self._subtitle = ctk.CTkLabel(
            self, text="", font=("", 11), text_color=MUTED)
        self._subtitle.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.grid(row=2, column=0, sticky="ew", padx=20)
        self._container.columnconfigure(0, weight=1)

    def fill(self, result, reporter) -> None:
        for w in self._container.winfo_children():
            w.destroy()

        if result is None:
            return

        sf = result.session_flow
        ec = result.error_categories
        tb = result.time_bottlenecks
        profiles = sorted(getattr(sf, "session_profiles", []),
                          key=lambda p: getattr(p, "duration_s", 0), reverse=True)

        self._subtitle.configure(
            text=f"{len(profiles)} conversation{'s' if len(profiles) != 1 else ''} found")

        # Build turn lookup for per-turn detail
        turn_lookup: dict = {}
        if reporter:
            for t in getattr(reporter, "_turns", []):
                turn_lookup.setdefault(t.session_id, []).append(t)

        for i, p in enumerate(profiles):
            sid    = getattr(p, "session_id", "")
            title  = getattr(p, "title", "") or sid
            mode   = getattr(p, "agent_mode", "")
            n      = getattr(p, "n_turns", 0)
            er     = getattr(p, "error_rate", 0.0)
            dur    = getattr(p, "duration_s", 0.0)

            pill_text, pill_col = _status_pill(er)

            card = ctk.CTkFrame(self._container, fg_color=CARD,
                                 corner_radius=12, border_width=1,
                                 border_color=BORDER)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 12))
            card.columnconfigure(0, weight=1)

            # Card header
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
            hdr.columnconfigure(0, weight=1)

            ctk.CTkLabel(hdr, text=title, font=("", 14, "bold"),
                         text_color=TEXT, anchor="w").grid(
                row=0, column=0, sticky="w")

            pill = ctk.CTkFrame(hdr, fg_color=_hex_20(pill_col),
                                 corner_radius=8)
            pill.grid(row=0, column=1, padx=(8, 0))
            ctk.CTkLabel(pill, text=pill_text, font=("", 9, "bold"),
                         text_color=pill_col).pack(padx=10, pady=3)

            # Meta row
            meta = ctk.CTkFrame(card, fg_color="transparent")
            meta.grid(row=1, column=0, sticky="w", padx=16, pady=(4, 12))
            for txt, col in (
                (_fmt_dur(dur), MUTED),
                (f"{n} turn{'s' if n != 1 else ''}", MUTED),
                (mode, DIM),
                (sid[:24], DIM),
            ):
                ch = ctk.CTkFrame(meta, fg_color=SURFACE, corner_radius=6)
                ch.pack(side="left", padx=(0, 6))
                ctk.CTkLabel(ch, text=txt, font=("", 9),
                             text_color=col).pack(padx=8, pady=3)

            # Per-turn mini list
            turns = turn_lookup.get(sid, [])
            if turns:
                sep = ctk.CTkFrame(card, height=1, fg_color=BORDER)
                sep.grid(row=2, column=0, sticky="ew", padx=16)
                for j, t in enumerate(
                    sorted(turns, key=lambda x: x.timestamp)
                ):
                    bg = _hex_08(RED) if t.error_text else "transparent"
                    row_f = ctk.CTkFrame(card, fg_color=bg)
                    row_f.grid(row=3 + j, column=0, sticky="ew",
                               padx=16, pady=2)
                    row_f.columnconfigure(1, weight=1)

                    icon = "✗" if t.error_text else "✓"
                    ic   = RED if t.error_text else GREEN
                    ctk.CTkLabel(row_f, text=icon, font=("", 11),
                                 text_color=ic, width=20).grid(
                        row=0, column=0, padx=(8, 4), pady=4)

                    q = t.user_query or "—"
                    ctk.CTkLabel(row_f, text=q[:80],
                                 font=("", 10), text_color=TEXT,
                                 anchor="w").grid(
                        row=0, column=1, sticky="w")

                    ctk.CTkLabel(row_f, text=_fmt_dur(t.duration_seconds),
                                 font=("", 9), text_color=MUTED).grid(
                        row=0, column=2, padx=(0, 12))

                ctk.CTkFrame(card, height=1,
                             fg_color="transparent").grid(row=3 + len(turns),
                                                           column=0, pady=4)


class _ProblemsView(ctk.CTkScrollableFrame):
    """Plain-language problem cards."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, fg_color=BG, **kw)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Problems",
                     font=("", 20, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 4))

        self._subtitle = ctk.CTkLabel(
            self, text="", font=("", 11), text_color=MUTED)
        self._subtitle.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.grid(row=2, column=0, sticky="ew", padx=20)
        self._container.columnconfigure(0, weight=1)

    def fill(self, result, reporter) -> None:
        for w in self._container.winfo_children():
            w.destroy()

        if result is None:
            return

        ec = result.error_categories
        active = [c for c in ec.categories if c.count > 0]
        self._subtitle.configure(
            text=f"{len(active)} issue type{'s' if len(active) != 1 else ''} found  ·  "
                 f"{ec.error_turns} affected requests out of {ec.total_turns}")

        if not active:
            ctk.CTkLabel(self._container,
                          text="🎉  No problems detected! Your agent ran perfectly.",
                          font=("", 14), text_color=GREEN).grid(
                row=0, column=0, sticky="w", padx=4, pady=20)
            return

        for i, cat in enumerate(sorted(active, key=lambda c: -c.count)):
            example = cat.example_messages[0] if cat.example_messages else ""
            _ProblemCard(self._container, cat.category,
                         cat.count, example).grid(
                row=i, column=0, sticky="ew", pady=(0, 12))


class _TipsView(ctk.CTkScrollableFrame):
    """Actionable recommendation cards parsed from the desktop report."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, fg_color=BG, **kw)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Tips  &  Next Steps",
                     font=("", 20, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(self, text="Prioritised actions to improve your agent's performance.",
                     font=("", 11), text_color=MUTED).grid(
            row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.grid(row=2, column=0, sticky="ew", padx=20)
        self._container.columnconfigure(0, weight=1)

    def fill(self, result, reporter) -> None:
        for w in self._container.winfo_children():
            w.destroy()

        if result is None or reporter is None:
            return

        # Try to get recommendations from desktop report
        try:
            md = reporter.render_desktop(result)
        except Exception:
            md = ""

        recs = _parse_recommendations(md)
        if not recs:
            # Fallback: generate from error categories
            ec = result.error_categories
            recs = []
            for i, cat in enumerate([c for c in ec.categories if c.count > 0]):
                pri = "P0" if i == 0 else "P1" if i == 1 else "P2"
                fix = _ERROR_FIX.get(cat.category, "Review error logs.")
                recs.append({"priority": pri, "fix": fix,
                             "effort": "Low", "impact": "High"})

        for i, r in enumerate(recs):
            _TipCard(
                self._container,
                priority=r.get("priority", "P2"),
                fix=r.get("fix", "—"),
                effort=r.get("effort", ""),
                impact=r.get("impact", ""),
            ).grid(row=i, column=0, sticky="ew", pady=(0, 10))

        if not recs:
            ctk.CTkLabel(self._container,
                          text="✓  Nothing urgent. Keep monitoring your agent's performance.",
                          font=("", 13), text_color=GREEN).grid(
                row=0, column=0, sticky="w", padx=4, pady=20)


# ── Numbers view helpers ──────────────────────────────────────────────────────

def _jstats(parent: ctk.CTkFrame,
            stats: list[tuple[str, str, str]]) -> None:
    """Render alternating label:value rows into parent."""
    parent.columnconfigure(1, weight=1)
    for i, (label, value, color) in enumerate(stats):
        bg = SURFACE if i % 2 == 0 else "transparent"
        f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        f.grid(row=i, column=0, columnspan=2, sticky="ew")
        f.columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label, font=("", 9), text_color=DIM,
                     anchor="w").grid(row=0, column=0, padx=(10, 6), pady=3, sticky="w")
        ctk.CTkLabel(f, text=str(value), font=("", 9, "bold"),
                     text_color=color, anchor="e").grid(
            row=0, column=1, padx=(0, 10), pady=3, sticky="e")


def _jtable(parent: ctk.CTkFrame,
            headers: list[str],
            rows: list[list],
            start_row: int = 0) -> None:
    """Render a styled table into parent starting at start_row."""
    n = len(headers)
    for j in range(n):
        parent.columnconfigure(j, weight=1)
    hdr_f = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0)
    hdr_f.grid(row=start_row, column=0, columnspan=n, sticky="ew")
    for j, h in enumerate(headers):
        hdr_f.columnconfigure(j, weight=1)
        ctk.CTkLabel(hdr_f, text=h, font=("", 8, "bold"),
                     text_color=MUTED, anchor="w").grid(
            row=0, column=j, padx=8, pady=3, sticky="w")
    for i, row in enumerate(rows):
        bg = CARD if i % 2 == 0 else _hex_08(BLUE)
        rf = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        rf.grid(row=start_row + i + 1, column=0, columnspan=n, sticky="ew")
        for j, cell in enumerate(row):
            s = str(cell)
            col = (RED   if any(w in s.lower() for w in ("err", "fail", "100%")) else
                   GREEN if any(w in s.lower() for w in ("ok", "100%", "yes")) else TEXT)
            rf.columnconfigure(j, weight=1)
            ctk.CTkLabel(rf, text=s, font=("", 9), text_color=col,
                         anchor="w").grid(row=0, column=j, padx=8, pady=2, sticky="w")


class _NumbersView(ctk.CTkScrollableFrame):
    """All-data dashboard: 8 sections covering every metric domain."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, fg_color=BG, **kw)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Numbers  —  All Data",
                     font=("", 20, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(
            self, text="Every metric the analyzer collected, organized by domain.",
            font=("", 11), text_color=MUTED).grid(
            row=1, column=0, sticky="w", padx=24, pady=(0, 12))

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 24))
        self._body.columnconfigure(0, weight=1)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _section(self, title: str, r_ref: list) -> ctk.CTkFrame:
        """Add a titled card section and return its content frame."""
        hdr = ctk.CTkFrame(self._body, fg_color="transparent")
        hdr.grid(row=r_ref[0], column=0, sticky="ew", pady=(14, 4))
        hdr.columnconfigure(1, weight=1)
        ctk.CTkFrame(hdr, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="ew", ipadx=16, padx=(0, 8))
        ctk.CTkLabel(hdr, text=title, font=("", 11, "bold"),
                     text_color=BLUE).grid(row=0, column=1, sticky="w")
        ctk.CTkFrame(hdr, height=1, fg_color=BORDER).grid(
            row=0, column=2, sticky="ew", ipadx=40, padx=(8, 0))
        hdr.columnconfigure(2, weight=1)
        r_ref[0] += 1

        cf = ctk.CTkFrame(self._body, fg_color=CARD, corner_radius=10)
        cf.grid(row=r_ref[0], column=0, sticky="ew")
        cf.columnconfigure(0, weight=1)
        r_ref[0] += 1
        return cf

    def _two_col(self, title: str, r_ref: list) -> tuple:
        """Section split into (left_stats_frame, right_table_frame)."""
        cf = self._section(title, r_ref)
        cf.columnconfigure(0, weight=1)
        cf.columnconfigure(1, weight=0)
        cf.columnconfigure(2, weight=1)
        left = ctk.CTkFrame(cf, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.columnconfigure(1, weight=1)
        ctk.CTkFrame(cf, width=1, fg_color=BORDER).grid(
            row=0, column=1, sticky="ns", pady=8)
        right = ctk.CTkFrame(cf, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(0, weight=1)
        return left, right

    # ── fill ─────────────────────────────────────────────────────────────────

    def fill(self, result, reporter) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        if result is None:
            return

        r = [0]   # mutable row counter shared with helpers
        dh  = result.data_health
        qt  = result.quality_trends
        cp  = result.correction_patterns
        tb  = result.time_bottlenecks
        tu  = result.token_usage
        lp  = result.llm_performance
        ts  = result.tool_success
        cd  = result.content_delivery
        ec  = result.error_categories
        sf  = result.session_flow
        uq  = result.user_queries

        # ── 1. Data Health ────────────────────────────────────────────
        cf = self._section("Data Health", r)
        _jstats(cf, [
            ("Total turns analyzed",    str(dh.total_turns),       TEXT),
            ("Date range",              f"{dh.date_range[0].strftime('%Y-%m-%d')} → {dh.date_range[1].strftime('%Y-%m-%d')}"
                                         if dh.date_range else "—", MUTED),
            ("Real sessions",           str(sf.total_real_sessions),  TEXT),
            ("Heartbeat sessions",      str(sf.total_heartbeat_sessions), MUTED),
            ("Skipped (malformed)",     str(dh.skipped_records),
                                         RED if dh.skipped_records > 0 else MUTED),
            ("Low-data weeks",          ", ".join(dh.weeks_with_low_data) or "None",
                                         AMBER if dh.weeks_with_low_data else GREEN),
        ])

        # ── 2. Quality & Trends ───────────────────────────────────────
        q  = qt.overall_mean
        cr = cp.baseline_correction_rate
        left, right = self._two_col("Quality & Trends", r)
        trend_map = {"improving": "↑ Improving", "degrading": "↓ Degrading",
                     "flat": "→ Flat", "insufficient_data": "? Not enough data"}
        _jstats(left, [
            ("Overall mean quality",  f"{q:.3f}",
                                       GREEN if q >= 0.7 else AMBER if q >= 0.4 else RED),
            ("Trend",                 trend_map.get(qt.trend_direction, "—"), MUTED),
            ("Best week",             qt.best_week  or "—", GREEN),
            ("Worst week",            qt.worst_week or "—", RED if qt.worst_week else MUTED),
            ("Correction rate",       f"{cr:.1%}",
                                       AMBER if cr > 0.2 else MUTED),
            ("Corrected turns",       str(cp.total_corrected_turns), MUTED),
        ])
        if qt.weeks:
            ctk.CTkLabel(right, text="Weekly Breakdown",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            _jtable(right,
                    ["Week", "Turns", "Quality", "Corrections"],
                    [[w.week_tag, w.n_turns, f"{w.mean_quality:.3f}",
                      w.n_follow_up_corrections] for w in qt.weeks],
                    start_row=1)

        # ── 3. Timing ─────────────────────────────────────────────────
        left, right = self._two_col("Timing & Speed", r)
        verdict_map = {
            "slower_is_worse": "Slower = worse quality",
            "slower_is_better": "Slower = better quality",
            "no_correlation": "No speed-quality link",
        }
        _jstats(left, [
            ("Turns timed",       f"{tb.n_turns_with_timing} / {tb.n_turns_total}", MUTED),
            ("Min duration",      _fmt_dur(tb.min_duration_s),  GREEN),
            ("Median duration",   _fmt_dur(tb.median_duration_s), MUTED),
            ("Mean duration",     _fmt_dur(tb.mean_duration_s),  MUTED),
            ("p90 duration",      _fmt_dur(tb.p90_duration_s),   AMBER),
            ("Max duration",      _fmt_dur(tb.max_duration_s),   RED),
            ("Total net compute", _fmt_dur(tb.total_time_s),     MUTED),
            ("Speed/quality",     verdict_map.get(tb.speed_quality_verdict,
                                                   tb.speed_quality_verdict), MUTED),
            ("Slow half quality", f"{tb.slow_quartile_mean_quality:.3f}",
                                   RED if tb.slow_quartile_mean_quality < 0.4 else MUTED),
            ("Fast half quality", f"{tb.fast_half_mean_quality:.3f}",
                                   GREEN if tb.fast_half_mean_quality >= 0.7 else MUTED),
        ])
        if tb.slowest_turns:
            ctk.CTkLabel(right, text="Slowest Turns",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            slow_rows = []
            for t in tb.slowest_turns:
                st = "ERR" if t.has_error else ("OK" if t.task_completed else "INC")
                slow_rows.append([t.turn_id[:22], _fmt_dur(t.duration_seconds),
                                   st, f"{t.quality:.2f}", t.n_messages])
            _jtable(right, ["Turn ID", "Duration", "Status", "Quality", "Msgs"],
                    slow_rows, start_row=1)

        # ── 4. Tokens & Cost ──────────────────────────────────────────
        left, right = self._two_col("Tokens & Cost", r)
        _jstats(left, [
            ("Total input tokens",  f"{tu.total_input_tokens:,}",  MUTED),
            ("Total output tokens", f"{tu.total_output_tokens:,}", MUTED),
            ("Total tokens",        f"{tu.total_tokens:,}",        TEXT),
            ("Mean tokens / turn",  f"{tu.mean_tokens_per_turn:.0f}", MUTED),
            ("Median tokens / turn",f"{tu.median_tokens_per_turn:.0f}", MUTED),
            ("Max tokens",          f"{tu.max_tokens_per_turn:,}", MUTED),
            ("Near-limit turns",    str(tu.turns_near_limit),
                                     RED if tu.turns_near_limit > 0 else MUTED),
            ("Mean context %",      f"{tu.mean_usage_percent:.1%}", MUTED),
            ("p90 context %",       f"{tu.p90_usage_percent:.1%}",
                                     AMBER if tu.p90_usage_percent > 0.8 else MUTED),
            ("Estimated cost",      f"${tu.estimated_total_cost:.4f}" if tu.estimated_total_cost else "—",
                                     AMBER if tu.estimated_total_cost > 0 else MUTED),
        ])
        if tu.model_summary:
            ctk.CTkLabel(right, text="By Model",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            _jtable(right,
                    ["Model", "Turns", "Tokens", "Avg Tok", "Ctx%", "Cost"],
                    [[m.model_name[:18], m.n_turns, f"{m.total_tokens:,}",
                      f"{m.mean_total_tokens:.0f}",
                      f"{m.mean_usage_percent:.1%}",
                      f"${m.estimated_cost:.4f}" if m.estimated_cost else "—"]
                     for m in tu.model_summary],
                    start_row=1)

        # ── 5. LLM Performance ────────────────────────────────────────
        cf = self._section("LLM Performance", r)
        has_lp = lp.n_turns_with_timing > 0
        stats_lp = [
            ("Turns with LLM timing",    str(lp.n_turns_with_timing), MUTED),
            ("Median total latency",      f"{lp.total_latency.median:.0f} ms" if has_lp else "—", MUTED),
            ("p90 total latency",         f"{lp.total_latency.p90:.0f} ms"    if has_lp else "—",
                                           AMBER if has_lp and lp.total_latency.p90 > 5000 else MUTED),
            ("Max latency",               f"{lp.total_latency.max:.0f} ms"    if has_lp else "—",
                                           RED   if has_lp and lp.total_latency.max > 30000 else MUTED),
            ("Median TTFT",               f"{lp.ttft.median:.0f} ms"          if has_lp else "—", MUTED),
            ("Median TPOT",               f"{lp.tpot.median:.0f} ms"          if has_lp else "—", MUTED),
            ("Output throughput",         f"{lp.mean_output_tokens_per_second:.1f} tok/s" if has_lp else "—", MUTED),
            ("Slow prompt processing",    str(lp.slow_prompt_processing_count), AMBER if lp.slow_prompt_processing_count > 0 else MUTED),
            ("Slow generation",           str(lp.slow_generation_count),        AMBER if lp.slow_generation_count > 0 else MUTED),
            ("High-latency errors",       str(lp.high_latency_error_count),     RED   if lp.high_latency_error_count > 0 else MUTED),
        ]
        _jstats(cf, stats_lp)

        # ── 6. Tools & Execution ──────────────────────────────────────
        left, right = self._two_col("Tools & Execution", r)
        _jstats(left, [
            ("Total tool calls",    str(ts.total_tool_calls),   TEXT),
            ("Total failures",      str(ts.total_tool_failures),
                                     RED if ts.total_tool_failures > 0 else MUTED),
            ("Success rate",        f"{ts.overall_success_rate:.1%}" if ts.total_tool_calls else "—",
                                     GREEN if ts.overall_success_rate >= 0.9 else AMBER),
            ("Recovery turns",      str(ts.recovery_turns),     MUTED),
            ("Recovery rate",       f"{ts.recovery_rate:.1%}" if ts.recovery_turns else "—", MUTED),
        ])
        if ts.per_tool_stats:
            ctk.CTkLabel(right, text="Per Tool",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            _jtable(right,
                    ["Tool", "Calls", "Fails", "Rate"],
                    [[t.tool_name[:20], t.total_calls, t.total_failures,
                      f"{t.success_rate:.1%}"]
                     for t in ts.per_tool_stats[:10]],
                    start_row=1)
        else:
            ctk.CTkLabel(right, text="No tool calls recorded.",
                         font=("", 9), text_color=DIM).grid(
                row=0, column=0, padx=8, pady=8, sticky="w")

        # ── 7. Content Delivery ───────────────────────────────────────
        left, right = self._two_col("Content Delivery", r)
        _jstats(left, [
            ("Productive turns",     f"{cd.productive_turns} / {cd.total_turns} ({cd.productivity_rate:.1%})",
                                      GREEN if cd.productivity_rate > 0.5 else AMBER),
            ("Files delivered",      str(cd.total_files_delivered), TEXT),
            ("Avg files / turn",     f"{cd.avg_files_per_turn:.2f}", MUTED),
            ("Avg files / session",  f"{cd.avg_files_per_session:.2f}", MUTED),
            ("Sessions with files",  str(cd.sessions_with_files), MUTED),
            ("Silent successes",     str(cd.silent_success_turns), MUTED),
            ("Tool→no-content rate", f"{cd.tool_to_content_rate:.1%}", MUTED),
            ("Mean response length", f"{cd.response_length_mean:.0f} chars", MUTED),
            ("Median resp. length",  f"{cd.response_length_median} chars",    MUTED),
            ("Max resp. length",     f"{cd.response_length_max} chars",       MUTED),
        ])
        if cd.response_buckets:
            ctk.CTkLabel(right, text="Response Length Buckets",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            _jtable(right,
                    ["Bucket", "Chars", "Turns", "Quality"],
                    [[b.label, b.char_range, b.n_turns,
                      f"{b.mean_quality:.3f}"] for b in cd.response_buckets],
                    start_row=1)

        # ── 8. User Queries ───────────────────────────────────────────
        left, right = self._two_col("User Queries", r)
        _jstats(left, [
            ("Total queries",         str(uq.total_turns), TEXT),
            ("Min length",            f"{uq.length_min} chars",    MUTED),
            ("Median length",         f"{uq.length_median} chars", MUTED),
            ("Mean length",           f"{uq.length_mean:.0f} chars", MUTED),
            ("p90 length",            f"{uq.length_p90:.0f} chars", MUTED),
            ("Max length",            f"{uq.length_max} chars",    MUTED),
            ("Most common type",      uq.most_common_type or "—",  MUTED),
            ("Best quality type",     uq.best_quality_type or "—", GREEN),
            ("Len vs duration corr.", f"r = {uq.length_vs_duration_correlation:.3f}", MUTED),
            ("Len vs tokens corr.",   f"r = {uq.length_vs_tokens_correlation:.3f}",   MUTED),
        ])
        if uq.query_type_distribution:
            ctk.CTkLabel(right, text="Query Types",
                         font=("", 8, "bold"), text_color=DIM).grid(
                row=0, column=0, sticky="w", pady=(0, 2))
            _jtable(right,
                    ["Type", "Count", "Quality", "Duration", "Tokens"],
                    [[q2.type_label, q2.count, f"{q2.mean_quality:.3f}",
                      _fmt_dur(q2.mean_duration), f"{q2.mean_tokens:.0f}"]
                     for q2 in uq.query_type_distribution],
                    start_row=1)


# ── Nav sidebar ───────────────────────────────────────────────────────────────

_NAV_ITEMS = [
    ("🏠", "Summary",       "_summary"),
    ("💬", "Conversations", "_convos"),
    ("⚠️", "Problems",      "_problems"),
    ("💡", "Tips",          "_tips"),
    ("📊", "Numbers",       "_numbers"),
]


class ModernApp(ctk.CTkToplevel):
    """Consumer-friendly analytics window."""

    def __init__(self, parent, result=None, reporter=None, loader=None,
                 **kw) -> None:
        super().__init__(parent, **kw)
        self.title("✨  Agent Journal  —  TraceHound")
        self.geometry("1280x820")
        self.minsize(900, 600)
        self.configure(fg_color=BG)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # ── Sidebar nav ──────────────────────────────────────────────────
        nav = ctk.CTkFrame(self, width=NAV_W, fg_color=SURFACE,
                           corner_radius=0)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.rowconfigure(len(_NAV_ITEMS) + 2, weight=1)
        nav.grid_propagate(False)
        nav.columnconfigure(0, weight=1)

        # Brand
        ctk.CTkLabel(nav, text="✨", font=("", 22)).grid(
            row=0, column=0, pady=(22, 2))
        ctk.CTkLabel(nav, text="Journal", font=("", 11, "bold"),
                     text_color=BLUE).grid(row=1, column=0, pady=(0, 16))

        # Separator
        ctk.CTkFrame(nav, height=1, fg_color=BORDER).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 10))

        self._nav_btns: list[ctk.CTkButton] = []
        self._active_key = _NAV_ITEMS[0][2]

        for i, (icon, label, key) in enumerate(_NAV_ITEMS):
            btn = ctk.CTkButton(
                nav,
                text=f"{icon}\n{label}",
                font=("", 10),
                height=64,
                corner_radius=10,
                fg_color="transparent",
                hover_color=CARD,
                text_color=MUTED,
                anchor="center",
                command=lambda k=key: self._show(k),
            )
            btn.grid(row=i + 3, column=0, sticky="ew",
                     padx=8, pady=3)
            self._nav_btns.append(btn)

        # ── Content ──────────────────────────────────────────────────────
        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        # Build views — NOT pre-gridded; _show() manages visibility
        self._summary  = _SummaryView(content)
        self._convos   = _ConversationsView(content)
        self._problems = _ProblemsView(content)
        self._tips     = _TipsView(content)
        self._numbers  = _NumbersView(content)

        self._all_views: dict[str, ctk.CTkFrame] = {
            "_summary":  self._summary,
            "_convos":   self._convos,
            "_problems": self._problems,
            "_tips":     self._tips,
            "_numbers":  self._numbers,
        }

        # Grid all views into the same cell; _show() hides/reveals them
        for v in self._all_views.values():
            v.grid(row=0, column=0, sticky="nsew")
            v.grid_remove()

        self._show("_summary")

        # Fill data if provided
        if result is not None:
            self.load(result, reporter, loader)

    def load(self, result, reporter, loader=None) -> None:
        """Populate all views with analysis data."""
        self._summary .fill(result, reporter)
        self._convos  .fill(result, reporter)
        self._problems.fill(result, reporter)
        self._tips    .fill(result, reporter)
        self._numbers .fill(result, reporter)

    def _show(self, key: str) -> None:
        self._active_key = key

        for k, v in self._all_views.items():
            if k == key:
                v.grid(row=0, column=0, sticky="nsew")
            else:
                v.grid_remove()

        for i, (_, _, k) in enumerate(_NAV_ITEMS):
            active = k == key
            self._nav_btns[i].configure(
                fg_color=CARD if active else "transparent",
                text_color=TEXT if active else MUTED,
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hex_20(color: str) -> str:
    """Return a very transparent version (approx 20% opacity blended with CARD bg)."""
    # Simple approximation: shift each channel toward CARD (#1c2128)
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        br, bg_, bb = 0x1c, 0x21, 0x28
        r2 = br + (r - br) * 20 // 100
        g2 = bg_ + (g - bg_) * 20 // 100
        b2 = bb + (b - bb) * 20 // 100
        return f"#{r2:02x}{g2:02x}{b2:02x}"
    except Exception:
        return CARD


def _hex_12(color: str) -> str:
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        br, bg_, bb = 0x1c, 0x21, 0x28
        r2 = br + (r - br) * 12 // 100
        g2 = bg_ + (g - bg_) * 12 // 100
        b2 = bb + (b - bb) * 12 // 100
        return f"#{r2:02x}{g2:02x}{b2:02x}"
    except Exception:
        return CARD


def _hex_08(color: str) -> str:
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        br, bg_, bb = 0x1c, 0x21, 0x28
        r2 = br + (r - br) * 8 // 100
        g2 = bg_ + (g - bg_) * 8 // 100
        b2 = bb + (b - bb) * 8 // 100
        return f"#{r2:02x}{g2:02x}{b2:02x}"
    except Exception:
        return CARD


def _parse_recommendations(markdown: str) -> list[dict]:
    """Extract prioritised fix rows from a markdown Priority Fixes table."""
    recs: list[dict] = []
    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            if in_table:
                break
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if not cells:
            continue
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue  # separator row
        lower = stripped.lower()
        if not in_table:
            if "priority" in lower or "fix" in lower:
                in_table = True
            continue
        if len(cells) >= 2:
            pri    = cells[0] if cells else "P2"
            fix    = cells[1] if len(cells) > 1 else "—"
            effort = cells[2] if len(cells) > 2 else ""
            impact = cells[3] if len(cells) > 3 else ""
            if pri.startswith("P") and fix:
                recs.append({"priority": pri, "fix": fix,
                             "effort": effort, "impact": impact})
    return recs
