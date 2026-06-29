# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Outcome quality scorer.

Mirrors the quality formula from ``thalamus/shared/outcome_scorer.py`` so the
analyzer can compute quality scores without importing thalamus directly.

Priority:
  1. explicit_rating  → "positive" = 1.0, "negative" = 0.0
  2. llm_judge_score  → use directly (already in [0, 1])
  3. implicit signals → formula based on task_completed, follow_up_correction,
                        and conversation_length
"""

from __future__ import annotations

from loader import TurnRecord


def compute_quality(turn: TurnRecord) -> float:
    """Return a scalar quality score in [0.0, 1.0] for a single turn."""
    if turn.explicit_rating == "positive":
        return 1.0
    if turn.explicit_rating == "negative":
        return 0.0

    if turn.llm_judge_score is not None:
        return max(0.0, min(1.0, float(turn.llm_judge_score)))

    # Implicit signals fallback
    score = 0.5
    if turn.task_completed:
        score += 0.2
    if turn.follow_up_correction:
        score -= 0.3
    score += max(0.0, 0.1 - 0.02 * turn.conversation_length)
    return max(0.0, min(1.0, score))


def compute_qualities(turns: list[TurnRecord]) -> list[float]:
    """Return quality scores for a list of turns (same order)."""
    return [compute_quality(t) for t in turns]
