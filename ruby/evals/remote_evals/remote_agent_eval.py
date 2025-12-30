from braintrust import Eval, init_dataset
from autoevals import Factuality, Possible
from pydantic import BaseModel, Field
import sys
from dotenv import load_dotenv
import os
import subprocess
import json


load_dotenv()

# Add parent directory to path to import from main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class ModelParam(BaseModel):
    model: str = Field(
        default="gpt-4o-mini",
        description="model to use"
    )


def task_wrapper(input, hooks):
    """
    Wrapper function that calls the run_agent function with parameters.

    Args:
        input: The test case input containing the investment thesis
        hooks: Braintrust hooks object containing metadata and parameters

    Returns:
        str: The agent's output
    """
    location = input

    # Get parameters directly from hooks object
    # hooks.parameters contains Pydantic model instances, access fields directly
    params = hooks.parameters if hasattr(hooks, 'parameters') else {}

    # Extract values from Pydantic models
    model = params.get("model").model if "model" in params and params.get("model") else "gpt-4o-mini"

    ruby_exc = 'ruby'
    cwd = os.getcwd()
    if "ruby/evals/remote_evals" not in cwd:
        sys.exit("CD to /ruby/evals/remote_evals before running remote eval")

    process = subprocess.run(
        [ruby_exc, 'agent.rb', model, location],
        capture_output=True, # Capture stdout and stderr
        text=True
    )

    # Check if the subprocess failed
    if process.returncode != 0:
        print("Ruby script error:")
        print(process.stderr)
        raise RuntimeError(f"Ruby script failed with return code {process.returncode}: {process.stderr}")

    # Parse JSON with error handling
    try:
        output_data = json.loads(process.stdout)
    except json.JSONDecodeError as e:
        print(process.stderr)
        raise ValueError(f"Failed to parse Ruby script output as JSON: {e}\nOutput was: {process.stdout}")

    # Validate that result key exists
    if 'result' not in output_data:
        raise KeyError(f"'result' key not found in Ruby script output. Got keys: {list(output_data.keys())}")

    result = output_data['result']

    print(f"The result from Ruby is: {result}")

    return result


Eval(
    "Weather Agent",
    data=init_dataset(os.environ.get("BRAINTRUST_PARENT"), {"dataset": "WeatherLocations"}),
    task=task_wrapper,
    scores=[Factuality, Possible],
    parameters={
        "model": ModelParam,
    }
)