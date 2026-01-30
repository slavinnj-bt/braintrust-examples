#!/usr/bin/env python3
"""
Basic example of Braintrust tracing with Langchain.
This example demonstrates automatic tracing of a multi-turn conversation
using Langchain, Tavily search tool, and Braintrust SDK with callback handlers.

Installation:
    pip install braintrust braintrust-langchain langchain-core langchain-openai langchain-community python-dotenv
"""

import os
from dotenv import load_dotenv
import braintrust
from braintrust import init_logger
from braintrust_langchain import BraintrustCallbackHandler, set_global_handler
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_community.tools.tavily_search import TavilySearchResults

# Load environment variables
load_dotenv()

# Initialize Braintrust logger for tracing
init_logger(
    project="SlavinScratchArea",
    api_key=os.environ.get("BRAINTRUST_API_KEY", ""),
)

# Create and set up global Braintrust callback handler
# This will automatically capture all Langchain activity
handler = BraintrustCallbackHandler()
set_global_handler(handler)

@braintrust.traced(metadata={"integration": "langchain"})
def run_conversation():
    """
    Run a multi-turn conversation with Tavily search that will generate multiple spans.
    This demonstrates:
    1. Initial greeting
    2. Search query using Tavily
    3. Follow-up question based on search results
    """

    # Initialize the LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=os.environ.get("OPENAI_API_KEY")
    )

    # Initialize Tavily search tool
    search = TavilySearchResults(
        max_results=3,
        api_key=os.environ.get("TAVILY_API_KEY")
    )

    # Bind the tool to the LLM
    llm_with_tools = llm.bind_tools([search])

    # Store conversation history
    messages = []

    # Turn 1: Greeting and introduction
    print("\n=== Turn 1: Greeting ===")
    messages.append(HumanMessage(content="Hello! I'm interested in learning about recent developments in AI."))
    response = llm.invoke(messages)
    messages.append(response)
    print(f"Assistant: {response.content}")

    # Turn 2: Ask a question that requires search
    print("\n=== Turn 2: Question requiring search ===")
    messages.append(HumanMessage(content="What are the latest breakthroughs in large language models in 2026?"))
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    # Check if the model wants to use tools
    if response.tool_calls:
        print(f"Assistant is using search tool...")
        for tool_call in response.tool_calls:
            # Execute the tool
            tool_result = search.invoke(tool_call["args"])
            print(f"Search results: {len(tool_result)} results found")

            # Add tool results to messages
            messages.append(ToolMessage(
                content=str(tool_result),
                tool_call_id=tool_call["id"]
            ))

        # Get final response with search results
        final_response = llm.invoke(messages)
        messages.append(final_response)
        print(f"Assistant: {final_response.content[:200]}...")
    else:
        print(f"Assistant: {response.content}")

    # Turn 3: Follow-up question
    print("\n=== Turn 3: Follow-up question ===")
    messages.append(HumanMessage(content="Can you summarize the key points from what you found?"))
    response = llm.invoke(messages)
    messages.append(response)
    print(f"Assistant: {response.content}")

    return messages

if __name__ == "__main__":
    print("Running Langchain with Braintrust tracing...")
    print("The global callback handler will capture all Langchain operations.")

    # Run the conversation - all calls will be logged to Braintrust automatically
    run_conversation()

    print("\nConversation complete!")
    print("Check Braintrust dashboard for the traces:")
    print("https://www.braintrust.dev/")
