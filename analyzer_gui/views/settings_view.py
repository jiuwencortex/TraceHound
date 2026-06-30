# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SettingsView — thresholds, re-run, and export controls."""

from __future__ import annotations

import json
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Callable

import customtkinter as ctk


class SettingsView(ctk.CTkFrame):
    """Threshold sliders + Re-Run / Export controls."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Settings", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        # Scroll container so it looks fine at any height
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        scroll.columnconfigure(0, weight=1)

        row = 0

        # ── Analysis parameters ──────────────────────────────────────
        ctk.CTkLabel(scroll, text="Analysis Parameters", font=("", 14, "bold")).grid(
            row=row, column=0, sticky="w", pady=(8, 4)
        )
        row += 1

        params = ctk.CTkFrame(scroll)
        params.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        params.columnconfigure(1, weight=1)
        row += 1

        # Max weeks
        ctk.CTkLabel(params, text="Max weeks to load:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(12, 8), pady=8
        )
        self._max_weeks_var = tk.IntVar(value=8)
        self._max_weeks_entry = ctk.CTkEntry(params, textvariable=self._max_weeks_var, width=70)
        self._max_weeks_entry.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=8)

        # Quality deficit threshold
        ctk.CTkLabel(params, text="Quality deficit threshold (0.01 – 0.50):", anchor="w").grid(
            row=1, column=0, sticky="w", padx=(12, 8), pady=8
        )
        self._qd_var = tk.DoubleVar(value=0.15)
        self._qd_lbl = ctk.CTkLabel(params, text="0.15", width=48)
        self._qd_lbl.grid(row=1, column=2, padx=8)
        self._qd_slider = ctk.CTkSlider(
            params, from_=0.01, to=0.50, number_of_steps=49,
            variable=self._qd_var, command=self._on_qd_change,
        )
        self._qd_slider.grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=8)

        # Correction lift threshold
        ctk.CTkLabel(params, text="Correction lift threshold (1.0 – 5.0):", anchor="w").grid(
            row=2, column=0, sticky="w", padx=(12, 8), pady=8
        )
        self._lift_var = tk.DoubleVar(value=1.5)
        self._lift_lbl = ctk.CTkLabel(params, text="1.50", width=48)
        self._lift_lbl.grid(row=2, column=2, padx=8)
        self._lift_slider = ctk.CTkSlider(
            params, from_=1.0, to=5.0, number_of_steps=40,
            variable=self._lift_var, command=self._on_lift_change,
        )
        self._lift_slider.grid(row=2, column=1, sticky="ew", padx=(0, 4), pady=8)

        # ── Re-run ───────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="Re-Run Analysis", font=("", 14, "bold")).grid(
            row=row, column=0, sticky="w", pady=(4, 4)
        )
        row += 1

        rerun_frame = ctk.CTkFrame(scroll)
        rerun_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1

        ctk.CTkLabel(
            rerun_frame,
            text="Apply the parameters above and re-analyse the currently loaded directory.",
            font=("", 11),
            text_color="gray60",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self._rerun_btn = ctk.CTkButton(
            rerun_frame, text="Re-Run Analysis",
            width=180, command=self._do_rerun,
        )
        self._rerun_btn.pack(anchor="w", padx=12, pady=(4, 10))

        # ── Export ───────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="Export", font=("", 14, "bold")).grid(
            row=row, column=0, sticky="w", pady=(4, 4)
        )
        row += 1

        export_frame = ctk.CTkFrame(scroll)
        export_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1

        ctk.CTkLabel(
            export_frame,
            text="Save the last analysis result to a file.",
            font=("", 11),
            text_color="gray60",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 4))

        self._export_json_btn = ctk.CTkButton(
            export_frame, text="Export JSON",
            width=160, command=self._do_export_json,
        )
        self._export_json_btn.grid(row=1, column=0, padx=12, pady=(4, 10))

        self._export_text_btn = ctk.CTkButton(
            export_frame, text="Export Text (Verbose)",
            width=180, command=self._do_export_text,
        )
        self._export_text_btn.grid(row=1, column=1, padx=4, pady=(4, 10))

        # ── Appearance ───────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="Appearance", font=("", 14, "bold")).grid(
            row=row, column=0, sticky="w", pady=(4, 4)
        )
        row += 1

        appear_frame = ctk.CTkFrame(scroll)
        appear_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1

        ctk.CTkLabel(appear_frame, text="Color theme:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=8
        )
        self._theme_var = tk.StringVar(value="Dark")
        theme_menu = ctk.CTkOptionMenu(
            appear_frame,
            values=["Dark", "Light", "System"],
            variable=self._theme_var,
            command=self._on_theme_change,
        )
        theme_menu.grid(row=0, column=1, padx=8, pady=8)

        # State
        self._result = None
        self._loader = None
        self._reporter = None
        self._rerun_callback: Callable | None = None

    # ------------------------------------------------------------------
    # Callbacks from sliders
    # ------------------------------------------------------------------

    def _on_qd_change(self, value: float) -> None:
        self._qd_lbl.configure(text=f"{value:.2f}")

    def _on_lift_change(self, value: float) -> None:
        self._lift_lbl.configure(text=f"{value:.2f}")

    def _on_theme_change(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)

    # ------------------------------------------------------------------
    # Public API for app.py
    # ------------------------------------------------------------------

    def set_rerun_callback(self, cb: Callable) -> None:
        """Register callback(log_dir, max_weeks, qd_thresh, lift_thresh)."""
        self._rerun_callback = cb

    def get_thresholds(self) -> tuple[int, float, float]:
        """Return (max_weeks, qd_threshold, lift_threshold)."""
        try:
            mw = int(self._max_weeks_var.get())
        except (tk.TclError, ValueError):
            mw = 8
        return mw, self._qd_var.get(), self._lift_var.get()

    def set_max_weeks(self, value: int) -> None:
        self._max_weeks_var.set(value)

    # ------------------------------------------------------------------

    def refresh(self, result, loader, reporter) -> None:
        self._result = result
        self._loader = loader
        self._reporter = reporter

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _do_rerun(self) -> None:
        if self._rerun_callback is None:
            messagebox.showinfo("Re-Run", "No analysis loaded yet.")
            return
        mw, qd, lift = self.get_thresholds()
        self._rerun_callback(mw, qd, lift)

    def _do_export_json(self) -> None:
        if self._result is None or self._reporter is None:
            messagebox.showinfo("Export", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*")],
            title="Export JSON",
        )
        if not path:
            return
        try:
            text = self._reporter.render_json(self._result)
            Path(path).write_text(text, encoding="utf-8")
            messagebox.showinfo("Export", f"Saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export Error", str(exc))

    def _do_export_text(self) -> None:
        if self._result is None or self._reporter is None or self._loader is None:
            messagebox.showinfo("Export", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*")],
            title="Export Verbose Text",
        )
        if not path:
            return
        try:
            text = self._reporter.render_verbose(self._result, self._loader)
            Path(path).write_text(text, encoding="utf-8")
            messagebox.showinfo("Export", f"Saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export Error", str(exc))
