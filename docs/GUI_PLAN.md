# TraceHound GUI Plan

**Status:** Engineering specification — pre-implementation
**Target:** `/Users/mishka/PycharmProjects/openjiuwen/TraceHound/analyzer_gui/`

---

## Table of Contents

1. [Motivation and Constraints](#1-motivation-and-constraints)
2. [Python GUI Framework Evaluation](#2-python-gui-framework-evaluation)
3. [Recommended Framework: CustomTkinter](#3-recommended-framework-customtkinter)
4. [Architecture Overview](#4-architecture-overview)
5. [New Files and Packages](#5-new-files-and-packages)
6. [Screen and Panel Breakdown](#6-screen-and-panel-breakdown)
7. [Integration with the Existing Pipeline](#7-integration-with-the-existing-pipeline)
8. [New CLI Entry Point](#8-new-cli-entry-point)
9. [Dependencies](#9-dependencies)
10. [Implementation Phases](#10-implementation-phases)
11. [Widget Reference Table](#11-widget-reference-table)
12. [Error Handling and Edge Cases](#12-error-handling-and-edge-cases)
13. [Cross-Platform Notes](#13-cross-platform-notes)

---

## 1. Motivation and Constraints

TraceHound currently exposes a single CLI entry point (`python -m analyzer --log-dir ...`). All
analyzers produce rich structured data via `ReportResult`, but that data is rendered as plain UTF-8
text to stdout. For a typical jiuwenswarm dataset with dozens of sessions and hundreds of turns, the text output
can be 500+ lines — difficult to scan and impossible to compare interactively.

A desktop GUI would allow:

- Immediate visual triage (which session degraded? which tool is the bottleneck?)
- Drill-down from aggregate metrics to individual turns
- Interactive threshold adjustment (`quality_deficit_threshold`, `correction_lift_threshold`)
  with live re-analysis
- Side-by-side comparison of analyzers without reading monolithic text
- A session browser for exploring raw turn content without editing CLI flags

### Hard constraints

- **No JavaScript.** No web frontend of any kind (React, Vue, Angular, Flask/FastAPI serving HTML).
- **Cross-platform:** must run on Python 3.12 on both Windows 10/11 and macOS 13+.
- Only `loguru` is a current dependency; total additional weight must be reasonable.
- The existing `loader.py` + `report.py` pipeline must be **reused unchanged**. The GUI is a new
  presentation layer, not a replacement of existing logic.
- A new GUI entry point is added alongside — not replacing — the existing `python -m analyzer` CLI.

---

## 2. Python GUI Framework Evaluation

Four frameworks were considered: CustomTkinter, PyQt6, Dear PyGui, and wxPython.

### 2.1 CustomTkinter

CustomTkinter is a thin wrapper around Python's built-in `tkinter` that replaces its dated widgets
with modern, rounded, theme-aware equivalents (light/dark mode, accent colour). It ships as a pure
Python package (`pip install customtkinter`), has no C++ or Rust build step, and installs in under
five seconds.

**Pros:**
- `tkinter` is part of the Python standard library; CustomTkinter only adds cosmetic widgets on top.
- No external runtime DLLs on Windows; no macOS framework bundle required.
- Grid and pack geometry managers are well-understood and deterministic.
- `CTkScrollableFrame`, `CTkTabview`, `CTkTable` cover the most common TraceHound layouts.
- Ships `CTkProgressBar` for the analysis loading phase.
- Python-native threading: `threading.Thread` + `root.after()` polling is the standard
  pattern for keeping the UI responsive during long analysis runs.
- Stable API since version 5.x.

**Cons:**
- No built-in charting. `matplotlib` embedded via `FigureCanvasTkAgg` must be added separately.
- `tkinter` on some Linux distributions requires a system package (`python3-tk`). On Windows and
  macOS the stdlib ships with Tcl/Tk already bundled.

### 2.2 PyQt6

PyQt6 binds to Qt 6, a full-featured C++ GUI framework.

**Pros:**
- Extremely rich widget set: `QTableWidget`, `QTreeView`, `QSplitter`, `QChartView`.
- High DPI support is automatic on both platforms.
- Qt Designer enables WYSIWYG layout with `.ui` files.

**Cons:**
- **GPLv3 license** for PyQt6. Commercial/proprietary use requires a paid Riverbank license.
  TraceHound carries a Huawei copyright, making GPLv3 a legal concern.
- `pip install PyQt6` downloads ~100 MB of compiled binaries including the full Qt runtime.
- Build-time C extensions can fail in restricted corporate environments with no compiler.

### 2.3 Dear PyGui

Dear PyGui wraps the C++ Dear ImGui immediate-mode renderer via compiled Python bindings.

**Pros:**
- Very fast rendering; suitable for real-time dashboards.
- Built-in charts, histograms, and tables without an additional library.
- Modern look out of the box.

**Cons:**
- Immediate-mode paradigm (redraw every frame) requires manual scroll/selection state management.
- Compiled C extension: installation requires a compatible binary wheel for the exact Python
  version and platform.
- Fewer StackOverflow answers and community resources than tkinter or Qt.
- No built-in text wrapping; long turn IDs and tool names truncate.

### 2.4 wxPython

wxPython wraps the native wxWidgets C++ framework, rendering platform-native controls.

**Pros:**
- Genuinely native look on Windows (Win32) and macOS (Cocoa).
- `wx.grid.Grid` is powerful for tabular data.

**Cons:**
- `pip install wxPython` on Python 3.12 macOS ARM (M1/M2/M3) has historically lagged behind
  CPython releases; ARM64 wheels are delayed.
- Large compiled package (~20 MB wheel on Windows).
- The customisation story (themes, dark mode) is worse than CustomTkinter.

### 2.5 Comparison Matrix

| Criterion                    | CustomTkinter | PyQt6       | Dear PyGui | wxPython |
|------------------------------|:-------------:|:-----------:|:----------:|:--------:|
| Pure Python install          | Yes           | No          | No         | No       |
| License risk for Huawei code | None (MIT)    | GPLv3 risk  | None (MIT) | LGPL     |
| Charting built-in            | No (+mpl)     | Yes         | Yes        | No       |
| Cross-platform ease          | High          | High        | Medium     | Medium   |
| Dark mode / modern look      | Excellent     | Good        | Excellent  | Poor     |
| Python 3.12 macOS ARM wheel  | Yes           | Yes         | Yes*       | Delayed  |
| Corporate proxy install risk | Low           | Medium      | Medium     | Medium   |
| Suitable for data tables     | Good          | Excellent   | Good       | Good     |
| Total extra packages         | 2 (ctk+mpl)   | 2 (pyqt+ch) | 1          | 2        |

---

## 3. Recommended Framework: CustomTkinter

**Recommendation: CustomTkinter + Matplotlib** (embedded via `matplotlib.backends.backend_tkagg`).

The decisive reasons:

1. **License safety.** CustomTkinter is MIT. No GPLv3 exposure for proprietary code.
2. **Pure Python install.** `pip install customtkinter matplotlib` succeeds on any Python 3.12
   installation on Windows or macOS without a C compiler, Visual C++ redistributables, or system
   packages (the stdlib `tkinter` is bundled with the official CPython Windows and macOS
   installers).
3. **Matplotlib is well-understood.** `FigureCanvasTkAgg` embeds any matplotlib figure inside a
   `tk.Frame` with three lines of code — covers quality trend line charts, hourly bar charts, and
   duration histograms without introducing an unfamiliar GUI paradigm.
4. **Sufficient widget richness.** `CTkTabview`, `CTkScrollableFrame`, `CTkTextbox`,
   `CTkEntry` + `CTkSlider`, and `CTkTable` (companion package) cover every identified screen.
5. **Maintainability.** tkinter is part of the Python standard library. Even if CustomTkinter
   is abandoned, the fallback is plain tkinter with minimal visual regression.

---

## 4. Architecture Overview

```
TraceHound/
├── analyzer/                    (existing — NOT modified)
│   ├── loader.py
│   ├── report.py
│   ├── cli.py
│   ├── scorer.py
│   └── analyzers/
│       ├── data_health.py
│       ├── quality_trends.py
│       ├── correction_patterns.py
│       ├── conversation_length.py
│       ├── time_bottlenecks.py
│       ├── token_usage.py
│       ├── llm_performance.py
│       ├── tool_success.py
│       ├── error_categories.py
│       ├── user_queries.py
│       ├── session_flow.py
│       ├── tool_arguments.py
│       └── content_delivery.py
│
└── analyzer_gui/                (NEW package)
    ├── __init__.py              (empty)
    ├── __main__.py              (entry point: python -m analyzer_gui)
    ├── app.py                   (TraceHoundApp — root window + navigation)
    ├── gui_cli.py               (argparse wrapper for the GUI entry point)
    ├── backend.py               (AnalysisBackend — runs loader+report in background thread)
    ├── views/
    │   ├── __init__.py
    │   ├── load_view.py         (LoadView — log directory chooser + run button)
    │   ├── overview_view.py     (OverviewView — summary stat cards + quality badge)
    │   ├── quality_view.py      (QualityView — matplotlib line chart + session table)
    │   ├── timing_view.py       (TimingView — duration histogram + slowest-turns table)
    │   └── sessions_view.py     (SessionsView — session list + turn browser)
    └── widgets/
        ├── __init__.py
        ├── stat_card.py         (StatCard — reusable labelled metric card widget)
        ├── sortable_table.py    (SortableTable — CTkScrollableFrame + CTkTable wrapper)
        └── mpl_frame.py         (MplFrame — matplotlib FigureCanvasTkAgg wrapper)
```

The `analyzer_gui` package sits alongside the existing `analyzer` package in the repository root.
It imports from `analyzer` but `analyzer` has zero imports from `analyzer_gui`. The dependency
arrow is strictly one-directional.

---

## 5. New Files and Packages

### 5.1 `analyzer_gui/__main__.py`

```python
from analyzer_gui.gui_cli import main
main()
```

Mirrors the pattern in `analyzer/__main__.py`. Allows `python -m analyzer_gui` as the launch
command.

### 5.2 `analyzer_gui/gui_cli.py`

Parses GUI-specific command-line arguments and launches the application.

```python
import argparse
from pathlib import Path

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="TraceHoundGUI",
        description="TraceHound graphical dashboard.",
    )
    parser.add_argument("--log-dir", default=None, metavar="PATH",
        help="Pre-populate the log directory field on launch.")
    parser.add_argument("--max-sessions", type=int, default=30,
        help="Maximum sessions to load (default: 30).")
    return parser

def main() -> None:
    args = _build_parser().parse_args()
    from analyzer_gui.app import TraceHoundApp
    app = TraceHoundApp(
        initial_log_dir=Path(args.log_dir) if args.log_dir else None,
        initial_max_sessions=args.max_sessions,
    )
    app.mainloop()
```

### 5.3 `analyzer_gui/app.py`

Class `TraceHoundApp(customtkinter.CTk)`. Responsibilities:

- Creates the root window (title "TraceHound", minimum size 1100×700).
- Sets `customtkinter.set_appearance_mode("System")` to follow the OS light/dark theme.
- Builds a left-side `CTkFrame` navigation rail with `CTkButton` items: Load, Overview, Quality,
  Timing, Sessions.
- Holds a right-side content area where each `View` is instantiated and shown/hidden via
  `grid_remove()` / `grid()`.
- Stores the `AnalysisBackend` instance and the current `ReportResult` (initially `None`).
- Exposes `on_result_ready(result: ReportResult, loader: TrajectoriesLoader)` called from the
  backend thread via `root.after(0, callback)` to trigger all views to refresh.
- Exposes `start_analysis(config: AnalysisConfig)` called by `LoadView`.

### 5.4 `analyzer_gui/backend.py`

Class `AnalysisBackend`. Wraps the existing `TrajectoriesLoader` + `TrajectoriesReport` pipeline
in a `threading.Thread` so the GUI never blocks.

```python
import threading
from pathlib import Path
from typing import Callable
from analyzer.loader import TrajectoriesLoader
from analyzer.report import TrajectoriesReport, ReportResult

class AnalysisBackend:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None

    def run_async(
        self,
        log_dir: Path,
        max_sessions: int,
        quality_deficit_threshold: float,
        correction_lift_threshold: float,
        on_progress: Callable[[str], None],
        on_complete: Callable[[ReportResult, TrajectoriesLoader], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self._thread and self._thread.is_alive():
            return  # analysis already running; ignore
        self._thread = threading.Thread(
            target=self._worker,
            args=(log_dir, max_sessions,
                  quality_deficit_threshold,
                  correction_lift_threshold,
                  on_progress, on_complete, on_error),
            daemon=True,
        )
        self._thread.start()

    def _worker(self, log_dir, max_sessions,
                qd_thresh, lift_thresh,
                on_progress, on_complete, on_error):
        try:
            on_progress("Loading log files...")
            loader = TrajectoriesLoader(
                log_dir, max_weeks=max_sessions,
            )
            on_progress("Running analyzers...")
            reporter = TrajectoriesReport(
                loader,
                quality_deficit_threshold=qd_thresh,
                correction_lift_threshold=lift_thresh,
            )
            result = reporter.run()
            on_complete(result, loader)
        except Exception as exc:
            on_error(exc)
```

`on_progress`, `on_complete`, and `on_error` are called from the worker thread. Callers must use
`root.after(0, lambda: ...)` to marshal widget mutations back to the main thread.

---

## 6. Screen and Panel Breakdown

### 6.1 LoadView (`views/load_view.py`)

The first screen shown on launch.

**Widgets:**
- `CTkLabel` — "TraceHound" title
- `CTkEntry` `self.dir_entry` — typed log directory path
- `CTkButton` "Browse..." — opens `tkinter.filedialog.askdirectory()`
- `CTkEntry` `self.sessions_entry` — integer, default 30
- `CTkButton` "Run Analysis" — calls `app.start_analysis()`
- `CTkProgressBar` `self.progress_bar` — indeterminate pulse during analysis
- `CTkLabel` `self.status_label` — "Ready.", "Loading...", "Done.", "Error: ..."

If `--log-dir` was passed on the command line, the entry is pre-populated and analysis starts
automatically after the window initialises.

### 6.2 OverviewView (`views/overview_view.py`)

One-glance summary using `StatCard` widgets in a `CTkScrollableFrame`.

**Stat cards rendered from `ReportResult`:**

| Card label                  | Source                                                            |
|-----------------------------|-------------------------------------------------------------------|
| Total Turns                 | `result.data_health.total_turns`                                 |
| Date Range                  | `result.data_health.date_range` as "YYYY-MM-DD → YYYY-MM-DD"    |
| Overall Mean Quality        | `result.quality_trends.overall_mean` (colour-coded)              |
| Trend Direction             | `result.quality_trends.trend_direction` with arrow symbol        |
| Baseline Correction Rate    | `result.correction_patterns.baseline_correction_rate`            |
| Sessions (real / heartbeat) | `result.session_flow.total_real_sessions / total_heartbeat_sessions` |
| Median Turn Duration        | `result.time_bottlenecks.median_duration_s` (if > 0)            |
| Overall Error Rate          | `result.error_categories.overall_error_rate`                     |
| Estimated Cost              | `result.token_usage.estimated_total_cost` formatted as "$X.XXXX" |
| Productive Session Rate     | `result.session_flow.productive_session_rate`                    |

Colour coding for Overall Mean Quality: green frame (> 0.70), yellow (0.50–0.70), red (< 0.50).
Colour coding for Overall Error Rate: green (< 0.10), yellow (0.10–0.30), red (> 0.30).

Below the cards: a `CTkTextbox` (read-only, height=15) showing the first 80 lines of
`report.render_text(result)` for quick text-mode reference.

### 6.3 QualityView (`views/quality_view.py`)

**Upper half — `MplFrame` line chart:**
- X axis: session indices from `result.quality_trends.weeks` (chronological).
- Y axis: `mean_quality` per session, range [0, 1].
- Line colour: green (`improving`), red (`degrading`), grey otherwise.
- Filled area under line at 30% alpha.
- Secondary bar chart (twin axis, `ax.twinx()`) showing `n_turns` per session as light blue bars.
- Horizontal dashed reference line at `overall_mean`.
- Annotations on best and worst session data points.

**Lower half — `SortableTable`:**

Columns: `Session`, `Turns`, `Mean Quality`, `Completed`, `Corrections`

Data source: `result.quality_trends.weeks` (list of `WeeklyQualitySummary`).

Row colour coding: green background if `mean_quality > overall_mean + 0.05`, red if below `−0.05`.

### 6.4 TimingView (`views/timing_view.py`)

Only active when `result.time_bottlenecks.n_turns_with_timing > 0`; otherwise shows an
"No timing data available" label.

**Left column:**
- `MplFrame` — histogram of `duration_seconds` values across all timed turns (20 bins).
  Vertical dashed lines at `median_duration_s` and `p90_duration_s`.
- Row of `StatCard` widgets: min / median / p90 / max / total wall time.
- Speed/quality verdict label with colour (green = slower_is_better, red = slower_is_worse,
  grey = no_correlation).

**Right column — `CTkTabview` with four tabs:**

**Tab "Slowest Turns"** — `SortableTable`
Columns: `Turn ID`, `Duration (s)`, `Quality`, `Status`, `Tools Called`, `Messages`
Data: `result.time_bottlenecks.slowest_turns` (list of `TurnTimingRecord`).
Default sort: duration descending.

**Tab "Tool Turn Correlation"** — `SortableTable`
Columns: `Tool`, `Turns`, `Mean Duration (s)`, `Global Mean (s)`, `Ratio`
Data: `result.time_bottlenecks.tool_turn_correlation`.
Rows with `duration_ratio >= 1.5` highlighted red.

**Tab "Per-Tool Call Timing"** — `SortableTable`
Columns: `Tool`, `Calls`, `Mean (s)`, `Median (s)`, `p90 (s)`, `Max (s)`, `Total (s)`
Data: `result.time_bottlenecks.tool_call_timing`.
Only shown if `len(result.time_bottlenecks.tool_call_timing) > 0`.

**Tab "Hourly Distribution"** — `MplFrame` bar chart
X axis: hour 0–23 UTC. Y axis: `n_turns`. Bars colour-coded by `mean_quality` (green/yellow/red).
Data: `result.time_bottlenecks.hourly_distribution`.

### 6.5 SessionsView (`views/sessions_view.py`)

Uses `loader.raw_sessions` (the `dict[Path, list[dict]]` on `TrajectoriesLoader`) directly.

**Layout:** horizontal split — left panel 25%, right panel 75%.

**Left panel — Session list**
`CTkScrollableFrame` with one `CTkButton` per session path.
Button text: `path.parent.name` + turn count.
Clicking a session populates the right panel.

**Right panel — Turn browser**
Top: `CTkLabel` showing session name, file path, message count.
Below: `CTkScrollableFrame` where each turn is a collapsible `CTkFrame`:
- **Header row (always visible):** Turn ID (28 chars), status badge (OK / ERROR / NO_CONTENT),
  duration, message count. Clicking the header expands/collapses.
- **Expanded body:**
  - User query (first 300 chars) in a `CTkTextbox` (read-only, height=4).
  - Tools called in a `CTkLabel`.
  - Error text in a red `CTkLabel` (if `has_error`).
  - Assistant result preview (first 300 chars) in a `CTkTextbox` (read-only, height=4).

Turn groups are built by grouping `raw_sessions[path]` by `request_id`, mirroring
`report.py`'s `render_verbose()` logic.

**Lazy loading:** only the first 50 turns are rendered immediately. A "Load more..." `CTkButton`
appends the next 50 on each click, preventing widget overload for sessions with 200+ turns.

### 6.6 ErrorsView (`views/errors_view.py`)

Covers `result.error_categories` and `result.user_queries`.

**Layout:** `CTkTabview` with three tabs.

**Tab "Error Breakdown":**
- `SortableTable`: Columns `Category`, `Count`, `% of Errors`, `Affected Sessions`.
  Data: `result.error_categories.categories` (all 9 known categories; zeros still shown).
- Below: two `StatCard` widgets — Overall Error Rate, Recovery Rate.
- `CTkLabel` for persistent error categories.

**Tab "Weekly Errors":**
- `MplFrame` bar chart. X axis: week tags. Y axis: error count.
  Bars colour-coded red. Secondary line (twin axis) shows total turn count.
  Data: `result.error_categories.weekly_summaries`.

**Tab "User Queries":**
- Row of `StatCard` widgets: min length / median / mean / p90 / max.
- `SortableTable`: Columns `Type`, `Count`, `Mean Quality`, `Mean Duration (s)`, `Mean Tokens`.
  Data: `result.user_queries.query_type_distribution`.
- `CTkLabel` for most common type, best quality type, most tool-heavy type.
- Two `StatCard` widgets: Length vs Duration correlation, Length vs Tokens correlation.

### 6.7 TokensView (`views/tokens_view.py`)

Covers `result.token_usage`, `result.llm_performance`, `result.tool_success`,
and `result.content_delivery`.

**Layout:** `CTkTabview` with four tabs.

**Tab "Token Usage":**
- Row of `StatCard` widgets: Total Tokens, Mean/Turn, Context avg %, Near-limit Turns, Est. Cost.
- `SortableTable`: per-model breakdown.
  Columns: `Model`, `Turns`, `Total Tokens`, `Avg Tokens`, `Avg Context %`, `Est. Cost`.
  Data: `result.token_usage.model_summary`.
- `MplFrame` bar chart of weekly total tokens.
  Data: `result.token_usage.weekly_summary`.

**Tab "LLM Latency":**
- Row of `StatCard` widgets: Median Latency, p90 Latency, Throughput (tok/s).
- `SortableTable`: slowest turns.
  Columns: `Turn ID`, `Latency (ms)`, `TTFT (ms)`, `TPOT (ms)`, `Model`, `Status`.
  Data: `result.llm_performance.slowest_turns`.
- `MplFrame` line chart of weekly mean latency with p90 shading.
  Data: `result.llm_performance.weekly_summaries`.

**Tab "Tool Success":**
- Row of `StatCard` widgets: Total Calls, Total Failures, Overall Success Rate, Recovery Rate.
- `SortableTable`: per-tool stats, sorted by failure rate descending.
  Columns: `Tool`, `Calls`, `Successes`, `Failures`, `Success Rate`, `Avg Duration (s)`.
  Rows with `success_rate < 0.80` highlighted red.
  Data: `result.tool_success.per_tool_stats`.
- `CTkLabel` for top error messages.

**Tab "Content Delivery":**
- Row of `StatCard` widgets: Productive Rate, Files Delivered, Silent Successes, Tool-to-Content Rate.
- `SortableTable`: response bucket breakdown.
  Columns: `Bucket`, `Char Range`, `Turns`, `Mean Quality`.
  Data: `result.content_delivery.response_buckets`.
- `MplFrame` bar chart of weekly average response length.
  Data: `result.content_delivery.weekly_summaries`.

### 6.8 SettingsView (`views/settings_view.py`)

Exposes the two threshold parameters from `TrajectoriesReport.__init__()` as interactive
controls for live re-analysis without the CLI.

**Controls:**

| Control type       | Parameter                         | Range        | Default |
|--------------------|-----------------------------------|--------------|---------|
| `CTkSlider`        | `quality_deficit_threshold`       | 0.01 – 0.50  | 0.15    |
| `CTkSlider`        | `correction_lift_threshold`       | 1.0 – 5.0    | 1.5     |
| `CTkEntry`         | `max_sessions`                    | integer      | 30      |

Each slider is accompanied by a live value readout `CTkLabel` that updates as the slider moves.

**Buttons:**
- "Re-Run Analysis" — calls `app.start_analysis()` with current settings.
- "Export JSON" — calls `reporter.render_json(result)` → `filedialog.asksaveasfilename()`.
- "Export Text (Verbose)" — calls `reporter.render_text(result, verbose=True)` → save dialog.

---

## 7. Navigation Flow

```
Launch
  └─ LoadView (always first, nav rail buttons disabled)
       ├─ User picks directory + clicks "Run Analysis"
       │    └─ AnalysisBackend.run_async() → background thread
       │         ├─ progress updates: status_label + progress_bar
       │         └─ on_complete → root.after(0, ...) → all views refresh
       │              └─ navigate automatically to OverviewView
       │
       └─ If --log-dir passed on CLI → auto-populate + auto-run
```

### Navigation rail buttons

| Button label | View class           | Keyboard shortcut |
|--------------|----------------------|-------------------|
| Load         | `LoadView`           | Ctrl+0            |
| Overview     | `OverviewView`       | Ctrl+1            |
| Quality      | `QualityView`        | Ctrl+2            |
| Timing       | `TimingView`         | Ctrl+3            |
| Errors       | `ErrorsView`         | Ctrl+4            |
| Tokens & LLM | `TokensView`         | Ctrl+5            |
| Sessions     | `SessionsView`       | Ctrl+6            |
| Settings     | `SettingsView`       | Ctrl+7            |

All nav buttons except "Load" are `state="disabled"` until `on_result_ready()` fires.

### Window dimensions

Root window minimum: 1100×700. Nav rail: 160 px wide (fixed). Content area fills remaining
940×700. All views use `sticky="nsew"` in the grid to expand with the window.

---

## 8. Integration with the Existing Pipeline

The GUI does not modify any file under `analyzer/`. It reuses the pipeline as a library:

```python
# Inside AnalysisBackend._worker()
from analyzer.loader import TrajectoriesLoader
from analyzer.report import TrajectoriesReport

loader = TrajectoriesLoader(log_dir, max_weeks=max_sessions)
reporter = TrajectoriesReport(
    loader,
    quality_deficit_threshold=qd_thresh,
    correction_lift_threshold=lift_thresh,
)
result = reporter.run()
# result: ReportResult (frozen dataclass) — data source for every view
# loader.raw_sessions: dict[Path, list[dict]] — used by SessionsView directly
```

The `TrajectoriesReport` instance is stored on `TraceHoundApp` so `SettingsView` can call
`reporter.render_json(result)` and `reporter.render_text(result, verbose=True)` for export.

### Data flow

```
LoadView (user input)
      │
      ▼
AnalysisBackend._worker()
  TrajectoriesLoader.load()    →  list[TurnRecord]
  TrajectoriesReport.run()     →  ReportResult (frozen)
      │
      ▼  root.after(0, callback)
TraceHoundApp.on_result_ready(result, loader)
      │
      ├──► OverviewView.refresh(result, loader)
      ├──► QualityView.refresh(result)
      ├──► TimingView.refresh(result)
      ├──► SessionsView.refresh(loader)
      └──► SettingsView.refresh(result, reporter)
```

Each `View.refresh()` is called once per analysis run and must not cache stale data between runs.

---

## 9. New CLI Entry Point

### 9.1 `python -m analyzer_gui`

No installation required. Works from the repo root:

```bash
# macOS / Linux
python -m analyzer_gui --log-dir /Users/mishka/.jiuwenswarm --max-sessions 30

# Windows
python -m analyzer_gui --log-dir C:\Users\m00645993\.jiuwenswarm --max-sessions 30
```

### 9.2 Relationship to the existing CLI

The existing `python -m analyzer` (`analyzer/cli.py`) is **completely untouched**. Both entry
points coexist permanently. There is no `--gui` flag added to the existing CLI; the GUI is always
launched via `analyzer_gui`.

---

## 10. Dependencies

Additions to `requirements.txt`:

```
loguru
customtkinter>=5.2.2
CTkTable>=1.1
matplotlib>=3.9.0
```

Notes:
- `customtkinter>=5.2.2` — first release with stable `CTkTabview` and `CTkScrollableFrame`.
- `CTkTable>=1.1` — companion PyPI package (`pip install CTkTable`) providing a grid of
  `CTkLabel` widgets with per-cell colour control.
- `matplotlib>=3.9.0` — ships ARM64 macOS wheels, supports Python 3.12.
- All three are pure Python at runtime or ship binary wheels for all target platforms.
- Total additional packages: 3.

---

## 11. Implementation Phases

Each phase produces a runnable, testable increment.

### Phase 1: Skeleton + Backend

**Goal:** `python -m analyzer_gui` opens a window, runs analysis, shows "Done."

Files to create:
- `analyzer_gui/__init__.py`
- `analyzer_gui/__main__.py`
- `analyzer_gui/gui_cli.py`
- `analyzer_gui/app.py` — root window + nav rail (buttons disabled) + `on_result_ready()` stub
- `analyzer_gui/backend.py` — `AnalysisBackend.run_async()` + `_worker()`
- `analyzer_gui/views/load_view.py` — directory entry, Browse, Run, progress bar, status label

Acceptance test: browse to `.jiuwenswarm`, click Run, see "Done." in status label, no crash.

### Phase 2: Overview + StatCard + MplFrame

**Goal:** clicking "Overview" shows meaningful summary data.

Files to create:
- `analyzer_gui/widgets/stat_card.py`
- `analyzer_gui/widgets/mpl_frame.py`
- `analyzer_gui/views/overview_view.py`

Acceptance test: all stat cards populate from a real jiuwenswarm dataset. Colour coding on
overall_mean is correct (green > 0.70, yellow 0.50–0.70, red < 0.50).

### Phase 3: Quality View

**Goal:** matplotlib chart shows per-session quality with correct trend colour.

Files to create:
- `analyzer_gui/views/quality_view.py`

Uses `MplFrame` from Phase 2 and a plain `CTkScrollableFrame` row list for the table (replaced
in Phase 4).

Acceptance test: chart renders for a dataset; best/worst annotations appear; table shows correct
turn counts.

### Phase 4: SortableTable + Timing View

**Goal:** introduce `SortableTable` and populate the Timing view.

Files to create:
- `analyzer_gui/widgets/sortable_table.py`
- `analyzer_gui/views/timing_view.py`

Backfill `QualityView` to use `SortableTable`.

Acceptance test: clicking a column header sorts the timing table. Slowest-turns tab shows correct
10 entries. Histogram has correct bin counts and vertical markers.

### Phase 5: Sessions View

**Goal:** browse raw session data turn by turn.

Files to create:
- `analyzer_gui/views/sessions_view.py`

Acceptance test: clicking a session ID populates the right panel. Clicking a turn header expands
it. "Load more..." appends 50 turns. No crash on sessions with 200+ turns.

### Phase 6: Errors View + Tokens & LLM View

**Goal:** expose the 8 new analyzers (ErrorCategories, UserQueries, TokenUsage,
LLMPerformance, ToolSuccess, ContentDelivery) through two tabbed views.

Files to create:
- `analyzer_gui/views/errors_view.py`
- `analyzer_gui/views/tokens_view.py`

Acceptance test: Errors tab shows correct category counts and weekly bar chart.
Tokens tab shows model breakdown and slowest-turn table. No crashes on empty data.

### Phase 7: Settings View + Export

**Goal:** sliders adjust thresholds; "Re-Run" triggers a new analysis; export buttons work.

Files to create:
- `analyzer_gui/views/settings_view.py`

Acceptance test: move `quality_deficit_threshold` from 0.15 to 0.30, click Re-Run — analysis updates.
"Export JSON" saves a valid JSON file matching the CLI `--format json` output.

### Phase 8: Polish + Cross-Platform Testing

- Test on Windows 11 Python 3.12 official installer.
- Test on macOS 14 Intel and ARM with Python 3.12.
- Fix any DPI scaling issues (`customtkinter.set_widget_scaling()` if needed).
- Ensure `CTkScrollableFrame` mousewheel binding works on Windows.
- Add window icon via `root.iconphoto()` if a suitable `.ico` / `.png` is available.

---

## 12. Widget Reference Table

| Widget class                   | Package        | Used in                                       |
|--------------------------------|----------------|-----------------------------------------------|
| `CTkFrame`                     | customtkinter  | All views (base layout container)             |
| `CTkScrollableFrame`           | customtkinter  | OverviewView, SessionsView                    |
| `CTkTabview`                   | customtkinter  | TimingView, ErrorsView, TokensView            |
| `CTkButton`                    | customtkinter  | Nav rail, Browse, Run, Export                 |
| `CTkLabel`                     | customtkinter  | All views (static text)                       |
| `CTkEntry`                     | customtkinter  | LoadView dir input, SettingsView sessions     |
| `CTkSlider`                    | customtkinter  | SettingsView threshold controls               |
| `CTkProgressBar`               | customtkinter  | LoadView analysis progress indicator          |
| `CTkTextbox`                   | customtkinter  | OverviewView text preview, SessionsView turns |
| `CTkTable`                     | CTkTable       | Wrapped inside `SortableTable`                |
| `Figure` + `FigureCanvasTkAgg` | matplotlib     | Wrapped inside `MplFrame`                     |
| `filedialog.askdirectory`      | tkinter stdlib | LoadView Browse button                        |
| `filedialog.asksaveasfilename` | tkinter stdlib | SettingsView export buttons                   |

---

## 13. Error Handling and Edge Cases

### Analysis errors

`AnalysisBackend._worker()` catches all exceptions and calls `on_error(exc)`. `TraceHoundApp`
marshals to the UI thread and shows a `CTkToplevel` error dialog with the exception message and
a "Retry" button that returns the user to `LoadView`.

### Empty dataset

If `result.data_health.total_turns == 0`, all views show an empty-state `CTkLabel`:
"No turns loaded. Check the log directory."
Timing views hide their `MplFrame` and `SortableTable` widgets to avoid rendering empty charts.

### Thread safety

All tkinter widget mutations must happen on the main thread. `AnalysisBackend` never touches
widgets directly. Callbacks from the worker thread are wrapped with `root.after(0, ...)`:

```python
def _on_progress_from_thread(self, message: str) -> None:
    self.after(0, lambda: self.load_view.status_label.configure(text=message))
```

### Re-run while running

`AnalysisBackend.run_async()` is a no-op if `self._thread.is_alive()`. The "Run Analysis" and
"Re-Run Analysis" buttons are set to `state="disabled"` while analysis is in progress and
re-enabled in `on_complete` / `on_error`.

---

## 14. Cross-Platform Notes

### Windows

- File paths use `pathlib.Path` throughout; forward/backslash handling is transparent.
- `tkinter.filedialog.askdirectory()` opens the native Windows folder picker.
- The Python 3.12 official Windows installer bundles Tcl/Tk 8.6.13, compatible with CustomTkinter 5.2+.
- CustomTkinter `CTkScrollableFrame` mouse-wheel binding: on Windows `<MouseWheel>` fires with
  `event.delta` in multiples of 120; CustomTkinter 5.2+ handles this internally.

### macOS

- `tkinter.filedialog.askdirectory()` opens the native macOS folder chooser.
- On macOS 14+ with Dark Mode, `customtkinter.set_appearance_mode("System")` automatically
  switches between light and dark palettes.
- Python 3.12 from python.org bundles Tcl/Tk 8.6 in a `Python.framework` bundle. Homebrew
  Python users may need `brew install python-tk@3.12`.
- Matplotlib ARM64 macOS wheels available from PyPI since matplotlib 3.8+.

### Font sizing

All font specifications use `font=("", size)` (empty family string) to inherit the platform
default (Segoe UI on Windows, SF Pro on macOS). This avoids font-not-found warnings and produces
a native-looking UI on both platforms.

---

## 15. Summary of New Files

```
analyzer_gui/__init__.py
analyzer_gui/__main__.py
analyzer_gui/gui_cli.py
analyzer_gui/app.py
analyzer_gui/backend.py
analyzer_gui/views/__init__.py
analyzer_gui/views/load_view.py
analyzer_gui/views/overview_view.py
analyzer_gui/views/quality_view.py
analyzer_gui/views/timing_view.py
analyzer_gui/views/errors_view.py
analyzer_gui/views/tokens_view.py
analyzer_gui/views/sessions_view.py
analyzer_gui/views/settings_view.py
analyzer_gui/widgets/__init__.py
analyzer_gui/widgets/stat_card.py
analyzer_gui/widgets/sortable_table.py
analyzer_gui/widgets/mpl_frame.py
```

**18 new files. Zero changes to files under `analyzer/`.**

New entry point: `python -m analyzer_gui [--log-dir PATH] [--max-sessions N]`

Existing CLI unchanged: `python -m analyzer --log-dir PATH ...`
