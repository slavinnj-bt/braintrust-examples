# NPS Scoring After Ingestion

Two-script example showing how to add scores to Braintrust traces after they have already been logged—simulating a real workflow where conversations are recorded during the day and scored later as a batch job.

## Scripts

**`customer_service_chatbot.py`** — logs customer service conversations to Braintrust. Each span is tagged `unscored` so the scorer can find it later.

**`score_traces.py`** — queries Braintrust for `unscored` spans, uses Claude to predict an NPS score for each conversation, and writes the score back to the original span without overwriting any existing data.

## Setup

Install dependencies:

```bash
pip install braintrust braintrust-langchain langchain-anthropic anthropic requests
```

Copy `.env` and fill in your keys:

```
BRAINTRUST_API_KEY=...
BRAINTRUST_PROJECT=...
ANTHROPIC_API_KEY=...
```

Load the env file before running:

```bash
export $(grep -v '^#' .env | xargs)
```

## Running

**Step 1** — log conversations (run once, or on a schedule):

```bash
python customer_service_chatbot.py
```

**Step 2** — score the unscored spans (run independently, any time after step 1):

```bash
python score_traces.py
```

The scorer finds spans by tag, so it does not need to know span IDs. Re-running step 2 will only score spans that are still tagged `unscored`; already-scored spans are tagged `scored` and skipped.

## How it works

`customer_service_chatbot.py` logs each conversation with `tags=["customer_service", "unscored"]`.

`score_traces.py` queries BTQL for spans matching both tags, calls Claude with a scoring prompt, then patches each span using `_is_merge=true`:

```
scores:   { nps: 0.0–1.0 }
tags:     ["customer_service", "scored"]
metadata: { nps_score, nps_rationale, scorer_model, scorer_version }
```

`_is_merge=true` deep-merges the new fields into the existing span record. The original input, output, LangChain child spans, and all other metadata are preserved.
