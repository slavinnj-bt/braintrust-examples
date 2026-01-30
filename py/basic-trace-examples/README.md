# Braintrust Tracing Examples

This directory contains two basic examples demonstrating Braintrust tracing with different integration methods: LangChain (callback-based) and Traceloop (OpenTelemetry-based).

## Examples Overview

Both examples implement the same multi-turn conversation workflow with Tavily search:
1. Initial greeting about AI developments
2. Search query using Tavily to find latest LLM breakthroughs
3. Follow-up question to summarize findings

### 1. LangChain Example (`langchain_basic_example.py`)

Demonstrates Braintrust tracing using **callback handlers** with LangChain.

**Integration Method**: Uses `BraintrustCallbackHandler` to automatically capture LangChain operations (chains, LLM calls, tool invocations) as nested spans.

**Key Features**:
- Direct integration via Braintrust callback handler
- Automatic capture of all LangChain components
- Nested span structure with `@braintrust.traced` decorator
- Tagged with `integration: langchain` metadata

### 2. Traceloop Example (`traceloop_basic_example.py`)

Demonstrates Braintrust tracing using **OpenTelemetry** via Traceloop.

**Integration Method**: Uses Traceloop SDK which routes traces to Braintrust via OpenTelemetry protocol (OTLP).

**Key Features**:
- OpenTelemetry-based tracing
- Works with any OpenTelemetry-compatible service
- Uses `@workflow` decorators for span creation
- Tagged with `integration: traceloop` metadata

## Installation

### LangChain Example

```bash
pip install braintrust braintrust-langchain langchain-core langchain-openai langchain-community python-dotenv
```

### Traceloop Example

```bash
pip install "braintrust[otel]" traceloop-sdk openai requests python-dotenv
```

## Configuration

### Step 1: Get Your API Keys

You'll need:
- **Braintrust API Key**: Get from [Braintrust Settings](https://www.braintrust.dev/app/settings)
- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Tavily API Key**: Get from [Tavily](https://tavily.com/)

### Step 2: Get Your Braintrust Project ID

Run this Python script to get your project ID:

```python
import requests
headers = {'Authorization': 'Bearer YOUR_BRAINTRUST_API_KEY'}
resp = requests.get('https://api.braintrust.dev/v1/project', headers=headers)
for proj in resp.json().get('objects', []):
    print(f"{proj['name']}: {proj['id']}")
```

Or use the project ID from your Braintrust dashboard URL:
`https://www.braintrust.dev/app/[ORG]/p/[PROJECT_ID]`

### Step 3: Configure Environment Variables

Create a `.env` file in the parent directory (`braintrust-examples/.env`):

```bash
# Common - Required for both examples
BRAINTRUST_API_KEY=sk-...
OPENAI_API_KEY=sk-proj-...
TAVILY_API_KEY=tvly-...

# Traceloop-specific - Only for Traceloop example
TRACELOOP_BASE_URL=https://api.braintrust.dev/otel
TRACELOOP_HEADERS=Authorization=Bearer%20YOUR_API_KEY, x-bt-parent=project_id:YOUR_PROJECT_ID
```

**Important Notes**:
- Replace `YOUR_API_KEY` with your Braintrust API key
- Replace `YOUR_PROJECT_ID` with your actual project ID (UUID format)
- The space between "Bearer" and your key must be encoded as `%20`
- Do not use quotes around the `TRACELOOP_HEADERS` value

**Example**:
```bash
TRACELOOP_HEADERS=Authorization=Bearer%20sk-A1v90JN408CU3XXGTkv69KYhx0kOeanP1C1QeDYESRVILAQV, x-bt-parent=project_id:304df10c-25af-4bee-823b-40554cd8d1ea
```

## Running the Examples

### LangChain Example

```bash
cd braintrust-examples
python langchain_basic_example.py
```

**Expected Output**:
```
Running Langchain with Braintrust tracing...
The global callback handler will capture all Langchain operations.

=== Turn 1: Greeting ===
Assistant: [Greeting response]

=== Turn 2: Question requiring search ===
Assistant is using search tool...
Search results: 3 results found
Assistant: [Response with search results]

=== Turn 3: Follow-up question ===
Assistant: [Summary response]

Conversation complete!
Check Braintrust dashboard for the traces:
https://www.braintrust.dev/
```

### Traceloop Example

```bash
cd braintrust-examples
python traceloop_basic_example.py
```

**Expected Output**:
```
Running Traceloop with Braintrust tracing...
This will automatically capture the conversation via OpenTelemetry.

=== Turn 1: Greeting ===
Assistant: [Greeting response]

=== Turn 2: Question requiring search ===
Searching with Tavily...
Search results: 3 results found
Assistant: [Response with search results]

=== Turn 3: Follow-up question ===
Assistant: [Summary response]

Conversation complete!
Check Braintrust dashboard for the trace:
https://www.braintrust.dev/
```

## Viewing Traces

After running either example, view your traces in the [Braintrust Dashboard](https://www.braintrust.dev/).

**Trace Structure** (both examples):
```
run_conversation (parent span)
  ├─ Turn 1: LLM call (greeting)
  ├─ Turn 2: LLM call (with tools)
  │   ├─ Tavily search tool call
  │   └─ Final LLM call (with results)
  └─ Turn 3: LLM call (summary)
```

Each trace is tagged with metadata:
- LangChain: `integration: langchain`
- Traceloop: `integration: traceloop`

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'traceloop'"

**Solution**: Install `traceloop-sdk` (not `traceloop`):
```bash
pip install traceloop-sdk
```

### Issue: "403 Forbidden" error with Traceloop

**Problem**: Incorrect project ID in `TRACELOOP_HEADERS`

**Solution**:
1. Use the Python script above to get your actual project ID (UUID format)
2. Update `TRACELOOP_HEADERS` with the correct project ID
3. Ensure the API key in `TRACELOOP_HEADERS` matches your `BRAINTRUST_API_KEY`

### Issue: Traces not appearing in Braintrust

**Solution**:
1. Verify API keys are correct in `.env`
2. Check that `.env` file is in the parent directory
3. Ensure network connectivity to Braintrust API
4. For LangChain: Verify `init_logger()` is called before running the conversation
5. For Traceloop: Verify environment variables are loaded before `Traceloop.init()`

### Issue: LangChain spans are not nested properly

**Solution**: This is expected behavior if the `@braintrust.traced` decorator is not used. The decorator creates a parent span that groups all LangChain operations together.

## Key Differences

| Feature | LangChain Example | Traceloop Example |
|---------|------------------|-------------------|
| Integration | Callback handler | OpenTelemetry |
| Setup | Direct Braintrust SDK | Environment variables + Traceloop SDK |
| Dependencies | `braintrust-langchain` | `traceloop-sdk` |
| Trace routing | Direct to Braintrust | Via OTLP to Braintrust |
| Best for | LangChain applications | Any framework with OpenTelemetry |

## Documentation References

- [Braintrust LangChain Integration](https://www.braintrust.dev/docs/integrations/sdk-integrations/langchain)
- [Braintrust Traceloop Integration](https://www.braintrust.dev/docs/integrations/sdk-integrations/traceloop)
- [Traceloop Python Docs](https://www.traceloop.com/docs/openllmetry/getting-started-python)
