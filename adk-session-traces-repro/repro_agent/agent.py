import os
from pathlib import Path

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    import dotenv

    env_vars = dotenv.dotenv_values(env_file)
    for key, value in env_vars.items():
        if value:
            os.environ[key] = value

from braintrust_adk import setup_adk

setup_adk(project_name="adk-multi-turn-repro")

from google.adk.agents import LlmAgent

# Each message sent via `adk web` is a separate runner.run() call,
# reproducing the bug: each turn creates its own root-level Braintrust log entry
# instead of being grouped under a single session.
root_agent = LlmAgent(
    name="assistant",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant. Keep responses very brief.",
)
