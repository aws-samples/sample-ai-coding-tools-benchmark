# Evaluation Report — 2026-06-24

A side-by-side comparison of four AI coding tools run against an identical set
of prompts. Each tool was measured on **cost**, **speed**, and **correctness** across three scenarios: one greenfield build and two brownfield
analysis tasks.

## Summary

- **Run date:** 2026-06-24
- **Aggregation:** mean over 1 run per tool/scenario
- **Mode:** Automated
- **Tools under test:** Claude Code, Codex CLI, Kiro CLI, Kiro IDE

**Headline findings**

- **Lowest cost:** Kiro CLI at **$0.117** total across the three scenarios —
  roughly 25x cheaper than Codex CLI and 13x cheaper than Claude Code.
- **Fastest:** Codex CLI completed all three scenarios in **186.5s** total
  (62.2s average), the quickest of the group.
- **Most expensive:** Codex CLI at **$2.903** total, driven by large input
  token counts billed at the GPT-5.5 rate.
- **Best cost/speed balance:** Kiro IDE — near Kiro-CLI pricing ($0.152 total)
  with the second-fastest aggregate time (385s).

## Configuration

| Tool | Model | Effort | Mode |
| ---- | ----- | ------ | ---- |
| Claude Code | us.anthropic.claude-opus-4-8 | xHigh | Automated |
| Codex CLI | openai.gpt-5.5 | High | Automated |
| Kiro CLI | claude-opus-4.8 | xHigh | Automated |
| Kiro IDE | claude-opus-4.8 | xHigh | Manual |

## Methodology

- **Harness:** runs were executed and aggregated by `tools/run_benchmark.py`
  (run-average mode) and recorded in `run-complete.json`.
- **Procedure:** each tool received the identical prompt for each scenario, run
  in Automated mode with no manual intervention. Output was written to the
  tool's designated folder and metrics captured from each tool's own usage
  reporting.
- **Runs and aggregation:** 1 run per tool/scenario; reported figures are the
  mean (a single run here, so mean equals the observed value).
- **Metrics captured:**
  - *Cost (USD)* — derived per the pricing and methodology below.
  - *Time (s)* — wall-clock elapsed time from prompt to finished result.
  - *Lines* — lines of output produced (where reported by the tool).
  - *Tokens* — input/output token counts (where reported by the tool).
- **Held constant:** prompts, scenario order, model effort level (xHigh for
  Claude/Kiro, High for Codex), and Automated mode across all tools.
- **Not scored:** correctness/quality of output is out of scope for this run
  and assessed separately.

## Pricing

**OpenAI GPT 5.5 (on Amazon Bedrock)** — used for Codex CLI

| Token type | Price per 1M tokens |
| ---------- | ------------------- |
| Input | $5.50 |
| Cached input | $0.55 |
| Output | $33.00 |

**Claude Opus 4.8 (on Amazon Bedrock)** — used for Claude Code

| Token type | Price per 1M tokens |
| ---------- | ------------------- |
| Input | $5.00 |
| Output | $25.00 |

**Kiro credits** — used for Kiro CLI and Kiro IDE

| Unit | Price |
| ---- | ----- |
| Per credit | $0.02 |

**Cost methodology**

- **Kiro CLI / Kiro IDE:** derived from credits consumed at **$0.02/credit**.
- **Claude Code:** reported run cost in USD from the `/usage` command
  (Connected to Amazon Bedrock, Claude Opus 4.8 at $5.00/1M input and
  $25.00/1M output; reported totals also include cache read/write).
- **Codex CLI:** computed from session token totals using the GPT-5.5 on
  Amazon Bedrock pricing above (input × $5.50/1M + output × $33.00/1M).

## Evaluated Scenarios

- **GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from
  scratch.
- **CA-1** — Brownfield analysis: read an existing TypeScript API and explain
  architecture, pricing, and the order state machine.
- **CA-2** — Brownfield investigation: pinpoint which check rejects a specific
  request and what response it returns.

## Results

### Full results matrix

| Scenario | Tool | Cost (USD) | Time (s) | Lines | Input Tokens | Output Tokens |
| -------- | ---- | ---------- | -------- | ----- | ------------ | ------------- |
| GF-1 | Claude Code | **$0.3281** | 87.1  | 197 | 2,448   | 4,079  |
| GF-1 | Codex CLI   | **$0.7275** | 62.7  | 164 | 106,652 | 4,270  |
| GF-1 | Kiro CLI    | **$0.0316** | 64.8  | 189 | NA      | NA     |
| GF-1 | Kiro IDE    | **$0.0540** | 138.0 | NA  | NA      | NA     |
| CA-1 | Claude Code | **$0.7966** | 313.2 | 308 | 2,577   | 16,931 |
| CA-1 | Codex CLI   | **$1.4613** | 90.1  | 324 | 228,014 | 6,279  |
| CA-1 | Kiro CLI    | **$0.0518** | 102.8 | 281 | NA      | NA     |
| CA-1 | Kiro IDE    | **$0.0620** | 194.0 | NA  | NA      | NA     |
| CA-2 | Claude Code | **$0.4145** | 61.3  | 111 | 2,446   | 4,745  |
| CA-2 | Codex CLI   | **$0.7140** | 33.7  | 96  | 115,527 | 2,383  |
| CA-2 | Kiro CLI    | **$0.0336** | 296.0 | 88  | NA      | NA     |
| CA-2 | Kiro IDE    | **$0.0360** | 53.0  | NA  | NA      | NA     |

> Token counts are not reported for Kiro CLI/IDE (credit-based billing). Kiro
> IDE does not report a line count in this run.

### Aggregate by tool

Totals and means across all three scenarios:

| Tool | Total Cost (USD) | Avg Cost (USD) | Total Time (s) | Avg Time (s) | Total Lines |
| ---- | ---------------- | -------------- | -------------- | ------------ | ----------- |
| Kiro CLI    | **$0.1170** | $0.0390 | 463.6 | 154.5 | 558 |
| Kiro IDE    | **$0.1520** | $0.0507 | 385.0 | 128.3 | NA  |
| Claude Code | **$1.5392** | $0.5131 | 461.6 | 153.9 | 616 |
| Codex CLI   | **$2.9028** | $0.9676 | 186.5 | 62.2  | 584 |

### Visualizations

![Cost per prompt](./cost-per-prompt.png)

![Duration per prompt](./duration-per-prompt.png)

## Per-Scenario Breakdown

### GF-1 — Greenfield build

All four tools produced comparable output volume (164–197 lines). On cost,
Kiro CLI ($0.0316) and Kiro IDE ($0.0540) were an order of magnitude cheaper
than Claude Code ($0.3281) and Codex CLI ($0.7275). Codex CLI was the fastest
to complete after Kiro CLI, but its large input token footprint (106,652
tokens) made it the most expensive on this scenario.

### CA-1 — Brownfield analysis

This was the most demanding scenario and the widest cost spread. Codex CLI cost
$1.4613 — the single most expensive result in the run — driven by 228,014
input tokens. Claude Code followed at $0.7966 with the highest output token
count (16,931). Codex CLI was fastest (90.1s) despite the cost, while Kiro CLI
delivered the analysis for $0.0518, roughly 28x cheaper than Codex CLI.

### CA-2 — Brownfield investigation

The lightest scenario by output. Codex CLI was again the fastest (33.7s) and
the most expensive among the paid-token tools ($0.7140). Kiro CLI was the
slowest here (296.0s) but the cheapest ($0.0336). Kiro IDE offered a strong
balance: $0.0360 in 53.0s.

## Observations

- **Credit-based tools dominate on cost.** Kiro CLI and Kiro IDE were
  consistently 10–30x cheaper per scenario than the token-billed tools, because
  Codex CLI in particular sends very large input contexts (over 100K tokens per
  scenario) billed at $5.50/1M.
- **Codex CLI trades cost for speed.** It was the fastest tool overall (62.2s
  average) but also the most expensive (~$0.97 average per scenario).
- **Claude Code sits in the middle on speed** but its cost scales with output
  volume — CA-1's 16,931 output tokens pushed it to $0.7966.
- **Kiro CLI's time is uneven.** It was competitive on GF-1 and CA-1 but slow
  on CA-2 (296.0s), which inflated its aggregate time above Kiro IDE despite a
  lower total cost.

## Caveats

- Results reflect a **single run** per tool/scenario; figures are means but not
  yet variance-tested. Treat individual numbers as indicative rather than
  definitive.
- Kiro IDE line counts and Kiro token counts are unavailable due to how each
  tool reports usage, limiting like-for-like comparison on those dimensions.
- This report measures cost, speed, and output volume only. **Correctness of
  the output is not scored here** and should be assessed separately before
  drawing quality conclusions.

## References

- Source repository: [https://github.com/aws-samples/sample-ai-coding-tools-benchmark](https://github.com/aws-samples/sample-ai-coding-tools-benchmark)

