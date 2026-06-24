#!/usr/bin/env python3
"""
Automated multi-tool AI coding benchmark harness (CLI only).

Runs the same benchmark prompt through several AI coding CLIs
(Kiro CLI, Claude Code, Codex CLI) in isolated workspaces, captures
cost / time / token / output-size metrics, and writes results in the
repo's evaluations/{date}/{tool}/ layout plus a combined JSON file
matching evaluation-data-*.json.

USAGE
-----
    python3 tools/run_benchmark.py --prompt GF-1
    python3 tools/run_benchmark.py --prompt CA-1 --tools kiro-cli,claude-code
    python3 tools/run_benchmark.py --prompt all --date 2026-06-22 --runs 3

Each evaluation is run --runs times (default 3). Per-run output lands in
evaluations/{date}/run-{n}/{tool}/, with one evaluations/{date}/run-{n}.json
per run plus an averaged evaluations/{date}/run-average.json (mean of the runs).

Run from the repo root. Requires Python 3.8+. No third-party deps.

Tool availability is auto-detected; missing tools are skipped with a note.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import date as _date
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_FILE = REPO_ROOT / "samples" / "prompts" / "prompts-v1.md"
EVAL_ROOT = REPO_ROOT / "evaluations"
SAMPLE_API = REPO_ROOT / "samples" / "sample-api"

KIRO_BIN = os.environ.get("KIRO_BIN", "kiro-cli")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")

# Model ids per tool (override via env). Kiro uses dotted names; Bedrock uses dashes.
KIRO_MODEL = os.environ.get("KIRO_MODEL", "claude-opus-4.8")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-opus-4-8")
CODEX_MODEL = os.environ.get("CODEX_MODEL", "openai.gpt-5.5")

COST_PER_KIRO_CREDIT = 0.02

# ANSI / control-char stripper for noisy TTY output
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def strip_ansi(s):
    return _ANSI_RE.sub("", s)


def count_lines(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                with open(os.path.join(root, f), "r", errors="ignore") as fh:
                    total += sum(1 for _ in fh)
            except OSError:
                pass
    return total


def count_file_lines(path):
    try:
        with open(path, "r", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _extract_markdown(stdout):
    """Salvage analysis markdown from a tool's stdout when it didn't write the
    file. If the text contains a fenced ```markdown / ``` block, return its
    contents; otherwise return the stripped stdout as-is."""
    if not stdout:
        return ""
    m = re.search(r"```(?:markdown|md)?\s*\n(.*?)```", stdout, re.S)
    if m:
        return m.group(1).strip() + "\n"
    return stdout.strip() + "\n"

# ---------------------------------------------------------------------------
# Prompt definitions (kept in sync with samples/prompts/prompts-v1.md)
# ---------------------------------------------------------------------------
# type:
#   "generation" -> tool creates files in its own workspace (GF-1)
#   "analysis"   -> tool reads sample-api (copied in) and writes an analysis md
PROMPTS = {
    "GF-1": {
        "type": "generation",
        "summary": "Greenfield build: produce a fresh, spec-bound CLI to-do app from scratch",
        "needs_sample_api": False,
        "output_glob": "todo-app",
        "text": """Build a command-line to-do app in Python. Follow this specification exactly. Do not add features, files, or dependencies beyond what is listed.

Location: New folder named todo-app

Files to create (exactly these four, no more):
- todo.py        # entry point and CLI argument parsing
- storage.py     # load/save tasks to a JSON file
- task.py        # Task data model
- README.md      # setup and usage

Commands to support:
- add "<title>"      Add a task. Prints "Added task <id>".
- list               List all tasks as "<id>. [ ] <title>" or "[x]" if done.
- done <id>          Mark a task complete. Prints "Completed task <id>".
- delete <id>        Delete a task. Prints "Deleted task <id>".

Behavior and constraints:
- Persist tasks to tasks.json in the current directory.
- Each task has: integer id (auto-incrementing), title (string), done (bool).
- Use only the Python standard library (argparse, json). No third-party packages.
- On invalid input (missing title, unknown id, bad command), print a clear error message to stderr and exit with code 1.
- No tests, no packaging files, no extra modules.""",
    },
    "CA-1": {
        "type": "analysis",
        "summary": "Brownfield analysis: read an existing TypeScript API and explain architecture, pricing, and state machine",
        "needs_sample_api": True,
        "output_glob": "analysis-ca-1.md",
        "text": """Read the project in samples/sample-api and explain it to me. Do not read any other files outside of this folder.

Cover:
- What the API does and the domain it models.
- The layered architecture and how a request flows from HTTP entry to storage and back (name the modules involved at each layer).
- How an order is priced: walk through discounts, the discount cap, and tax, using a concrete example with numbers.
- The order status state machine: valid transitions, terminal states, and any side effects of a transition.
- How stock reservation avoids partially reserving inventory when one line in a multi-line order is invalid.

Then list anything confusing, risky, or likely to cause bugs. Do not change any code. Write your results in analysis-ca-1.md""",
    },
    "CA-2": {
        "type": "analysis",
        "summary": "Brownfield investigation: pinpoint which check rejects a specific request and what response it returns",
        "needs_sample_api": True,
        "output_glob": "analysis-ca-2.md",
        "text": """In samples/sample-api, a POST /api/v1/orders request for a gold-tier customer ordering 13 of prod_3 (the 27-inch monitor, which has 12 in stock) is rejected. Without running the code, trace exactly which module and which check rejects it, what HTTP status and error code come back, and what the response body looks like. Then explain what would need to change for the order to succeed. Do not read any other files outside of the samples/sample-api folder. Write your findings in analysis-ca-2.md""",
    },
}


# ---------------------------------------------------------------------------
# Tool adapters
# ---------------------------------------------------------------------------
# Each adapter runs the prompt in `workdir` and returns a metrics dict:
#   { ok, cost_usd, credits_used, cost_per_credit_usd,
#     elapsed_seconds, input_tokens, output_tokens, raw_tail }

def _run(cmd, workdir, timeout):
    start = time.time()
    proc = subprocess.run(
        cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout
    )
    elapsed = round(time.time() - start, 1)
    return proc, elapsed


def run_kiro(prompt_text, workdir, timeout):
    cmd = [
        KIRO_BIN, "chat", "--no-interactive", "--trust-all-tools",
        "--model", KIRO_MODEL, prompt_text,
    ]
    proc, elapsed = _run(cmd, workdir, timeout)
    out = strip_ansi(proc.stdout + "\n" + proc.stderr)
    # Kiro prints a trailer like: "Credits: 1.21 • Time: 36s"
    credits = None
    m = re.search(r"Credits:\s*([0-9.]+)", out)
    if m:
        credits = float(m.group(1))
    cost = round(credits * COST_PER_KIRO_CREDIT, 4) if credits is not None else None
    return {
        "ok": proc.returncode == 0,
        "cost_usd": cost,
        "credits_used": credits,
        "cost_per_credit_usd": COST_PER_KIRO_CREDIT if credits is not None else None,
        "elapsed_seconds": elapsed,
        "input_tokens": None,
        "output_tokens": None,
        "stdout": proc.stdout,
        "raw_tail": out[-600:],
    }


def run_claude(prompt_text, workdir, timeout):
    cmd = [
        CLAUDE_BIN, "--print", "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--model", CLAUDE_MODEL, prompt_text,
    ]
    proc, elapsed = _run(cmd, workdir, timeout)
    cost = inp = outp = None
    data = None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        pass
    if isinstance(data, dict):
        cost = data.get("total_cost_usd")
        usage = data.get("usage") or {}
        inp = usage.get("input_tokens")
        outp = usage.get("output_tokens")
        if data.get("duration_ms"):
            elapsed = round(data["duration_ms"] / 1000.0, 1)
    # The assistant text (where Claude may inline the analysis) lives in
    # data["result"] for --output-format json; fall back to raw stdout.
    text_out = ""
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        text_out = data["result"]
    else:
        text_out = proc.stdout
    return {
        "ok": proc.returncode == 0,
        "cost_usd": cost,
        "credits_used": None,
        "cost_per_credit_usd": None,
        "elapsed_seconds": elapsed,
        "input_tokens": inp,
        "output_tokens": outp,
        "stdout": text_out,
        "raw_tail": (proc.stdout + proc.stderr)[-600:],
    }


def run_codex(prompt_text, workdir, timeout):
    cmd = [
        CODEX_BIN, "exec", "--model", CODEX_MODEL,
        "--dangerously-bypass-approvals-and-sandbox", prompt_text,
    ]
    proc, elapsed = _run(cmd, workdir, timeout)
    out = strip_ansi(proc.stdout + "\n" + proc.stderr)
    inp = outp = None
    m = re.search(r"tokens used[:\s]+([0-9,]+)", out, re.I)
    if m:
        outp = int(m.group(1).replace(",", ""))
    return {
        "ok": proc.returncode == 0,
        # Amazon Bedrock does not return an inline USD cost; left NA on purpose.
        "cost_usd": None,
        "credits_used": None,
        "cost_per_credit_usd": None,
        "elapsed_seconds": elapsed,
        "input_tokens": inp,
        "output_tokens": outp,
        "stdout": proc.stdout,
        "raw_tail": out[-600:],
    }


TOOLS = {
    "kiro-cli":    {"label": "Kiro CLI",    "bin": KIRO_BIN,   "run": run_kiro},
    "claude-code": {"label": "Claude Code", "bin": CLAUDE_BIN, "run": run_claude},
    "codex":       {"label": "Codex CLI",   "bin": CODEX_BIN,  "run": run_codex},
}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def tool_available(tool_key):
    return shutil.which(TOOLS[tool_key]["bin"]) is not None


def evaluate(prompt_id, tool_key, run_dir, timeout, verbose):
    spec = PROMPTS[prompt_id]
    tool = TOOLS[tool_key]
    out_dir = run_dir / tool_key
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build an isolated workspace so tools can't see the repo or each other.
    work = out_dir / "_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # Analysis prompts reference samples/sample-api — provide a local copy.
    if spec["needs_sample_api"]:
        shutil.copytree(SAMPLE_API, work / "samples" / "sample-api")

    print(f"  -> {tool['label']}: running {prompt_id} ...", flush=True)
    try:
        metrics = tool["run"](spec["text"], str(work), timeout)
    except subprocess.TimeoutExpired:
        print(f"     TIMEOUT after {timeout}s", flush=True)
        metrics = {
            "ok": False, "cost_usd": None, "credits_used": None,
            "cost_per_credit_usd": None, "elapsed_seconds": timeout,
            "input_tokens": None, "output_tokens": None,
            "stdout": "", "raw_tail": "TIMEOUT",
        }

    # Collect produced output into the tool's eval folder and count lines.
    lines = 0
    glob = spec["output_glob"]
    if spec["type"] == "generation":
        produced = work / glob
        if produced.exists():
            dest = out_dir / glob
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(produced, dest)
            lines = count_lines(dest)
    else:  # analysis: find the analysis-*.md the tool wrote anywhere in work
        found = None
        for root, _d, files in os.walk(work):
            if glob in files:
                found = Path(root) / glob
                break
        dest = out_dir / glob
        if found:
            shutil.copy(found, dest)
            lines = count_file_lines(dest)
        else:
            # Fallback: the tool described the analysis in stdout but never
            # wrote the file (seen with Claude --print). The analysis file is
            # proof of results, so salvage the stdout markdown to disk.
            salvaged = _extract_markdown(metrics.get("stdout", ""))
            if salvaged.strip():
                dest.write_text(salvaged)
                lines = count_file_lines(dest)
                print("     (note: analysis file not written by tool; "
                      "salvaged from stdout)", flush=True)

    shutil.rmtree(work, ignore_errors=True)

    result = {
        "evaluation_id": prompt_id,
        "tool": tool["label"],
        "credits_used": metrics["credits_used"],
        "cost_per_credit_usd": metrics["cost_per_credit_usd"],
        "cost_usd": metrics["cost_usd"],
        "elapsed_seconds": metrics["elapsed_seconds"],
        "lines_produced": lines,
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
    }
    status = "ok" if metrics["ok"] and lines > 0 else "PARTIAL/FAIL"
    print(f"     {status}: cost={result['cost_usd']} "
          f"time={result['elapsed_seconds']}s lines={lines}", flush=True)
    if verbose:
        print("     raw tail:\n" + "\n".join(
            "       " + l for l in metrics["raw_tail"].splitlines()), flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description="Multi-tool AI coding benchmark (POC)")
    ap.add_argument("--prompt", default="all",
                    help="GF-1 | CA-1 | CA-2 | all (default)")
    ap.add_argument("--tools", default="auto",
                    help="comma list of kiro-cli,claude-code,codex or 'auto' (all available)")
    ap.add_argument("--date", default=_date.today().isoformat(),
                    help="run date / eval folder (YYYY-MM-DD)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="per-run timeout in seconds (default 600)")
    ap.add_argument("--runs", type=int, default=3,
                    help="number of repeated runs per evaluation (default 3); "
                         "writes run-1.json .. run-N.json + run-average.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.runs < 1:
        ap.error("--runs must be >= 1")

    prompt_ids = list(PROMPTS) if args.prompt == "all" else [args.prompt.upper()]
    for pid in prompt_ids:
        if pid not in PROMPTS:
            ap.error(f"unknown prompt {pid}; choose from {list(PROMPTS)} or 'all'")

    if args.tools == "auto":
        tool_keys = [k for k in TOOLS if tool_available(k)]
    else:
        tool_keys = [t.strip() for t in args.tools.split(",") if t.strip()]
        for t in tool_keys:
            if t not in TOOLS:
                ap.error(f"unknown tool {t}; choose from {list(TOOLS)}")

    print(f"Benchmark run {args.date}")
    print(f"Prompts: {prompt_ids}")
    skipped = []
    active = []
    for t in tool_keys:
        if tool_available(t):
            active.append(t)
        else:
            skipped.append(t)
    if skipped:
        print(f"Skipping unavailable tools: {[TOOLS[s]['label'] for s in skipped]}")
    if not active:
        print("No available tools to run. Install at least one CLI.")
        return 1
    print(f"Tools under test: {[TOOLS[t]['label'] for t in active]}")
    print(f"Runs per evaluation: {args.runs}\n")

    config = {
        "models": {
            "kiro-cli": KIRO_MODEL,
            "claude-code": CLAUDE_MODEL,
            "codex": CODEX_MODEL,
        },
        "mode": "Automated",
    }
    eval_meta = [
        {"id": pid, "type": PROMPTS[pid]["type"], "summary": PROMPTS[pid]["summary"]}
        for pid in prompt_ids
    ]
    date_dir = EVAL_ROOT / args.date
    date_dir.mkdir(parents=True, exist_ok=True)

    def _merge(old, new, keyer):
        index = {keyer(x): x for x in old}
        for item in new:
            index[keyer(item)] = item
        return list(index.values())

    def write_run_json(path, results):
        # Merge with any existing file so prompt-by-prompt invocations of the
        # same run number accumulate instead of clobbering.
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except ValueError:
                existing = {}
        merged_results = _merge(existing.get("results", []), results,
                                lambda r: (r["evaluation_id"], r["tool"]))
        merged_evals = _merge(existing.get("evaluations", []), eval_meta,
                              lambda e: e["id"])
        merged_tools = sorted({*existing.get("tools", []),
                               *[TOOLS[t]["label"] for t in active]})
        data = {
            "run_date": args.date,
            "generated_by": "tools/run_benchmark.py",
            "config": config,
            "tools": merged_tools,
            "evaluations": merged_evals,
            "results": merged_results,
        }
        path.write_text(json.dumps(data, indent=2))
        return data

    run_datas = []
    for n in range(1, args.runs + 1):
        run_dir = date_dir / f"run-{n}"
        print(f"========== RUN {n}/{args.runs} ==========")
        results = []
        for pid in prompt_ids:
            print(f"Prompt {pid}: {PROMPTS[pid]['summary']}")
            for t in active:
                results.append(
                    evaluate(pid, t, run_dir, args.timeout, args.verbose))
            print()
        run_json = date_dir / f"run-{n}.json"
        data = write_run_json(run_json, results)
        run_datas.append(data)
        print(f"Wrote {run_json}\n")

    # ----- Average across ALL persisted runs on disk -----
    # Read every run-*.json (not just this invocation's runs) so that
    # re-running a single cell still yields a correct full-history average.
    disk_runs = []
    for p in sorted(date_dir.glob("run-*.json")):
        if p.name == "run-average.json":
            continue
        try:
            disk_runs.append(json.loads(p.read_text()))
        except ValueError:
            pass
    avg_data = build_average(disk_runs or run_datas, args.date, config,
                             eval_meta, [TOOLS[t]["label"] for t in active])
    avg_json = date_dir / "run-average.json"
    avg_json.write_text(json.dumps(avg_data, indent=2))
    print(f"Wrote {avg_json}")

    # Console summary table (averages)
    print(f"\n=== SUMMARY (averaged over {avg_data['runs']} run(s) on disk) ===")
    hdr = (f"{'Prompt':7} {'Tool':13} {'Cost($)':9} {'Time(s)':8} "
           f"{'Lines':6} {'Runs':5}")
    print(hdr)
    print("-" * len(hdr))
    for r in avg_data["results"]:
        cost = "NA" if r["cost_usd"] is None else f"{r['cost_usd']:.4f}"
        print(f"{r['evaluation_id']:7} {r['tool']:13} {cost:9} "
              f"{str(r['elapsed_seconds']):8} "
              f"{str(r['lines_produced']):6} {str(r['runs_counted']):5}")
    return 0


def _avg(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def build_average(run_datas, run_date, config, eval_meta, tool_labels):
    """Average cost/time/lines/tokens for each (evaluation_id, tool) pair
    across every run-N.json. None values are ignored in the mean; runs_counted
    records how many runs contributed a value."""
    buckets = {}
    for data in run_datas:
        for r in data.get("results", []):
            key = (r["evaluation_id"], r["tool"])
            buckets.setdefault(key, []).append(r)
    metric_keys = ["credits_used", "cost_per_credit_usd", "cost_usd",
                   "elapsed_seconds", "lines_produced",
                   "input_tokens", "output_tokens"]
    results = []
    for (pid, tool), rows in buckets.items():
        avg = {"evaluation_id": pid, "tool": tool}
        for mk in metric_keys:
            avg[mk] = _avg([row.get(mk) for row in rows])
        avg["runs_counted"] = len(rows)
        results.append(avg)
    results.sort(key=lambda r: (r["evaluation_id"], r["tool"]))
    return {
        "run_date": run_date,
        "generated_by": "tools/run_benchmark.py (run-average)",
        "aggregate": "mean",
        "runs": len(run_datas),
        "config": config,
        "tools": sorted(set(tool_labels)),
        "evaluations": eval_meta,
        "results": results,
    }


if __name__ == "__main__":
    sys.exit(main())
