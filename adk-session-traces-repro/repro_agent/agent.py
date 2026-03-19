import os
from pathlib import Path

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    import dotenv

    env_vars = dotenv.dotenv_values(env_file)
    for key, value in env_vars.items():
        if value:
            os.environ[key] = value

from braintrust.logger import init_logger
from braintrust_adk import setup_adk
from wrapt import wrap_function_wrapper

PROJECT_NAME = "adk-multi-turn-repro"

setup_adk(project_name=PROJECT_NAME)
logger = init_logger(project=PROJECT_NAME)

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.tools import google_search


def _make_session_span(session_id):
    # Create (or reuse) a session-level root span using session_id as the
    # span ID. Each turn re-creates a span with the same span_id; Braintrust
    # merges all events under a single root span in the UI.
    return logger.start_span(
        name=f"chat-session [{session_id}]",
        span_id=session_id,
        root_span_id=session_id,
    )


def _session_run_wrapper(wrapped, _instance, args, kwargs):
    session_id = kwargs.get("session_id")

    if session_id:
        session_span = _make_session_span(session_id)
        session_span.__enter__()
        try:
            yield from wrapped(*args, **kwargs)
        finally:
            session_span.__exit__(None, None, None)
    else:
        yield from wrapped(*args, **kwargs)


async def _session_run_async_wrapper(wrapped, _instance, args, kwargs):
    session_id = kwargs.get("session_id")

    if session_id:
        session_span = _make_session_span(session_id)
        session_span.__enter__()
        try:
            async for event in wrapped(*args, **kwargs):
                yield event
        finally:
            session_span.__exit__(None, None, None)
    else:
        async for event in wrapped(*args, **kwargs):
            yield event


wrap_function_wrapper(Runner, "run", _session_run_wrapper)
wrap_function_wrapper(Runner, "run_async", _session_run_async_wrapper)


_WEATHER_DATA = {
    "new york": {"condition": "Partly cloudy", "temp_f": 62},
    "london": {"condition": "Rainy", "temp_f": 55},
    "tokyo": {"condition": "Sunny", "temp_f": 75},
    "sydney": {"condition": "Clear", "temp_f": 81},
    "paris": {"condition": "Overcast", "temp_f": 58},
}


def get_weather(location: str) -> dict:
    """Returns the current weather for a given location.

    Args:
        location: The city or location to get weather for.

    Returns:
        A dict with condition and temperature, or an error if unknown.
    """
    data = _WEATHER_DATA.get(location.lower().strip())
    if data:
        return {"location": location, **data}
    return {"location": location, "condition": "Unknown", "temp_f": None}


root_agent = LlmAgent(
    name="assistant",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant. Keep responses very brief.",
    tools=[get_weather],
)
