# ADK Web Multi-Turn Tracing with Braintrust

A solution for tracing multi-turn ADK Web conversations in Braintrust. ADK Web normally creates separate traces per invocation; this implementation groups conversation turns together for better multi-turn analysis.

## What This Solves

**Problem:** ADK Web creates a separate trace for each invocation, making it difficult to analyze multi-turn conversations as a unified session.

**Solution:** Two implementations that create organizational "task" spans to group invocations, with metadata tags for correlation. Filter by `session.id` in Braintrust to view complete conversations.

## Quick Start

```bash
# 1. Install dependencies
./setup.sh

# 2. Add API keys to agents/research_agent/.env
# - GOOGLE_GENAI_API_KEY: https://aistudio.google.com/apikey
# - BRAINTRUST_API_KEY: https://www.braintrust.dev/app/settings

# 3. Verify configuration
./check_config.sh

# 4. Start server (choose one)
# Option A: Basic production (recommended for stable environments)
uvicorn main_production:app --port 3000

# Option B: With restart handling (recommended for development)
uvicorn main_force_new_sessions:app --port 3000

# Or use the start script (runs Option B by default)
./start_server.sh
```

Then open http://localhost:3000/dev-ui/

## Implementation Options

### Option 1: main_production.py (Stable Environments)

**Best for:** Production deployments with infrequent restarts

**Features:**
- Dual tracing: `setup_adk()` for detailed operations + manual spans for organization
- Session persistence across requests (in-memory)
- Comprehensive metadata tagging (`session.id`, `turn.number`, `session.user_id`)
- Streaming response support
- Session expiry (1 hour default)

**What you see in Braintrust:**
- Organizational spans: `adk_session` → `turn_1`, `turn_2`, etc.
- Detailed operation traces: `invocation`, `call_llm`, `tool`
- Both tagged with same `session.id` for filtering

### Option 2: main_force_new_sessions.py (Development/Restart Handling)

**Best for:** Development environments with frequent server restarts

**Everything from Option 1, PLUS:**
- Cookie-based server instance tracking
- Automatically forces new sessions on server restart
- Prevents duplicate/orphaned traces
- Tags traces with `server.instance_id` for filtering

**How restart detection works:**
1. Server generates unique instance ID on startup
2. Sends ID to browser via httponly cookie
3. Checks cookie on each request to detect restarts
4. Forces new session if restart detected

## Usage

### Basic Workflow

1. Open http://localhost:3000/dev-ui/
2. Select "research_assistant" agent
3. Have a multi-turn conversation
4. View traces at https://www.braintrust.dev/app

### Viewing Traces in Braintrust

**Filter by session to see complete conversation:**
```
Tags → session.id → equals → <paste session UUID>
```

**Show only detailed traces (hide organizational spans):**
```
Search: invocation
```

**Find session ID:**
- Check server logs: "Extracted session: abc-123..."
- Or click any trace → Tags → session.id

## How It Works

### Dual Tracing Strategy

```python
# 1. Initialize both tracing systems
setup_adk(project_name="your_project")      # Auto-traces ADK operations
logger = init_logger(project="your_project") # Manual organizational spans

# 2. Create session span (organizational)
session_span = logger.start_span(
    name="adk_session",
    span_attributes={"type": "task", "session.id": session_id}
)

# 3. Create turn spans as children (organizational)
turn_span = session_span.start_span(
    name=f"turn_{turn_number}",
    span_attributes={"type": "task", "turn.number": turn_number}
)

# 4. ADK operations traced separately (detailed)
# setup_adk() automatically creates: invocation → agent_run → call_llm → tool

# 5. Both tagged with same session.id for correlation
```

### Session Persistence

**Session tracking via referer header:**
- Browser sends: `http://localhost:3000/dev-ui/?session=<UUID>`
- Server extracts session UUID from referer
- Maps to stored session span in-memory dict
- Reuses same session span for all turns in conversation

**Session expiry:**
- Default: 1 hour of inactivity
- Configurable via `SESSION_EXPIRY_SECONDS`

## Files

| File | Purpose |
|------|---------|
| `main_production.py` | Production implementation (stable environments) |
| `main_force_new_sessions.py` | Development implementation (with restart handling) |
| `PRODUCTION_GUIDE.md` | Complete guide on using the production version |
| `QUICK_REFERENCE.md` | Quick lookup for commands and troubleshooting |
| `RESTART_BEHAVIOR_GUIDE.md` | Deep dive on server restart detection |
| `agents/research_agent/` | Sample research agent with Google Search |
| `setup.sh` | Installation script |
| `check_config.sh` | Configuration verification |
| `start_server.sh` | Server startup script |
| `requirements.txt` | Python dependencies |

## Limitations

### Separate Trace Trees

**Current behavior:**
- Organizational spans (`adk_session`, `turn_N`) appear as separate root traces
- Detailed ADK operation traces (`invocation`) appear as separate root traces
- Correlated via metadata tags, not parent-child hierarchy

**Why:** ADK's internal OpenTelemetry context is separate from Braintrust's Python contextvars

**Workaround:** Filter by `session.id` in Braintrust UI to group related traces

### In-Memory Session Storage

**Current behavior:**
- Session state stored in-memory, lost on server restart
- `main_production.py`: Continues existing sessions after restart (can cause issues)
- `main_force_new_sessions.py`: Forces new sessions on restart (clean break)

**Production consideration:** Use Redis or database for persistent session storage

### Referer Header Dependency

**Current behavior:**
- Relies on browser sending referer header with session ID
- Falls back to cookie if referer missing
- Some privacy tools block referer headers

**Alternative:** Implement custom header or request body approach

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

### Duplicate traces after restart
```bash
# Use main_force_new_sessions.py instead of main_production.py
uvicorn main_force_new_sessions:app --port 3000
```

## Production Deployment

### Scaling Considerations

**Session persistence:**
- Replace in-memory dict with Redis
- Use session ID as Redis key
- Store span metadata for reconstruction

**Load balancing:**
- Enable session affinity (sticky sessions)
- Or share session state via Redis

**Monitoring:**
- Track session expiry rates
- Monitor server instance churn
- Alert on high restart frequency

### Recommended Setup

```python
# For production:
uvicorn main_production:app --host 0.0.0.0 --port 3000 --workers 4

# For development:
uvicorn main_force_new_sessions:app --reload --port 3000
```

## Advanced Configuration

### Adjust Session Expiry

```python
# In main_production.py or main_force_new_sessions.py
SESSION_EXPIRY_SECONDS = 3600  # 1 hour (default)
SESSION_EXPIRY_SECONDS = 14400  # 4 hours (for longer conversations)
```

### Custom Project Name

```bash
# Set environment variable
export BRAINTRUST_PROJECT="my-custom-project"

# Or edit in the Python file
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

## Further Reading

- **PRODUCTION_GUIDE.md** - Complete workflows for debugging, cost analysis, performance tuning
- **QUICK_REFERENCE.md** - Braintrust filters, common tasks, keyboard shortcuts
- **RESTART_BEHAVIOR_GUIDE.md** - How restart detection works, edge cases, monitoring

## Support

For questions about:
- **ADK (Agent Development Kit):** https://github.com/google/genkit
- **Braintrust:** https://www.braintrust.dev/docs
- **This implementation:** Open an issue or refer to the guide files
