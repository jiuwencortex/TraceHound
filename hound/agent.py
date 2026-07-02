# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""HoundAgent — the main event loop that wires all subsystems together."""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .accumulate.analyzer import IncrementalAnalyzer
from .actions.event_logger import EventLogger
from .actions.executor import ActionExecutor
from .actions.feedback_writer import JiuwenswarmFeedbackWriter
from .actions.markdown_writer import MarkdownAlertWriter
from .actions.notifier import MacOSNotifier
from .actions.slack_poster import SlackPoster
from .alerts.engine import AlertEngine
from .alerts.rules import build_rules
from .alerts.severity import Severity
from .advisor.advisor import LLMAdvisor
from .config.schema import AgentConfig
from .ingest.ingester import TurnIngester
from .memory.alert_store import AlertStore
from .memory.baseline_store import BaselineStore
from .memory.db import Database
from .memory.offset_store import IngestionOffsetStore
from .memory.snapshot_store import SnapshotStore
from .schedule.jobs import run_full_analysis, write_session_summary
from .schedule.scheduler import ReportScheduler
from .watch.watcher import WatchAgent


class HoundAgent:
    """Autonomous agent that continuously monitors jiuwenswarm logs.

    Lifecycle:
    1. Initialise all subsystems
    2. Start WatchAgent (OS filesystem events)
    3. Process NewDataEvent queue in main asyncio loop
    4. For each batch of new turns: update accumulators → evaluate alerts → dispatch actions
    5. Run ReportScheduler in background thread for periodic full analyses
    """

    def __init__(self, config: AgentConfig) -> None:
        self._cfg = config
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="hound-io"
        )

        # --- Memory ---
        self._db = Database(config.state_db_path)
        self._conn = self._db.connect()
        self._offsets = IngestionOffsetStore(self._conn)
        self._baselines = BaselineStore(self._conn)
        self._snapshots = SnapshotStore(self._conn)
        self._alert_store = AlertStore(self._conn)

        # --- Accumulator ---
        self._analyzer = IncrementalAnalyzer()

        # --- Actions ---
        handlers: list = [
            EventLogger(config.events_log_path),
        ]
        if config.actions.markdown_files:
            handlers.append(MarkdownAlertWriter(config.output_dir))
        if config.actions.macos_notification.enabled:
            handlers.append(
                MacOSNotifier(
                    min_severity=Severity(config.actions.macos_notification.min_severity)
                )
            )
        if config.actions.slack.enabled and config.actions.slack.webhook_url:
            handlers.append(
                SlackPoster(
                    webhook_url=config.actions.slack.webhook_url,
                    min_severity=Severity(config.actions.slack.min_severity),
                )
            )
        self._actions = ActionExecutor(handlers)

        # --- Alerts ---
        rules = build_rules(config, self._alert_store, self._offsets)
        self._alert_engine = AlertEngine(
            rules=rules,
            alert_store=self._alert_store,
            baseline_store=self._baselines,
            on_alert=self._on_alert,
        )

        # --- Advisor ---
        self._advisor = LLMAdvisor(config.advisor)

        # --- Feedback writer ---
        self._feedback = JiuwenswarmFeedbackWriter(config.feedback_path)

        # --- Watch ---
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watcher: WatchAgent | None = None

        # --- Ingester ---
        self._ingester: TurnIngester | None = None

        # --- Scheduler ---
        self._scheduler: ReportScheduler | None = None

        # Internal counters
        self._turns_since_snapshot = 0
        self._snapshot_interval = 25

        # Session-end detection: session_id → (last_seen_utc, accumulated_turns)
        self._session_last_seen: dict[str, tuple[datetime, list]] = {}
        self._session_summarised: set[str] = set()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start all subsystems and enter the main event loop."""
        self._loop = asyncio.get_running_loop()

        self._ingester = TurnIngester(
            offset_store=self._offsets,
            on_turns=self._on_new_turns,
            loop=self._loop,
            executor=self._executor,
        )

        self._watcher = WatchAgent(
            log_root=self._cfg.watch.log_root,
            event_queue=self._event_queue,
            loop=self._loop,
            debounce_ms=self._cfg.watch.debounce_ms,
            offset_getter=self._offsets.get_offset,
        )

        self._scheduler = self._build_scheduler()

        logger.info("hound: watching {}", self._cfg.watch.log_root)
        self._watcher.start()
        self._scheduler.start()

        try:
            await self._event_loop()
        finally:
            self._shutdown()

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    async def _event_loop(self) -> None:
        while True:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=60.0)
                await self._ingester.process(event)
            except asyncio.TimeoutError:
                # Periodic: evaluate rules even without new data (for no_data rule)
                self._alert_engine.evaluate(self._analyzer.state)
                self._check_session_ends()

    # ------------------------------------------------------------------
    # Turn processing
    # ------------------------------------------------------------------

    def _on_new_turns(self, turns) -> None:
        """Called from TurnIngester when new turns are parsed (may be in thread)."""
        self._analyzer.ingest(turns)
        state = self._analyzer.state

        # Track per-session activity for session-end detection
        now = datetime.now(tz=timezone.utc)
        for turn in turns:
            sid = turn.session_id or "unknown"
            prev_last, prev_turns = self._session_last_seen.get(sid, (now, []))
            self._session_last_seen[sid] = (now, prev_turns + [turn])
            # If a session gets new turns, reset its "summarised" flag
            self._session_summarised.discard(sid)

        # Evaluate alert rules
        self._alert_engine.evaluate(state)

        # Periodic snapshot save
        self._turns_since_snapshot += len(turns)
        if self._turns_since_snapshot >= self._snapshot_interval:
            self._turns_since_snapshot = 0
            self._snapshots.save(state.to_dict())

        # Periodic feedback write
        if self._cfg.actions.jiuwenswarm_feedback.enabled:
            # Write every N turns (not per-turn to avoid file thrash)
            if state.turn_count % 10 == 0:
                try:
                    self._feedback.write(state)
                except Exception:  # noqa: BLE001
                    pass

    def _check_session_ends(self) -> None:
        """Detect sessions that have gone idle and write their summary."""
        if not self._cfg.schedule.on_session_end:
            return
        idle_threshold_s = self._cfg.schedule.session_end_idle_minutes * 60
        now = datetime.now(tz=timezone.utc)
        for sid, (last_seen, turns) in list(self._session_last_seen.items()):
            if sid in self._session_summarised:
                continue
            elapsed_s = (now - last_seen).total_seconds()
            if elapsed_s >= idle_threshold_s:
                self._session_summarised.add(sid)
                # Find the file path for this session
                file_path = None
                for s in self._offsets.all_sessions():
                    if s["session_id"] == sid:
                        from pathlib import Path as _Path
                        file_path = _Path(s["file_path"])
                        break
                if file_path:
                    try:
                        write_session_summary(file_path, turns, reporter=None)
                        logger.info("hound: session-end summary written for {}", sid[:24])
                    except Exception:  # noqa: BLE001
                        pass

    def _on_alert(self, alert) -> None:
        """Called by AlertEngine when a new alert fires."""
        logger.warning("hound: ALERT [{}] {} — {}", alert.severity.value, alert.rule_id, alert.title)
        self._actions.dispatch(alert)

        # Optional LLM explanation
        if self._advisor.should_advise(alert):
            state = self._analyzer.state
            explanation = self._advisor.advise(alert, state)
            if explanation:
                logger.info("hound: LLM advice for {}:\n{}", alert.rule_id, explanation)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def _build_scheduler(self) -> ReportScheduler:
        cfg = self._cfg

        def _full_run(label: str):
            run_full_analysis(
                log_root=cfg.watch.log_root,
                max_weeks=cfg.analysis.max_weeks,
                qd_thresh=cfg.analysis.quality_deficit_threshold,
                lift_thresh=cfg.analysis.correction_lift_threshold,
                skip_heartbeats=cfg.analysis.skip_heartbeats,
                output_dir=cfg.output_dir,
                baseline_store=self._baselines,
                label=label,
            )
            # After full run, write feedback
            if cfg.actions.jiuwenswarm_feedback.enabled:
                try:
                    self._feedback.write(self._analyzer.state)
                except Exception:  # noqa: BLE001
                    pass

        return ReportScheduler(
            daily_time=cfg.schedule.daily_summary,
            weekly_time=cfg.schedule.weekly_report,
            daily_job=lambda: _full_run("daily"),
            weekly_job=lambda: _full_run("weekly"),
            hourly_check=cfg.schedule.hourly_check,
            hourly_job=lambda: self._alert_engine.evaluate(self._analyzer.state),
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        if self._watcher:
            self._watcher.stop()
        if self._scheduler:
            self._scheduler.stop()
        self._actions.shutdown()
        self._executor.shutdown(wait=False)
        # Final snapshot
        self._snapshots.save(self._analyzer.state.to_dict())
        logger.info("hound: shutdown complete")
