# repro_agent

Each ADK turn in a multi-turn conversation creates a **separate root-level trace** in Braintrust instead of being grouped under a single session.


**Expected:** One Braintrust log entry per conversation session, with each turn nested inside as child spans.

**Actual:** One Braintrust log entry per turn — N messages → N separate traces.

**Root cause:** `braintrust_adk` wraps `Runner.run()` with `start_span()`. Each call to `runner.run()` runs in a fresh async context with no parent span in scope, so `start_span()` finds nothing to attach to and creates a new root span.

## Setup

```bash
cp .env.example .env  # fill in your keys
pip install -r requirements.txt
```

`.env` requires:
```
BRAINTRUST_API_KEY=...
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
```

Authenticate with Google Cloud:
```bash
gcloud auth application-default login
```

Alternatively, provide a `GEMINI_API_KEY`.

## Run

```bash
adk web .
```

Select **repro_agent** in the UI, then send a few messages in the same conversation.

Open the [Braintrust project `adk-multi-turn-repro`](https://www.braintrust.dev) — each message appears as its own top-level log entry rather than turns within one session.
