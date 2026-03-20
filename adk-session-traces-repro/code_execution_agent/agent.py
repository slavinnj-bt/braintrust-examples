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
from google.adk.code_executors import BuiltInCodeExecutor


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
        # Use __enter__/__exit__ explicitly instead of `with` — Python doesn't
        # allow `with` to span a `yield` boundary in a generator.
        session_span.__enter__()
        try:
            # Re-yield all ADK events from the original generator to the caller.
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


root_agent = LlmAgent(
    name="assistant",
    model="gemini-2.5-flash",
    code_executor=BuiltInCodeExecutor(),
    instruction="You are a mathematical tutor. You use code to perform complex calculations. Always explain your work.",
)
