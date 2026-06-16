# Evaluation Report

## Configuration

- Model: claude-opus-4-7
- Effort: xHigh
- Mode: Manual run

## Coding Tools

- Kiro IDE
- Kiro CLI
- Claude Code (Connected to Amazon Bedrock)

## Evaluation GF-1 

**GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from
scratch.

```text
You are verifying another AI tool's output, not writing the app yourself. A
command-line to-do app was generated into a folder named todo-app from this
specification:

- Files: exactly todo.py, storage.py, task.py, README.md (no more, no fewer).
- Commands: add "<title>", list, done <id>, delete <id>.
- Output strings (exact): "Added task <id>", "Completed task <id>",
  "Deleted task <id>"; list rows as "<id>. [ ] <title>" or "<id>. [x] <title>".
- Tasks persist to tasks.json in the current directory.
- Each task has: integer auto-incrementing id, title (string), done (bool).
- Standard library only (argparse, json); no third-party packages.
- Invalid input (missing title, unknown id, bad command) prints a clear error
  to stderr and exits with code 1.
- No tests, packaging files, or extra modules.

Do this:
1. List the files actually present and flag any missing or extra files.
2. Statically review the code: confirm stdlib-only imports, the Task model,
   id auto-increment, JSON load/save, and that the printed strings match the
   spec exactly (including the "[ ]"/"[x]" format).
3. Actually run the app in a clean working directory and execute, in order:
   - add "Buy milk"        -> expect "Added task 1", tasks.json created
   - add "Walk dog"        -> expect "Added task 2"
   - list                  -> expect "1. [ ] Buy milk" and "2. [ ] Walk dog"
   - done 1                -> expect "Completed task 1"
   - list                  -> expect "1. [x] Buy milk"
   - delete 2              -> expect "Deleted task 2"
   - list                  -> expect task 2 gone, task 1 remains
   For each command, record the exact stdout, stderr, and exit code.
4. Test the error paths and confirm each writes to stderr and exits with code 1:
   - add with no title
   - done <unknown id>
   - delete <unknown id>
   - an unrecognized command
5. Confirm ids keep auto-incrementing correctly (and note the behavior when all
   tasks are deleted, then a new one is added).

Report a PASS/FAIL verdict per spec bullet in a checklist, quote any mismatched
output, and end with an overall verdict: PASS, PASS WITH MINOR ISSUES, or FAIL.
Do not modify the generated code; if a command fails, report it rather than
fixing it.
```

### Results

**Kiro IDE**

Est. Credits Used: 2.25
Elapsed time: 1m 1s

Total files: 4
Total lines: 195

Breakdown:
task.py: 19
storage.py: 24
todo.py: 95
README.md: 57

Cost (at 0.02 per credit): $0.045

**Kiro CLI**

▸ Credits: 1.21 • Time: 36s

Total files: 4
Total lines: 195

Breakdown:
task.py: 15
storage.py: 19
todo.py: 98
README.md: 63

Cost (at 0.02 per credit): $0.0242

**Claude Code**

  Session

  Total cost:            $0.2331
  Total duration (API):  30s
  Total duration (wall): 1m 20s
  Total code changes:    163 lines added, 0 lines removed
  Usage by model:
       claude-opus-4-7:  828 input, 3.0k output, 205.4k cache read, 8.2k cache
   write ($0.2331)

## Evaluation CA-1

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

### Results

**Kiro IDE**

Est. Credits Used: 3.42
Elapsed time: 1m 48s

Cost (at 0.02 per credit): $0.0684

Lines produced: 155

**Kiro CLI**

▸ Credits: 9.38 • Time: 4m 2s

Cost (at 0.02 per credit): $0.1876

Lines produced: 206

Notes:
analysis.md generated in the root of the opened project.

**Claude Code**

Session

  Total cost:            $1.06
  Total duration (API):  2m 52s
  Total duration (wall): 3m 15s
  Total code changes:    156 lines added, 0 lines removed
  Usage by model:
       claude-opus-4-7:  683 input, 12.3k output, 941.3k cache read, 44.9k
  cache write ($1.06)

Notes:
analysis.md generated in the root of the samples/sample-api instead of the opened project.

## Evaluation CA-2

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

### Results

**Kiro IDE**

Est. Credits Used: 2.48
Elapsed time: 1m 5s

Lines produced: 149

Cost (at 0.02 per credit): $0.0496

**Kiro CLI**

Credits: 3.51
Time: 1m 14s

Lines produced: 144

Cost (at 0.02 per credit): $0.0702

**Claude Code (Connected to Amazon Bedrock)**

Total cost:            $0.51
Total duration (API):  1m 11s
Total duration (wall): 2m 19s
Total code changes:    65 lines added, 0 lines removed
Usage by model:
      claude-opus-4-7:  606 input, 4.2k output, 411.6k cache read, 32.2k
cache write ($0.51)
