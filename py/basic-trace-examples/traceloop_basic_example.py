#!/usr/bin/env python3
"""
Basic example of Braintrust tracing with Traceloop.
This example demonstrates automatic tracing of a multi-turn conversation
with Tavily search using Traceloop and Braintrust SDK via OpenTelemetry.

Installation:
    pip install "braintrust[otel]" traceloop-sdk openai requests python-dotenv

Setup:
1. Set environment variables in your .env file:
   TRACELOOP_BASE_URL=https://api.braintrust.dev/otel
   TRACELOOP_HEADERS="Authorization=Bearer%20<Your API Key>, x-bt-parent=project_id:<Your Project ID>"
   OPENAI_API_KEY=<Your OpenAI API Key>
   TAVILY_API_KEY=<Your Tavily API Key>

   Note: The space between "Bearer" and your key must be encoded as %20
"""

import os
from dotenv import load_dotenv
from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow
from openai import OpenAI
import requests

# Load environment variables
load_dotenv()

# Initialize Traceloop - traces will automatically route to Braintrust
# via the TRACELOOP_BASE_URL and TRACELOOP_HEADERS environment variables
Traceloop.init(disable_batch=True)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@workflow(name="tavily_search")
def tavily_search(query: str) -> list:
    """
    Search using Tavily API.
    This will create a span in Braintrust via Traceloop's OpenTelemetry integration.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    url = "https://api.tavily.com/search"

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": 3
    }

    response = requests.post(url, json=payload)
    results = response.json()
    return results.get("results", [])

@workflow(name="run_conversation")
def run_conversation():
    """
    Run a multi-turn conversation with Tavily search that will generate multiple spans.
    This demonstrates:
    1. Initial greeting
    2. Search query using Tavily
    3. Follow-up question based on search results
    """

    # Add metadata to the workflow span
    from opentelemetry import trace
    span = trace.get_current_span()
    if span:
        span.set_attribute("integration", "traceloop")

    # Store conversation history
    messages = []

    # Turn 1: Greeting and introduction
    print("\n=== Turn 1: Greeting ===")
    messages.append({
        "role": "user",
        "content": "Hello! I'm interested in learning about recent developments in AI."
    })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7
    )

    assistant_message = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_message})
    print(f"Assistant: {assistant_message}")

    # Turn 2: Ask a question that requires search
    print("\n=== Turn 2: Question requiring search ===")
    user_query = "What are the latest breakthroughs in large language models in 2026?"
    messages.append({"role": "user", "content": user_query})

    # Perform Tavily search
    print("Searching with Tavily...")
    search_results = tavily_search(user_query)
    print(f"Search results: {len(search_results)} results found")

    # Format search results for the LLM
    search_context = "\n\n".join([
        f"Source: {result.get('title', 'Unknown')}\n{result.get('content', '')}"
        for result in search_results
    ])

    # Add search results to context
    messages.append({
        "role": "system",
        "content": f"Here are some search results to help answer the question:\n\n{search_context}"
    })

    # Get response with search results
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7
    )

    assistant_message = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_message})
    print(f"Assistant: {assistant_message[:200]}...")

    # Turn 3: Follow-up question
    print("\n=== Turn 3: Follow-up question ===")
    messages.append({
        "role": "user",
        "content": "Can you summarize the key points from what you found?"
    })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7
    )

    assistant_message = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_message})
    print(f"Assistant: {assistant_message}")

    return messages

if __name__ == "__main__":
    print("Running Traceloop with Braintrust tracing...")
    print("This will automatically capture the conversation via OpenTelemetry.")

    # Run the conversation
    run_conversation()

    print("\nConversation complete!")
    print("Check Braintrust dashboard for the trace:")
    print("https://www.braintrust.dev/")