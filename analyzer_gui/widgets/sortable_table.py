# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SortableTable — a CTkScrollableFrame-based table with sortable columns."""

from __future__ import annotations

import customtkinter as ctk

_HEADER_FONT = ("", 12, "bold")
_CELL_FONT = ("", 11)
_ROW_BG_EVEN = ("gray88", "gray18")
_ROW_BG_ODD = ("gray82", "gray22")
_HEADER_BG = ("gray70", "gray30")


class SortableTable(ctk.CTkScrollableFrame):
    """Scrollable table with clickable column headers for sorting.

    Parameters
    ----------
    columns:
        List of column header strings.
    col_widths:
        Optional list of minimum column widths in pixels (one per column).
    max_rows:
        If set, only the first *max_rows* rows are rendered (for performance).
    """

    def __init__(
        self,
        parent,
        columns: list[str],
        col_widths: list[int] | None = None,
        max_rows: int = 500,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self._columns = columns
        self._col_widths = col_widths or [120] * len(columns)
        self._max_rows = max_rows
        self._data: list[list] = []
        self._sort_col: int | None = None
        self._sort_reverse = False
        self._header_labels: list[ctk.CTkLabel] = []
        self._cell_widgets: list[list[ctk.CTkLabel]] = []
        self._row_highlights: list[str | None] = []  # per-row optional colour

        for c in range(len(columns)):
            self.columnconfigure(c, weight=1, minsize=self._col_widths[c])

        self._build_headers()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_headers(self) -> None:
        for c, name in enumerate(self._columns):
            lbl = ctk.CTkLabel(
                self,
                text=f"  {name}",
                font=_HEADER_FONT,
                fg_color=_HEADER_BG,
                anchor="w",
                cursor="hand2",
            )
            lbl.grid(row=0, column=c, padx=1, pady=(2, 1), sticky="ew")
            lbl.bind("<Button-1>", lambda e, col=c: self._on_header_click(col))
            self._header_labels.append(lbl)

    def _on_header_click(self, col: int) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False
        self._sort_and_render()

    def _sort_and_render(self) -> None:
        col = self._sort_col
        if col is None:
            self._render()
            return

        def _key(row_highlight):
            row = row_highlight[0]
            v = row[col] if col < len(row) else ""
            try:
                return (0, float(str(v).replace(",", "").replace("%", "")))
            except (ValueError, TypeError):
                return (1, str(v).lower())

        combined = list(zip(self._data, self._row_highlights))
        combined.sort(key=_key, reverse=self._sort_reverse)
        self._data = [r for r, _ in combined]
        self._row_highlights = [h for _, h in combined]

        # Update header arrows
        for i, lbl in enumerate(self._header_labels):
            col_name = self._columns[i]
            if i == col:
                arrow = "▼" if self._sort_reverse else "▲"
                lbl.configure(text=f"{arrow} {col_name}")
            else:
                lbl.configure(text=f"  {col_name}")

        self._render()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def set_data(
        self,
        data: list[list],
        row_highlights: list[str | None] | None = None,
    ) -> None:
        """Populate the table.

        Parameters
        ----------
        data:
            List of rows; each row is a list of values (str/int/float).
        row_highlights:
            Optional per-row fg_color override (e.g. '#6b1a1a' for red).
            Pass None for a row to use the default alternating colour.
        """
        self._data = [list(row) for row in data]
        self._row_highlights = list(row_highlights) if row_highlights else [None] * len(data)
        self._sort_col = None
        self._sort_reverse = False
        # Reset header arrows
        for i, lbl in enumerate(self._header_labels):
            lbl.configure(text=f"  {self._columns[i]}")
        self._render()

    def clear(self) -> None:
        self.set_data([])

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        # Destroy existing cell widgets
        for row_cells in self._cell_widgets:
            for w in row_cells:
                w.destroy()
        self._cell_widgets.clear()

        rows_to_show = self._data[: self._max_rows]
        for r, row in enumerate(rows_to_show):
            highlight = self._row_highlights[r] if r < len(self._row_highlights) else None
            if highlight:
                bg = highlight
            else:
                bg = _ROW_BG_EVEN if r % 2 == 0 else _ROW_BG_ODD

            row_cells: list[ctk.CTkLabel] = []
            for c in range(len(self._columns)):
                val = row[c] if c < len(row) else ""
                text = str(val) if val is not None else ""
                lbl = ctk.CTkLabel(
                    self,
                    text=text,
                    font=_CELL_FONT,
                    fg_color=bg,
                    anchor="w",
                )
                lbl.grid(row=r + 1, column=c, padx=1, pady=0, sticky="ew")
                row_cells.append(lbl)
            self._cell_widgets.append(row_cells)
