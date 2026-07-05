# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""StatCard widget — a labelled metric card with a coloured left accent bar."""

from __future__ import annotations

import customtkinter as ctk

# Colour tokens used for the left accent bar
COLOR_GOOD    = "#27ae60"   # green
COLOR_WARN    = "#e67e22"   # orange
COLOR_BAD     = "#e74c3c"   # red
COLOR_NEUTRAL = "#4a90d9"   # steel blue (default)

_ACCENT_W = 5   # width of left border bar in pixels


class StatCard(ctk.CTkFrame):
    """A compact metric card: coloured left bar | title (small) / value (large).

    Visual structure
    ----------------
    ┌───┬──────────────────────┐
    │   │  TITLE               │
    │ ▌ │  VALUE               │  ← accent bar on left
    │   │                      │
    └───┴──────────────────────┘
    """

    def __init__(
        self,
        parent,
        title: str,
        value: str = "—",
        color_key: str = COLOR_NEUTRAL,
        width: int = 160,
        **kwargs,
    ) -> None:
        super().__init__(parent, width=width, fg_color=("gray84", "gray20"), **kwargs)
        self.columnconfigure(1, weight=1)

        # Left accent bar
        self._accent = ctk.CTkFrame(
            self, width=_ACCENT_W, corner_radius=0,
            fg_color=color_key if color_key != COLOR_NEUTRAL else COLOR_NEUTRAL,
        )
        self._accent.grid(row=0, column=0, sticky="ns", rowspan=2, padx=(0, 0))
        self._accent.grid_propagate(False)

        # Title label (small, muted)
        self._title_lbl = ctk.CTkLabel(
            self,
            text=title,
            font=("", 10),
            text_color=("gray50", "gray60"),
            anchor="w",
            justify="left",
            wraplength=width - _ACCENT_W - 16,
        )
        self._title_lbl.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))

        # Value label (large, bold)
        self._value_lbl = ctk.CTkLabel(
            self,
            text=value,
            font=("", 18, "bold"),
            anchor="w",
            justify="left",
        )
        self._value_lbl.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(2, 8))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, value: str, color_key: str = COLOR_NEUTRAL) -> None:
        """Update the displayed value and optionally the accent colour."""
        self._value_lbl.configure(text=value)
        self._accent.configure(
            fg_color=color_key if color_key and color_key != COLOR_NEUTRAL else COLOR_NEUTRAL
        )

    @staticmethod
    def quality_color(value: float) -> str:
        if value >= 0.70:
            return COLOR_GOOD
        if value >= 0.50:
            return COLOR_WARN
        return COLOR_BAD

    @staticmethod
    def error_rate_color(rate: float) -> str:
        if rate < 0.10:
            return COLOR_GOOD
        if rate < 0.30:
            return COLOR_WARN
        return COLOR_BAD
