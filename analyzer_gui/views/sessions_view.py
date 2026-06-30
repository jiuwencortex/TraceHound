# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SessionsView — session list + turn browser with lazy loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import customtkinter as ctk

_TURNS_PER_PAGE = 50

_STATUS_COLORS = {
    "error": "#6b1a1a",
    "ok": "#1a472a",
    "incomplete": "#7a5c00",
}


class _TurnCard(ctk.CTkFrame):
    """Collapsible card showing one turn's details."""

    def __init__(self, parent, turn_dict: dict[str, Any], index: int, **kwargs) -> None:
        super().__init__(parent, fg_color=("gray86", "gray17"), **kwargs)
        self.columnconfigure(0, weight=1)

        self._turn = turn_dict
        self._expanded = False

        # Derive key values
        tid = turn_dict.get("turn_id", "") or turn_dict.get("id", "")
        agent_mode = turn_dict.get("agent_mode", "")
        quality = turn_dict.get("quality")
        has_error = bool(turn_dict.get("error_text") or turn_dict.get("error_category"))
        task_done = turn_dict.get("task_completed", False)
        dur = turn_dict.get("duration_seconds")
        tokens = turn_dict.get("total_tokens")
        tools = turn_dict.get("tools_called") or []

        # Status indicator
        if has_error:
            status = "ERR"
            hdr_color = "#6b1a1a"
        elif task_done:
            status = "OK"
            hdr_color = "#1a472a"
        else:
            status = "INC"
            hdr_color = "#3d3d00"

        # Header row (always visible)
        hdr = ctk.CTkFrame(self, fg_color=hdr_color, corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        hdr.columnconfigure(1, weight=1)

        idx_lbl = ctk.CTkLabel(hdr, text=f"#{index + 1}", width=36,
                               font=("", 11, "bold"), text_color="gray80")
        idx_lbl.grid(row=0, column=0, padx=(6, 0))

        tid_short = tid[:32] + "…" if len(tid) > 32 else tid
        title_text = f"{tid_short}  [{status}]"
        if agent_mode:
            title_text += f"  mode={agent_mode}"
        if dur is not None:
            title_text += f"  {dur:.1f}s"
        if tokens:
            title_text += f"  {tokens:,}tok"
        if quality is not None:
            title_text += f"  q={quality:.3f}"

        title_lbl = ctk.CTkLabel(hdr, text=title_text, font=("", 11),
                                 anchor="w", justify="left")
        title_lbl.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        expand_btn = ctk.CTkButton(
            hdr, text="▶", width=28, height=22, font=("", 10),
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._toggle,
        )
        expand_btn.grid(row=0, column=2, padx=(0, 4))
        self._expand_btn = expand_btn

        # Detail frame (hidden by default)
        self._detail = ctk.CTkFrame(self, fg_color="transparent")
        self._detail.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 4))
        self._detail.grid_remove()

        # Build detail content
        lines: list[str] = []
        if tid:
            lines.append(f"Turn ID : {tid}")
        req_id = turn_dict.get("request_id", "")
        if req_id:
            lines.append(f"Req  ID : {req_id}")
        if tools:
            lines.append(f"Tools   : {', '.join(tools)}")
        uq = turn_dict.get("user_query", "")
        if uq:
            preview = uq[:200] + ("…" if len(uq) > 200 else "")
            lines.append(f"Query   : {preview}")
        resp = turn_dict.get("final_response", "") or ""
        if resp:
            preview = resp[:200] + ("…" if len(resp) > 200 else "")
            lines.append(f"Response: {preview}")
        err = turn_dict.get("error_text", "") or ""
        if err:
            lines.append(f"Error   : {err[:120]}")
        files = turn_dict.get("files_delivered") or []
        if files:
            lines.append(f"Files   : {', '.join(str(f) for f in files[:5])}")

        detail_text = "\n".join(lines) if lines else "(no detail available)"

        ctk.CTkLabel(
            self._detail,
            text=detail_text,
            font=("Courier", 10),
            anchor="nw",
            justify="left",
            wraplength=700,
        ).pack(anchor="w", padx=4)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._detail.grid()
            self._expand_btn.configure(text="▼")
        else:
            self._detail.grid_remove()
            self._expand_btn.configure(text="▶")


class SessionsView(ctk.CTkFrame):
    """Horizontal split: session list (left) + turn browser (right)."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Sessions & Turns", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        # Body: left list + right browser
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, minsize=200, weight=1)
        body.columnconfigure(1, weight=4)

        # ── Left panel ──────────────────────────────────────────────────
        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Sessions", font=("", 13, "bold")).grid(
            row=0, column=0, pady=(8, 4), padx=8, sticky="w"
        )

        self._session_list = ctk.CTkScrollableFrame(left, label_text="")
        self._session_list.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._session_list.columnconfigure(0, weight=1)

        # ── Right panel ─────────────────────────────────────────────────
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._right_header = ctk.CTkLabel(
            right, text="Select a session", font=("", 13, "bold")
        )
        self._right_header.grid(row=0, column=0, pady=(8, 4), padx=8, sticky="w")

        self._turn_scroll = ctk.CTkScrollableFrame(right, label_text="")
        self._turn_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._turn_scroll.columnconfigure(0, weight=1)

        self._load_more_btn = ctk.CTkButton(
            right, text="Load more…", command=self._load_more
        )

        # State
        self._raw_sessions: dict[Path, list[dict]] = {}
        self._current_turns: list[dict] = []
        self._rendered_count = 0
        self._session_buttons: list[ctk.CTkButton] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh(self, result, loader, *_) -> None:
        if result is None or loader is None:
            return
        self._raw_sessions = getattr(loader, "raw_sessions", {})
        self._populate_session_list()

    # ------------------------------------------------------------------
    # Session list
    # ------------------------------------------------------------------

    def _populate_session_list(self) -> None:
        # Clear previous buttons
        for btn in self._session_buttons:
            btn.destroy()
        self._session_buttons.clear()

        paths = sorted(self._raw_sessions.keys(), key=lambda p: p.name)
        for i, path in enumerate(paths):
            turns = self._raw_sessions[path]
            n = len(turns)
            label = f"{path.parent.name}\n({n} turns)"
            btn = ctk.CTkButton(
                self._session_list,
                text=label,
                font=("", 11),
                anchor="w",
                height=44,
                fg_color="transparent",
                hover_color=("gray75", "gray25"),
                command=lambda p=path: self._show_session(p),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=2, padx=4)
            self._session_buttons.append(btn)

    # ------------------------------------------------------------------
    # Turn browser
    # ------------------------------------------------------------------

    def _show_session(self, path: Path) -> None:
        turns = self._raw_sessions.get(path, [])
        self._current_turns = turns
        self._rendered_count = 0

        # Clear existing turn cards
        for widget in self._turn_scroll.winfo_children():
            widget.destroy()
        self._load_more_btn.grid_remove()

        n_real = sum(1 for t in turns if not t.get("is_heartbeat"))
        n_hb = len(turns) - n_real
        hdr = f"{path.parent.name}  —  {len(turns)} turns"
        if n_hb:
            hdr += f"  ({n_hb} heartbeat)"
        self._right_header.configure(text=hdr)

        self._render_next_page()

    def _render_next_page(self) -> None:
        start = self._rendered_count
        end = min(start + _TURNS_PER_PAGE, len(self._current_turns))

        for i in range(start, end):
            card = _TurnCard(self._turn_scroll, self._current_turns[i], index=i)
            card.grid(row=i, column=0, sticky="ew", padx=4, pady=2)

        self._rendered_count = end

        if self._rendered_count < len(self._current_turns):
            remaining = len(self._current_turns) - self._rendered_count
            self._load_more_btn.configure(text=f"Load more… ({remaining} remaining)")
            self._load_more_btn.grid(
                row=self._rendered_count, column=0, pady=8, padx=4, in_=self._turn_scroll
            )
        else:
            self._load_more_btn.grid_remove()

    def _load_more(self) -> None:
        self._load_more_btn.grid_remove()
        self._render_next_page()
