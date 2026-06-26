# Sample AI Coding Tools Benchmark

A side-by-side comparison of popular AI coding tools. We run the same prompts
through each tool and measure how they stack up on **cost**, **speed**, and
**correctness**.

## Latest Report

- Run date: **2026-06-25** (Kiro IDE, Kiro CLI, Claude Code on Bedrock, Codex on Bedrock)

### Evaluated Scenarios
- **GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from scratch.
- **CA-1** — Brownfield analysis: read an existing TypeScript API and explain architecture, pricing, and state machine.
- **CA-2** — Brownfield investigation: pinpoint which check rejects a specific request and what response it returns.

## Metrics We Track

- **Cost**: token/credit usage or dollar cost for the run.
- **Speed**: wall-clock time from prompt to finished result.
- **Results**: correctness of the output. (To be expanded upon)

## Methodology

We run each scenario through every tool under identical conditions and capture
cost, wall-clock time, and output size. The harness lives in
[`tools/run_benchmark.py`](./tools/run_benchmark.py) and works like this:

- **Same prompt, every tool.** The three scenarios (GF-1, CA-1, CA-2) are
  defined in the harness and kept in sync with
  [`samples/prompts/prompts-v1.md`](./samples/prompts/prompts-v1.md). Each tool
  receives the exact same prompt text.
- **Isolated workspaces.** Every tool runs in its own temporary directory so it
  can't see the repo or another tool's output. Analysis scenarios get a fresh
  copy of [`samples/sample-api`](./samples/sample-api) inside that workspace.
- **Non-interactive, full-trust runs.** Each CLI is invoked headless with
  permissions bypassed so the run completes without prompts
  (`kiro-cli chat --no-interactive --trust-all-tools`,
  `claude --print --permission-mode bypassPermissions`,
  `codex exec --dangerously-bypass-approvals-and-sandbox`).
- **Repeat and average.** Each scenario runs `--runs` times (default 3). Per-run
  results are written to `evaluations/{date}/run-{n}/{tool}/`, with one
  `run-{n}.json` per run, then averaged into `run-average.json`.
- **Metrics captured per run.** Cost (Kiro credits × $0.02/credit, Claude's
  reported run cost, Codex token-based Bedrock pricing and the token count is captured in the session log), elapsed seconds, lines
  of output produced, and input/output tokens where the tool reports them.
- **Auto-detection.** Tools that aren't installed are skipped with a note, so
  you can benchmark whatever subset you have available.

## Using This Framework

You can run the benchmark yourself against any subset of the supported tools.

### Run it

From the repo root:

```bash
# Run every scenario through every installed tool (3 runs each)
python3 tools/run_benchmark.py --prompt all

# Run one scenario through specific tools
python3 tools/run_benchmark.py --prompt CA-1 --tools kiro-cli,claude-code

# Custom date folder and number of runs
python3 tools/run_benchmark.py --prompt all --date 2026-06-25 --runs 5
```

Key flags:

- `--prompt` — `GF-1`, `CA-1`, `CA-2`, or `all` (default).
- `--tools` — comma list of `kiro-cli,claude-code,codex`, or `auto` to use every
  installed tool (default).
- `--date` — output folder under `evaluations/` (defaults to today).
- `--runs` — repeated runs per scenario for averaging (default 3).
- `--timeout` — per-run timeout in seconds (default 600).
- `--verbose` — print raw output tails for debugging.

Override binaries or models with environment variables if your setup differs
(e.g. `KIRO_BIN`, `CLAUDE_BIN`, `CODEX_BIN`, `KIRO_MODEL`, `CLAUDE_MODEL`,
`CODEX_MODEL`).

### Read the results

After a run, results land under `evaluations/{date}/`:

- `run-{n}/{tool}/` — the actual files each tool produced for each scenario.
- `run-{n}.json` — metrics for that run.
- `run-average.json` — mean cost/time/lines/tokens across all runs on disk.

The harness also prints a summary table to the console at the end of the run.

### Add your own scenarios

Extend the `PROMPTS` dictionary in
[`tools/run_benchmark.py`](./tools/run_benchmark.py) with a new entry (set
`type` to `generation` for build tasks or `analysis` for read-only
investigations) and mirror it in
[`samples/prompts/prompts-v1.md`](./samples/prompts/prompts-v1.md).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
