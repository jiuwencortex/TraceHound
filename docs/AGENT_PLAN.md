# TraceHound Agent — Architecture Plan

> **Status:** Planning
> **Goal:** Transform TraceHound from a passive batch-analysis tool into an autonomous agent
> that continuously watches jiuwenswarm logs, detects issues in real time, and takes
> action without being asked.

---

## 1. What Changes and Why

### Current TraceHound (passive tool)
```
You run it → it loads logs → you read the report → you decide what to do
```

### TraceHound Agent (autonomous agent)
```
It watches logs continuously → it notices changes → it decides what matters
→ it acts (alerts, reports, writes files, feeds back) → it waits for the next event
```

The key difference is **initiative**: the agent runs a loop independently, holds memory
of past states, applies a decision layer to determine what is worth surfacing, and
executes actions — all without a human kicking it off each time.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TraceHound Agent                                   │
│                                                                               │
│   ┌──────────────┐    ┌───────────────┐    ┌────────────────────────────┐   │
│   │  WatchAgent  │───▶│ TurnIngester  │───▶│  IncrementalAnalyzer       │   │
│   │  (fs events) │    │ (parse new    │    │  (maintains rolling        │   │
│   │              │    │  JSONL lines) │    │   windows + baselines)     │   │
│   └──────────────┘    └───────────────┘    └────────────┬───────────────┘   │
│                                                          │                   │
│                                            ┌─────────────▼──────────────┐   │
│                                            │      AlertEngine           │   │
│                                            │  (rules → signals →        │   │
│                                            │   decisions)               │   │
│                                            └─────────────┬──────────────┘   │
│                                                          │                   │
│   ┌──────────────┐    ┌───────────────┐    ┌────────────▼───────────────┐   │
│   │  MemoryStore │    │  LLMAdvisor   │    │   ActionExecutor           │   │
│   │  (SQLite:    │◀──▶│  (optional:   │◀───│   (decides what to do,     │   │
│   │  baselines,  │    │  interpret    │    │    dispatches to channels) │   │
│   │  history,    │    │  findings in  │    └────────────────────────────┘   │
│   │  ack'd alts) │    │  natural lang)│                                      │
│   └──────────────┘    └───────────────┘                                      │
│                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Output Channels                                   │   │
│   │  Markdown files │ macOS notifications │ Slack webhook │ SQLite log  │   │
│   │  Jiuwenswarm feedback files │ Scheduled summary reports             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 WatchAgent

**Responsibility:** Detect new or modified `history.jsonl` files under the log root.

**Implementation:**
- Use `watchdog` library (`pip install watchdog`) for `inotify` / `FSEvents` / `ReadDirectoryChangesW`
- Watch the entire `~/.jiuwenswarm/agent/sessions/` tree recursively
- On `FileCreatedEvent` or `FileModifiedEvent` matching `history.jsonl`, emit a `NewData` event
- Debounce rapid bursts (e.g., 500 ms quiet window) to avoid processing a file mid-write
- Also handle session directory creation (new session started)

**Key design:** WatchAgent knows nothing about analysis. It only converts filesystem
events into `NewData(path, session_id)` signals on an internal asyncio queue.

```
WatchAgent
├── watches:  log_root/agent/sessions/**/history.jsonl
├── emits:    NewData(path: Path, session_id: str, file_offset: int)
└── debounce: 500 ms
```

---

### 3.2 TurnIngester

**Responsibility:** Read ONLY the new lines added since the last time a file was processed
(tail mode), parse them into `TurnRecord` objects.

**Key design:** Tracks `{session_id → bytes_consumed}` in `MemoryStore` so it never
re-processes old data after a restart. This makes the agent stateful and restart-safe.

**Implementation:**
- Reuses existing `loader.py` parsing logic, but applied incrementally per-file
- Reads from `file_offset` bytes; updates offset after successful parse
- Groups messages by `request_id` to form complete turns (same as current loader)
- Emits `TurnBatch(session_id, turns: list[TurnRecord])` when a turn's `request_id`
  appears to be complete (no new messages for that request_id in 2 s)

**Complexity note:** A turn is "complete" when no new messages share its `request_id`
for a settling window. If jiuwenswarm writes messages synchronously (one turn at a
time), this is straightforward. If it can interleave turns, a 2 s settling window
covers the common case.

---

### 3.3 IncrementalAnalyzer

**Responsibility:** Maintain a rolling window of `TurnRecord` objects and re-run
analyzers efficiently as new turns arrive.

**Approach:** Not fully re-running all 13 analyzers on every new turn — that would
be wasteful. Instead, maintain **metric accumulators** that update in O(1) per turn:

| Metric                  | Accumulator type                        |
|-------------------------|-----------------------------------------|
| Quality score           | Exponential moving average (α=0.1)      |
| Error rate              | Rolling count over last N turns         |
| Token burn per turn     | Running mean + variance                 |
| Tool success rate       | Per-tool sliding window (last 50 calls) |
| Turn duration           | Percentile reservoir (t-digest sketch)  |
| Weekly aggregates       | Current-week bucket updated per turn    |

**Full re-analysis** (all 13 analyzers) is triggered on:
- Scheduled intervals (default: every 6 h)
- Manual request via CLI / API
- Session end detection (no new turns for 30 min in a session)

**Output:** `AnalyzerState` — a live snapshot of all accumulator values, plus the most
recent full `ReportResult`.

---

### 3.4 AlertEngine

**Responsibility:** Compare current `AnalyzerState` against configured thresholds and
previously acknowledged alert states to decide whether to fire an alert.

**Alert lifecycle:**
```
DETECTED → FIRING → RESOLVED (or ACKNOWLEDGED)
```

An alert fires when a condition transitions from OK to violated. It does NOT re-fire
on every turn while the condition remains violated. It fires again if it resolves and
then re-violates (flapping detection: suppress if violates < 5 min after resolution).

**Built-in alert rules (all configurable):**

| Rule ID               | Trigger condition                                            | Severity |
|-----------------------|--------------------------------------------------------------|----------|
| `quality_drop`        | 5-turn EMA quality drops > 0.15 below 4-week baseline       | WARNING  |
| `quality_critical`    | 5-turn EMA quality < 0.40                                    | CRITICAL |
| `error_spike`         | Error rate in last 20 turns > 2× baseline rate              | WARNING  |
| `tool_failure_storm`  | Any single tool: > 5 failures in last 10 calls              | CRITICAL |
| `context_pressure`    | mean_usage_percent > 0.80 over last 10 turns                | WARNING  |
| `context_critical`    | Any single turn with usage_percent > 0.95                   | CRITICAL |
| `latency_regression`  | Median total_latency_ms > 1.5× 7-day median                 | WARNING  |
| `new_error_category`  | Error category appears that hasn't appeared in last 14 days  | INFO     |
| `session_dead`        | No new turns in any session for > 2 h during working hours   | INFO     |
| `cost_threshold`      | Estimated daily cost exceeds configured budget               | WARNING  |
| `correction_loop`     | follow_up_correction rate > 0.40 in last 15 turns           | WARNING  |
| `no_data`             | No new log data for > 4 h (watchdog still running)           | WARNING  |

Each rule is a Python dataclass; new rules can be added without touching engine code.

**Custom rules:** Users define additional rules in `agent_config.yaml` as threshold
expressions referencing named metrics from `AnalyzerState`.

---

### 3.5 MemoryStore

**Responsibility:** Persist all agent state to SQLite so the agent survives restarts.

**Schema:**

```sql
-- Baselines for regression detection
CREATE TABLE baselines (
    metric_name TEXT PRIMARY KEY,
    value       REAL,
    computed_at TEXT  -- ISO datetime
);

-- Alert history (for deduplication and ack tracking)
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY,
    rule_id     TEXT,
    severity    TEXT,
    fired_at    TEXT,
    resolved_at TEXT,
    acked_at    TEXT,
    payload     TEXT  -- JSON with context values
);

-- Per-session ingestion offsets (for incremental reads)
CREATE TABLE ingestion_state (
    session_id  TEXT PRIMARY KEY,
    file_path   TEXT,
    bytes_read  INTEGER,
    last_turn   TEXT  -- ISO datetime of last processed turn
);

-- Accumulator snapshots (saved every N turns for crash recovery)
CREATE TABLE accumulator_snapshots (
    id          INTEGER PRIMARY KEY,
    snapshot_at TEXT,
    data        TEXT  -- JSON-serialized AnalyzerState
);

-- User annotations
CREATE TABLE annotations (
    turn_id     TEXT,
    note        TEXT,
    created_at  TEXT
);
```

**File location:** `~/.jiuwenswarm/tracehound_agent/state.db` (configurable)

---

### 3.6 LLMAdvisor (optional, opt-in)

**Responsibility:** Use an LLM to convert raw metric deltas into actionable natural-
language explanations and ranked recommendations.

**When it runs:**
- After a CRITICAL alert fires
- On the daily scheduled summary
- On demand via `tracehound-agent explain --alert <id>`

**What it receives:** A compact context bundle:
```
- Alert rule ID and trigger values
- Last 7 days quality trend (weekly means)
- Top 3 error messages in the last 24 h
- Tools with highest failure rates
- Any correction-pattern lifts > 2.0
- render_desktop() markdown (trimmed to fit context window)
```

**What it returns:**
```
## What happened
[2-3 sentence summary in plain English]

## Most likely root cause
[Hypothesis with supporting evidence]

## Suggested next steps
1. [Specific action]
2. [Specific action]
3. [Specific action]
```

**LLM backend:** Configurable — Kimi API (already used by jiuwenswarm), OpenAI,
Anthropic, or local Ollama. The advisor is a thin wrapper around the configured
client; the same system prompt is used regardless of backend.

**Privacy:** The advisor only sends aggregated metrics and anonymised error messages,
never raw user queries or full session content.

---

### 3.7 ActionExecutor

**Responsibility:** Receive fired alerts and execute configured actions.

**Action types:**

#### A. Write Markdown alert file
Write `~/.jiuwenswarm/tracehound_agent/alerts/{datetime}_{rule_id}.md`
containing the alert context, metric snapshot, and (if LLMAdvisor is on) the
natural language explanation. These can be picked up by jiuwenswarm itself or
read by the user.

#### B. macOS notification
Use `osascript` to fire a native macOS notification with title and summary.
Respects Do Not Disturb — only fires on WARNING+ by default.

#### C. Slack / Discord webhook
POST a JSON payload to a configured webhook URL. Includes severity emoji, rule
description, current vs threshold values, and a link to the GUI (if running).

#### D. Write jiuwenswarm feedback file
Write structured YAML to `~/.jiuwenswarm/tracehound_feedback.yaml`:
```yaml
generated_at: "2026-07-02T14:00:00Z"
quality_trend: degrading
problem_tools:
  - name: bash
    failure_rate: 0.38
    recommendation: "Consider adding retry logic"
  - name: file_write
    correction_lift: 2.3
    recommendation: "Review argument patterns"
high_risk_modes:
  - agent.plan
preferred_modes:
  - team
token_pressure: moderate
```
jiuwenswarm can optionally read this file to adjust its own behavior (e.g.,
avoid certain tool patterns, prefer a mode with better quality metrics). This
is the **feedback loop** that makes the agent genuinely useful to the system
it watches.

#### E. Append to shared log
Append a JSON line to `~/.jiuwenswarm/tracehound_agent/events.jsonl`.
Used by dashboards and other tools that want to subscribe to agent events.

#### F. Scheduled summary report
On a cron-like schedule (default: daily at 08:00, weekly on Monday at 07:00),
run the full 13-analyzer pipeline and write both a JSON result and a Markdown
summary report to the output directory. Optionally post the summary to Slack.

**Action routing:** Each alert rule specifies a list of action IDs to execute.
Users override routing per-rule in `agent_config.yaml`.

---

### 3.8 ReportScheduler

**Responsibility:** Trigger periodic full analyses and output reports on schedule.

**Schedules (defaults):**
- **Hourly heartbeat** — check `AnalyzerState` accumulators, fire any threshold alerts
- **Daily (08:00)** — full 13-analyzer run + daily Markdown summary + optional Slack post
- **Weekly (Mon 07:00)** — full run + weekly trend report + quality regression check vs
  previous 4-week baseline
- **On session end** — lightweight analysis of the just-completed session + per-session
  summary written to the session directory as `tracehound_summary.md`

The scheduler uses Python's `APScheduler` library (already common in async contexts)
or a simple `asyncio.sleep` loop — no external cron dependency.

---

## 4. Data Flow

```
New JSONL line written by jiuwenswarm
          │
          ▼
     WatchAgent (debounce 500ms)
          │  NewData(path, session_id, offset)
          ▼
    TurnIngester (tail read, group by request_id)
          │  TurnBatch(session_id, [TurnRecord, ...])
          ▼
  IncrementalAnalyzer (update accumulators)
          │  AnalyzerState (updated)
          ▼
     AlertEngine (evaluate all rules)
          │  [AlertFired(rule_id, severity, context), ...]
          ▼
    ActionExecutor
     ├── write alert markdown file       (always)
     ├── macOS notification              (if WARNING+)
     ├── Slack webhook                   (if configured)
     ├── jiuwenswarm feedback file       (if CRITICAL or scheduled)
     └── events.jsonl append             (always)

Separately, on schedule:
     ReportScheduler
          │  triggers full 13-analyzer run
          ▼
     TrajectoriesReport.run()  (existing code, unchanged)
          │  ReportResult
          ▼
     ActionExecutor (summary report actions)
          ├── write daily_summary_{date}.md
          ├── update baselines in MemoryStore
          └── optional Slack post
```

---

## 5. Configuration (`agent_config.yaml`)

```yaml
# TraceHound Agent configuration
agent:
  log_root: ~/.jiuwenswarm
  state_db: ~/.jiuwenswarm/tracehound_agent/state.db
  output_dir: ~/.jiuwenswarm/tracehound_agent
  max_weeks: 8
  working_hours: "09:00-22:00"   # for session_dead alert suppression

analysis:
  quality_deficit_threshold: 0.15
  correction_lift_threshold: 1.5

alerts:
  # Override thresholds per rule:
  quality_drop:
    enabled: true
    delta_threshold: 0.15
    window_turns: 5
  cost_threshold:
    enabled: true
    daily_budget_usd: 2.00
  session_dead:
    enabled: false            # turn off if running overnight experiments

actions:
  markdown_files:
    enabled: true
  macos_notification:
    enabled: true
    min_severity: WARNING
  slack:
    enabled: false
    webhook_url: ""           # set to activate
    min_severity: WARNING
  jiuwenswarm_feedback:
    enabled: true
    path: ~/.jiuwenswarm/tracehound_feedback.yaml
    update_interval_minutes: 30

schedule:
  hourly_check: true
  daily_summary: "08:00"
  weekly_report: "Monday 07:00"
  on_session_end: true

llm_advisor:
  enabled: false              # opt-in
  provider: kimi              # kimi | openai | anthropic | ollama
  model: moonshot-v1-8k
  api_key_env: MOONSHOT_API_KEY
  trigger_on: [CRITICAL]      # severities that trigger LLM explanation
```

---

## 6. CLI Interface (`tracehound-agent`)

The agent runs as a long-lived process, but also has a control CLI:

```
tracehound-agent start          # Start the agent (foreground)
tracehound-agent start --daemon # Start as background daemon (writes PID file)
tracehound-agent stop           # Stop the running daemon
tracehound-agent status         # Show current AnalyzerState snapshot
tracehound-agent alerts         # List active (un-resolved) alerts
tracehound-agent ack <id>       # Acknowledge an alert (suppress re-fire for 1 h)
tracehound-agent explain <id>   # Run LLMAdvisor on a specific alert
tracehound-agent report         # Trigger an immediate full analysis + report
tracehound-agent baseline       # Recompute baselines from last 4 weeks of data
tracehound-agent replay --since 2026-06-01  # Replay historical logs through agent
```

---

## 7. Integration with jiuwenswarm

The most powerful capability is a **feedback loop**: TraceHound Agent writes findings
in a format that jiuwenswarm can read and act on.

### 7.1 Preference hints (read by jiuwenswarm at session start)
`~/.jiuwenswarm/tracehound_feedback.yaml` — written by TraceHound, read by jiuwenswarm.

Contents:
- Quality trend and recent error categories
- Tools with high failure rates (jiuwenswarm can add retry logic or avoid them)
- Agent modes ranked by quality score
- Token pressure level (jiuwenswarm can compress context if "high")

### 7.2 Per-session quality signal (written after session ends)
`session_dir/tracehound_summary.md` — a quick markdown file the developer can read
to understand what happened in that session, without opening the full GUI.

### 7.3 Quality gate (optional, for CI/CD usage)
`tracehound-agent gate --min-quality 0.65 --last-turns 20`
Exits 0 if quality is OK, exits 1 if not. Can be used in a jiuwenswarm pipeline to
decide whether to continue a run or escalate to a human.

---

## 8. Existing Code Reuse Strategy

The agent is designed to **not break or replace** anything in the current codebase.

| Existing component        | Agent usage                                            |
|---------------------------|--------------------------------------------------------|
| `loader.py` / `TurnRecord`| Used by TurnIngester for incremental parsing           |
| All 13 analyzers          | Used unchanged by ReportScheduler for full runs        |
| `report.py`               | Used unchanged; `render_desktop()` feeds LLMAdvisor    |
| `scorer.py`               | Used per-turn in IncrementalAnalyzer accumulators      |
| `analyzer_gui/`           | GUI unchanged; add a "Live" status indicator on Overview|
| `docs/`                   | ANALYZERS.md and GUI_PLAN.md remain unchanged          |

New code lives exclusively in `tracehound_agent/` (new top-level package).

---

## 9. New Package Structure

```
TraceHound/
├── analyzer/                      # existing, untouched
├── analyzer_gui/                  # existing, untouched
├── tracehound_agent/              # NEW
│   ├── __init__.py
│   ├── __main__.py                # python -m tracehound_agent
│   ├── cli.py                     # CLI argument parsing + commands
│   ├── config.py                  # AgentConfig dataclass + YAML loader
│   ├── watch.py                   # WatchAgent (watchdog integration)
│   ├── ingest.py                  # TurnIngester (incremental tail parser)
│   ├── incremental.py             # IncrementalAnalyzer + accumulators
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── engine.py              # AlertEngine (rule evaluation loop)
│   │   ├── rules.py               # Built-in AlertRule dataclasses
│   │   └── models.py              # Alert, Severity, AlertState enums
│   ├── actions/
│   │   ├── __init__.py
│   │   ├── executor.py            # ActionExecutor (dispatch)
│   │   ├── markdown_writer.py     # Write alert .md files
│   │   ├── notify.py              # macOS osascript notification
│   │   ├── slack.py               # Slack webhook POST
│   │   └── feedback_writer.py     # jiuwenswarm feedback YAML
│   ├── memory.py                  # MemoryStore (SQLite)
│   ├── advisor.py                 # LLMAdvisor (optional LLM integration)
│   ├── scheduler.py               # ReportScheduler (APScheduler wrapper)
│   └── agent.py                   # TraceHoundAgent (main event loop, wires all above)
└── docs/
    ├── ANALYZERS.md
    ├── GUI_PLAN.md
    └── AGENT_PLAN.md              # this file
```

---

## 10. Implementation Phases

### Phase 1 — Foundation (minimal viable agent)
Files: `config.py`, `memory.py`, `ingest.py`, `watch.py`

Goals:
- Watch the log directory for new JSONL content
- Parse new turns incrementally (tail mode)
- Persist ingestion offsets in SQLite
- Log all new `TurnRecord` objects to console

Deliverable: `tracehound-agent start` watches logs and prints every new turn as it arrives.

---

### Phase 2 — Accumulators
Files: `incremental.py`

Goals:
- Maintain rolling EMA quality, error rate, token burn, tool failure rate
- Persist accumulator snapshots to SQLite on every turn
- Expose `AnalyzerState.snapshot()` as a dict for downstream use

Deliverable: `tracehound-agent status` prints a live metric snapshot.

---

### Phase 3 — Alert Engine
Files: `alerts/models.py`, `alerts/rules.py`, `alerts/engine.py`

Goals:
- Implement all 12 built-in rules from Section 3.4
- Alert lifecycle: DETECTED → FIRING → RESOLVED
- Deduplication (no re-fire while condition holds)
- Persist alert history in SQLite

Deliverable: Alerts print to console when thresholds are crossed.

---

### Phase 4 — Action Executor + Notifications
Files: `actions/executor.py`, `actions/markdown_writer.py`, `actions/notify.py`

Goals:
- Write Markdown alert files to output directory
- macOS notifications via `osascript`
- Slack webhook (if configured)
- `tracehound-agent alerts` lists firing alerts

Deliverable: A quality drop fires a macOS notification and writes a markdown file.

---

### Phase 5 — Scheduled Reports + Feedback Loop
Files: `scheduler.py`, `actions/feedback_writer.py`

Goals:
- Daily full 13-analyzer run
- Daily/weekly Markdown summary reports
- Write `tracehound_feedback.yaml` for jiuwenswarm consumption
- Per-session summary written when session ends

Deliverable: Agent runs silently in the background and delivers a morning summary.

---

### Phase 6 — LLM Advisor
Files: `advisor.py`

Goals:
- Integrate configured LLM API for natural-language explanations
- Trigger on CRITICAL alerts (configurable)
- `tracehound-agent explain <alert_id>` command

Deliverable: CRITICAL alerts include an LLM-generated "what happened / why / what to do" section.

---

### Phase 7 — GUI Integration
Changes: `analyzer_gui/overview_view.py`, `analyzer_gui/app.py`

Goals:
- Add "Agent Status" panel to OverviewView (active alerts count, last event time)
- Add "Live" toggle to GUI that polls the agent's SQLite state and updates charts
- Show firing alerts as banners in the GUI

Deliverable: The existing GUI shows live data when the agent is running alongside it.

---

### Phase 8 — Quality Gate + Packaging
Files: `cli.py` (`gate` command), `pyproject.toml`, systemd/launchd service files

Goals:
- `tracehound-agent gate` command for pipeline integration
- Proper daemon mode (PID file, stdout/stderr logging)
- Optional macOS launchd plist for auto-start
- `requirements-agent.txt` with additional dependencies

---

## 11. Additional Dependencies

```
# requirements-agent.txt
watchdog>=4.0.0        # filesystem event monitoring
apscheduler>=3.10.0    # scheduled jobs (no cron dependency)
pyyaml>=6.0            # agent_config.yaml parsing
aiohttp>=3.9.0         # Slack webhook async POST
```

The LLMAdvisor adds a provider-specific client (e.g., `openai`, `anthropic`)
only if the advisor is enabled in config.

---

## 12. Key Design Decisions

### Why not re-run all 13 analyzers on every new turn?
Full runs take ~1-3 seconds on large datasets. With potentially dozens of turns per
minute, that would cause the agent to fall behind. Accumulators are O(1) per turn
and give near-instant alert evaluation. Full runs are reserved for scheduled reports
and on-demand requests.

### Why SQLite and not an in-memory dict?
The agent should survive restarts without losing baselines or alert history. SQLite
is zero-dependency, process-safe, and fast enough for this workload (<1000 writes/day).

### Why not an async event loop for everything?
`watchdog` uses threads internally. The ingester and analyzer are compute-heavy.
The main loop is `asyncio` but ingestion runs in a thread pool executor.
`MemoryStore` uses a connection-per-thread pattern with `check_same_thread=False`.

### Why YAML config and not argparse only?
The agent is a long-lived process. Reloading config on SIGHUP (no restart needed)
is easier with a file than with command-line flags. The CLI only overrides the
config file for one-off commands.

### Why write feedback files instead of calling jiuwenswarm's API directly?
Loose coupling: TraceHound Agent does not depend on jiuwenswarm's internal API.
File-based communication is robust (survives jiuwenswarm restarts), inspectable
(you can `cat tracehound_feedback.yaml` at any time), and reversible (just delete
the file to stop influencing jiuwenswarm). jiuwenswarm can decide whether to read
it — TraceHound never forces a behavior change.
