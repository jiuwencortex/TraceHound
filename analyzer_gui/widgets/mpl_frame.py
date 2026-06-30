# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""MplFrame — embeds a matplotlib Figure inside a CTkFrame."""

from __future__ import annotations

import customtkinter as ctk
import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


def _dark_style() -> str:
    """Return 'dark_background' when CTk is in dark mode, else 'default'."""
    mode = ctk.get_appearance_mode()
    return "dark_background" if mode.lower() == "dark" else "default"


class MplFrame(ctk.CTkFrame):
    """A CTkFrame that contains a resizable matplotlib Figure.

    Usage::

        frame = MplFrame(parent, figsize=(8, 4))
        ax = frame.get_ax()
        ax.plot(...)
        frame.draw()
    """

    def __init__(
        self,
        parent,
        figsize: tuple[float, float] = (7, 4),
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        with plt.style.context(_dark_style()):
            self._fig = Figure(figsize=figsize, tight_layout=True)

        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._mpl_canvas.get_tk_widget().pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def figure(self) -> Figure:
        return self._fig

    def clear(self) -> None:
        """Clear all axes from the figure."""
        self._fig.clear()

    def get_ax(self, *subplot_args, **subplot_kwargs):
        """Add and return a fresh subplot axis.

        If no args are given, defaults to a single full-figure axis (1,1,1).
        """
        if not subplot_args:
            subplot_args = (1, 1, 1)
        return self._fig.add_subplot(*subplot_args, **subplot_kwargs)

    def draw(self) -> None:
        """Flush pending draw commands to the Tk canvas."""
        self._mpl_canvas.draw_idle()

    def redraw(self, draw_func) -> None:
        """Clear the figure, call ``draw_func(fig)`` to populate, then flush.

        Example::

            mpl_frame.redraw(lambda fig: fig.add_subplot(111).bar(...))
        """
        self._fig.clear()
        draw_func(self._fig)
        self._mpl_canvas.draw_idle()
