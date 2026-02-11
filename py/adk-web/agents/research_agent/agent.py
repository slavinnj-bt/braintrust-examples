"""
Research Agent with Braintrust Tracing

⚠️ KNOWN ISSUE: Session-level tracing is not working properly with braintrust-adk.
Currently, only the first turn gets traced, or each turn creates a separate trace.

Expected behavior:
  Session (parent trace)
  ├── Turn 1 (child span)
  ├── Turn 2 (child span)
  └── Turn 3 (child span)

Actual behavior:
  - Only Turn 1 trace appears
  OR
  - Separate traces: Turn 1, Turn 2, Turn 3 (not grouped)

For details and workarounds, see: ../../SESSION_TRACING_ISSUE.md

This implementation uses setup_adk() which should provide session-level tracing,
but due to limitations in the current braintrust-adk integration with ADK Web,
it doesn't work as expected.

Key implementation details:
1. setup_adk() is called once at module load time (should work, but doesn't)
2. Environment variables are loaded before any imports
3. The agent uses google_search for real-time web research
4. ADK's web framework should handle session management (but tracing context is lost)
"""

import os
from pathlib import Path

# STEP 1: Load environment variables FIRST, before any imports that use them
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    import dotenv

    # Load into a dict first
    env_vars = dotenv.dotenv_values(env_file)

    # Explicitly set in os.environ
    for key, value in env_vars.items():
        if value:  # Only set if not empty
            os.environ[key] = value

    # CRITICAL FIX: google.genai.Client looks for GOOGLE_API_KEY, not GOOGLE_GENAI_API_KEY
    # Set both to ensure compatibility
    if 'GOOGLE_GENAI_API_KEY' in os.environ:
        os.environ['GOOGLE_API_KEY'] = os.environ['GOOGLE_GENAI_API_KEY']

    print(f"✓ Loaded {len(env_vars)} variables from .env")
else:
    print(f"⚠ No .env file found at {env_file}")

# Verify API keys are loaded
api_key = os.environ.get('GOOGLE_API_KEY')
braintrust_key = os.environ.get('BRAINTRUST_API_KEY')

if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY not found in environment. "
        "Please set GOOGLE_GENAI_API_KEY in your .env file."
    )

if not braintrust_key:
    print("⚠ BRAINTRUST_API_KEY not configured - tracing will not be enabled")

print(f"✓ GOOGLE_API_KEY: {'*' * 20}{api_key[-8:]}")
print(f"✓ BRAINTRUST_API_KEY: {'configured' if braintrust_key else 'NOT configured'}")

# STEP 2: Braintrust tracing is now handled by the custom server (main.py)
# We do NOT call setup_adk() here because:
# - braintrust-adk's session tracing doesn't work properly
# - main.py's custom middleware handles session-level tracing instead
# - Calling setup_adk() here would conflict with the middleware

# Note: If you see "only first turn traced", make sure you're running
# the custom server (./start_server.sh) not the old adk web command

print("✓ Braintrust tracing will be handled by custom server middleware")

# STEP 3: Import ADK components and create the agent
from google.adk.agents import LlmAgent
from google.adk.tools import google_search

# Create the research agent
# Note: ADK expects the variable to be named 'root_agent'
# The google_search tool provides real-time web search capabilities
# Note: google_search can only be used by itself (no other custom tools per ADK design)
root_agent = LlmAgent(
    name="research_assistant",
    tools=[google_search],
    model="gemini-2.0-flash",  # Requires Gemini 2.0+ for google_search
    instruction="""You are a helpful research assistant that can search the web for current information.

When a user asks a question:
1. Use the google_search tool to find relevant, up-to-date information
2. Synthesize the search results into a clear, comprehensive answer
3. Cite your sources when providing information
4. If the search doesn't yield good results, explain what you found and suggest alternative queries

Always prioritize accuracy and recency of information.""",
)

print(f"✓ Research agent '{root_agent.name}' created successfully")
print("✓ Agent ready (tracing handled by main.py middleware)")
