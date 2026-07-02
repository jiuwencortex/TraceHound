# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Background analysis worker.

Runs TrajectoriesLoader + TrajectoriesReport in a daemon thread so the GUI
remains responsive.  All callbacks are invoked from the worker thread;
callers must marshal widget mutations back to the main thread via
``root.after(0, ...)``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable


class AnalysisBackend:
    """Wraps the analysis pipeline in a background daemon thread."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_async(
        self,
        log_dir: Path,
        max_weeks: int,
        quality_deficit_threshold: float,
        correction_lift_threshold: float,
        on_progress: Callable[[str], None],
        on_complete: Callable,
        on_error: Callable[[Exception], None],
        skip_heartbeats: bool = True,
    ) -> None:
        """Start analysis in a background thread.

        Parameters
        ----------
        on_progress(message):
            Called with status strings during loading.
        on_complete(result, loader, reporter):
            Called with the finished ReportResult, the TrajectoriesLoader
            instance, and the TrajectoriesReport instance.
        on_error(exc):
            Called if an exception is raised.
        """
        if self.is_running():
            return
        self._thread = threading.Thread(
            target=self._worker,
            args=(
                log_dir,
                max_weeks,
                quality_deficit_threshold,
                correction_lift_threshold,
                skip_heartbeats,
                on_progress,
                on_complete,
                on_error,
            ),
            daemon=True,
        )
        self._thread.start()

    def _worker(
        self,
        log_dir: Path,
        max_weeks: int,
        qd_thresh: float,
        lift_thresh: float,
        skip_heartbeats: bool,
        on_progress: Callable,
        on_complete: Callable,
        on_error: Callable,
    ) -> None:
        try:
            from analyzer.loader import TrajectoriesLoader
            from analyzer.report import TrajectoriesReport

            on_progress("Loading log files...")
            loader = TrajectoriesLoader(
                log_dir, max_weeks=max_weeks, skip_heartbeats=skip_heartbeats
            )

            on_progress("Running analyzers...")
            reporter = TrajectoriesReport(
                loader,
                quality_deficit_threshold=qd_thresh,
                correction_lift_threshold=lift_thresh,
            )
            result = reporter.run()
            on_complete(result, loader, reporter)
        except Exception as exc:  # noqa: BLE001
            on_error(exc)
