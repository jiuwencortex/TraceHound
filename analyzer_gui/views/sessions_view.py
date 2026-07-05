# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SessionsView — session list + turn browser with lazy loading."""

from __future__ import annotations

import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any

import customtkinter as ctk

_TURNS_PER_PAGE = 50

# ── colour palette ────────────────────────────────────────────────────────────
_HDR_ERROR      = "#6b1a1a"   # dark red
_HDR_OK         = "#1a472a"   # dark green
_HDR_INCOMPLETE = "#3d3900"   # dark amber
_TXT_ERROR      = "#ff8a8a"
_TXT_OK         = "#80d080"
_TXT_INC        = "#d4b800"

_SENTINEL = object()


def _fmt_ts(ts: float | None) -> str:
    """Format a unix timestamp as 'YYYY-MM-DD HH:MM:SS UTC'."""
    if not ts:
        return ""
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _short_query(text: str, n: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text[:n] + "…" if len(text) > n else text


# ── TurnCard ──────────────────────────────────────────────────────────────────

class _TurnCard(ctk.CTkFrame):
    """Collapsible card for one conversation turn.

    Accepts either a TurnRecord dataclass (preferred) or a dict built from
    raw JSONL messages.
    """

    def __init__(self, parent, turn: Any, index: int, **kwargs) -> None:
        super().__init__(parent, fg_color=("gray86", "gray17"), **kwargs)
        self.columnconfigure(0, weight=1)

        self._turn = turn
        self._expanded = False

        # ── pull fields from TurnRecord or raw dict ──────────────────────
        def _g(attr: str, key: str | None = None, default=None):
            """Get from dataclass attr or dict key."""
            v = getattr(turn, attr, _SENTINEL)
            if v is not _SENTINEL:
                return v if v is not None else default
            return turn.get(key or attr, default) if isinstance(turn, dict) else default

        user_query      = _g("user_query",   default="")
        timestamp       = _g("timestamp",    default=None)
        duration        = _g("duration_seconds", default=None)
        total_tokens    = _g("total_tokens", default=0)
        input_tokens    = _g("input_tokens", default=0)
        output_tokens   = _g("output_tokens", default=0)
        model_name      = _g("model_name",   default="")
        agent_mode      = _g("agent_mode",   default="")
        task_done       = _g("task_completed", default=False)
        error_text      = _g("error_text",   default="")
        error_category  = _g("error_category", default="")
        tools_called    = _g("tools_called", default=[]) or []
        n_tool_calls    = _g("n_tool_calls", default=0)
        n_tool_failures = _g("n_tool_failures", default=0)
        tool_errors     = _g("tool_errors",  default=[]) or []
        turn_id         = _g("turn_id",      default="")
        session_id      = _g("session_id",   default="")

        # timestamp may be a datetime object (TurnRecord) or float (raw dict)
        if isinstance(timestamp, datetime.datetime):
            ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(timestamp, (int, float)):
            ts_str = _fmt_ts(float(timestamp))
        else:
            ts_str = ""

        has_error = bool(error_text or error_category)

        if has_error:
            status_label = "ERR"
            hdr_color    = _HDR_ERROR
            badge_color  = _TXT_ERROR
        elif task_done:
            status_label = "OK"
            hdr_color    = _HDR_OK
            badge_color  = _TXT_OK
        else:
            status_label = "INC"
            hdr_color    = _HDR_INCOMPLETE
            badge_color  = _TXT_INC

        # ── Header row ───────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=hdr_color, corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        hdr.columnconfigure(2, weight=1)

        # #N  [STATUS]
        ctk.CTkLabel(
            hdr, text=f"#{index + 1}", width=32,
            font=("", 11, "bold"), text_color="gray80",
        ).grid(row=0, column=0, padx=(6, 2))

        ctk.CTkLabel(
            hdr, text=f"[{status_label}]", width=40,
            font=("", 11, "bold"), text_color=badge_color,
        ).grid(row=0, column=1, padx=(0, 6))

        # user query preview (centre, grows)
        query_preview = _short_query(user_query) if user_query else "(no query)"
        ctk.CTkLabel(
            hdr, text=query_preview, font=("", 11),
            anchor="w", justify="left",
        ).grid(row=0, column=2, sticky="ew", padx=4, pady=4)

        # right-side metrics  ·  timestamp  ·  duration  ·  tokens
        meta_parts: list[str] = []
        if ts_str:
            meta_parts.append(ts_str)
        if duration is not None and duration > 0:
            meta_parts.append(f"{duration:.1f}s")
        if total_tokens:
            meta_parts.append(f"{total_tokens:,} tok")

        if meta_parts:
            ctk.CTkLabel(
                hdr, text="  ".join(meta_parts), font=("", 10),
                text_color="gray70", anchor="e",
            ).grid(row=0, column=3, padx=(0, 4))

        expand_btn = ctk.CTkButton(
            hdr, text="▶", width=28, height=22, font=("", 10),
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._toggle,
        )
        expand_btn.grid(row=0, column=4, padx=(0, 4))
        self._expand_btn = expand_btn

        # ── Detail frame (hidden by default) ─────────────────────────────
        self._detail = ctk.CTkFrame(self, fg_color="transparent")
        self._detail.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))
        self._detail.columnconfigure(1, weight=1)
        self._detail.grid_remove()

        def _row(label: str, value: str, row: int, color: str = "gray80") -> None:
            ctk.CTkLabel(
                self._detail, text=label + ":", font=("Courier", 10, "bold"),
                text_color="gray60", anchor="ne", justify="right", width=80,
            ).grid(row=row, column=0, sticky="ne", padx=(0, 6), pady=1)
            ctk.CTkLabel(
                self._detail, text=value, font=("Courier", 10),
                text_color=color, anchor="nw", justify="left", wraplength=650,
            ).grid(row=row, column=1, sticky="nw", pady=1)

        r = 0
        if user_query:
            preview = user_query[:400] + ("…" if len(user_query) > 400 else "")
            _row("Query", preview, r); r += 1

        if error_text:
            _row("Error", error_text[:300] + ("…" if len(error_text) > 300 else ""),
                 r, color=_TXT_ERROR); r += 1
        elif error_category:
            _row("Err cat.", error_category, r, color=_TXT_ERROR); r += 1

        if agent_mode:
            _row("Mode", agent_mode, r); r += 1

        if model_name:
            _row("Model", model_name, r); r += 1

        if total_tokens:
            tok_str = f"{total_tokens:,} total"
            if input_tokens or output_tokens:
                tok_str += f"  (in {input_tokens:,} / out {output_tokens:,})"
            _row("Tokens", tok_str, r); r += 1

        if duration is not None and duration > 0:
            _row("Duration", f"{duration:.2f} s", r); r += 1

        if tools_called:
            _row("Tools", ", ".join(tools_called), r); r += 1
        elif n_tool_calls:
            fails = f"  ({n_tool_failures} failed)" if n_tool_failures else ""
            _row("Tool calls", f"{n_tool_calls}{fails}", r); r += 1

        if tool_errors:
            _row("Tool errs", "; ".join(str(e) for e in tool_errors[:3]), r,
                 color=_TXT_ERROR); r += 1

        if turn_id:
            _row("Turn ID", turn_id, r); r += 1

        if r == 0:
            _row("Info", "(no detail available)", r)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._detail.grid()
            self._expand_btn.configure(text="▼")
        else:
            self._detail.grid_remove()
            self._expand_btn.configure(text="▶")


# ── raw-message fallback: group request_id → synthetic turn dict ──────────────

def _group_raw_messages(messages: list[dict]) -> list[dict]:
    """Group raw JSONL messages by request_id into synthetic turn dicts."""
    order: list[str] = []
    groups: dict[str, dict] = {}

    for msg in messages:
        rid = msg.get("request_id") or msg.get("id", "")
        # strip ":user"/":assistant" suffix if present
        rid = rid.split(":")[0] if ":" in rid else rid
        if rid not in groups:
            order.append(rid)
            groups[rid] = {
                "turn_id": rid,
                "user_query": "",
                "error_text": "",
                "error_category": "",
                "task_completed": False,
                "timestamp": None,
                "agent_mode": "",
                "duration_seconds": None,
            }
        g = groups[rid]

        role = msg.get("role", "")
        if role == "user":
            g["user_query"]  = msg.get("content", "")
            g["timestamp"]   = msg.get("timestamp")
            g["agent_mode"]  = msg.get("mode", "")
        elif role == "assistant":
            err = msg.get("error") or msg.get("content", "") if msg.get("event_type") == "chat.error" else ""
            if err:
                g["error_text"] = err
                g["error_category"] = "api_error"
            else:
                g["task_completed"] = True
            # compute duration from timestamps
            user_ts  = g.get("timestamp")
            asst_ts  = msg.get("timestamp")
            if user_ts and asst_ts:
                g["duration_seconds"] = float(asst_ts) - float(user_ts)

    return [groups[rid] for rid in order]


# ── SessionsView ──────────────────────────────────────────────────────────────

class SessionsView(ctk.CTkFrame):
    """Horizontal split: session list (left) + turn browser (right)."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Sessions & Turns", font=("", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(16, 8), sticky="w"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, minsize=220, weight=1)
        body.columnconfigure(1, weight=4)

        # ── Left panel ───────────────────────────────────────────────────
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

        # ── Right panel ──────────────────────────────────────────────────
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
        self._session_turns: dict[str, list[Any]] = {}   # session_id → TurnRecord list
        self._path_to_sid: dict[Path, str] = {}          # path → session_id
        self._current_turns: list[Any] = []
        self._rendered_count = 0
        self._session_buttons: list[ctk.CTkButton] = []

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self, result, loader, reporter=None, *_) -> None:
        if result is None or loader is None:
            return

        self._raw_sessions = getattr(loader, "raw_sessions", {})

        # Try to get rich TurnRecord objects from the reporter
        self._session_turns = {}
        self._path_to_sid = {}
        reporter_turns: list[Any] = []
        if reporter is not None:
            reporter_turns = getattr(reporter, "_turns", [])

        if reporter_turns:
            by_sid: dict[str, list[Any]] = defaultdict(list)
            for t in reporter_turns:
                by_sid[t.session_id].append(t)
            self._session_turns = dict(by_sid)

            # Map raw session paths → session_id via messages
            for path, messages in self._raw_sessions.items():
                for msg in messages:
                    sid = msg.get("session_id", "")
                    if not sid:
                        # derive from path: sessions/<sid>/history.jsonl
                        sid = path.parent.name
                    if sid in self._session_turns:
                        self._path_to_sid[path] = sid
                        break

        self._populate_session_list()

    # ── Session list ─────────────────────────────────────────────────────────

    def _populate_session_list(self) -> None:
        for btn in self._session_buttons:
            btn.destroy()
        self._session_buttons.clear()

        # Build display info per path
        entries: list[tuple[float, Path, str]] = []   # (last_ts, path, label)
        for path in self._raw_sessions:
            messages = self._raw_sessions[path]

            sid = self._path_to_sid.get(path, path.parent.name)
            turns_for_sid = self._session_turns.get(sid)

            if turns_for_sid:
                n = len(turns_for_sid)
                last_ts_dt = max(
                    (t.timestamp for t in turns_for_sid),
                    default=None,
                )
                last_ts = last_ts_dt.timestamp() if last_ts_dt else 0.0
                title = turns_for_sid[0].session_title or sid
                has_errors = any(bool(t.error_text) for t in turns_for_sid)
                err_mark = " ⚠" if has_errors else ""
                label = f"{title[:28]}{err_mark}\n{n} turn{'s' if n != 1 else ''}  ·  {_fmt_ts(last_ts)}"
            else:
                # fall back to raw messages
                user_msgs = [m for m in messages if m.get("role") == "user"]
                n = len(user_msgs)
                timestamps = [m.get("timestamp", 0) for m in messages if m.get("timestamp")]
                last_ts = max(timestamps) if timestamps else 0.0
                first_query = user_msgs[0].get("content", sid) if user_msgs else sid
                label = f"{_short_query(first_query, 28)}\n{n} turn{'s' if n != 1 else ''}  ·  {_fmt_ts(last_ts)}"

            entries.append((last_ts, path, label))

        # Sort newest-first
        entries.sort(key=lambda x: x[0], reverse=True)

        for i, (_, path, label) in enumerate(entries):
            btn = ctk.CTkButton(
                self._session_list,
                text=label,
                font=("", 11),
                anchor="w",
                height=52,
                fg_color="transparent",
                hover_color=("gray75", "gray25"),
                command=lambda p=path: self._show_session(p),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=2, padx=4)
            self._session_buttons.append(btn)

    # ── Turn browser ─────────────────────────────────────────────────────────

    def _show_session(self, path: Path) -> None:
        for widget in self._turn_scroll.winfo_children():
            widget.destroy()
        self._load_more_btn.grid_remove()
        self._rendered_count = 0

        sid = self._path_to_sid.get(path, path.parent.name)
        turns_for_sid = self._session_turns.get(sid)

        if turns_for_sid:
            # Rich TurnRecord objects
            self._current_turns = [t for t in turns_for_sid if not t.is_heartbeat]
            n_hb = len(turns_for_sid) - len(self._current_turns)
            n_err = sum(1 for t in self._current_turns if t.error_text)
            n_ok  = sum(1 for t in self._current_turns if t.task_completed)

            title = turns_for_sid[0].session_title or sid
            hdr = f"{title}  —  {len(self._current_turns)} turn(s)"
            if n_hb:
                hdr += f"  · {n_hb} heartbeat"
            parts = []
            if n_ok:
                parts.append(f"{n_ok} OK")
            if n_err:
                parts.append(f"{n_err} ERR")
            if parts:
                hdr += f"  · " + " / ".join(parts)
        else:
            # Fallback: group raw messages
            messages = self._raw_sessions.get(path, [])
            self._current_turns = _group_raw_messages(messages)
            hdr = f"{sid}  —  {len(self._current_turns)} turn(s)"

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
                row=self._rendered_count, column=0, pady=8, padx=4,
                in_=self._turn_scroll,
            )
        else:
            self._load_more_btn.grid_remove()

    def _load_more(self) -> None:
        self._load_more_btn.grid_remove()
        self._render_next_page()
