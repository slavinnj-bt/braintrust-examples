# Earnings Call PDF Agent — Braintrust Example

A lightweight multi-turn agent that retrieves earnings-call PDFs and answers
questions about them, with full Braintrust tracing and PDF attachment logging.

## What this demonstrates

| Feature | Where |
|---------|-------|
| Multi-turn agent conversation | `earnings_agent.py` – `chat()` loop |
| OpenAI Agents SDK tool use | `fetch_and_analyze_earnings` tool |
| PDF sent to GPT-4o as a base64 `file` part | inside the tool |
| Braintrust `Attachment` logged per span | `span.log(input={"pdf": attachment})` |
| `braintrust.wrap_openai()` auto-tracing | top of both files |
| Batch evaluation with PDFs in dataset | `eval.py` |
| `Factuality` scoring via `autoevals` | `eval.py` |

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API keys
cp .env.example .env
# edit .env and fill in OPENAI_API_KEY and BRAINTRUST_API_KEY

# 3. Run the interactive agent
python earnings_agent.py

# 4a. Run the evaluation locally (direct GPT-4o baseline)
python eval.py

# 4b. Run the evaluation locally through the full agent pipeline
python eval.py --agent

# 4c. Upload the dataset to Braintrust (required before remote eval)
python eval.py --upload-dataset

# 4d. Start the remote eval dev server
braintrust eval remote_eval.py --dev
```

## Remote eval

The remote eval dev server lets you trigger evals directly from the Braintrust
UI against the uploaded dataset, without re-uploading PDFs each time.

**One-time setup:**
```bash
# Upload dataset (PDFs are stored in Braintrust object storage)
python eval.py --upload-dataset
```

**Start the dev server:**
```bash
braintrust eval remote_eval.py --dev
```

This starts a local HTTP server (default port 8300). Open the Braintrust UI,
navigate to your project, select the `earnings-pdfs` dataset, and click
**Run Eval** → point it at your dev server URL. Braintrust will call the server
once per dataset row, passing the PDF as a signed `braintrust_attachment`
reference. The task function downloads the bytes via `ReadonlyAttachment` and
calls GPT-4o with the PDF inline. Results are streamed back and logged as a new
experiment.

## Available companies

| Name in chat | Key | Quarter |
|---|---|---|
| Meta / Meta Platforms / Facebook | `meta` | Q4 2024 |
| JPMorgan / JPMorgan Chase | `jpmorgan` | Q4 2024 |
| AT&T | `att` | Q4 2024 |
| Qualcomm | `qualcomm` | Q1 FY2025 |
| Home Depot | `homeDepot` | Q3 2024 |

## Updating PDF URLs

The PDF URLs in `EARNINGS_PDFS` (both files) point to investor-relations pages
that may rotate over time. If a download fails you will see a clear error
message with the attempted URL. Replace the `url` value with the current link
from the company's investor-relations page or the SEC EDGAR filing index.

## How tracing works

```
Braintrust project: earnings-pdf-agent
└── earnings-agent-session          (top-level span, one per run)
    ├── turn-1                       (one span per user message)
    │   └── fetch_and_analyze_earnings  (@traced tool span)
    │       ├── input.pdf  → Attachment (viewable in playground)
    │       └── GPT-4o chat completion  (auto-traced by wrap_openai)
    └── turn-2
        └── …
```

For the eval (`eval.py`) each experiment row carries the PDF attachment in
`input.pdf`, making it viewable and re-runnable directly in the Braintrust
playground.

## Large PDFs (> 20 MB)

Braintrust imposes a 20 MB per-span limit for standard `Attachment` objects.
For larger PDFs use `JSONAttachment` (stores data out-of-band) or
`ExternalAttachment` (self-hosted S3 reference):

```python
from braintrust import JSONAttachment

# JSONAttachment – good for structured data stored alongside the span
span.log(input={"transcript": JSONAttachment(data, filename="transcript.json")})
```

See [Braintrust attachment docs](https://www.braintrust.dev/docs/instrument/attachments#advanced-examples)
for details.
