# Sample AI Coding Tools Benchmark

A side-by-side comparison of popular AI coding tools. We run the same prompts
through each tool and measure how they stack up on **cost**, **speed**, and
**correctness**.

## Latest Report

- Run date: **2026-06-25** (Kiro IDE, Kiro CLI, Claude Code on Bedrock, Codex on Bedrock)

- Full PDF report: [`evaluations/2026-06-25/evaluation-report-2026-06-25.pdf`](./evaluations/2026-06-25/evaluation-report-2026-06-25.pdf)

### Evaluated Scenarios
- **GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from scratch.
- **CA-1** — Brownfield analysis: read an existing TypeScript API and explain architecture, pricing, and state machine.
- **CA-2** — Brownfield investigation: pinpoint which check rejects a specific request and what response it returns.

![Cost per prompt](./evaluations/2026-06-25/cost-per-prompt.png)

![Duration per prompt](./evaluations/2026-06-25/duration-per-prompt.png)

### Full results matrix

| Scenario | Tool | Model | Effort | Cost (USD) | Time (s) | Lines | Input Tokens | Output Tokens |
| -------- | ---- | ----- | ------ | ---------- | -------- | ----- | ------------ | ------------- |
| GF-1 | Claude Code | Claude Opus 4.8 | xHigh | **$0.3352** | 66.3  | 209 | 2,311   | 6,257  |
| GF-1 | Codex CLI   | GPT-5.5         | xHigh | **$0.9337** | 112.6 | 154 | 128,130 | 6,940  |
| GF-1 | Kiro CLI    | Claude Opus 4.8 | xHigh | **$0.0308** | 46.6  | 203 | NA      | NA     |
| GF-1 | Kiro IDE    | Claude Opus 4.8 | xHigh | **$0.0540** | 138.0 | NA  | NA      | NA     |
| CA-1 | Claude Code | Claude Opus 4.8 | xHigh | **$0.9711** | 256.5 | 330 | 2,446   | 22,590 |
| CA-1 | Codex CLI   | GPT-5.5         | xHigh | **$1.5280** | 131.5 | 211 | 229,972 | 7,974  |
| CA-1 | Kiro CLI    | Claude Opus 4.8 | xHigh | **$0.0646** | 121.4 | 269 | NA      | NA     |
| CA-1 | Kiro IDE    | Claude Opus 4.8 | xHigh | **$0.0620** | 194.0 | NA  | NA      | NA     |
| CA-2 | Claude Code | Claude Opus 4.8 | xHigh | **$0.6179** | 135.7 | 112 | 2,450   | 11,602 |
| CA-2 | Codex CLI   | GPT-5.5         | xHigh | **$1.0856** | 108.2 | 132 | 159,971 | 6,234  |
| CA-2 | Kiro CLI    | Claude Opus 4.8 | xHigh | **$0.0394** | 52.5  | 87  | NA      | NA     |
| CA-2 | Kiro IDE    | Claude Opus 4.8 | xHigh | **$0.0360** | 53.0  | NA  | NA      | NA     |

> Assumptions:
> Kiro costs derived from credits used at $0.02/credit.
> Claude Code cost is the reported run cost in /usage command. 
> Codex CLI cost is based on token pricing on Amazon Bedrock.

## Metrics We Track

- **Cost**: token/credit usage or dollar cost for the run.
- **Speed**: wall-clock time from prompt to finished result.
- **Results**: correctness of the output. (To be expanded upon)

## Methodology

- See full report in: [`evaluations/2026-06-25/evaluation-report-2026-06-25.pdf`](./evaluations/2026-06-25/evaluation-report-2026-06-25.pdf)

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
