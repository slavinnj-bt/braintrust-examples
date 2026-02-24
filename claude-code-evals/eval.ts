import { Eval, currentSpan } from "braintrust";
import { Factuality, LLMClassifierFromSpec } from "autoevals";
import { execFileSync } from "child_process";

// Uses OpenAI
const Conciseness = LLMClassifierFromSpec("Conciseness", {
  prompt: `You are evaluating whether an AI assistant's response is concise.

[BEGIN DATA]
************
[Task]: {{{input}}}
************
[Response]: {{{output}}}
************
[END DATA]

The task asks the assistant to execute code and return the printed output. A concise response contains only the program output with minimal or no extra explanation. Evaluate the response and choose one of the following options:

(A) The response contains only the program output (or output plus a very brief label), with no unnecessary explanation.
(B) The response includes the output but adds a short explanation or surrounding context that is not strictly necessary.
(C) The response is verbose — it includes lengthy explanations, descriptions of steps taken, or other content well beyond the bare output.`,
  choice_scores: { A: 1, B: 0.5, C: 0 },
  use_cot: true,
  model: "gpt-4o-mini",
});

const CLAUDE_BIN = process.env.CLAUDE_BIN ?? "claude";
const PROJECT_NAME = process.env.BRAINTRUST_PROJECT ?? "claude-code-eval";

Eval(PROJECT_NAME, {
  data: [
    {
      // Requires write + bash: basic computation
      input:
        "Write a Python script that computes the sum of squares from 1 to 50 (1² + 2² + ... + 50²) and prints the result. Save it to /tmp/sumsq.py, execute it with Python, and return the printed output.",
      expected: "42925",
    },
    {
      // Requires write + bash: sorting algorithm
      input:
        "Write a Python script to /tmp/mergesort.py that implements merge sort and sorts the list [38, 27, 43, 3, 9, 82, 10]. Print the sorted result. Execute it and return the output.",
      expected: "[3, 9, 10, 27, 38, 43, 82]",
    },
    {
      // Requires write + bash: string processing
      input:
        "Write a Python script to /tmp/wordfreq.py that counts word frequencies in the string 'to be or not to be that is the question'. Print each word and its count, sorted by frequency descending. Execute it and return the output.",
      expected: "be",
    },
    {
      // Requires write two files + bash: multi-file import
      input:
        "Create two Python files: /tmp/fibonacci_lib.py containing a function `fib(n)` that returns the nth Fibonacci number (0-indexed, so fib(0)=0, fib(1)=1), and /tmp/test_fib.py that imports it and prints fib(10). Execute /tmp/test_fib.py and return the output.",
      expected: "55",
    },
    {
      // Requires write + bash: dynamic programming
      input:
        "Write a Python script to /tmp/lcs.py that finds the length of the longest common subsequence of the strings 'ABCBDAB' and 'BDCAB' using dynamic programming. Print the length. Execute it and return the output.",
      expected: "4",
    },
    {
      // Requires bash + write + bash: multi-step pipeline
      input:
        "Using bash, create a file /tmp/numbers.txt containing the integers 1 through 20, one per line. Then write a Python script /tmp/evens.py that reads this file and prints only the even numbers, one per line. Execute the Python script and return the output.",
      expected: "20",
    },
  ],
  task: (input) => {
    const span = currentSpan();
    const experimentId = span.getParentInfo()?.objectId.getSync().value;

    try {
      return execFileSync(
        CLAUDE_BIN,
        ["--print", "--dangerously-skip-permissions", input],
        {
          encoding: "utf-8",
          timeout: 120_000,
          env: {
            // Inherit all env vars from the parent process (e.g. API keys, PATH)
            ...process.env,
            // Unset CLAUDECODE so the subprocess doesn't detect it's running
            // inside Claude Code and alter its behavior (e.g. suppress tracing)
            CLAUDECODE: undefined,
            // Pass the current span's ID so the subprocess can attach its
            // own Braintrust traces as children of this span
            CC_PARENT_SPAN_ID: span.spanId,
            // Pass the root span ID so the subprocess can link back to the
            // top-level trace for this eval run
            CC_ROOT_SPAN_ID: span.rootSpanId,
            // If we have an experiment ID, pass it so the subprocess logs
            // its traces into the same experiment
            ...(experimentId ? { CC_EXPERIMENT_ID: experimentId } : {}),
          },
        },
      ).trim();
    } catch (err: any) {
      return err.stdout?.trim() || err.stderr?.trim() || err.message || "";
    }
  },
  scores: [Factuality, Conciseness],
});
