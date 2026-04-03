"""
Earnings Call PDF Agent
=======================
A multi-turn agent that lets users request earnings-call PDFs for various
companies and ask follow-up questions about them.

Architecture:
- OpenAI Agents SDK drives the conversation loop (multi-turn)
- `fetch_and_analyze_earnings` tool downloads a PDF, logs it as a Braintrust
  Attachment, then calls GPT-4o directly with the PDF as a base64 file part
- braintrust.wrap_openai() instruments every model call automatically
- Each user turn becomes a new traced span inside the same top-level session

Run:
    python earnings_agent.py
"""

import asyncio
import base64
import os
import pathlib
import sys

from dotenv import load_dotenv

import openai as openai_sdk
import braintrust
from braintrust import Attachment, init_logger, traced, current_span

from agents import Agent, Runner, function_tool, set_default_openai_client
from agents.tracing import set_trace_processors  # disable built-in OTEL noise

load_dotenv()

# ── Braintrust setup ──────────────────────────────────────────────────────────

logger = init_logger(
    project=os.environ.get("BRAINTRUST_PROJECT", "earnings-pdf-agent"),
    api_key=os.environ.get("BRAINTRUST_API_KEY"),
)

# Wrap the async OpenAI client so every chat completion is traced in Braintrust
_base_client = openai_sdk.AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
)
_oai = braintrust.wrap_openai(_base_client)

# Tell the OpenAI Agents SDK to use our wrapped client for its own calls
set_default_openai_client(_oai)

# Silence the Agents SDK's own OpenTelemetry exporter – Braintrust handles it
set_trace_processors([])

# ── PDF catalog ───────────────────────────────────────────────────────────────
_PDFS_DIR = pathlib.Path(__file__).parent / "pdfs"

EARNINGS_PDFS: dict[str, dict] = {
    "meta": {
        "file": _PDFS_DIR / "meta_earnings_Q4_2024.pdf",
        "company": "Meta Platforms",
        "quarter": "Q4 2024",
    },
    "jpmorgan": {
        "file": _PDFS_DIR / "jpmorgan_earnings_Q4_2024.pdf",
        "company": "JPMorgan Chase",
        "quarter": "Q4 2024",
    },
    "att": {
        "file": _PDFS_DIR / "att_earnings_Q4_2024.pdf",
        "company": "AT&T",
        "quarter": "Q4 2024",
    },
    "qualcomm": {
        "file": _PDFS_DIR / "qualcomm_earnings_Q1_FY2025.pdf",
        "company": "Qualcomm",
        "quarter": "Q1 FY2025",
    },
    "homeDepot": {
        "file": _PDFS_DIR / "homeDepot_earnings_Q4_2024.pdf",
        "company": "Home Depot",
        "quarter": "Q4 2024",
    },
    "keybank": {
        "file": _PDFS_DIR / "keybank_earnings.pdf",
        "company": "KeyBank",
        "quarter": "Q4 2024",
    },
}

COMPANY_ALIASES: dict[str, str] = {
    # normalise user-facing names → catalog keys
    "meta": "meta",
    "facebook": "meta",
    "meta platforms": "meta",
    "jpmorgan": "jpmorgan",
    "jp morgan": "jpmorgan",
    "jpmorgan chase": "jpmorgan",
    "jp morgan chase": "jpmorgan",
    "att": "att",
    "at&t": "att",
    "qualcomm": "qualcomm",
    "home depot": "homeDepot",
    "homedepot": "homeDepot",
    "keybank": "keybank",
    "key bank": "keybank",
}


def _resolve_company(name: str) -> str | None:
    return COMPANY_ALIASES.get(name.lower().strip())


# ── Tool: fetch & analyze a PDF ───────────────────────────────────────────────

@function_tool
@traced  # creates a child span in Braintrust
async def fetch_and_analyze_earnings(company_name: str, question: str) -> str:
    """
    Load a local earnings-call PDF for *company_name*, log it as a Braintrust
    Attachment, then ask GPT-4o *question* about the document.

    Args:
        company_name: One of: meta, jpmorgan, att, qualcomm, homeDepot
        question: The specific question to answer from the document
    """
    key = _resolve_company(company_name)
    if key is None:
        available = ", ".join(EARNINGS_PDFS)
        return (
            f"Unknown company '{company_name}'. "
            f"Available options: {available}"
        )

    entry = EARNINGS_PDFS[key]
    pdf_path: pathlib.Path = entry["file"]
    filename = pdf_path.name

    # ── Read local PDF ────────────────────────────────────────────────────────
    pdf_bytes = pdf_path.read_bytes()

    # ── Log Attachment to Braintrust ──────────────────────────────────────────
    # For PDFs > 20 MB use JSONAttachment; typical earnings slides are well under.
    attachment = Attachment(
        data=pdf_bytes,
        filename=filename,
        content_type="application/pdf",
    )
    span = current_span()
    if span:
        span.log(
            input={
                "company": entry["company"],
                "quarter": entry["quarter"],
                "question": question,
                "pdf": attachment,
            }
        )

    # ── Send PDF to GPT-4o and return the analysis ────────────────────────────
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    response = await _oai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial analyst. Answer questions about earnings calls "
                    "clearly and concisely. Focus on: revenue & EPS vs. expectations, "
                    "key business highlights or challenges, and forward guidance."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"This is the {entry['quarter']} earnings document for "
                            f"{entry['company']}.\n\n{question}"
                        ),
                    },
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:application/pdf;base64,{pdf_b64}",
                        },
                    },
                ],
            },
        ],
    )

    answer = response.choices[0].message.content or "(no response)"

    if span:
        span.log(output={"analysis": answer})

    return f"[{entry['company']} – {entry['quarter']}]\n\n{answer}"


# ── Agent definition ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an Earnings Call Analyst. You help users understand company performance
by retrieving and analysing earnings-call documents.

Available companies: Meta, JPMorgan, AT&T, Qualcomm, Home Depot, KeyBank

When a user asks about a company's earnings:
1. Call `fetch_and_analyze_earnings` with the company name and a specific
   question derived from the user's request.
2. Present the key findings conversationally.
3. Invite follow-up questions about the same or a different company.

Keep answers concise. Always cite the quarter and company clearly.
"""

earnings_agent = Agent(
    name="EarningsCallAnalyst",
    instructions=SYSTEM_PROMPT,
    tools=[fetch_and_analyze_earnings],
    model="gpt-4o",
)


# ── Multi-turn conversation loop ──────────────────────────────────────────────

async def chat() -> None:
    """Run an interactive multi-turn session, logging everything to Braintrust."""
    print("Earnings Call Agent  (type 'quit' to exit)")
    print("Available companies: Meta, JPMorgan, AT&T, Qualcomm, Home Depot, KeyBank\n")

    history: list[dict] = []

    # The entire session is wrapped in a single top-level Braintrust span so
    # all turns appear together in the trace viewer.
    with logger.start_span(name="earnings-agent-session") as session_span:
        turn = 0
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                print("Goodbye!")
                break

            turn += 1
            history.append({"role": "user", "content": user_input})

            # Each turn gets its own child span
            with session_span.start_span(name=f"turn-{turn}") as turn_span:
                turn_span.log(input={"user": user_input})

                result = await Runner.run(
                    earnings_agent,
                    input=history,
                )

                assistant_reply = result.final_output
                history.append({"role": "assistant", "content": assistant_reply})

                turn_span.log(output={"assistant": assistant_reply})

            print(f"\nAssistant: {assistant_reply}\n")


if __name__ == "__main__":
    asyncio.run(chat())
