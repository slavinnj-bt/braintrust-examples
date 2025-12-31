from braintrust import Eval, init_dataset
from autoevals import Factuality, Possible, LLMClassifier # LLMClassifier lets us build a custome eval prompt
from pydantic import BaseModel, Field
import sys
from dotenv import load_dotenv
import os
import subprocess
import json

load_dotenv()

# Define a prompt prefix for a LLMClassifier (returns just one answer)
prompt_prefix = """
You are an expert evaluator that strives to find the most concise wording for a response.

I'm going to provide you with a question and an output and you will rate its conciseness. The output should not compromise the relevancy of the answer to the original question.

Question: {{input}}

Answer: {{output}}

You will choose from the following scores:
A - The response is brief and concise but is completely understandable, and answers the question in its entirety.
B - The response is brief and concise, but leaves out important details that are relevant to the question.
C - The response fails to answer the question, is very verbose, and/or excludes relevant details.
"""

# Define the scoring mechanism
# 1 if the generated answer is better than the expected answer
# 0 otherwise
output_scores = {"A": 1, "B": 0.5, "C": 0.0}

concisenessEvaluator = LLMClassifier(
    name="WeatherAppConciseness",
    prompt_template=prompt_prefix,
    choice_scores=output_scores,
    use_cot=True,
)

DEFAULT_SYSTEM_PROMPT = """
        You are a weather agent that gathers the current forecast for a location using the `Weather` tool. 
  You will only return the current weather. Do not return future-looking forecasts. You strive for conciseness and will only return the
  temperature, wind speed, and current time. No need to elaborate or editorialize about the conditions.
  """

class ModelParam(BaseModel):
    model: str = Field(
        default="gpt-4o-mini",
        description="model to use"
    )

class SystemPromptParam(BaseModel):
    system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        description="the model's system prompt"
    )

def task_wrapper(input, hooks):
    """
    Wrapper function that calls the run_agent function with parameters.

    Args:
        input: the input to run the eval with (in this case, location to get weather for)
        hooks: Braintrust hooks object containing metadata and parameters

    Returns:
        str: The agent's output
    """
    location = input

    # Get parameters directly from hooks object
    # hooks.parameters contains Pydantic model instances, access fields directly
    params = hooks.parameters if hasattr(hooks, 'parameters') else {}

    # Extract param values from Pydantic models
    model = params.get("model").model if "model" in params and params.get("model") else "gpt-4o-mini"
    system_prompt = params.get("system_prompt").system_prompt if "system_prompt" in params and params.get("system_prompt") else DEFAULT_SYSTEM_PROMPT

    ruby_exc = 'ruby'
    cwd = os.getcwd()
    if "ruby/evals/remote_evals" not in cwd:
        sys.exit("CD to /ruby/evals/remote_evals before running remote eval")

    # add system_prompt param
    # Pass environment variables to Ruby subprocess
    env = os.environ.copy()
    process = subprocess.run(
        [ruby_exc, 'agent.rb', model, location, system_prompt],
        capture_output=True, # Capture stdout and stderr, we'll use stdout for our eval later
        text=True,
        env=env  # Pass environment variables including API keys
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

    # this returns the output of the Ruby agent to the Eval()
    return result 

# This kicks off our Remote Eval
Eval(
    "Weather Agent",
    data=init_dataset(os.environ.get("BRAINTRUST_PARENT"), {"dataset": "WeatherLocations"}), # dataset or data struct to get inputs from
    task=task_wrapper, # the task you will evaluate, this should call the code which runs your agent
    scores=[Factuality, Possible, concisenessEvaluator], # the scoring functions (or AutoEvals built-in scorers) to use
    parameters={ 
        "model": ModelParam,
        "system_prompt": SystemPromptParam
    }
)