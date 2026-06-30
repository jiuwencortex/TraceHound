# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Outcome quality scorer.

Computes quality scores from implicit signals:
  - task_completed / follow_up_correction (base outcome)
  - conversation_length (conciseness bonus)
  - token efficiency (reward lower token usage per unit output)
  - tool failures (penalize failed tool calls)
  - latency (penalize excessive latency)

For jiuwenswarm logs, explicit_rating and llm_judge_score are never available,
so the implicit formula is the primary scoring mechanism.
"""

from __future__ import annotations

from .loader import TurnRecord


def compute_quality(turn: TurnRecord) -> float:
    """Return a scalar quality score in [0.0, 1.0] for a single turn."""
    # explicit_rating / llm_judge are legacy hooks for thalamus format
    if turn.explicit_rating == "positive":
        return 1.0
    if turn.explicit_rating == "negative":
        return 0.0
    if turn.llm_judge_score is not None:
        return max(0.0, min(1.0, float(turn.llm_judge_score)))

    # --- jiuwenswarm implicit signals ---
    score = 0.5

    # Base outcome
    if turn.task_completed:
        score += 0.2
    if turn.follow_up_correction:
        score -= 0.3

    # Conciseness bonus (shorter turns get a small boost)
    score += max(0.0, 0.1 - 0.02 * turn.conversation_length)

    # Tool failure penalty (-0.05 per failure, max -0.15)
    failure_penalty = min(0.15, 0.05 * turn.n_tool_failures)
    score -= failure_penalty

    # Token efficiency bonus (reward lower token burn for successful turns)
    if turn.task_completed and turn.total_tokens > 0:
        # Expect ~500 tokens for a simple successful turn
        token_ratio = turn.total_tokens / 500.0
        if token_ratio > 3.0:
            score -= 0.05  # penalize extremely token-heavy turns
        elif token_ratio < 1.0:
            score += 0.03  # reward efficient turns

    # Latency penalty (excessive latency suggests problems)
    if turn.total_latency_ms > 30000:  # > 30 seconds
        score -= 0.05
    elif turn.total_latency_ms > 60000:  # > 60 seconds
        score -= 0.08

    # Heartbeat sessions are always neutral (they're system health checks)
    if turn.is_heartbeat:
        score = 0.5

    return max(0.0, min(1.0, score))


def compute_qualities(turns: list[TurnRecord]) -> list[float]:
    """Return quality scores for a list of turns (same order)."""
    return [compute_quality(t) for t in turns]
