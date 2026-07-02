# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""TraceHoundApp — root CTk window with nav rail and view container."""

from __future__ import annotations

import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from analyzer_gui.backend import AnalysisBackend
from analyzer_gui.views.desktop_report_view import DesktopReportView
from analyzer_gui.views.errors_view import ErrorsView
from analyzer_gui.views.load_view import LoadView
from analyzer_gui.views.overview_view import OverviewView
from analyzer_gui.views.quality_view import QualityView
from analyzer_gui.views.sessions_view import SessionsView
from analyzer_gui.views.settings_view import SettingsView
from analyzer_gui.views.timing_view import TimingView
from analyzer_gui.views.tokens_view import TokensView

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

_NAV_WIDTH = 160
_WIN_TITLE = "TraceHound"
_WIN_SIZE = "1280x800"

_NAV_ENTRIES = [
    ("Load",         "Ctrl+0", 0),
    ("Overview",     "Ctrl+1", 1),
    ("Quality",      "Ctrl+2", 2),
    ("Timing",       "Ctrl+3", 3),
    ("Errors",       "Ctrl+4", 4),
    ("Tokens & LLM", "Ctrl+5", 5),
    ("Sessions",     "Ctrl+6", 6),
    ("Desktop Rpt",  "Ctrl+7", 7),
    ("Settings",     "Ctrl+8", 8),
]


class TraceHoundApp(ctk.CTk):
    """Main application window."""

    def __init__(
        self,
        initial_log_dir: Optional[Path] = None,
        initial_max_sessions: int = 30,
    ) -> None:
        super().__init__()
        self.title(_WIN_TITLE)
        self.geometry(_WIN_SIZE)
        self.minsize(900, 600)

        self._backend = AnalysisBackend()
        self._current_log_dir: Optional[Path] = initial_log_dir
        self._last_result = None
        self._last_loader = None
        self._last_reporter = None

        # ── Layout ─────────────────────────────────────────────────────
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # Nav rail
        self._nav = ctk.CTkFrame(self, width=_NAV_WIDTH, corner_radius=0)
        self._nav.grid(row=0, column=0, sticky="nsew")
        self._nav.rowconfigure(len(_NAV_ENTRIES) + 1, weight=1)  # spacer row
        self._nav.grid_propagate(False)

        ctk.CTkLabel(
            self._nav, text=_WIN_TITLE, font=("", 16, "bold")
        ).grid(row=0, column=0, pady=(20, 12), padx=8)

        self._nav_buttons: list[ctk.CTkButton] = []
        for i, (label, shortcut, idx) in enumerate(_NAV_ENTRIES):
            btn = ctk.CTkButton(
                self._nav,
                text=f"{label}\n{shortcut}",
                font=("", 11),
                height=52,
                corner_radius=6,
                fg_color="transparent",
                hover_color=("gray75", "gray25"),
                anchor="w",
                command=lambda n=idx: self._show_view(n),
            )
            btn.grid(row=i + 1, column=0, sticky="ew", padx=8, pady=2)
            self._nav_buttons.append(btn)

        # Content area
        self._content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)

        # ── Views ──────────────────────────────────────────────────────
        self._load_view    = LoadView(self._content)
        self._overview     = OverviewView(self._content)
        self._quality      = QualityView(self._content)
        self._timing       = TimingView(self._content)
        self._errors       = ErrorsView(self._content)
        self._tokens       = TokensView(self._content)
        self._sessions     = SessionsView(self._content)
        self._desktop_rpt  = DesktopReportView(self._content)
        self._settings     = SettingsView(self._content)

        self._views = [
            self._load_view,
            self._overview,
            self._quality,
            self._timing,
            self._errors,
            self._tokens,
            self._sessions,
            self._desktop_rpt,
            self._settings,
        ]

        # Place all views in the same cell; only one shown at a time
        for view in self._views:
            view.grid(row=0, column=0, sticky="nsew")

        # Wire up callbacks
        self._load_view.set_run_callback(self._start_analysis)
        self._settings.set_rerun_callback(self._rerun_analysis)

        # Initial state: only Load visible; analysis views disabled
        self._disable_analysis_nav()
        self._show_view(0)

        # Pre-populate if CLI provided a directory
        if initial_log_dir:
            self._load_view.prepopulate(initial_log_dir)
        if initial_max_sessions != 30:
            self._settings.set_max_weeks(initial_max_sessions)

        # Keyboard shortcuts
        for i in range(9):
            self.bind(f"<Control-Key-{i}>", lambda e, n=i: self._show_view(n))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _show_view(self, index: int) -> None:
        if index >= len(self._views):
            return
        for view in self._views:
            view.grid_remove()
        self._views[index].grid()

        # Highlight active nav button
        for i, btn in enumerate(self._nav_buttons):
            if i == index:
                btn.configure(fg_color=("gray70", "gray30"))
            else:
                btn.configure(fg_color="transparent")

    def _disable_analysis_nav(self) -> None:
        """Grey out all nav buttons except Load (index 0)."""
        for i, btn in enumerate(self._nav_buttons):
            if i != 0:
                btn.configure(state="disabled")

    def _enable_analysis_nav(self) -> None:
        for btn in self._nav_buttons:
            btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Analysis orchestration
    # ------------------------------------------------------------------

    def _start_analysis(self) -> None:
        """Called by LoadView's Run button."""
        log_dir = self._load_view.get_log_dir()
        if not log_dir:
            messagebox.showwarning("No directory", "Please enter or browse for a log directory.")
            return
        if not log_dir.exists():
            messagebox.showerror("Not found", f"Directory does not exist:\n{log_dir}")
            return

        max_weeks = self._load_view.get_max_sessions()
        _, qd_thresh, lift_thresh = self._settings.get_thresholds()

        self._current_log_dir = log_dir
        self._run_backend(log_dir, max_weeks, qd_thresh, lift_thresh)

    def _rerun_analysis(self, max_weeks: int, qd_thresh: float, lift_thresh: float) -> None:
        """Called by SettingsView's Re-Run button."""
        if self._current_log_dir is None:
            messagebox.showinfo("Re-Run", "No log directory loaded yet.")
            return
        self._show_view(0)  # Switch to Load tab to show progress
        self._run_backend(self._current_log_dir, max_weeks, qd_thresh, lift_thresh)

    def _run_backend(
        self,
        log_dir: Path,
        max_weeks: int,
        qd_thresh: float,
        lift_thresh: float,
        skip_heartbeats: bool = True,
    ) -> None:
        if self._backend.is_running():
            return
        self._load_view.set_busy(True)
        self._load_view.set_status("Starting…")
        self._disable_analysis_nav()

        self._backend.run_async(
            log_dir=log_dir,
            max_weeks=max_weeks,
            quality_deficit_threshold=qd_thresh,
            correction_lift_threshold=lift_thresh,
            skip_heartbeats=skip_heartbeats,
            on_progress=lambda msg: self.after(0, self._load_view.set_status, msg),
            on_complete=lambda r, lo, rp: self.after(0, self._on_complete, r, lo, rp),
            on_error=lambda exc: self.after(0, self._on_error, exc),
        )

    def _on_complete(self, result, loader, reporter) -> None:
        self._last_result = result
        self._last_loader = loader
        self._last_reporter = reporter

        self._load_view.set_busy(False)
        self._load_view.set_status("Analysis complete.")
        self._enable_analysis_nav()

        # Refresh analysis views (skip LoadView at index 0)
        for view in self._views[1:]:
            view.refresh(result, loader, reporter)

        # Navigate to Overview automatically
        self._show_view(1)

    def _on_error(self, exc: Exception) -> None:
        self._load_view.set_busy(False)
        self._load_view.set_status(f"Error: {exc}")
        self._enable_analysis_nav()
        messagebox.showerror("Analysis Error", str(exc))
