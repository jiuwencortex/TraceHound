# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""DesktopReportView — renders the Desktop-style analysis report as HTML."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

import customtkinter as ctk


class DesktopReportView(ctk.CTkFrame):
    """View that displays the Desktop-style markdown report rendered as HTML."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(self, text="Desktop Report", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        # Toolbar with buttons
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="e")

        self._refresh_btn = ctk.CTkButton(
            toolbar, text="🔄 Refresh", width=80, command=self._refresh_report
        )
        self._refresh_btn.pack(side="right", padx=(8, 0))

        self._save_btn = ctk.CTkButton(
            toolbar, text="💾 Save", width=80, command=self._save_report
        )
        self._save_btn.pack(side="right", padx=(8, 0))

        self._edit_btn = ctk.CTkButton(
            toolbar, text="✏️ Toggle Edit", width=100, command=self._toggle_edit
        )
        self._edit_btn.pack(side="right")

        # HTML content area using tkinter Text widget with HTML rendering capability
        self._text_widget = tk.Text(
            self,
            wrap="word",
            state="disabled",
            bg="#2b2b2b",
            fg="#e0e0e0",
            insertbackground="white",
            selectbackground="#4a90d9",
            selectforeground="white",
            padx=20,
            pady=20,
            font=("Consolas", 11),
            relief="flat",
            borderwidth=0,
        )
        self._text_widget.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Scrollbar
        scrollbar = ctk.CTkScrollbar(self, command=self._text_widget.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 8))
        self._text_widget.configure(yscrollcommand=scrollbar.set)

        # Configure text tags for markdown rendering
        self._configure_tags()

        self._current_markdown: str = ""
        self._result = None
        self._loader = None
        self._reporter = None
        self._is_edit_mode = False

    def _configure_tags(self) -> None:
        """Configure text styling tags."""
        # Header styles
        self._text_widget.tag_configure("h1", font=("Consolas", 18, "bold"), foreground="#ffffff", spacing3=12)
        self._text_widget.tag_configure("h2", font=("Consolas", 14, "bold"), foreground="#c7020e", spacing3=8)
        self._text_widget.tag_configure("h3", font=("Consolas", 12, "bold"), foreground="#e8a0a0", spacing3=6)

        # Body text
        self._text_widget.tag_configure("body", font=("Consolas", 11), foreground="#e0e0e0")
        self._text_widget.tag_configure("bold", font=("Consolas", 11, "bold"), foreground="#ffffff")
        self._text_widget.tag_configure("italic", font=("Consolas", 11, "italic"), foreground="#c0c0c0")

        # Code / inline code
        self._text_widget.tag_configure("code", font=("Consolas", 10), foreground="#7ee787", background="#1e3a2f")
        self._text_widget.tag_configure("code_block", font=("Consolas", 10), foreground="#7ee787", background="#1e3a2f", spacing1=6, spacing3=6)

        # Lists
        self._text_widget.tag_configure("bullet", font=("Consolas", 11), foreground="#e0e0e0", lmargin1=20, lmargin2=30)
        self._text_widget.tag_configure("list_item", font=("Consolas", 11), foreground="#e0e0e0", lmargin1=30, lmargin2=40)

        # Tables
        self._text_widget.tag_configure("table_header", font=("Consolas", 10, "bold"), foreground="#ffffff", background="#3a3a3a")
        self._text_widget.tag_configure("table_row", font=("Consolas", 10), foreground="#e0e0e0")
        self._text_widget.tag_configure("table_cell", font=("Consolas", 10), foreground="#e0e0e0")

        # Links
        self._text_widget.tag_configure("link", font=("Consolas", 11, "underline"), foreground="#4a90d9")

        # Blockquote / emphasis
        self._text_widget.tag_configure("blockquote", font=("Consolas", 11, "italic"), foreground="#a0a0a0", lmargin1=20, lmargin2=30)

        # Emoji / special
        self._text_widget.tag_configure("emoji", font=("Segoe UI Emoji", 11))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, result, loader, reporter) -> None:
        """Called when analysis completes — render the Desktop report."""
        self._result = result
        self._loader = loader
        self._reporter = reporter

        if reporter is not None:
            try:
                md_text = reporter.render_desktop(result)
            except Exception:
                md_text = "Error generating Desktop report."
        else:
            md_text = "No report available. Run analysis first."

        self._current_markdown = md_text
        self._render_markdown(md_text)

    def _render_markdown(self, text: str) -> None:
        """Simple markdown parser that converts to styled tkinter text."""
        self._text_widget.configure(state="normal")
        self._text_widget.delete("1.0", "end")

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Horizontal rule
            if stripped == "---" or set(stripped) == {"-"}:
                self._text_widget.insert("end", "\n" + "—" * 60 + "\n", "body")
                i += 1
                continue

            # Headers
            if stripped.startswith("# "):
                self._insert_formatted(stripped[2:], "h1")
                i += 1
                continue
            if stripped.startswith("## "):
                self._insert_formatted(stripped[3:], "h2")
                i += 1
                continue
            if stripped.startswith("### "):
                self._insert_formatted(stripped[4:], "h3")
                i += 1
                continue

            # Code block
            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                code_text = "\n".join(code_lines)
                self._text_widget.insert("end", "\n", "body")
                self._text_widget.insert("end", code_text + "\n", "code_block")
                if i < len(lines):
                    i += 1  # skip closing ```
                continue

            # Table
            if "|" in stripped and stripped.startswith("|"):
                # Render table
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                self._render_table(table_lines)
                continue

            # Empty line
            if not stripped:
                self._text_widget.insert("end", "\n", "body")
                i += 1
                continue

            # List items
            if stripped.startswith("- ") or stripped.startswith("* "):
                content = stripped[2:]
                self._insert_formatted("  • " + content, "bullet")
                i += 1
                continue
            if stripped.startswith("> "):
                self._insert_formatted(stripped[2:], "blockquote")
                i += 1
                continue

            # Regular paragraph with inline formatting
            self._insert_formatted(stripped, "body")
            i += 1

        self._text_widget.configure(state="disabled")

    def _insert_formatted(self, text: str, base_tag: str) -> None:
        """Insert text with inline markdown formatting (bold, italic, code, links)."""
        self._text_widget.insert("end", "\n", base_tag)

        # Parse inline formatting
        i = 0
        while i < len(text):
            # Bold **text**
            if text[i:i+2] == "**":
                end = text.find("**", i + 2)
                if end != -1:
                    self._text_widget.insert("end", text[i + 2:end], (base_tag, "bold"))
                    i = end + 2
                    continue

            # Italic *text* (but not **)
            if text[i] == "*" and (i + 1 >= len(text) or text[i + 1] != "*"):
                end = text.find("*", i + 1)
                if end != -1:
                    self._text_widget.insert("end", text[i + 1:end], (base_tag, "italic"))
                    i = end + 1
                    continue

            # Inline code `text`
            if text[i] == "`":
                end = text.find("`", i + 1)
                if end != -1:
                    self._text_widget.insert("end", text[i + 1:end], (base_tag, "code"))
                    i = end + 1
                    continue

            # Link [text](url)
            if text[i] == "[":
                close_bracket = text.find("]", i)
                if close_bracket != -1 and close_bracket + 1 < len(text) and text[close_bracket + 1] == "(":
                    close_paren = text.find(")", close_bracket + 2)
                    if close_paren != -1:
                        link_text = text[i + 1:close_bracket]
                        self._text_widget.insert("end", link_text, (base_tag, "link"))
                        i = close_paren + 1
                        continue

            # Regular character
            self._text_widget.insert("end", text[i], base_tag)
            i += 1

        self._text_widget.insert("end", "\n", base_tag)

    def _render_table(self, lines: list[str]) -> None:
        """Render a markdown table using Tkinter Text widget."""
        if not lines:
            return

        # Parse rows
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]  # Remove empty from leading/trailing |
            if cells and not all(c.replace("-", "").replace(":", "") == "" for c in cells):
                rows.append(cells)

        if not rows:
            return

        self._text_widget.insert("end", "\n", "body")

        # Render header
        if rows:
            header = rows[0]
            header_text = " | ".join(header)
            self._text_widget.insert("end", header_text + "\n", "table_header")
            self._text_widget.insert("end", "=" * len(header_text) + "\n", "table_header")

        # Render data rows
        for row in rows[1:]:
            row_text = " | ".join(row)
            self._text_widget.insert("end", row_text + "\n", "table_row")

        self._text_widget.insert("end", "\n", "body")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _refresh_report(self) -> None:
        """Re-generate the report from current data."""
        if self._reporter is not None and self._result is not None:
            try:
                md_text = self._reporter.render_desktop(self._result)
                self._current_markdown = md_text
                self._render_markdown(md_text)
            except Exception as exc:
                self._text_widget.configure(state="normal")
                self._text_widget.delete("1.0", "end")
                self._text_widget.insert("end", f"Error refreshing report:\n{exc}", "body")
                self._text_widget.configure(state="disabled")

    def _save_report(self) -> None:
        """Save the current report to the Desktop."""
        desktop = Path.home() / "Desktop"
        desktop.mkdir(exist_ok=True)
        out_path = desktop / "analysis.md"
        out_path.write_text(self._current_markdown, encoding="utf-8")

        # Show confirmation in status area
        self._text_widget.configure(state="normal")
        self._text_widget.insert("end", f"\n\n[✅ Saved to {out_path}]\n", "bold")
        self._text_widget.configure(state="disabled")
        self._text_widget.see("end")

    def _toggle_edit(self) -> None:
        """Toggle between read-only and editable mode."""
        self._is_edit_mode = not self._is_edit_mode
        if self._is_edit_mode:
            self._text_widget.configure(state="normal")
            self._edit_btn.configure(text="👁 View")
        else:
            self._current_markdown = self._text_widget.get("1.0", "end-1c")
            self._text_widget.configure(state="disabled")
            self._edit_btn.configure(text="✏️ Toggle Edit")
