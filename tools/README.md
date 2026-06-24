# Tools

Utility scripts for running benchmarks, validating outputs, and generating
dashboard charts. All scripts are run from the **repo root**.

## Prerequisites

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install matplotlib   # only needed for build_chart.py
```

---

## run_benchmark.py

Automated multi-tool benchmark harness. Runs the same prompt through several
AI coding CLIs (Kiro CLI, Claude Code, Codex CLI), captures cost / time /
token / output-size metrics, and writes results to `evaluations/{date}/`.

```bash
# Run a single prompt through all available tools
.venv/bin/python tools/run_benchmark.py --prompt GF-1

# Run specific tools only
.venv/bin/python tools/run_benchmark.py --prompt CA-1 --tools kiro-cli,claude-code

# Run all prompts with 3 repetitions on a given date
.venv/bin/python tools/run_benchmark.py --prompt all --date 2026-06-22 --runs 3
```

Tool availability is auto-detected; missing tools are skipped. Per-run results
land in `evaluations/{date}/run-{n}/` with a combined `run-average.json`.

No third-party dependencies required.

---

## gf1_qa.py

QA harness for the GF-1 (greenfield to-do app) prompt. Tests a generated CLI
to-do app against the GF-1 specification — verifies file structure, reviews
the code, drives the CLI through positive and negative scenarios, and reports
a PASS/FAIL checklist.

```bash
# Test a single app
.venv/bin/python tools/gf1_qa.py evaluations/2026-05-31/claude-code/todo-app

# Test all apps from a run
.venv/bin/python tools/gf1_qa.py evaluations/2026-05-31/*/todo-app
```

No third-party dependencies required.

---

## build_chart.py

Generates dashboard charts from a benchmark results JSON. Currently produces:

| Chart | Metric | Output file |
|-------|--------|-------------|
| Cost per Prompt | `cost_usd` | `cost-per-prompt.png` |
| Duration per Prompt | `elapsed_seconds` | `duration-per-prompt.png` |

The script is **fully data-driven** — tools, prompts, and colours are derived
from the JSON at runtime. New tools appear automatically when they have data.

```bash
# Default: writes PNGs next to the input JSON
.venv/bin/python tools/build_chart.py evaluations/2026-06-23/run-average.json

# Custom output directory and title prefix
.venv/bin/python tools/build_chart.py evaluations/2026-06-23/run-average.json \
    --output-dir ./charts \
    --title-prefix "June 23 Benchmark"
```

**Missing data handling:**
- A tool/prompt pair with `null` shows as a zero-height bar labelled "N/A".
- A tool with no data for any prompt in a metric is omitted from that chart.

Requires `matplotlib`.
