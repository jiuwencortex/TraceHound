# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""ReportScheduler — triggers periodic full-analysis jobs."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Callable

from loguru import logger


class ReportScheduler:
    """Calls ``daily_job`` and ``weekly_job`` on a schedule.

    Uses a background thread with a simple sleep loop to avoid requiring
    APScheduler as a hard dependency.  The schedule is checked every minute.
    """

    def __init__(
        self,
        daily_time: str,       # "HH:MM"
        weekly_time: str,      # "Monday HH:MM"
        daily_job: Callable,
        weekly_job: Callable,
        hourly_check: bool = True,
        hourly_job: Callable | None = None,
    ) -> None:
        self._daily_hhmm = daily_time
        self._weekly_spec = weekly_time
        self._daily_job = daily_job
        self._weekly_job = weekly_job
        self._hourly_check = hourly_check
        self._hourly_job = hourly_job

        self._last_daily: str = ""
        self._last_weekly: str = ""
        self._last_hourly: int = -1

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hound-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(60)  # check every minute

    def _tick(self) -> None:
        now = datetime.now(tz=timezone.utc)
        hhmm = now.strftime("%H:%M")
        day_key = now.strftime("%Y-%m-%d")
        weekday = now.strftime("%A")

        # Daily
        if hhmm == self._daily_hhmm and day_key != self._last_daily:
            self._last_daily = day_key
            logger.info("hound: triggering daily report job")
            threading.Thread(target=self._daily_job, daemon=True).start()

        # Weekly
        target_day, target_time = (self._weekly_spec + " ").split(" ", 1)
        if weekday == target_day and hhmm == target_time.strip() and day_key != self._last_weekly:
            self._last_weekly = day_key
            logger.info("hound: triggering weekly report job")
            threading.Thread(target=self._weekly_job, daemon=True).start()

        # Hourly
        if self._hourly_check and self._hourly_job and now.hour != self._last_hourly:
            self._last_hourly = now.hour
            threading.Thread(target=self._hourly_job, daemon=True).start()
