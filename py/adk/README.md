# ADK-Web Braintrust Tracing Issue

Minimal reproduction case for Braintrust tracing issue in ADK-Web where only the first agent invocation gets traced.

## Quick Start

```bash
# 1. Install dependencies
./setup.sh

# 2. Configure API keys
# Edit agents/weather_agent/.env and set:
#   GOOGLE_GENAI_API_KEY=your-google-ai-key
#   BRAINTRUST_API_KEY=your-braintrust-key

# 3. Verify configuration
./check_config.sh

# 4. Start server
./start_server.sh

# 5. Test via web UI
# Open http://localhost:3000/dev-ui/
# Select "weather_agent" and send multiple messages
```

## Get API Keys

- **Google AI**: https://aistudio.google.com/apikey
- **Braintrust**: https://www.braintrust.dev/app/settings

## The Issue

**Problem**: Only the first agent invocation gets traced to Braintrust. Subsequent invocations in the same session are not traced.

**Root Cause**: ADK-Web loads agent modules lazily during the first request (not at server startup). When `setup_adk()` runs mid-request, Braintrust's context variables become polluted, preventing subsequent traces from being created.

**Expected**: Each agent invocation should create a separate trace in Braintrust.

**Actual**: Only the first invocation per agent creates a trace.

**📄 See [BUG_REPORT.md](BUG_REPORT.md) for detailed analysis and proposed fixes.**

## Verification Steps

1. Start the server and open the web UI
2. Send 3 different messages to the agent:
   - "What's the weather in New York?"
   - "What about London?"
   - "What time is it?"
3. Check the Braintrust dashboard at https://www.braintrust.dev/
4. Look for project: `adk-web-tracing-test`
5. **Bug**: You'll see only 1 trace instead of 3

## Files

```
.
├── README.md                    # This file
├── BUG_REPORT.md               # Detailed bug analysis and proposed fixes
├── requirements.txt             # Python dependencies
├── setup.sh                     # Setup script
├── check_config.sh             # Verify API keys
├── start_server.sh             # Start ADK server
└── agents/
    └── weather_agent/
        ├── __init__.py         # Package marker
        ├── agent.py            # Minimal agent demonstrating the bug
        ├── .env                # API keys (add yours here)
        └── .env.example        # Example configuration
```

## Agent Capabilities

The agent uses Google Search to answer questions with current web information:
- **google_search**: Google Search integration for real-time web information (Gemini 2.0+ only)

Example queries:
- "What's the weather in New York?"
- "What's the latest news about AI?"
- "What time is it in Tokyo?"
- "Tell me about the Python programming language"

## Notes

- The agent uses `google_search` tool which requires Gemini 2.0+ models
- **Important**: `google_search` can only be used by itself (no other custom function tools allowed per ADK design)
- Braintrust tracing is configured via `setup_adk()` in agent.py
- Environment variables are loaded in agent.py before creating the agent
- The server uses standard ADK CLI: `adk web --port 3000 ./agents`
