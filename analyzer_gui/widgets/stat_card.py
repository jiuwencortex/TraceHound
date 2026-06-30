# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""StatCard widget — a labelled metric card for the Overview panel."""

from __future__ import annotations

import customtkinter as ctk

# Colour tokens (fg_color)
COLOR_GOOD = "#1a472a"      # dark green
COLOR_WARN = "#7a5c00"      # dark amber
COLOR_BAD = "#6b1a1a"       # dark red
COLOR_NEUTRAL = "default"   # let CTkFrame use theme default


class StatCard(ctk.CTkFrame):
    """A small card that shows a metric title and its current value."""

    def __init__(
        self,
        parent,
        title: str,
        value: str = "—",
        color_key: str = COLOR_NEUTRAL,
        width: int = 160,
        **kwargs,
    ) -> None:
        super().__init__(parent, width=width, **kwargs)

        self._title_lbl = ctk.CTkLabel(
            self,
            text=title,
            font=("", 11),
            text_color="gray70",
            wraplength=width - 20,
            anchor="w",
            justify="left",
        )
        self._title_lbl.pack(padx=10, pady=(8, 0), anchor="w")

        self._value_lbl = ctk.CTkLabel(
            self,
            text=value,
            font=("", 20, "bold"),
            anchor="w",
        )
        self._value_lbl.pack(padx=10, pady=(2, 8), anchor="w")

        if color_key != COLOR_NEUTRAL:
            self.configure(fg_color=color_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, value: str, color_key: str = COLOR_NEUTRAL) -> None:
        """Update the displayed value and optionally the card's accent colour."""
        self._value_lbl.configure(text=value)
        if not color_key or color_key == COLOR_NEUTRAL:
            # Reset to theme default
            self.configure(fg_color=("gray86", "gray17"))
        else:
            self.configure(fg_color=color_key)

    @staticmethod
    def quality_color(value: float) -> str:
        """Map a 0–1 quality score to a card accent colour."""
        if value >= 0.70:
            return COLOR_GOOD
        if value >= 0.50:
            return COLOR_WARN
        return COLOR_BAD

    @staticmethod
    def error_rate_color(rate: float) -> str:
        """Map an error rate fraction to a card accent colour."""
        if rate < 0.10:
            return COLOR_GOOD
        if rate < 0.30:
            return COLOR_WARN
        return COLOR_BAD
