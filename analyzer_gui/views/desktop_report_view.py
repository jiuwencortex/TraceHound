# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""DesktopReportView — styled markdown report + full structured issue-card dashboard."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Any

import customtkinter as ctk

from analyzer_gui.widgets.sortable_table import SortableTable


# ── Severity palette ──────────────────────────────────────────────────────────
_SEV = {
    "CRITICAL": {"hdr": "#6b1a1a", "badge": "#ff6b6b", "bar": "#e74c3c"},
    "HIGH":     {"hdr": "#5a2d00", "badge": "#ff9c4b", "bar": "#e67e22"},
    "MEDIUM":   {"hdr": "#3a3700", "badge": "#ffd84b", "bar": "#f1c40f"},
    "INFO":     {"hdr": "#1a2a4a", "badge": "#7ec8e3", "bar": "#4a90d9"},
}

_SEC_COLOR = "#a0b8d0"     # section label colour (Description, Evidence…)
_BODY_COLOR = "#d8d8d8"    # body text colour
_REC_COLOR = "#80d080"     # recommendation bullet colour


def _severity(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ("auth", "billing", "balance", "payment", "401", "402")):
        return "CRITICAL"
    if any(w in t for w in ("cascade", "recovery", "fail", "misconfiguration")):
        return "HIGH"
    if any(w in t for w in ("latency", "slow", "bottleneck", "timeout")):
        return "MEDIUM"
    return "INFO"


def _bullet_lines(text: str) -> list[str]:
    """Extract bullet items from a recommendations block."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            out.append(stripped[2:].strip())
        elif stripped.startswith("  •"):
            out.append(stripped[3:].strip())
        elif stripped and not stripped.startswith("#"):
            out.append(stripped)
    return [l for l in out if l]


# ── Markdown parsers ─────────────────────────────────────────────────────────

def _parse_issues(markdown: str) -> list[dict[str, str]]:
    """Extract structured issue dicts from the markdown report.

    Each dict has keys: title, description, evidence, impact,
    root_cause, recommendations.
    """
    issues: list[dict] = []
    cur: dict | None = None
    cur_sec: str | None = None
    cur_lines: list[str] = []

    _BLANK = {"title": "", "description": "", "evidence": "",
              "impact": "", "root_cause": "", "recommendations": ""}

    def _flush_section() -> None:
        if cur is not None and cur_sec is not None:
            cur[cur_sec] = "\n".join(cur_lines).strip()

    def _flush_issue() -> None:
        if cur is not None:
            _flush_section()
            issues.append(cur)

    for line in markdown.splitlines():
        stripped = line.strip()

        # New issue: ## [N. Issue: Title] or ## [Issue: Title]
        if stripped.startswith("## ") and "issue" in stripped.lower():
            _flush_issue()
            raw = stripped[3:].strip()
            # Strip leading "N. Issue: " or "Issue: "
            lower_raw = raw.lower()
            for prefix in ("issue:", "issue :", "issue"):
                if prefix in lower_raw:
                    idx = lower_raw.index(prefix) + len(prefix)
                    raw = raw[idx:].lstrip(": ").strip()
                    break
            cur = {**_BLANK, "title": raw}
            cur_sec = None
            cur_lines = []
            continue

        # Another ## header while inside an issue → close it
        if stripped.startswith("## ") and cur is not None:
            _flush_issue()
            cur = None
            cur_sec = None
            cur_lines = []
            continue

        if cur is None:
            continue

        # Section header within an issue
        if stripped.startswith("### "):
            _flush_section()
            sec = stripped[4:].strip().lower()
            cur_lines = []
            if "description" in sec:
                cur_sec = "description"
            elif "evidence" in sec:
                cur_sec = "evidence"
            elif "impact" in sec:
                cur_sec = "impact"
            elif "root" in sec:
                cur_sec = "root_cause"
            elif "recommend" in sec:
                cur_sec = "recommendations"
            else:
                cur_sec = sec.replace(" ", "_")
            continue

        if cur_sec is not None:
            cur_lines.append(line)

    _flush_issue()
    return issues


def _parse_md_table(markdown: str, header_keyword: str) -> list[list[str]]:
    """Return rows from the first markdown table whose header contains keyword."""
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
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue
        if not in_table:
            if header_keyword.lower() in stripped.lower():
                in_table = True
                rows.append(cells)
        else:
            rows.append(cells)
    return rows


# ── Issue card widget ─────────────────────────────────────────────────────────

class _IssueCard(ctk.CTkFrame):
    """A rich card displaying one issue from the report."""

    def __init__(self, parent, index: int, issue: dict[str, str], **kwargs) -> None:
        sev    = _severity(issue["title"])
        palette = _SEV[sev]

        super().__init__(
            parent,
            fg_color=("gray83", "gray15"),
            border_color=palette["bar"],
            border_width=1,
            corner_radius=8,
            **kwargs,
        )
        self.columnconfigure(0, weight=1)

        # ── Coloured header ─────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=palette["hdr"],
                           corner_radius=6, height=36)
        hdr.grid(row=0, column=0, sticky="ew", padx=1, pady=(1, 0))
        hdr.columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr, text=f"  #{index}", width=36,
            font=("", 13, "bold"), text_color="gray70",
        ).grid(row=0, column=0, padx=(4, 0))

        ctk.CTkLabel(
            hdr,
            text=f"  [{sev}]",
            font=("", 11, "bold"),
            text_color=palette["badge"],
            width=90,
        ).grid(row=0, column=1, sticky="w", padx=(2, 0))

        ctk.CTkLabel(
            hdr,
            text=issue["title"],
            font=("", 13, "bold"),
            text_color="#ffffff",
            anchor="w",
        ).grid(row=0, column=2, sticky="ew", padx=(4, 8), pady=4)

        # ── Body: left detail cols + right recommendations ───────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=10, pady=(6, 8))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=0)   # separator
        body.columnconfigure(2, weight=2)

        # Left: Description, Evidence, Impact, Root Cause
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw")
        left.columnconfigure(0, weight=1)

        row_i = 0
        for sec_key, label_text in [
            ("description", "Description"),
            ("evidence",    "Evidence"),
            ("impact",      "Impact"),
            ("root_cause",  "Root Cause"),
        ]:
            content = issue.get(sec_key, "").strip()
            if not content:
                continue

            ctk.CTkLabel(
                left, text=label_text,
                font=("", 10, "bold"), text_color=_SEC_COLOR,
                anchor="w",
            ).grid(row=row_i, column=0, sticky="w", pady=(6 if row_i else 2, 0))
            row_i += 1

            ctk.CTkLabel(
                left, text=content,
                font=("", 11), text_color=_BODY_COLOR,
                anchor="nw", justify="left", wraplength=520,
            ).grid(row=row_i, column=0, sticky="w", padx=(4, 0), pady=(0, 4))
            row_i += 1

        # Vertical separator
        ctk.CTkFrame(body, width=1, fg_color=("gray50", "gray35")).grid(
            row=0, column=1, sticky="ns", padx=10,
        )

        # Right: Recommendations
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nw")
        right.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right, text="Recommendations",
            font=("", 10, "bold"), text_color=_SEC_COLOR,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(2, 4))

        recs = _bullet_lines(issue.get("recommendations", ""))
        for ri, rec in enumerate(recs):
            ctk.CTkLabel(
                right,
                text=f"  •  {rec}",
                font=("", 11), text_color=_REC_COLOR,
                anchor="nw", justify="left", wraplength=340,
            ).grid(row=ri + 1, column=0, sticky="w", pady=1)

        if not recs:
            ctk.CTkLabel(
                right, text="—", font=("", 11), text_color="gray50",
            ).grid(row=1, column=0, sticky="w")


# ── DesktopReportView ─────────────────────────────────────────────────────────

class DesktopReportView(ctk.CTkFrame):
    """Two-mode view: styled markdown text report OR structured issue-card dashboard."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # ── Title / toolbar ──────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        hdr.columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Desktop Report", font=("", 20, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self._mode_seg = ctk.CTkSegmentedButton(
            hdr,
            values=["Report", "AI Report", "Tables"],
            command=self._on_mode_change,
            width=280,
        )
        self._mode_seg.set("Report")
        self._mode_seg.grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            hdr, text="Save .md", width=80, command=self._save_report
        ).grid(row=0, column=2)

        # Thin separator
        ctk.CTkFrame(self, height=1, fg_color=("gray60", "gray30")).grid(
            row=1, column=0, sticky="ew", padx=16, pady=(8, 0)
        )

        # ── Report mode: styled text ─────────────────────────────────
        self._report_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._report_frame.grid(row=2, column=0, sticky="nsew")
        self._report_frame.rowconfigure(0, weight=1)
        self._report_frame.columnconfigure(0, weight=1)

        self._text_widget = tk.Text(
            self._report_frame,
            wrap="word",
            state="disabled",
            bg="#1a1a1a",
            fg="#e0e0e0",
            insertbackground="white",
            selectbackground="#4a90d9",
            selectforeground="white",
            padx=28,
            pady=18,
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

        # ── AI Report mode ───────────────────────────────────────────
        self._ai_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._ai_frame.rowconfigure(1, weight=1)
        self._ai_frame.columnconfigure(0, weight=1)

        ai_toolbar = ctk.CTkFrame(self._ai_frame, fg_color="transparent")
        ai_toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
        ai_toolbar.columnconfigure(1, weight=1)

        self._ai_gen_btn = ctk.CTkButton(
            ai_toolbar, text="⚡ Generate AI Report",
            width=180, command=self._generate_ai_report,
        )
        self._ai_gen_btn.grid(row=0, column=0)

        self._ai_status = ctk.CTkLabel(
            ai_toolbar, text="Click Generate to analyse sessions with AI.",
            font=("", 11), text_color=("gray50", "gray60"), anchor="w",
        )
        self._ai_status.grid(row=0, column=1, padx=(14, 0), sticky="w")

        ai_text_frame = ctk.CTkFrame(self._ai_frame, fg_color="transparent")
        ai_text_frame.grid(row=1, column=0, sticky="nsew")
        ai_text_frame.rowconfigure(0, weight=1)
        ai_text_frame.columnconfigure(0, weight=1)

        self._ai_text = tk.Text(
            ai_text_frame,
            wrap="word",
            state="disabled",
            bg="#1a1a1a",
            fg="#e0e0e0",
            insertbackground="white",
            selectbackground="#4a90d9",
            selectforeground="white",
            padx=28,
            pady=18,
            font=("Consolas", 11),
            relief="flat",
            borderwidth=0,
        )
        self._ai_text.grid(row=0, column=0, sticky="nsew")
        ai_scrollbar = ctk.CTkScrollbar(ai_text_frame, command=self._ai_text.yview)
        ai_scrollbar.grid(row=0, column=1, sticky="ns")
        self._ai_text.configure(yscrollcommand=ai_scrollbar.set)
        # Reuse same tag configuration from main text widget
        self._ai_frame_built = True

        # ── Tables mode: issue cards + summary tables ────────────────
        self._tables_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._tables_frame.columnconfigure(0, weight=1)
        # (gridded on demand in _on_mode_change)

        # Placeholders — populated in refresh()
        self._issue_container: ctk.CTkFrame | None = None

        # Bottom summary: side-by-side Fixes + Time
        self._bottom_frame = ctk.CTkFrame(
            self._tables_frame, fg_color="transparent")
        self._bottom_frame.columnconfigure(0, weight=2)
        self._bottom_frame.columnconfigure(1, weight=1)

        # Left: Recommendations priority table
        left_bot = ctk.CTkFrame(self._bottom_frame, fg_color="transparent")
        left_bot.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left_bot.columnconfigure(0, weight=1)
        self._sec_label(left_bot, "Priority Fixes", 0)
        self._rec_table = SortableTable(
            left_bot,
            columns=["Pri", "Fix", "Effort", "Impact"],
            col_widths=[50, 380, 90, 160],
        )
        self._rec_table.grid(row=1, column=0, sticky="ew")

        # Right: Time breakdown table
        right_bot = ctk.CTkFrame(self._bottom_frame, fg_color="transparent")
        right_bot.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right_bot.columnconfigure(0, weight=1)
        self._sec_label(right_bot, "Time Breakdown", 0)
        self._time_table = SortableTable(
            right_bot,
            columns=["Phase", "Value"],
            col_widths=[180, 120],
        )
        self._time_table.grid(row=1, column=0, sticky="ew")

        # Session overview table
        self._sess_section = ctk.CTkFrame(
            self._tables_frame, fg_color="transparent")
        self._sess_section.columnconfigure(0, weight=1)
        self._sec_label(self._sess_section, "Session Overview", 0)
        self._sess_table = SortableTable(
            self._sess_section,
            columns=["Session ID", "Title / First Query", "Turns",
                     "Error Rate", "Tokens", "Files", "Mode"],
            col_widths=[170, 240, 55, 90, 80, 55, 90],
        )
        self._sess_table.grid(row=1, column=0, sticky="ew")

        # State
        self._current_markdown: str = ""
        self._result: Any = None
        self._reporter: Any = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sec_label(parent, text: str, row: int) -> None:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=(14, 4))
        f.columnconfigure(1, weight=1)
        ctk.CTkFrame(f, height=1, fg_color=("gray55", "gray35")).grid(
            row=0, column=0, sticky="ew", padx=(0, 8), ipadx=20
        )
        ctk.CTkLabel(f, text=text, font=("", 13, "bold"),
                     text_color=("#4a90d9", "#7ec8e3")).grid(
            row=0, column=1, sticky="w"
        )
        ctk.CTkFrame(f, height=1, fg_color=("gray55", "gray35")).grid(
            row=0, column=2, sticky="ew", padx=(8, 0), ipadx=40
        )
        f.columnconfigure(0, weight=0)
        f.columnconfigure(2, weight=1)

    # ── Public ────────────────────────────────────────────────────────────────

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

    # ── AI Report generation ──────────────────────────────────────────────────

    def _generate_ai_report(self) -> None:
        """Kick off LLM report generation in a background thread."""
        if self._result is None or self._reporter is None:
            self._ai_status.configure(text="Run analysis first, then click Generate.")
            return

        self._ai_gen_btn.configure(state="disabled", text="Generating…")
        self._ai_status.configure(text="Calling AI — this may take 20–60 seconds…")
        self._ai_text.configure(state="normal")
        self._ai_text.delete("1.0", "end")
        self._ai_text.configure(state="disabled")

        threading.Thread(
            target=self._run_ai_thread,
            daemon=True,
        ).start()

    def _run_ai_thread(self) -> None:
        """Background thread: call LLM, then schedule UI update on main thread."""
        try:
            md = self._reporter.render_desktop_llm(self._result)
            self.after(0, self._on_ai_done, md, None)
        except Exception as exc:
            self.after(0, self._on_ai_done, None, str(exc))

    def _on_ai_done(self, markdown: str | None, error: str | None) -> None:
        """Called on the main thread once the LLM call completes."""
        self._ai_gen_btn.configure(state="normal", text="⚡ Generate AI Report")
        if error:
            self._ai_status.configure(
                text=f"Error: {error[:120]}",
                text_color=("#c0392b", "#e74c3c"),
            )
            return

        self._ai_status.configure(
            text="✓ AI report generated.",
            text_color=("#27ae60", "#2ecc71"),
        )
        # Render the markdown into the AI text widget using the same tags
        self._render_ai_markdown(markdown or "")

    def _render_ai_markdown(self, text: str) -> None:
        """Render markdown into _ai_text using the same tag logic as _render_markdown."""
        self._ai_text.configure(state="normal")
        self._ai_text.delete("1.0", "end")
        # Apply the same tag config
        w = self._ai_text
        w.tag_configure("h1",    font=("Consolas", 18, "bold"), foreground="#ffffff",   spacing3=12)
        w.tag_configure("h2",    font=("Consolas", 14, "bold"), foreground="#7ec8e3",   spacing3=8)
        w.tag_configure("h3",    font=("Consolas", 12, "bold"), foreground="#a8d8a8",   spacing3=6)
        w.tag_configure("body",  font=("Consolas", 11),         foreground="#e0e0e0")
        w.tag_configure("bold",  font=("Consolas", 11, "bold"), foreground="#ffffff")
        w.tag_configure("code",  font=("Consolas", 10),         foreground="#7ee787",   background="#1e3a2f")
        w.tag_configure("bullet",font=("Consolas", 11),         foreground="#e0e0e0",   lmargin1=20, lmargin2=30)
        w.tag_configure("table_header", font=("Consolas", 10, "bold"), foreground="#ffffff",  background="#3a3a3a")
        w.tag_configure("table_row",    font=("Consolas", 10),          foreground="#d0d0d0")
        # Reuse the main renderer logic
        self._render_into(w, text)
        self._ai_text.configure(state="disabled")
        self._ai_text.see("1.0")

    def _render_into(self, widget: tk.Text, text: str) -> None:
        """Shared markdown → tk.Text renderer (used by both report and AI frames)."""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped == "---" or (stripped and set(stripped) == {"-"}):
                widget.insert("end", "\n" + "—" * 60 + "\n", "body")
                i += 1; continue
            if stripped.startswith("# "):
                self._insert_into(widget, stripped[2:], "h1"); i += 1; continue
            if stripped.startswith("## "):
                self._insert_into(widget, stripped[3:], "h2"); i += 1; continue
            if stripped.startswith("### "):
                self._insert_into(widget, stripped[4:], "h3"); i += 1; continue
            if stripped.startswith("```"):
                i += 1
                code_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i]); i += 1
                widget.insert("end", "\n" + "\n".join(code_lines) + "\n", "body")
                if i < len(lines): i += 1
                continue
            if "|" in stripped and stripped.startswith("|"):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i]); i += 1
                rows = []
                for tl in table_lines:
                    cells = [c.strip() for c in tl.split("|") if c.strip()]
                    if cells and not all(c.replace("-", "").replace(":", "") == "" for c in cells):
                        rows.append(cells)
                if rows:
                    widget.insert("end", "\n", "body")
                    hdr = " | ".join(rows[0])
                    widget.insert("end", hdr + "\n", "table_header")
                    widget.insert("end", "=" * len(hdr) + "\n", "table_header")
                    for row in rows[1:]:
                        widget.insert("end", " | ".join(row) + "\n", "table_row")
                    widget.insert("end", "\n", "body")
                continue
            if not stripped:
                widget.insert("end", "\n", "body"); i += 1; continue
            if stripped.startswith(("- ", "* ")):
                self._insert_into(widget, "  • " + stripped[2:], "bullet"); i += 1; continue
            self._insert_into(widget, stripped, "body")
            i += 1

    def _insert_into(self, widget: tk.Text, text: str, base_tag: str) -> None:
        """Insert inline-formatted text into a tk.Text widget."""
        widget.insert("end", "\n", base_tag)
        i = 0
        while i < len(text):
            if text[i:i+2] == "**":
                end = text.find("**", i + 2)
                if end != -1:
                    widget.insert("end", text[i+2:end], (base_tag, "bold"))
                    i = end + 2; continue
            if text[i] == "`":
                end = text.find("`", i + 1)
                if end != -1:
                    widget.insert("end", text[i+1:end], (base_tag, "code"))
                    i = end + 1; continue
            widget.insert("end", text[i], base_tag)
            i += 1
        widget.insert("end", "\n", base_tag)

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _on_mode_change(self, mode: str) -> None:
        self._report_frame.grid_remove()
        self._ai_frame.grid_remove()
        self._tables_frame.grid_remove()
        if mode == "Report":
            self._report_frame.grid(row=2, column=0, sticky="nsew")
        elif mode == "AI Report":
            self._ai_frame.grid(row=2, column=0, sticky="nsew")
        else:
            self._tables_frame.grid(row=2, column=0, sticky="nsew")

    # ── Tables population ─────────────────────────────────────────────────────

    def _populate_tables(self, result, markdown: str) -> None:
        self._build_issue_cards(markdown)
        self._populate_rec_table(markdown)
        self._populate_time_table(result)
        self._populate_sess_table(result)

        # Lay out the tables_frame rows
        row = 0
        if self._issue_container:
            self._issue_container.grid(
                row=row, column=0, sticky="ew", padx=12, pady=(8, 0))
            row += 1
        self._bottom_frame.grid(
            row=row, column=0, sticky="ew", padx=12, pady=(0, 0))
        row += 1
        self._sess_section.grid(
            row=row, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _build_issue_cards(self, markdown: str) -> None:
        """Parse issues and build _IssueCard widgets."""
        issues = _parse_issues(markdown)

        # Destroy old container
        if self._issue_container is not None:
            self._issue_container.destroy()

        if not issues:
            return

        container = ctk.CTkFrame(self._tables_frame, fg_color="transparent")
        container.columnconfigure(0, weight=1)

        self._sec_label(container, "Executive Summary — Issues", 0)

        for i, issue in enumerate(issues):
            card = _IssueCard(container, index=i + 1, issue=issue)
            card.grid(row=i + 1, column=0, sticky="ew", pady=(0, 10))

        self._issue_container = container

    def _populate_rec_table(self, markdown: str) -> None:
        rows = _parse_md_table(markdown, "Priority")
        if len(rows) < 2:
            self._rec_table.set_data([["—", "No recommendations parsed", "—", "—"]])
            return
        data = rows[1:]
        highlights = []
        for row in data:
            pri = row[0].strip() if row else ""
            highlights.append(
                "#6b1a1a" if pri == "P0" else
                "#3a3300" if pri in ("P1", "P2") else None
            )
        self._rec_table.set_data(data, highlights)

    def _populate_time_table(self, result) -> None:
        tb = getattr(result, "time_bottlenecks", None)
        if tb is None or getattr(tb, "n_turns_with_timing", 0) == 0:
            self._time_table.set_data([["No timing data", "—"]])
            return

        rows = [
            ["Total net compute",  f"{tb.total_time_s:.1f}s ({tb.total_time_s/60:.1f} min)"],
            ["Mean / turn",        f"{tb.mean_duration_s:.1f}s"],
            ["Median / turn",      f"{tb.median_duration_s:.1f}s"],
            ["Max turn",           f"{tb.max_duration_s:.1f}s"],
            ["Min turn",           f"{tb.min_duration_s:.1f}s"],
            ["Turns timed",        str(tb.n_turns_with_timing)],
        ]
        highlights = [
            None, None, None,
            "#6b1a1a" if tb.max_duration_s > 60 else None,
            None, None,
        ]
        self._time_table.set_data(rows, highlights)

    def _populate_sess_table(self, result) -> None:
        sf       = getattr(result, "session_flow", None)
        profiles = getattr(sf, "session_profiles", []) if sf else []
        rows, highlights = [], []
        for p in profiles:
            sid      = getattr(p, "session_id",   "")
            title    = getattr(p, "title",        "") or getattr(p, "session_title", "") or sid
            n_turns  = getattr(p, "n_turns",       0)
            err_rate = getattr(p, "error_rate",    0.0)
            tokens   = getattr(p, "total_tokens",  0)
            files    = getattr(p, "files_delivered",0)
            mode     = getattr(p, "agent_mode",   "")
            rows.append([
                sid, title[:45], n_turns,
                f"{err_rate:.1%}",
                f"{tokens:,}" if tokens else "0",
                files, mode,
            ])
            highlights.append(
                "#6b1a1a" if err_rate >= 0.5 else
                "#3a3300" if err_rate > 0   else None
            )
        if not rows:
            self._sess_table.set_data([["No session data", "", "", "", "", "", ""]])
        else:
            self._sess_table.set_data(rows, highlights)

    # ── Markdown rendering (Report mode) ──────────────────────────────────────

    def _configure_tags(self) -> None:
        w = self._text_widget
        w.tag_configure("h1",    font=("Consolas", 18, "bold"), foreground="#ffffff",   spacing3=12)
        w.tag_configure("h2",    font=("Consolas", 14, "bold"), foreground="#7ec8e3",   spacing3=8)
        w.tag_configure("h3",    font=("Consolas", 12, "bold"), foreground="#a8d8a8",   spacing3=6)
        w.tag_configure("body",  font=("Consolas", 11),         foreground="#e0e0e0")
        w.tag_configure("bold",  font=("Consolas", 11, "bold"), foreground="#ffffff")
        w.tag_configure("italic",font=("Consolas", 11, "italic"),foreground="#c0c0c0")
        w.tag_configure("code",  font=("Consolas", 10),         foreground="#7ee787",   background="#1e3a2f")
        w.tag_configure("code_block", font=("Consolas", 10),    foreground="#7ee787",   background="#1e3a2f", spacing1=6, spacing3=6)
        w.tag_configure("bullet",font=("Consolas", 11),         foreground="#e0e0e0",   lmargin1=20, lmargin2=30)
        w.tag_configure("table_header", font=("Consolas", 10, "bold"), foreground="#ffffff",  background="#3a3a3a")
        w.tag_configure("table_row",    font=("Consolas", 10),          foreground="#d0d0d0")
        w.tag_configure("blockquote",   font=("Consolas", 11, "italic"),foreground="#a0a0a0",  lmargin1=20, lmargin2=30)
        w.tag_configure("link",         font=("Consolas", 11, "underline"), foreground="#4a90d9")

    def _render_markdown(self, text: str) -> None:
        self._text_widget.configure(state="normal")
        self._text_widget.delete("1.0", "end")
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line    = lines[i]
            stripped = line.strip()

            if stripped == "---" or (stripped and set(stripped) == {"-"}):
                self._text_widget.insert("end", "\n" + "—" * 60 + "\n", "body")
                i += 1; continue

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
                if i < len(lines): i += 1
                continue

            if "|" in stripped and stripped.startswith("|"):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i]); i += 1
                self._render_table(table_lines); continue

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
        hdr = " | ".join(rows[0])
        self._text_widget.insert("end", hdr + "\n", "table_header")
        self._text_widget.insert("end", "=" * len(hdr) + "\n", "table_header")
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
