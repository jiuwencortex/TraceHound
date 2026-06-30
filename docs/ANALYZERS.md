# TraceHound Analyzers Reference

Each analyzer in `analyzer/analyzers/` receives the loaded `list[TurnRecord]` (and optionally
quality scores or raw session messages) and returns a frozen result dataclass. All results
are assembled into `ReportResult` by `TrajectoriesReport.run()`.

---

## 1. DataHealth (`data_health.py`)

**What it analyzes:** Basic sanity of the loaded dataset. Counts total turns, checks
field-level coverage (how many turns have timing data, token data, error text, etc.),
identifies weeks with fewer than 3 turns ("low-data weeks"), and tracks how many raw
JSONL records were skipped during loading due to malformed JSON.

**Typical print output:**

```
--- Data Health ---
  Total turns: 56
  Date range: 2026-05-01 → 2026-06-10
  Sessions loaded: 25
  Session IDs: abc123, def456, ghi789  (+ 20 more)
  Skipped (malformed): 0
  Low-data weeks: none
```

---

## 2. QualityTrends (`quality_trends.py`)

**What it analyzes:** Per-week quality score aggregates. Quality is computed by
`scorer.py` using a formula based on `task_completed`, `follow_up_correction`,
token efficiency, and latency. The analyzer tracks the per-week mean, task completion
count, and correction count, then derives an overall trend direction
(`improving` / `degrading` / `stable` / `insufficient_data`) from a linear regression
over weekly means.

**Typical print output:**

```
--- Quality Trend: degrading ---
  Overall mean quality: 0.362
  Best week: 2026-W20 (mean=0.500, n=3)
  Worst week: 2026-W23 (mean=0.312, n=18)
  Per-week breakdown (3 weeks):
    2026-W20: mean=0.500 n=3 completed=3 corrections=0
    2026-W22: mean=0.375 n=35 completed=9 corrections=18
    2026-W23: mean=0.312 n=18 completed=4 corrections=12
```

---

## 3. CorrectionPatterns (`correction_patterns.py`)

**What it analyzes:** Identifies jiuwenswarm-native signals whose presence in a turn
correlates with the user issuing a follow-up correction. Uses a lift metric:

```
lift = correction_rate_when_signal_present / baseline_correction_rate
```

Signals examined per turn: `tools_called` (type "tool"), `agent_mode` (type "mode"),
`error_category` (type "error_cat"). Any signal present in at least 5 turns with
lift ≥ 1.5 is flagged as "high-lift". Heartbeat turns are excluded.

**Typical print output:**

```
--- Correction Patterns ---
  Rate: 31.7% (13/41)
  No high-lift patterns.
```

Or when patterns exist:

```
--- Correction Patterns ---
  Rate: 31.7% (13/41)
    error_cat: api_auth correction=90.0% lift=2.84x
    tool: send_message correction=62.5% lift=1.97x
    mode: agent.plan correction=45.0% lift=1.42x
```

---

## 4. ConversationLength (`conversation_length.py`)

**What it analyzes:** The `conversation_length` field (number of messages in the
conversation history at turn time). Produces a distribution (min/median/p90/max),
buckets turns into short (1) / medium (2–3) / long (4–5) / very_long (6+) with
per-bucket quality and completion rate, and flags jiuwenswarm signals (tools called,
agent mode) whose turns have a median conversation length > 1.5× the global median.

**Typical print output:**

```
--- Conversation Length ---
  Range: min=1 median=2.0 p90=4.0 max=6
  Long turns (>=4): 3 OK / 8 failed
  Quality by bucket:
    short      (len 1-1): n=8 qual=0.500 complete=100.0%
    medium     (len 2-3): n=22 qual=0.382 complete=45.5%
    long       (len 4-5): n=9 qual=0.278 complete=11.1%
    very_long  (len 6-10000): n=2 qual=0.250 complete=0.0%
```

---

## 5. TimeBottlenecks (`time_bottlenecks.py`)

**What it analyzes:** Turn-level duration from the `duration_seconds` field. Computes
a full distribution (min/median/mean/p90/max/total), lists the slowest turns, computes
per-tool duration ratios (turns calling tool X vs. baseline), shows per-tool call timing
from raw session timestamps (if available), reports hourly activity distribution,
and derives a speed/quality verdict (`slower_is_worse`, `slower_is_better`, `no_correlation`).

**Typical print output:**

```
--- Time Bottlenecks ---
  Timed: 56/56
  Duration: min=0.0s median=23.5s mean=28.3s p90=66.4s max=110.7s
  Total wall time: 1584.8s (26.4 min)
  Speed/quality: no_correlation (slow_q=0.337 fast_q=0.387)
  Slowest turns:
    req_abc123...   110.7s [ERR] q=0.250 msgs=6 [send_message, read_file]
  Tool-duration correlation:
    send_message                   ratio=1.41x mean=35.6s n=22
  Hourly activity:
    09:00 ################     n= 12 q=0.375 dur=30.1s err=42%
```

---

## 6. TokenUsage (`token_usage.py`)

**What it analyzes:** Token consumption from `input_tokens`, `output_tokens`,
`total_tokens`, `usage_percent`, and `model_name`. Produces overall aggregates,
success vs. failure token comparison, context window utilization stats
(mean/median/p90/max `usage_percent`; turns above 80% flagged as "near limit"),
a rough USD cost estimate (Kimi pricing vs. default), per-week trends, per-model
breakdowns, and per-tool average token consumption. Heartbeat turns excluded.

**Typical print output:**

```
--- Token Usage ---
  Total tokens: 3,456,789 (in=2,890,123 out=566,666)
  Per turn: avg=84,311 median=72,450 max=210,000
  Efficiency: success=90,100 failure=82,000 ratio=0.00
  Context: avg=348.9% p90=420.1%
  Near-limit turns: 41
  Est. cost: $1.6789
    2026-W22: total=2,890,000 avg=82,571 near-limit=32
    moonshot-v1-8k         turns=41 total=3,456,789 avg=84,311
```

---

## 7. LLMPerformance (`llm_performance.py`)

**What it analyzes:** LLM timing metrics from `total_latency_ms`, `ttft_ms` (time
to first token), and `tpot_ms` (time per output token). Produces latency distributions
(min/median/p90/max), identifies the 10 slowest turns, breaks down slow turns into
"slow prompt processing" (TTFT > 5 s) vs. "slow generation" (TPOT > 100 ms),
computes token throughput (tok/s), per-model performance comparison, weekly latency
trends, and high-latency error rate (turns with latency > p90 that also had errors).
Heartbeat turns excluded. Turns without timing data are noted but excluded from stats.

**Typical print output:**

```
--- LLM Performance ---
  Timed turns: 41
  Total latency: min=1200ms median=19800ms p90=58400ms max=95100ms
  TTFT: min=800ms median=4200ms p90=12000ms
  TPOT: min=12ms median=45ms p90=110ms
  Throughput: 3812.3 tok/s
  Slowest turns:
    req_abc...  lat= 95100ms ttft= 12000ms tpot= 110.0ms [error]
    2026-W22: avg=22400ms slow_prompt=2 slow_gen=1
    moonshot-v1-8k       avg=22400ms ttft=4200ms throughput=3812.3t/s
```

---

## 8. ToolSuccess (`tool_success.py`)

**What it analyzes:** Tool execution outcomes from `n_tool_calls`, `n_tool_failures`,
`tool_errors`, and `tools_called`. Produces overall success rate, per-tool success rates
(approximated proportionally since raw per-tool breakdowns are not in `TurnRecord`),
retry loop detection (same single tool called > 2 times in a turn), top error messages,
recovery rate (task completed despite failures), weekly failure trends, and Pearson
correlation between per-turn failure rate and turn duration. Heartbeat turns excluded.

**Typical print output:**

```
--- Tool Success Rate ---
  Total calls: 82476 Failures: 0 Success: 100.0%
  Per-tool:
    send_message          100.0% (82476/82476)
  Recovery: 0/0 turns (0.0%)
```

---

## 9. ErrorCategories (`error_categories.py`)

**What it analyzes:** Error patterns from `follow_up_correction`, `error_category`,
`error_text`, and `session_id`. Categorizes errors into 9 known buckets:
`import`, `syntax`, `api_auth`, `timeout`, `filesystem`, `model`, `network`,
`execution`, `other`. Shows count and percentage per category with example messages,
per-session error profiles (error count + recovery), overall recovery rate
(sessions with errors that also had a completed turn), weekly error trends, tool-error
associations (which tools co-occur with errors), and persistent error categories
(appearing in > 1 session). Heartbeat turns excluded.

**Typical print output:**

```
--- Error Categorization ---
  Rate: 31.7% (13/41 turns)
  By category:
    api_auth        13 (100.0%)
    import           0 (0.0%)
  Error-prone sessions:
    session_abc123...         errors=8
  Persistent: api_auth
  Recovery: 0.0%
    2026-W22: 13/35 top=api_auth
```

---

## 10. UserQueries (`user_queries.py`)

**What it analyzes:** User query patterns from `user_query` and `user_query_length`.
Produces query length distribution (min/median/p90/max), buckets queries into
short (0–100 ch) / medium (101–300) / long (301–800) / very_long (801+) with quality
and completion rate per bucket, classifies query intent into types
(`coding`, `file_op`, `debug`, `analysis`, `question`, `general`), computes
Pearson correlation of query length with turn duration and token usage, identifies the
most tool-heavy query type, weekly average length trends, and the 5 longest/shortest
queries. Heartbeat turns excluded.

**Typical print output:**

```
--- User Query Analysis ---
  Length: min=18 median=102 mean=148 p90=312 max=743
  Length vs quality:
    short       (   0- 100ch): n=18 qual=0.431
    medium      ( 101- 300ch): n=14 qual=0.357
  Types:
    file_op     :  22 qual=0.364
    coding      :  12 qual=0.417
  Len vs duration: r=0.421
  Len vs tokens: r=0.312
```

---

## 11. SessionFlow (`session_flow.py`)

**What it analyzes:** Cross-turn patterns within sessions. Groups turns by `session_id`,
builds a `SessionProfile` for each session (turn count, duration, error count/rate,
token total, files delivered, dominant agent mode, heartbeat flag), detects error cascades
(≥ 2 consecutive turns with `follow_up_correction`, plus whether recovery occurred),
compares agent modes by completion/error rate (requires ≥ 5 sessions per mode), tracks
productive sessions (any files delivered), persistent errors (same error category
appearing > 1 time within a session), and heartbeat session statistics. Real and heartbeat
sessions are reported separately.

**Typical print output:**

```
--- Session Overview ---
  Total sessions: 25 (real: 10, heartbeat: 15)
  Turns per session: min=1 median=3.5 mean=4.1 max=12
  Agent modes:
    agent.plan: 8
    team: 2
  Productive sessions: 1/10
  Sessions with errors: 7/10
  Error cascades: 4 (3 recovered)
  Persistent errors: api_auth
```

---

## 12. ToolArguments (`tool_arguments.py`)

**What it analyzes:** Raw tool call arguments from `raw_sessions` (the `dict[Path, list[dict]]`
on `TrajectoriesLoader`). Extracts file paths from tool argument JSON, classifies tool calls
as read/write/unknown, counts file accesses per path, identifies the most common file
extensions, extracts and classifies shell commands (bash/shell/exec tools), flags
dangerous commands (`rm -rf`, `DROP TABLE`, `sudo`, etc.), measures argument complexity
(average key count per tool call), and detects retry patterns (same tool called > 1 time
with similar arguments in the same turn). Requires raw message data; returns empty result
if `raw_sessions` is empty.

**Typical print output:**

```
--- Tool Arguments & File Access ---
  Tool calls analyzed: 82476
  Accessed paths:
    /Users/mishka/.jiuwenswarm/agent/sessions...  [R=12 W=0]
  Commands:
    python               5
  Read/write ratio: 0.00
  Extensions: json(45), py(12), txt(8)
```

---

## 13. ContentDelivery (`content_delivery.py`)

**What it analyzes:** The quality and volume of content the agent delivers. Uses
`final_response_length` and `files_delivered` fields. Produces response length
distribution, buckets responses into terse (0–99 ch) / normal (100–499) /
verbose (500–1499) / essay (1500+) with mean quality per bucket, total files
delivered and averages per turn/session, productivity rate (turn produced files or
response > 100 chars), silent successes (task completed with zero response length),
tool-to-content ratio (turns with > 3 tool calls but response < 100 chars, which
may indicate the agent acted but did not explain), Pearson correlations (response
length vs. token count and vs. query length), weekly delivery trends, and top
file-delivering sessions. Heartbeat turns excluded.

**Typical print output:**

```
--- Content Delivery ---
  Response length: min=0 median=412 mean=523 p90=1245 max=4800
  Productive: 35/41 (85.4%)
  Files: 3 (0.07/turn)
  Silent successes: 2
    terse       : n=5 qual=0.350
    normal      : n=18 qual=0.406
    verbose     : n=12 qual=0.417
    essay       : n=6 qual=0.458
    2026-W22: avg_len=498 files=3
```
