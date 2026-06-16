# Evaluation Report

## Prompt

- references/prompts-v1.md

## Coding Tools and Models

- Kiro IDE, Opus 4.8 xHigh
  - Cost at $0.02 per credit
- Kiro CLI, Opus 4.8 xHigh
  - Cost at $0.02 per credit
- Claude Code, Opus 4.8 xHigh (Connected to Amazon Bedrock)
  - Cost as displayed in USD in /usage
- Codex CLI, GPT-5.5 High (Plus plan, CLI v0.138.0)
  - Computed from the session token totals using OpenAI pay-as-you-go GPT-5.5
  pricing ($5.00 / 1M input, $0.50 / 1M cached input, $30.00 / 1M output;
  reasoning tokens billed at the output rate). Ref: https://developers.openai.com/api/docs/pricing


## Evaluation GF-1

**GF-1** — Greenfield build: produce a fresh, spec-bound CLI to-do app from
scratch.

### Results

**Kiro IDE**

(pending)

**Kiro CLI**

(pending)

**Claude Code**

(pending)

**Codex CLI**

Token usage: total=36,657 input=33,210 (+ 190,336 cached) output=3,447
(reasoning 656)

Total duration: 2m 10s

Total files: 4
Total lines: 118

Cost (API-equivalent estimate): $0.36
(input 33,210 × $5/1M = $0.1661 + cached 190,336 × $0.50/1M = $0.0952 +
output 3,447 × $30/1M = $0.1034)

## Evaluation CA-1

Token usage: total=33,283 input=28,328 (+ 182,656 cached) output=4,955
(reasoning 953)

Total duration: 1m 54s

Cost (API-equivalent estimate): $0.38
(input 28,328 × $5/1M = $0.1416 + cached 182,656 × $0.50/1M = $0.0913 +
output 4,955 × $30/1M = $0.1487)

## Evaluation CA-2

Token usage: total=28,555 input=26,436 (+ 128,640 cached) output=2,119
(reasoning 394)

Total duration: 53s

Cost (API-equivalent estimate): $0.26
(input 26,436 × $5/1M = $0.1322 + cached 128,640 × $0.50/1M = $0.0643 +
output 2,119 × $30/1M = $0.0636)