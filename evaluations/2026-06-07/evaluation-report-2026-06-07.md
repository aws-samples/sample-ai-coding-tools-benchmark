# Evaluation Report

## Configuration

- Model: claude-opus-4-7
- Effort: xHigh
- Mode: Manual run

## Coding Tools

- Kiro IDE
- Kiro CLI
- Claude Code (Connected to Amazon Bedrock)

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

**Claude Code**

Total cost:            $1.00
  Total duration (API):  3m 17s
  Total duration (wall): 6m 57s
  Total code changes:    392 lines added, 0 lines removed
  Usage by model:
       claude-opus-4-7:  684 input, 11.8k output, 820.5k cache read, 47.0k
  cache write ($1.00)
