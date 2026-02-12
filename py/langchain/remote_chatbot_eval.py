"""
Generic Remote Eval for Chatbots

This remote eval allows you to evaluate any chatbot with configurable:
- AI Provider (OpenAI, Anthropic, Mistral)
- Model selection
- System prompt

Note: Does not pass temperature or max_tokens (not supported by GPT 5+)

Run with: braintrust eval remote_chatbot_eval.py --dev
"""

from braintrust import Eval, init_dataset
from autoevals import Factuality
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

load_dotenv()

# Load default system prompt from file
DEFAULT_SYSTEM_PROMPT = ""
system_prompt_file = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
if os.path.exists(system_prompt_file):
    with open(system_prompt_file, "r") as f:
        DEFAULT_SYSTEM_PROMPT = f.read()

# If no file exists, use a simple default
if not DEFAULT_SYSTEM_PROMPT:
    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class ProviderParam(BaseModel):
    """AI Provider selection"""
    provider: str = Field(
        default="openai",
        description="AI provider to use (openai, anthropic, or mistral)"
    )


class ModelParam(BaseModel):
    """Model selection"""
    model: str = Field(
        default="",
        description="Model name (e.g., gpt-4o-mini, claude-sonnet-4-5-20250929). Leave empty for provider default."
    )


class SystemPromptParam(BaseModel):
    """System prompt configuration"""
    system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        description="The system prompt for the chatbot"
    )


def get_model_default(provider: str) -> str:
    """Get default model for provider"""
    defaults = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-5-20250929",
        "mistral": "mistral-small-latest",
    }
    return defaults.get(provider.lower(), "gpt-4o-mini")


def call_openai(messages, model):
    """Call OpenAI API"""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    return response.choices[0].message.content


def call_anthropic(messages, model):
    """Call Anthropic API"""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Anthropic has a different message format - extract system from messages
    system_msg = None
    user_messages = []

    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            user_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    response = client.messages.create(
        model=model,
        max_tokens=4096,  # Anthropic requires max_tokens
        system=system_msg if system_msg else "",
        messages=user_messages
    )

    return response.content[0].text


def call_mistral(messages, model):
    """Call Mistral API via LangChain"""
    from langchain_mistralai import ChatMistralAI
    from langchain_core.messages import SystemMessage, HumanMessage

    # Initialize Mistral client
    llm = ChatMistralAI(
        model=model,
        api_key=os.environ.get("MISTRAL_API_KEY")
    )

    # Convert messages to LangChain format
    lc_messages = []
    for msg in messages:
        if msg["role"] == "system":
            lc_messages.append(SystemMessage(content=msg["content"]))
        elif msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))

    # Invoke the model
    response = llm.invoke(lc_messages)

    return response.content


def task_wrapper(input, hooks):
    """
    Wrapper function that calls the chatbot with configurable parameters.

    Args:
        input: The user input/question to send to the chatbot
        hooks: Braintrust hooks object containing metadata and parameters

    Returns:
        str: The chatbot's response
    """
    # Get parameters from hooks
    params = hooks.parameters if hasattr(hooks, 'parameters') else {}

    # Extract parameter values from Pydantic models
    provider = params.get("provider").provider if "provider" in params else "openai"
    model = params.get("model").model if "model" in params else ""
    system_prompt = params.get("system_prompt").system_prompt if "system_prompt" in params else DEFAULT_SYSTEM_PROMPT

    # Allow environment variable override
    provider = os.environ.get("AI_PROVIDER", provider).lower()

    # Use provider default if no model specified
    if not model:
        model = os.environ.get("AI_MODEL", get_model_default(provider))

    # Build messages array
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input}
    ]

    # Call appropriate provider
    if provider == "anthropic":
        result = call_anthropic(messages, model)
    elif provider == "openai":
        result = call_openai(messages, model)
    elif provider == "mistral":
        result = call_mistral(messages, model)
    else:
        raise ValueError(f"Unsupported provider: {provider}. Use 'openai', 'anthropic', or 'mistral'")

    return result


# Define the remote eval
Eval(
    "Generic Chatbot",
    data=init_dataset(
        os.environ.get("BRAINTRUST_PARENT"),
        {"dataset": "ChatbotQuestions"}  # Update this to point to your dataset
    ),
    task=task_wrapper,
    scores=[Factuality],  # Add more scorers as needed
    parameters={
        "provider": ProviderParam,
        "model": ModelParam,
        "system_prompt": SystemPromptParam,
    }
)
