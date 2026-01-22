# Chainlit App - OpenAI & Anthropic Support

This Chainlit application supports both OpenAI and Anthropic AI providers.

## Installation

The virtual environment is already set up with Python 3.13.

**Important**: Use the parent directory's venv (from the repository root):

```bash
cd /Users/nick.slavin/repos/braintrust-examples
source .venv/bin/activate
cd py
```

Or activate from the py directory:

```bash
cd /Users/nick.slavin/repos/braintrust-examples/py
source ../.venv/bin/activate
```

All dependencies are already installed and upgraded.

## Environment Variables

Set the required API keys:

```bash
export OPENAI_API_KEY="your-openai-key"           # For OpenAI provider
export ANTHROPIC_API_KEY="your-anthropic-key"     # For Anthropic provider
export TAVILY_API_KEY="your-tavily-key"           # For web search
export BRAINTRUST_API_KEY="your-braintrust-key"   # For logging
```

Configure which provider to use:

```bash
export AI_PROVIDER="openai"      # or "anthropic" (default: openai)
export AI_MODEL="gpt-4"          # Optional: override default model
```

## Usage

### Using OpenAI (Default)
```bash
chainlit run app.py
```

### Using Anthropic
```bash
AI_PROVIDER=anthropic chainlit run app.py
```

### Specifying a Custom Model

```bash
# With OpenAI
AI_MODEL=gpt-4 chainlit run app.py

# With Anthropic
AI_PROVIDER=anthropic AI_MODEL=claude-3-opus-20240229 chainlit run app.py
```

## Default Models

- **OpenAI**: `gpt-4o-mini`
- **Anthropic**: `claude-3-5-sonnet-20241022`

## Features

- PDF document upload and processing
- RAG (Retrieval-Augmented Generation) with vector search
- Web search integration via Tavily
- Conversation history tracking
- Braintrust logging and tracing
- Streaming responses
- Tool calling support (web search)

## Troubleshooting

### OpenTelemetry Import Errors

If you encounter `ImportError: cannot import name 'ReadableLogRecord'`:

1. Make sure you're using the correct virtual environment (parent directory's .venv)
2. Upgrade OpenTelemetry packages:

```bash
cd /Users/nick.slavin/repos/braintrust-examples
source .venv/bin/activate
pip install --upgrade opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-common opentelemetry-exporter-otlp-proto-grpc opentelemetry-exporter-otlp-proto-http
```

### Verify Installation

```bash
source .venv/bin/activate
python -c "from opentelemetry.sdk._logs import LoggerProvider; print('✓ OpenTelemetry working')"
```
