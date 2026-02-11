# ADK Web Multi-Turn Tracing with Braintrust

Trace multi-turn ADK Web conversations in Braintrust. ADK Web normally creates separate traces per invocation; this implementation groups conversation turns together for session-level analysis.

## Problem

ADK Web creates a separate trace for each invocation, making it difficult to analyze multi-turn conversations as a unified session.

## Solution

Creates organizational "task" spans to group invocations, with metadata tags for correlation. Filter by `session.id` in Braintrust to view complete conversations.

## Quick Start

```bash
# 1. Install dependencies
./setup.sh

# 2. Add API keys to agents/research_agent/.env
# - GOOGLE_GENAI_API_KEY: https://aistudio.google.com/apikey
# - BRAINTRUST_API_KEY: https://www.braintrust.dev/app/settings

# 3. Verify configuration
./check_config.sh

# 4. Start server
./start_server.sh
```

Open http://localhost:3000/dev-ui/

## Features

- Dual tracing: `setup_adk()` for detailed operations + manual spans for organization
- Session persistence across requests (in-memory)
- Metadata tagging: `session.id`, `turn.number`, `session.user_id`
- Streaming response support
- Session expiry (1 hour default)
- Server restart detection via cookies
- Automatic new session creation on restart (prevents duplicate traces)

## Usage

### Start a Conversation

1. Open http://localhost:3000/dev-ui/
2. Select "research_assistant" agent
3. Have a multi-turn conversation
4. View traces at https://www.braintrust.dev/app

### View Traces in Braintrust

Filter by session to see complete conversation:
```
Tags → session.id → equals → <paste session UUID>
```

Show only detailed traces (hide organizational spans):
```
Search: invocation
```

Find session ID:
- Check server logs: "Extracted session: abc-123..."
- Or click any trace → Tags → session.id

## How It Works

### Dual Tracing Strategy

```python
# Initialize both tracing systems
setup_adk(project_name="your_project")      # Auto-traces ADK operations
logger = init_logger(project="your_project") # Manual organizational spans

# Create session span (organizational)
session_span = logger.start_span(
    name="adk_session",
    span_attributes={"type": "task", "session.id": session_id}
)

# Create turn spans as children (organizational)
turn_span = session_span.start_span(
    name=f"turn_{turn_number}",
    span_attributes={"type": "task", "turn.number": turn_number}
)

# ADK operations traced separately (detailed)
# setup_adk() automatically creates: invocation → agent_run → call_llm → tool

# Both tagged with same session.id for correlation
```

### Session Persistence

Session tracking via referer header:
- Browser sends: `http://localhost:3000/dev-ui/?session=<UUID>`
- Server extracts session UUID from referer
- Maps to stored session span in-memory dict
- Reuses same session span for all turns in conversation

Session expiry:
- Default: 1 hour of inactivity
- Configurable via `SESSION_EXPIRY_SECONDS`

### Restart Handling

Prevents duplicate traces when server restarts:

1. Server generates unique instance ID on startup
2. Sends ID to browser via httponly cookie
3. Checks cookie on each request to detect restarts
4. Forces new session if restart detected

## What You'll See in Braintrust

Two types of traces:

1. **Organizational spans** - `adk_session` → `turn_1`, `turn_2`, etc.
2. **Detailed operation traces** - `invocation`, `call_llm`, `tool`

Both tagged with same `session.id` for filtering.

Note: Organizational and detailed traces appear as separate root traces, not parent-child hierarchy. This is because ADK's internal OpenTelemetry context is separate from Braintrust's Python contextvars. Use filtering to group them.

## Limitations

### Separate Trace Trees

Organizational spans and detailed ADK operation traces appear as separate root traces, correlated via metadata tags rather than parent-child hierarchy.

Why: ADK's internal OpenTelemetry context is separate from Braintrust's Python contextvars.

Workaround: Filter by `session.id` in Braintrust UI to group related traces.

### In-Memory Session Storage

Session state stored in-memory, lost on server restart. The implementation forces new sessions on restart to prevent orphaned traces.

For production: Use Redis or database for persistent session storage.

### Referer Header Dependency

Relies on browser sending referer header with session ID. Falls back to cookie if referer missing.

Note: Some privacy tools block referer headers. For production, consider implementing custom header or request body approach.

## Troubleshooting

### No traces appearing
```bash
./check_config.sh
# Check for: "BRAINTRUST_API_KEY is set"
```

### Empty organizational spans but no detailed traces
```bash
# Verify GOOGLE_GENAI_API_KEY is set
cat agents/research_agent/.env | grep GOOGLE_GENAI_API_KEY
```

### Can't find session ID
```bash
# Check server logs for:
"Extracted session: abc-123..."

# Or click any trace in Braintrust → Tags → session.id
```

## Configuration

### Adjust Session Expiry

```python
# In unified_tracing.py
SESSION_EXPIRY_SECONDS = 3600  # 1 hour (default)
SESSION_EXPIRY_SECONDS = 14400  # 4 hours (for longer conversations)
```

### Custom Project Name

```bash
# Set environment variable
export BRAINTRUST_PROJECT="my-custom-project"

# Or edit in unified_tracing.py
project_name = "my-custom-project"
```

### Add Custom Tags

```python
# In the middleware, add to span_attributes:
span_attributes={
    "type": "task",
    "session.id": session_id,
    "environment": os.environ.get("ENV", "dev"),
    "version": "1.0.0",
}
```

## Production Deployment

### Scaling

Session persistence:
- Replace in-memory dict with Redis
- Use session ID as Redis key
- Store span metadata for reconstruction

Load balancing:
- Enable session affinity (sticky sessions)
- Or share session state via Redis

Monitoring:
- Track session expiry rates
- Monitor server instance churn
- Alert on high restart frequency

### Recommended Setup

```bash
# Development
uvicorn unified_tracing:app --reload --port 3000

# Production
uvicorn unified_tracing:app --host 0.0.0.0 --port 3000 --workers 4
```

## Support

For questions about:
- **ADK (Agent Development Kit):** https://github.com/google/genkit
- **Braintrust:** https://www.braintrust.dev/docs
