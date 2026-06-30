# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Session flow analyzer.

Analyzes cross-turn patterns within sessions from jiuwenswarm logs.
Turns are already sorted chronologically and linked by ``session_id``.
Heartbeat sessions are tracked separately so they do not distort
real-session metrics.

Key signals:
  - Session size distribution (turns per session)
  - Error cascades (consecutive error turns) and recovery
  - Total token consumption per session
  - Mode quality comparison (``agent.plan`` vs ``team``)
  - Productive sessions (delivered files)
  - Persistent error categories across turns
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..loader import TurnRecord

_CASCADE_MIN_CONSECUTIVE = 2   # errors in this many consecutive turns = cascade
_MIN_SESSIONS_FOR_MODE_COMP = 5
_MIN_SESSIONS_FOR_DISTR = 3


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _distribution(vals: list[float]) -> dict:
    if not vals:
        return {
            "min": 0.0,
            "median": 0.0,
            "mean": 0.0,
            "p90": 0.0,
            "max": 0.0,
        }
    sorted_vals = sorted(vals)
    return {
        "min": round(min(vals), 2),
        "median": round(float(statistics.median(vals)), 2),
        "mean": round(sum(vals) / len(vals), 2),
        "p90": round(_percentile(sorted_vals, 90), 2),
        "max": round(max(vals), 2),
    }


@dataclass(frozen=True)
class SessionProfile:
    session_id: str
    title: str
    n_turns: int
    n_messages_estimate: int
    duration_s: float
    error_count: int
    error_rate: float
    completion_rate: float
    total_tokens: int
    files_delivered: int
    agent_mode: str
    is_heartbeat_session: bool

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "n_turns": self.n_turns,
            "n_messages_estimate": self.n_messages_estimate,
            "duration_s": round(self.duration_s, 2),
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "completion_rate": round(self.completion_rate, 4),
            "total_tokens": self.total_tokens,
            "files_delivered": self.files_delivered,
            "agent_mode": self.agent_mode,
            "is_heartbeat_session": self.is_heartbeat_session,
        }


@dataclass(frozen=True)
class ErrorCascade:
    session_id: str
    turn_indices_with_errors: list[int]
    did_recover: bool
    recovery_turn_index: int | None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turn_indices_with_errors": self.turn_indices_with_errors,
            "did_recover": self.did_recover,
            "recovery_turn_index": self.recovery_turn_index,
        }


@dataclass(frozen=True)
class HeartbeatSummary:
    n_heartbeat_sessions: int
    n_heartbeat_turns: int
    avg_heartbeat_duration_s: float

    def to_dict(self) -> dict:
        return {
            "n_heartbeat_sessions": self.n_heartbeat_sessions,
            "n_heartbeat_turns": self.n_heartbeat_turns,
            "avg_heartbeat_duration_s": round(self.avg_heartbeat_duration_s, 2),
        }


@dataclass(frozen=True)
class ModeQualityComparison:
    mode: str
    n_sessions: int
    mean_completion_rate: float
    mean_error_rate: float
    mean_tokens_per_session: float
    mean_duration_s: float

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "n_sessions": self.n_sessions,
            "mean_completion_rate": round(self.mean_completion_rate, 4),
            "mean_error_rate": round(self.mean_error_rate, 4),
            "mean_tokens_per_session": round(self.mean_tokens_per_session, 2),
            "mean_duration_s": round(self.mean_duration_s, 2),
        }


@dataclass(frozen=True)
class PersistentError:
    error_category: str
    n_sessions: int
    total_occurrences: int
    mean_occurrences_per_session: float

    def to_dict(self) -> dict:
        return {
            "error_category": self.error_category,
            "n_sessions": self.n_sessions,
            "total_occurrences": self.total_occurrences,
            "mean_occurrences_per_session": round(self.mean_occurrences_per_session, 2),
        }


@dataclass(frozen=True)
class SessionFlowResult:
    total_sessions: int
    total_real_sessions: int
    total_heartbeat_sessions: int

    session_size_distribution: dict
    session_error_rate_distribution: dict
    session_duration_distribution: dict
    session_tokens_distribution: dict

    n_error_cascades: int
    n_recovery_sessions: int
    error_cascades: list[ErrorCascade]

    heartbeat_summary: HeartbeatSummary

    agent_mode_distribution: dict[str, int]
    mode_quality_comparison: list[ModeQualityComparison]
    best_mode: str | None

    productive_sessions: int
    productive_session_rate: float

    persistent_errors: list[PersistentError]

    session_profiles: list[SessionProfile]

    def to_dict(self) -> dict:
        return {
            "total_sessions": self.total_sessions,
            "total_real_sessions": self.total_real_sessions,
            "total_heartbeat_sessions": self.total_heartbeat_sessions,
            "session_size_distribution": self.session_size_distribution,
            "session_error_rate_distribution": self.session_error_rate_distribution,
            "session_duration_distribution": self.session_duration_distribution,
            "session_tokens_distribution": self.session_tokens_distribution,
            "n_error_cascades": self.n_error_cascades,
            "n_recovery_sessions": self.n_recovery_sessions,
            "error_cascades": [e.to_dict() for e in self.error_cascades],
            "heartbeat_summary": self.heartbeat_summary.to_dict(),
            "agent_mode_distribution": self.agent_mode_distribution,
            "mode_quality_comparison": [m.to_dict() for m in self.mode_quality_comparison],
            "best_mode": self.best_mode,
            "productive_sessions": self.productive_sessions,
            "productive_session_rate": round(self.productive_session_rate, 4),
            "persistent_errors": [p.to_dict() for p in self.persistent_errors],
            "session_profiles": [s.to_dict() for s in self.session_profiles],
        }


class SessionFlowAnalyzer:
    """Analyze cross-turn session patterns from jiuwenswarm logs."""

    def __init__(
        self,
        turns: list[TurnRecord],
        cascade_min_consecutive: int = _CASCADE_MIN_CONSECUTIVE,
        min_sessions_for_mode_comp: int = _MIN_SESSIONS_FOR_MODE_COMP,
    ) -> None:
        self._turns = turns
        self._cascade_min = cascade_min_consecutive
        self._min_sessions_mode = min_sessions_for_mode_comp

    def analyze(self) -> SessionFlowResult:
        if not self._turns:
            return SessionFlowResult(
                total_sessions=0,
                total_real_sessions=0,
                total_heartbeat_sessions=0,
                session_size_distribution=_distribution([]),
                session_error_rate_distribution=_distribution([]),
                session_duration_distribution=_distribution([]),
                session_tokens_distribution=_distribution([]),
                n_error_cascades=0,
                n_recovery_sessions=0,
                error_cascades=[],
                heartbeat_summary=HeartbeatSummary(0, 0, 0.0),
                agent_mode_distribution={},
                mode_quality_comparison=[],
                best_mode=None,
                productive_sessions=0,
                productive_session_rate=0.0,
                persistent_errors=[],
                session_profiles=[],
            )

        # ------------------------------------------------------------------
        # Group turns by session, preserving chronological order
        # ------------------------------------------------------------------
        sessions: dict[str, list[TurnRecord]] = defaultdict(list)
        for turn in self._turns:
            sessions[turn.session_id].append(turn)

        real_profiles: list[SessionProfile] = []
        heartbeat_profiles: list[SessionProfile] = []
        error_cascades: list[ErrorCascade] = []
        n_recovery_sessions = 0

        # mode -> list of profiles
        mode_profiles: dict[str, list[SessionProfile]] = defaultdict(list)

        # persistent errors: category -> sessions with repeated occurrences
        persistent_error_counter: Counter = Counter()
        persistent_error_sessions: dict[str, set[str]] = defaultdict(set)

        for sid, turns in sessions.items():
            profile = self._build_profile(sid, turns)
            if profile.is_heartbeat_session:
                heartbeat_profiles.append(profile)
            else:
                real_profiles.append(profile)
                if profile.agent_mode:
                    mode_profiles[profile.agent_mode].append(profile)

            # Error cascades & recovery
            cascade = self._detect_cascade(profile, turns)
            if cascade:
                error_cascades.append(cascade)

            if profile.error_count > 0 and profile.completion_rate > 0:
                n_recovery_sessions += 1

            # Persistent errors
            cat_counts: Counter = Counter()
            for t in turns:
                if t.error_category:
                    cat_counts[t.error_category] += 1
            for cat, count in cat_counts.items():
                if count > 1:
                    persistent_error_counter[cat] += count
                    persistent_error_sessions[cat].add(sid)

        # ------------------------------------------------------------------
        # Distributions (real sessions only)
        # ------------------------------------------------------------------
        real_sizes = [p.n_turns for p in real_profiles]
        real_error_rates = [p.error_rate for p in real_profiles]
        real_durations = [p.duration_s for p in real_profiles if p.duration_s > 0]
        real_tokens = [p.total_tokens for p in real_profiles]

        # ------------------------------------------------------------------
        # Mode comparison (real sessions only)
        # ------------------------------------------------------------------
        mode_comp: list[ModeQualityComparison] = []
        for mode, profiles in mode_profiles.items():
            if len(profiles) < self._min_sessions_mode:
                continue
            n = len(profiles)
            mode_comp.append(
                ModeQualityComparison(
                    mode=mode,
                    n_sessions=n,
                    mean_completion_rate=sum(p.completion_rate for p in profiles) / n,
                    mean_error_rate=sum(p.error_rate for p in profiles) / n,
                    mean_tokens_per_session=sum(p.total_tokens for p in profiles) / n,
                    mean_duration_s=sum(p.duration_s for p in profiles) / n,
                )
            )
        mode_comp.sort(key=lambda m: m.mean_completion_rate, reverse=True)
        best_mode = mode_comp[0].mode if mode_comp else None

        # ------------------------------------------------------------------
        # Productive sessions
        # ------------------------------------------------------------------
        productive = [p for p in real_profiles if p.files_delivered > 0]
        productive_rate = len(productive) / len(real_profiles) if real_profiles else 0.0

        # ------------------------------------------------------------------
        # Persistent errors summary (real sessions only)
        # ------------------------------------------------------------------
        persistent_errors: list[PersistentError] = []
        for cat, total_occ in persistent_error_counter.items():
            sess_count = len(persistent_error_sessions[cat])
            if sess_count < 1:
                continue
            persistent_errors.append(
                PersistentError(
                    error_category=cat,
                    n_sessions=sess_count,
                    total_occurrences=total_occ,
                    mean_occurrences_per_session=total_occ / sess_count,
                )
            )
        persistent_errors.sort(key=lambda p: p.total_occurrences, reverse=True)

        # ------------------------------------------------------------------
        # Heartbeat summary
        # ------------------------------------------------------------------
        hb_turns = sum(p.n_turns for p in heartbeat_profiles)
        hb_duration_sum = sum(
            p.duration_s for p in heartbeat_profiles
        )
        hb_avg_dur = hb_duration_sum / len(heartbeat_profiles) if heartbeat_profiles else 0.0
        heartbeat_summary = HeartbeatSummary(
            n_heartbeat_sessions=len(heartbeat_profiles),
            n_heartbeat_turns=hb_turns,
            avg_heartbeat_duration_s=hb_avg_dur,
        )

        # ------------------------------------------------------------------
        # Assemble result
        # ------------------------------------------------------------------
        all_profiles = sorted(
            real_profiles + heartbeat_profiles,
            key=lambda p: p.session_id,
        )

        return SessionFlowResult(
            total_sessions=len(sessions),
            total_real_sessions=len(real_profiles),
            total_heartbeat_sessions=len(heartbeat_profiles),
            session_size_distribution=_distribution([float(v) for v in real_sizes]),
            session_error_rate_distribution=_distribution(real_error_rates),
            session_duration_distribution=_distribution(real_durations),
            session_tokens_distribution=_distribution([float(v) for v in real_tokens]),
            n_error_cascades=len(error_cascades),
            n_recovery_sessions=n_recovery_sessions,
            error_cascades=error_cascades,
            heartbeat_summary=heartbeat_summary,
            agent_mode_distribution=dict(Counter(p.agent_mode for p in real_profiles)),
            mode_quality_comparison=mode_comp,
            best_mode=best_mode,
            productive_sessions=len(productive),
            productive_session_rate=productive_rate,
            persistent_errors=persistent_errors,
            session_profiles=all_profiles,
        )

    def _build_profile(self, session_id: str, turns: list[TurnRecord]) -> SessionProfile:
        n_turns = len(turns)
        n_messages_estimate = sum(t.conversation_length for t in turns)
        duration_s = (
            (turns[-1].timestamp - turns[0].timestamp).total_seconds()
            if n_turns > 1
            else turns[0].duration_seconds
        )
        error_count = sum(1 for t in turns if t.follow_up_correction)
        completed_count = sum(1 for t in turns if t.task_completed)
        total_tokens = sum(t.total_tokens for t in turns)
        files_delivered = sum(t.files_delivered for t in turns)
        agent_mode = (
            max(
                Counter(t.agent_mode for t in turns if t.agent_mode).most_common(),
                key=lambda x: x[1],
            )[0]
            if any(t.agent_mode for t in turns)
            else ""
        )
        is_heartbeat = all(t.is_heartbeat for t in turns) or any(t.is_heartbeat for t in turns)
        title = turns[0].session_title if turns else ""

        return SessionProfile(
            session_id=session_id,
            title=title,
            n_turns=n_turns,
            n_messages_estimate=n_messages_estimate,
            duration_s=duration_s,
            error_count=error_count,
            error_rate=error_count / n_turns if n_turns else 0.0,
            completion_rate=completed_count / n_turns if n_turns else 0.0,
            total_tokens=total_tokens,
            files_delivered=files_delivered,
            agent_mode=agent_mode,
            is_heartbeat_session=is_heartbeat,
        )

    def _detect_cascade(
        self, profile: SessionProfile, turns: list[TurnRecord]
    ) -> ErrorCascade | None:
        if profile.error_count < self._cascade_min:
            return None

        indices: list[int] = []
        for i, t in enumerate(turns):
            if t.follow_up_correction:
                indices.append(i)
            else:
                if len(indices) >= self._cascade_min:
                    break
                indices = []

        # Also check trailing run
        if len(indices) < self._cascade_min:
            # Re-scan for any consecutive run
            indices = []
            current_run: list[int] = []
            for i, t in enumerate(turns):
                if t.follow_up_correction:
                    current_run.append(i)
                else:
                    if len(current_run) >= self._cascade_min:
                        indices = current_run
                        break
                    current_run = []
            if len(current_run) >= self._cascade_min:
                indices = current_run

        if len(indices) < self._cascade_min:
            return None

        # Recovery: after the last error index, any successful turn?
        last_err = max(indices)
        did_recover = any(
            t.task_completed for t in turns[last_err + 1 :]
        )
        recovery_idx: int | None = None
        if did_recover:
            for i in range(last_err + 1, len(turns)):
                if turns[i].task_completed:
                    recovery_idx = i
                    break

        return ErrorCascade(
            session_id=profile.session_id,
            turn_indices_with_errors=indices,
            did_recover=did_recover,
            recovery_turn_index=recovery_idx,
        )
