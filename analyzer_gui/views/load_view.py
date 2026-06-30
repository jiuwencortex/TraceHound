# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""LoadView — log directory chooser, run button, and progress indicator."""

from __future__ import annotations

import tkinter.filedialog as filedialog
from pathlib import Path
from typing import Callable

import customtkinter as ctk


class LoadView(ctk.CTkFrame):
    """First screen shown on launch.

    Exposes a ``start_analysis`` callable that the app wires up to the
    AnalysisBackend after construction.
    """

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._on_run: Callable | None = None

        # Centred card
        card = ctk.CTkFrame(self, width=480)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(card, text="TraceHound", font=("", 32, "bold")).pack(
            padx=30, pady=(30, 4)
        )
        ctk.CTkLabel(
            card,
            text="jiuwenswarm session log analyser",
            font=("", 13),
            text_color="gray60",
        ).pack(padx=30, pady=(0, 24))

        # Directory row
        dir_row = ctk.CTkFrame(card, fg_color="transparent")
        dir_row.pack(padx=30, fill="x")
        ctk.CTkLabel(dir_row, text="Log directory:", font=("", 12)).pack(
            side="left", padx=(0, 8)
        )
        self._dir_entry = ctk.CTkEntry(dir_row, width=240, placeholder_text="Path to .jiuwenswarm")
        self._dir_entry.pack(side="left", expand=True, fill="x")
        ctk.CTkButton(dir_row, text="Browse…", width=80, command=self._browse).pack(
            side="left", padx=(8, 0)
        )

        # Sessions row
        sess_row = ctk.CTkFrame(card, fg_color="transparent")
        sess_row.pack(padx=30, pady=(12, 0), fill="x")
        ctk.CTkLabel(sess_row, text="Max sessions:", font=("", 12)).pack(
            side="left", padx=(0, 8)
        )
        self._sessions_entry = ctk.CTkEntry(sess_row, width=80, placeholder_text="30")
        self._sessions_entry.insert(0, "30")
        self._sessions_entry.pack(side="left")

        # Run button
        self._run_btn = ctk.CTkButton(
            card,
            text="Run Analysis",
            font=("", 14, "bold"),
            height=40,
            command=self._on_run_clicked,
        )
        self._run_btn.pack(padx=30, pady=(20, 0), fill="x")

        # Progress bar (hidden until running)
        self._progress = ctk.CTkProgressBar(card, mode="indeterminate")
        self._progress.pack(padx=30, pady=(10, 0), fill="x")
        self._progress.set(0)

        # Status label
        self._status_lbl = ctk.CTkLabel(
            card, text="Ready.", font=("", 11), text_color="gray60"
        )
        self._status_lbl.pack(padx=30, pady=(6, 24))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_run_callback(self, callback: Callable) -> None:
        """Wire up the run button to the app's start_analysis method."""
        self._on_run = callback

    def prepopulate(self, log_dir: Path) -> None:
        """Pre-fill the directory entry (e.g. from --log-dir CLI arg)."""
        self._dir_entry.delete(0, "end")
        self._dir_entry.insert(0, str(log_dir))

    def set_busy(self, busy: bool) -> None:
        """Toggle progress bar and run button state."""
        if busy:
            self._run_btn.configure(state="disabled")
            self._progress.start()
        else:
            self._run_btn.configure(state="normal")
            self._progress.stop()
            self._progress.set(0)

    def set_status(self, message: str) -> None:
        self._status_lbl.configure(text=message)

    def get_log_dir(self) -> Path | None:
        text = self._dir_entry.get().strip()
        return Path(text) if text else None

    def get_max_sessions(self) -> int:
        try:
            return max(1, int(self._sessions_entry.get()))
        except ValueError:
            return 30

    def refresh(self, result, loader, reporter) -> None:
        """No-op: LoadView does not display analysis results."""
        pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Select jiuwenswarm log directory")
        if chosen:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, chosen)

    def _on_run_clicked(self) -> None:
        if self._on_run:
            self._on_run()
