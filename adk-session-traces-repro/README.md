# ADK Session Traces

This example shows how to trace multi-turn Google ADK conversations as a single session in Braintrust.

## The problem

`braintrust_adk` wraps `Runner.run()` with `start_span()`, but each call runs in a fresh async context with no parent span in scope — so every turn creates a new root trace instead of being grouped under one session.

## The fix

`code_execution_agent/agent.py` monkey-patches `Runner.run` (and `run_async`) using `wrapt`. For each call, it looks up the `session_id` from the kwargs and opens a Braintrust span with that `session_id` used as both the span ID and root span ID:

```python
logger.start_span(
    name=f"chat-session [{session_id}]",
    span_id=session_id,
    root_span_id=session_id,
)
```

Using a stable, deterministic ID means that every turn in the same ADK session re-opens the same span. Braintrust merges all events with the same span ID into one root trace in the UI, so N turns produce one log entry with N invocation spans nested inside.

The patch uses `__enter__`/`__exit__` directly instead of a `with` block because Python doesn't allow `with` to span a `yield` boundary in a generator, and `Runner.run` is a generator that yields ADK events.

## Video Demo

Watch on [Loom](https://www.loom.com/share/331bcd7c04574a9ebd1e7e6348f0189d)

## Setup

```bash
cp .env.example .env  # fill in your keys
pip install -r code_execution_agent/requirements.txt
```

`.env` requires:
```
BRAINTRUST_API_KEY=...
GEMINI_API_KEY=...
```

## Run

```bash
adk web .
```

Select **code_execution_agent** in the UI and send a few messages in the same conversation. All turns will appear nested under a single session span in your [Braintrust](https://www.braintrust.dev) project.
