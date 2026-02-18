"""
customer_service_chatbot.py
============================
Simulates a customer-service chatbot that logs every conversation to
Braintrust as a span. Each span is tagged "unscored" so a separate
scoring process (score_traces.py) can find and evaluate it later—hours
or even a day after the conversations happen.

Workflow
--------
1. Run this script to simulate a batch of customer interactions.
2. Later, run score_traces.py to query unscored spans and add NPS metrics.

Requirements
------------
    pip install braintrust braintrust-langchain langchain-anthropic

Environment variables
---------------------
    BRAINTRUST_API_KEY   – your Braintrust API key
    BRAINTRUST_PROJECT   – Braintrust project name to log to
    ANTHROPIC_API_KEY    – Anthropic API key
"""

import asyncio
import os

from braintrust import flush, init_logger
from braintrust_langchain import BraintrustCallbackHandler
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_NAME = os.environ["BRAINTRUST_PROJECT"]
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are a helpful customer service agent for an e-commerce company called ShopFast.
Be concise, empathetic, and solution-focused. Keep responses to 2-3 sentences."""

# Realistic mix of conversations: some easy wins, some frustrated customers.
CONVERSATIONS = [
    {
        "customer_id": "cust_001",
        "ticket_id": "ticket_101",
        "topic": "billing",
        "channel": "chat",
        "message": "Hi, I think I was charged twice for my order #4521. Can you look into that?",
    },
    {
        "customer_id": "cust_002",
        "ticket_id": "ticket_102",
        "topic": "shipping",
        "channel": "chat",
        "message": "My package has been stuck at 'in transit' for 12 days. Where is it?",
    },
    {
        "customer_id": "cust_003",
        "ticket_id": "ticket_103",
        "topic": "returns",
        "channel": "chat",
        "message": "I got the wrong item—ordered a blue shirt but received a red one. How do I exchange it?",
    },
    {
        "customer_id": "cust_004",
        "ticket_id": "ticket_104",
        "topic": "account",
        "channel": "chat",
        "message": "I cannot log in to my account. It says 'invalid credentials' even after resetting my password.",
    },
    {
        "customer_id": "cust_005",
        "ticket_id": "ticket_105",
        "topic": "billing",
        "channel": "chat",
        "message": "This is outrageous. I cancelled my subscription three months ago and you're STILL charging me. I want a full refund immediately!",
    },
    # --- Detractor scenarios ---
    {
        "customer_id": "cust_006",
        "ticket_id": "ticket_106",
        "topic": "refund",
        "channel": "chat",
        "message": "I requested a refund 3 weeks ago and still haven't received it. Every time I call I get told to wait another 5-7 business days. This is unacceptable.",
    },
    {
        "customer_id": "cust_007",
        "ticket_id": "ticket_107",
        "topic": "product_defect",
        "channel": "chat",
        "message": "The blender I bought caught FIRE after 2 uses. My countertop is damaged. I need to know what you're going to do about this right now.",
    },
    {
        "customer_id": "cust_008",
        "ticket_id": "ticket_108",
        "topic": "billing",
        "channel": "chat",
        "message": "I've been a customer for 6 years and you just raised prices 40% with zero notice. I'm cancelling everything and leaving a review on every platform I can find.",
    },
    {
        "customer_id": "cust_009",
        "ticket_id": "ticket_109",
        "topic": "privacy",
        "channel": "chat",
        "message": "Why am I getting spam calls from third parties? I never gave consent to share my data. I want to know exactly who you sold my information to.",
    },
    {
        "customer_id": "cust_010",
        "ticket_id": "ticket_110",
        "topic": "shipping",
        "channel": "chat",
        "message": "Your delivery driver left my $400 order on the street in the rain. It's completely ruined. I've tried the chat bot three times and keep getting disconnected.",
    },
]


# ---------------------------------------------------------------------------
# Run one conversation and log it to Braintrust
# ---------------------------------------------------------------------------

async def handle_conversation(logger, llm: ChatAnthropic, convo: dict) -> str:
    """
    Invoke the LLM for a single customer message and log the full
    conversation as a Braintrust span.

    Tags the span "unscored" so score_traces.py can discover and evaluate
    it later without any knowledge of the span ID at call time.
    """
    handler = BraintrustCallbackHandler()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=convo["message"]),
    ]

    with logger.start_span(name=f"conversation:{convo['ticket_id']}") as span:
        result = await llm.ainvoke(messages, config={"callbacks": [handler]})

        span.log(
            input={"message": convo["message"]},
            output=result.content,
            metadata={
                "customer_id": convo["customer_id"],
                "ticket_id": convo["ticket_id"],
                "topic": convo["topic"],
                "channel": convo["channel"],
                "model": MODEL,
            },
            tags=["customer_service", "unscored"],
        )

        span_id = span.id

    print(f"[{convo['ticket_id']}] span_id={span_id}")
    print(f"  Customer : {convo['message'][:72]}...")
    print(f"  Agent    : {result.content[:80]}...\n")
    return span_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger = init_logger(project=PROJECT_NAME)
    llm = ChatAnthropic(model=MODEL)

    print(f"Logging {len(CONVERSATIONS)} customer conversations to '{PROJECT_NAME}'...\n")

    span_ids = []
    for convo in CONVERSATIONS:
        span_id = await handle_conversation(logger, llm, convo)
        span_ids.append(span_id)

    flush()
    print(f"All {len(span_ids)} conversations logged and flushed.")
    print("Run score_traces.py (now or later) to add NPS scores.")


if __name__ == "__main__":
    asyncio.run(main())
