# Claude Code Eval

Evaluates Claude Code's ability to use tools to solve programming tasks — writing files, executing code, and building multi-step pipelines.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and on your `PATH` as `claude`
  - Authenticated via `claude auth login`, or `ANTHROPIC_API_KEY` set in your environment
- A [Braintrust](https://braintrust.dev) account with `BRAINTRUST_API_KEY` set
- An OpenAI API key (`OPENAI_API_KEY`) for the LLM-based scorers

## Setup

```bash
npm install
```

## Run

```bash
BRAINTRUST_API_KEY=<your-key> npm run eval
```

Results are logged to the `claude-code-eval` project in Braintrust.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key used by the `claude` subprocess |
| `OPENAI_API_KEY` | — | OpenAI API key used by the LLM-based scorers |
| `BRAINTRUST_API_KEY` | — | Braintrust API key (required for logging and LLM scorers) |
| `CLAUDE_BIN` | `claude` | Path to the Claude Code binary |
| `BRAINTRUST_PROJECT` | `claude-code-eval` | Braintrust project name to log results to |

## What it tests

Each question requires Claude Code to write and execute code rather than answer from memory:

| Question | Tools required |
|---|---|
| Sum of squares 1–50 | `write` + `bash` |
| Merge sort implementation | `write` + `bash` |
| Word frequency counter | `write` + `bash` |
| Fibonacci across two files | `write` (×2) + `bash` |
| Longest common subsequence (DP) | `write` + `bash` |
| Bash-generated data piped to Python | `bash` + `write` + `bash` |

## Scoring

Each response is evaluated by two LLM-based scorers powered by `gpt-4o-mini` via the Braintrust AI proxy:

| Scorer | Description |
|---|---|
| **Factuality** | Checks whether the output is factually consistent with the expected answer |
| **Conciseness** | Checks whether the response contains only the program output with minimal extra explanation |
