# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""DesktopReportView — styled markdown report + structured table dashboard."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from analyzer_gui.widgets.sortable_table import SortableTable


# ── Markdown-to-table helpers ─────────────────────────────────────────────────

def _parse_md_table(markdown: str, header_keyword: str) -> list[list[str]]:
    """Return rows (excluding separator) from the first markdown table whose
    header line contains *header_keyword* (case-insensitive)."""
    lines = markdown.splitlines()
    rows: list[list[str]] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_table:
                break
            continue
        if "|" not in stripped:
            if in_table:
                break
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if not cells:
            continue
        # Skip separator rows (only dashes/colons)
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue
        if not in_table:
            if header_keyword.lower() in stripped.lower():
                in_table = True
                rows.append(cells)
        else:
            rows.append(cells)
    return rows   # rows[0] = header, rows[1:] = data


# ── DesktopReportView ─────────────────────────────────────────────────────────

class DesktopReportView(ctk.CTkFrame):
    """Two-mode view: styled markdown text report  OR  structured table dashboard."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # ── Title row ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        hdr.columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Desktop Report", font=("", 20, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        # Mode toggle (replaces Toggle Edit + Refresh)
        self._mode_seg = ctk.CTkSegmentedButton(
            hdr,
            values=["Report", "Tables"],
            command=self._on_mode_change,
            width=200,
        )
        self._mode_seg.set("Report")
        self._mode_seg.grid(row=0, column=1, padx=(0, 8))

        # Save button (kept — it's actually useful)
        ctk.CTkButton(
            hdr, text="Save .md", width=80, command=self._save_report
        ).grid(row=0, column=2)

        # ── Report mode: styled markdown textbox ─────────────────────────
        self._report_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._report_frame.grid(row=2, column=0, sticky="nsew")
        self._report_frame.rowconfigure(0, weight=1)
        self._report_frame.columnconfigure(0, weight=1)

        self._text_widget = tk.Text(
            self._report_frame,
            wrap="word",
            state="disabled",
            bg="#1e1e1e",
            fg="#e0e0e0",
            insertbackground="white",
            selectbackground="#4a90d9",
            selectforeground="white",
            padx=24,
            pady=16,
            font=("Consolas", 11),
            relief="flat",
            borderwidth=0,
        )
        self._text_widget.grid(row=0, column=0, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(self._report_frame,
                                     command=self._text_widget.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._text_widget.configure(yscrollcommand=scrollbar.set)

        self._configure_tags()

        # ── Tables mode: structured dashboard ────────────────────────────
        self._tables_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._tables_frame.columnconfigure(0, weight=1)
        # (not gridded yet — shown on demand)

        # Section: Recommendations
        self._sec_label(self._tables_frame, "Recommended Fixes (Priority Order)", 0)
        self._rec_table = SortableTable(
            self._tables_frame,
            columns=["Priority", "Fix", "Effort", "Impact"],
            col_widths=[70, 380, 100, 200],
        )
        self._rec_table.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 12))

        # Section: Session Overview
        self._sec_label(self._tables_frame, "Session Overview", 2)
        self._sess_table = SortableTable(
            self._tables_frame,
            columns=["Session ID", "Title / First Query", "Turns",
                     "Error Rate", "Tokens", "Files"],
            col_widths=[180, 260, 55, 90, 90, 55],
        )
        self._sess_table.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 12))

        # Section: Time Breakdown
        self._sec_label(self._tables_frame, "Time Breakdown", 4)
        self._time_table = SortableTable(
            self._tables_frame,
            columns=["Phase", "Value", "Notes"],
            col_widths=[200, 120, 400],
        )
        self._time_table.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 12))

        # Section: Error Categories
        self._sec_label(self._tables_frame, "Error Categories", 6)
        self._err_table = SortableTable(
            self._tables_frame,
            columns=["Category", "Count", "% of Errors", "Affected Sessions"],
            col_widths=[140, 70, 110, 140],
        )
        self._err_table.grid(row=7, column=0, sticky="ew", padx=8, pady=(0, 16))

        # State
        self._current_markdown: str = ""
        self._result = None
        self._reporter = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sec_label(parent, text: str, row: int) -> None:
        ctk.CTkLabel(
            parent, text=text, font=("", 14, "bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=12, pady=(12, 4))

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, result, loader, reporter) -> None:
        self._result   = result
        self._reporter = reporter

        md_text = "No report available. Run analysis first."
        if reporter is not None and result is not None:
            try:
                md_text = reporter.render_desktop(result)
            except Exception as exc:
                md_text = f"Error generating report:\n{exc}"

        self._current_markdown = md_text
        self._render_markdown(md_text)

        if result is not None:
            self._populate_tables(result, md_text)

    # ── Mode switch ───────────────────────────────────────────────────────────

    def _on_mode_change(self, mode: str) -> None:
        if mode == "Report":
            self._tables_frame.grid_remove()
            self._report_frame.grid(row=2, column=0, sticky="nsew")
        else:
            self._report_frame.grid_remove()
            self._tables_frame.grid(row=2, column=0, sticky="nsew")

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_tables(self, result, markdown: str) -> None:
        self._populate_rec_table(markdown)
        self._populate_sess_table(result)
        self._populate_time_table(result)
        self._populate_err_table(result)

    def _populate_rec_table(self, markdown: str) -> None:
        """Parse the 'Priority | Fix | Effort | Impact' markdown table."""
        rows = _parse_md_table(markdown, "Priority")
        if len(rows) < 2:
            self._rec_table.set_data([["No recommendations found", "", "", ""]])
            return
        data = rows[1:]   # skip header row
        highlights = []
        for row in data:
            pri = row[0] if row else ""
            highlights.append(
                "#6b1a1a" if pri == "P0" else
                "#3a3300" if pri in ("P1", "P2") else
                None
            )
        self._rec_table.set_data(data, highlights)

    def _populate_sess_table(self, result) -> None:
        sf = getattr(result, "session_flow", None)
        profiles = getattr(sf, "session_profiles", []) if sf else []
        rows = []
        highlights = []
        for p in profiles:
            sid      = getattr(p, "session_id",   "")
            title    = getattr(p, "session_title", "") or sid
            n_turns  = getattr(p, "n_turns",       0)
            err_rate = getattr(p, "error_rate",    0.0)
            tokens   = getattr(p, "total_tokens",  0)
            files    = getattr(p, "files_delivered",0)
            rows.append([
                sid,
                title[:50],
                n_turns,
                f"{err_rate:.1%}",
                f"{tokens:,}" if tokens else "0",
                files,
            ])
            highlights.append("#6b1a1a" if err_rate >= 0.5 else None)
        if not rows:
            self._sess_table.set_data([["No session data available", "", "", "", "", ""]])
        else:
            self._sess_table.set_data(rows, highlights)

    def _populate_time_table(self, result) -> None:
        tb = getattr(result, "time_bottlenecks", None)
        if tb is None or getattr(tb, "n_turns_with_timing", 0) == 0:
            self._time_table.set_data([["No timing data available", "—", ""]])
            return

        total_s  = getattr(tb, "total_time_s",      0.0)
        mean_s   = getattr(tb, "mean_duration_s",   0.0)
        median_s = getattr(tb, "median_duration_s", 0.0)
        max_s    = getattr(tb, "max_duration_s",    0.0)
        min_s    = getattr(tb, "min_duration_s",    0.0)
        n        = getattr(tb, "n_turns_with_timing",0)

        rows = [
            ["Total net compute time", f"{total_s:.1f}s ({total_s/60:.1f} min)",
             "Sum of all per-request durations. Idle time NOT included."],
            ["Mean turn duration",     f"{mean_s:.1f}s",   "Average request→response time"],
            ["Median turn duration",   f"{median_s:.1f}s", "Typical latency"],
            ["Max turn duration",      f"{max_s:.1f}s",    "Slowest single request"],
            ["Min turn duration",      f"{min_s:.1f}s",    "Fastest single request"],
            ["Turns with timing data", str(n),             ""],
        ]
        highlights = [
            None, None, None,
            "#6b1a1a" if max_s > 60 else None,
            None, None,
        ]
        self._time_table.set_data(rows, highlights)

    def _populate_err_table(self, result) -> None:
        ec = getattr(result, "error_categories", None)
        if ec is None:
            self._err_table.set_data([["No error data", "", "", ""]])
            return
        rows = []
        highlights = []
        for c in getattr(ec, "categories", []):
            count = getattr(c, "count", 0)
            if count == 0:
                continue
            rows.append([
                getattr(c, "category",             ""),
                count,
                f"{getattr(c, 'percentage_of_errors', 0):.1f}%",
                getattr(c, "affected_sessions",    0),
            ])
            highlights.append("#6b1a1a")
        if not rows:
            self._err_table.set_data([["No errors recorded", "0", "0%", "0"]])
        else:
            self._err_table.set_data(rows, highlights)

    # ── Markdown rendering ────────────────────────────────────────────────────

    def _configure_tags(self) -> None:
        self._text_widget.tag_configure(
            "h1", font=("Consolas", 18, "bold"), foreground="#ffffff", spacing3=12)
        self._text_widget.tag_configure(
            "h2", font=("Consolas", 14, "bold"), foreground="#7ec8e3", spacing3=8)
        self._text_widget.tag_configure(
            "h3", font=("Consolas", 12, "bold"), foreground="#a8d8a8", spacing3=6)
        self._text_widget.tag_configure(
            "body", font=("Consolas", 11), foreground="#e0e0e0")
        self._text_widget.tag_configure(
            "bold", font=("Consolas", 11, "bold"), foreground="#ffffff")
        self._text_widget.tag_configure(
            "italic", font=("Consolas", 11, "italic"), foreground="#c0c0c0")
        self._text_widget.tag_configure(
            "code", font=("Consolas", 10), foreground="#7ee787",
            background="#1e3a2f")
        self._text_widget.tag_configure(
            "code_block", font=("Consolas", 10), foreground="#7ee787",
            background="#1e3a2f", spacing1=6, spacing3=6)
        self._text_widget.tag_configure(
            "bullet", font=("Consolas", 11), foreground="#e0e0e0",
            lmargin1=20, lmargin2=30)
        self._text_widget.tag_configure(
            "table_header", font=("Consolas", 10, "bold"),
            foreground="#ffffff", background="#3a3a3a")
        self._text_widget.tag_configure(
            "table_row", font=("Consolas", 10), foreground="#d0d0d0")
        self._text_widget.tag_configure(
            "blockquote", font=("Consolas", 11, "italic"),
            foreground="#a0a0a0", lmargin1=20, lmargin2=30)
        self._text_widget.tag_configure(
            "link", font=("Consolas", 11, "underline"), foreground="#4a90d9")

    def _render_markdown(self, text: str) -> None:
        self._text_widget.configure(state="normal")
        self._text_widget.delete("1.0", "end")

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped == "---" or (stripped and set(stripped) == {"-"}):
                self._text_widget.insert("end", "\n" + "—" * 60 + "\n", "body")
                i += 1
                continue

            if stripped.startswith("# "):
                self._insert_formatted(stripped[2:], "h1"); i += 1; continue
            if stripped.startswith("## "):
                self._insert_formatted(stripped[3:], "h2"); i += 1; continue
            if stripped.startswith("### "):
                self._insert_formatted(stripped[4:], "h3"); i += 1; continue

            if stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                self._text_widget.insert("end", "\n", "body")
                self._text_widget.insert("end", "\n".join(code_lines) + "\n", "code_block")
                if i < len(lines):
                    i += 1
                continue

            if "|" in stripped and stripped.startswith("|"):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                self._render_table(table_lines)
                continue

            if not stripped:
                self._text_widget.insert("end", "\n", "body"); i += 1; continue

            if stripped.startswith(("- ", "* ")):
                self._insert_formatted("  • " + stripped[2:], "bullet"); i += 1; continue
            if stripped.startswith("> "):
                self._insert_formatted(stripped[2:], "blockquote"); i += 1; continue

            self._insert_formatted(stripped, "body")
            i += 1

        self._text_widget.configure(state="disabled")

    def _insert_formatted(self, text: str, base_tag: str) -> None:
        self._text_widget.insert("end", "\n", base_tag)
        i = 0
        while i < len(text):
            if text[i:i+2] == "**":
                end = text.find("**", i + 2)
                if end != -1:
                    self._text_widget.insert("end", text[i+2:end], (base_tag, "bold"))
                    i = end + 2; continue
            if text[i] == "*" and (i + 1 >= len(text) or text[i+1] != "*"):
                end = text.find("*", i + 1)
                if end != -1:
                    self._text_widget.insert("end", text[i+1:end], (base_tag, "italic"))
                    i = end + 1; continue
            if text[i] == "`":
                end = text.find("`", i + 1)
                if end != -1:
                    self._text_widget.insert("end", text[i+1:end], (base_tag, "code"))
                    i = end + 1; continue
            if text[i] == "[":
                cb = text.find("]", i)
                if cb != -1 and cb + 1 < len(text) and text[cb+1] == "(":
                    cp = text.find(")", cb + 2)
                    if cp != -1:
                        self._text_widget.insert("end", text[i+1:cb], (base_tag, "link"))
                        i = cp + 1; continue
            self._text_widget.insert("end", text[i], base_tag)
            i += 1
        self._text_widget.insert("end", "\n", base_tag)

    def _render_table(self, lines: list[str]) -> None:
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells and not all(c.replace("-", "").replace(":", "") == "" for c in cells):
                rows.append(cells)
        if not rows:
            return
        self._text_widget.insert("end", "\n", "body")
        header_text = " | ".join(rows[0])
        self._text_widget.insert("end", header_text + "\n", "table_header")
        self._text_widget.insert("end", "=" * len(header_text) + "\n", "table_header")
        for row in rows[1:]:
            self._text_widget.insert("end", " | ".join(row) + "\n", "table_row")
        self._text_widget.insert("end", "\n", "body")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_report(self) -> None:
        desktop = Path.home() / "Desktop"
        desktop.mkdir(exist_ok=True)
        out_path = desktop / "tracehound_report.md"
        out_path.write_text(self._current_markdown, encoding="utf-8")
        self._text_widget.configure(state="normal")
        self._text_widget.insert("end", f"\n\n[Saved → {out_path}]\n", "bold")
        self._text_widget.configure(state="disabled")
        self._text_widget.see("end")
