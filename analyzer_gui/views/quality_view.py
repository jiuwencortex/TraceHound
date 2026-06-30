# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""QualityView — quality-over-time chart and per-session table."""

from __future__ import annotations

import customtkinter as ctk

from analyzer_gui.widgets.mpl_frame import MplFrame
from analyzer_gui.widgets.sortable_table import SortableTable


def _trend_color(direction: str) -> str:
    return {
        "improving": "#2ecc71",
        "degrading": "#e74c3c",
    }.get(direction, "#95a5a6")


class QualityView(ctk.CTkFrame):
    """Quality trends: matplotlib line chart + per-week data table."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Quality Trends", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        self._chart = MplFrame(self, figsize=(9, 4))
        self._chart.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))

        self._table = SortableTable(
            self,
            columns=["Week", "Turns", "Mean Quality", "Completed", "Corrections"],
            col_widths=[120, 70, 120, 100, 110],
        )
        self._table.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

    # ------------------------------------------------------------------

    def refresh(self, result, *_) -> None:
        if result is None:
            return
        qt = result.quality_trends
        self._draw_chart(qt)
        self._fill_table(qt)

    # ------------------------------------------------------------------

    def _draw_chart(self, qt) -> None:
        weeks = qt.weeks
        if not weeks:
            self._chart.clear()
            self._chart.draw()
            return

        indices = list(range(len(weeks)))
        qualities = [w.mean_quality for w in weeks]
        n_turns = [w.n_turns for w in weeks]
        labels = [w.week_tag for w in weeks]
        overall = qt.overall_mean
        color = _trend_color(qt.trend_direction)

        def _draw(fig):
            ax = fig.add_subplot(111)
            ax2 = ax.twinx()

            # Turn count bars (background)
            ax2.bar(indices, n_turns, color="#3498db", alpha=0.25, label="Turns")
            ax2.set_ylabel("Turns", color="#3498db", fontsize=9)
            ax2.tick_params(axis="y", colors="#3498db")

            # Quality line
            ax.plot(indices, qualities, color=color, linewidth=2, marker="o", markersize=5, zorder=3)
            ax.fill_between(indices, qualities, alpha=0.15, color=color)
            ax.axhline(overall, linestyle="--", color="gray", linewidth=1, label=f"Overall mean {overall:.3f}")

            # Annotate best/worst
            if len(qualities) >= 2:
                best_i = max(range(len(qualities)), key=lambda i: qualities[i])
                worst_i = min(range(len(qualities)), key=lambda i: qualities[i])
                ax.annotate(f"best\n{qualities[best_i]:.3f}", xy=(best_i, qualities[best_i]),
                            xytext=(0, 10), textcoords="offset points", ha="center", fontsize=8)
                ax.annotate(f"worst\n{qualities[worst_i]:.3f}", xy=(worst_i, qualities[worst_i]),
                            xytext=(0, -20), textcoords="offset points", ha="center", fontsize=8)

            ax.set_xticks(indices)
            ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
            ax.set_ylim(0, 1)
            ax.set_ylabel("Mean Quality")
            ax.set_title(f"Quality by Week — trend: {qt.trend_direction}")
            ax.legend(loc="upper left", fontsize=8)

        self._chart.redraw(_draw)

    def _fill_table(self, qt) -> None:
        rows = [
            [
                w.week_tag,
                w.n_turns,
                f"{w.mean_quality:.4f}",
                w.n_task_completed,
                w.n_follow_up_corrections,
            ]
            for w in qt.weeks
        ]
        overall = qt.overall_mean
        highlights = []
        for w in qt.weeks:
            if w.mean_quality > overall + 0.05:
                highlights.append("#1a472a")
            elif w.mean_quality < overall - 0.05:
                highlights.append("#6b1a1a")
            else:
                highlights.append(None)
        self._table.set_data(rows, highlights)
