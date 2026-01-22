"""Simple weather agent for testing ADK-Web tracing."""

import os
from pathlib import Path

# CRITICAL: Load environment variables FIRST, before any imports
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

# Verify API key is loaded (will print to server logs)
api_key = os.environ.get('GOOGLE_API_KEY')
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY not found in environment after loading .env file")

print(f"✓ Agent module: GOOGLE_API_KEY={'*' * 20}{api_key[-8:]}")
print(f"✓ Agent module: BRAINTRUST_API_KEY is {'configured' if os.environ.get('BRAINTRUST_API_KEY') else 'NOT configured'}")

# Setup Braintrust tracing before creating the agent
from braintrust_adk import setup_adk

setup_adk(project_name="adk-web-tracing-test")

from google.adk.agents import LlmAgent
from google.adk.tools import google_search

# Create the agent
# Note: ADK expects the variable to be named 'root_agent'
# The LlmAgent will automatically use GOOGLE_API_KEY from the environment
# google_search can only be used by itself (no other custom tools allowed)
root_agent = LlmAgent(
    name="search_assistant",
    tools=[google_search],
    model="gemini-2.0-flash-exp",
    instruction="You are a helpful assistant that can search the web for current information to answer questions.",
)
