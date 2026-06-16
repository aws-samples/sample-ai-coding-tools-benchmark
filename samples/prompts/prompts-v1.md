# Benchmark Prompts

Shared prompts used across every tool. Each tool gets the **exact same prompt**
so results stay comparable. Prompts are grouped by category and numbered for
easy reference (e.g., `GF-1`, `BF-1`).

## How to Use

1. Pick a prompt below and copy it from its code block.
2. Run it through each tool in a clean workspace, fresh session and MCP disabled.
3. Record cost, speed, and results.

```
# Create a folder at mkdir ./evaluations/{yyyy-MM-dd}/{tool}
mkdir ./evaluations/2026-06-09/codex

# Launch the AI tool from the new folder

# Test the prompt below

# Kiro IDE - Consumed credits is shown after prompt completion
# Kiro CLI - Consumed credits is shown after prompt completion
# Claude Code CLI - run /usage after prompt completion to see cost
# Codex CLI - run /clear after prompt completion to see tokens used

```

---

## 1. Greenfield (New Project) — `GF`

Tests building something from scratch: scaffolding, structure, and getting to a
working baseline.

**GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from
scratch.

```text
Build a command-line to-do app in Python. Follow this specification exactly. Do
not add features, files, or dependencies beyond what is listed.

Location: New folder named todo-app

Files to create (exactly these four, no more):
- todo.py        # entry point and CLI argument parsing
- storage.py     # load/save tasks to a JSON file
- task.py        # Task data model
- README.md      # setup and usage

Commands to support:
- add "<title>"      Add a task. Prints "Added task <id>".
- list               List all tasks as "<id>. [ ] <title>" or "[x]" if done.
- done <id>          Mark a task complete. Prints "Completed task <id>".`
- delete <id>        Delete a task. Prints "Deleted task <id>".

Behavior and constraints:
- Persist tasks to tasks.json in the current directory.
- Each task has: integer id (auto-incrementing), title (string), done (bool).
- Use only the Python standard library (argparse, json). No third-party packages.
- On invalid input (missing title, unknown id, bad command), print a clear error
  message to stderr and exit with code 1.
- No tests, no packaging files, no extra modules.
```

---

## 2. Code Analysis & Understanding — `CA`

Tests reading and explaining an existing codebase, and surfacing risks without
making changes. These prompts run against the fixture in
[`samples/sample-api/`](./samples/sample-api/) — a layered TypeScript order
-management REST API (Express). Point each tool at that folder before running.

**CA-1** — Brownfield analysis: read an existing TypeScript API and explain
architecture, pricing, and state machine.

```text
Read the project in samples/sample-api and explain it to me. Do not read any other files outside of this folder.

Cover:
- What the API does and the domain it models.
- The layered architecture and how a request flows from HTTP entry to storage
  and back (name the modules involved at each layer).
- How an order is priced: walk through discounts, the discount cap, and tax,
  using a concrete example with numbers.
- The order status state machine: valid transitions, terminal states, and any
  side effects of a transition.
- How stock reservation avoids partially reserving inventory when one line in a
  multi-line order is invalid.

Then list anything confusing, risky, or likely to cause bugs. Do not change any
code. Write your results in analysis-ca-1.md
```

**CA-2** — Brownfield investigation: pinpoint which check rejects a specific
request and what response it returns.

```text
In samples/sample-api, a POST /api/v1/orders request for a gold-tier customer
ordering 13 of prod_3 (the 27-inch monitor, which has 12 in stock) is rejected.
Without running the code, trace exactly which module and which check rejects it,
what HTTP status and error code come back, and what the response body looks
like. Then explain what would need to change for the order to succeed.
Do not read any other files outside of the samples/sample-api folder. Write your findings in analysis-ca-2.md
```
