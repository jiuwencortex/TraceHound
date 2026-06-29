# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Data health analyzer.

Reports basic statistics about the loaded turn records: coverage of explicit
ratings and LLM judge scores, per-week turn counts, missing or low-data weeks,
and the date range of available logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..loader import TurnRecord

_LOW_DATA_THRESHOLD = 10  # turns per week below which a week is flagged


@dataclass(frozen=True)
class DataHealthResult:
    """Output of the DataHealthAnalyzer."""

    total_turns: int
    turns_per_week: dict[str, int]
    weeks_with_low_data: list[str]
    explicit_rating_coverage: float   # fraction of turns with explicit_rating set
    llm_judge_coverage: float          # fraction of turns with llm_judge_score set
    skipped_records: int
    date_range: tuple[datetime, datetime] | None
    log_files_found: list[str]

    def to_dict(self) -> dict:
        return {
            "total_turns": self.total_turns,
            "turns_per_week": self.turns_per_week,
            "weeks_with_low_data": self.weeks_with_low_data,
            "explicit_rating_coverage": round(self.explicit_rating_coverage, 4),
            "llm_judge_coverage": round(self.llm_judge_coverage, 4),
            "skipped_records": self.skipped_records,
            "date_range": (
                [self.date_range[0].isoformat(), self.date_range[1].isoformat()]
                if self.date_range
                else None
            ),
            "log_files_found": self.log_files_found,
        }


class DataHealthAnalyzer:
    """Analyze basic health metrics of the loaded turn log data."""

    def __init__(
        self,
        turns: list[TurnRecord],
        skipped_records: int = 0,
        log_files: list[Path] | None = None,
    ) -> None:
        self._turns = turns
        self._skipped = skipped_records
        self._log_files = log_files or []

    def analyze(self) -> DataHealthResult:
        turns = self._turns
        n = len(turns)

        turns_per_week: dict[str, int] = {}
        for t in turns:
            turns_per_week[t.week_tag] = turns_per_week.get(t.week_tag, 0) + 1

        weeks_with_low_data = [
            week for week, count in turns_per_week.items() if count < _LOW_DATA_THRESHOLD
        ]

        explicit_count = sum(1 for t in turns if t.explicit_rating is not None)
        judge_count = sum(1 for t in turns if t.llm_judge_score is not None)

        explicit_coverage = explicit_count / n if n else 0.0
        judge_coverage = judge_count / n if n else 0.0

        if turns:
            # turns are sorted ascending by timestamp
            date_range: tuple[datetime, datetime] | None = (
                turns[0].timestamp,
                turns[-1].timestamp,
            )
        else:
            date_range = None

        log_file_names = [p.name for p in self._log_files]

        return DataHealthResult(
            total_turns=n,
            turns_per_week=turns_per_week,
            weeks_with_low_data=sorted(weeks_with_low_data),
            explicit_rating_coverage=explicit_coverage,
            llm_judge_coverage=judge_coverage,
            skipped_records=self._skipped,
            date_range=date_range,
            log_files_found=log_file_names,
        )
