"""
Earnings Call PDF Eval
======================
Evaluates how well GPT-4o answers questions about earnings-call PDFs using
Braintrust's Eval framework.

Each dataset row contains:
- input.pdf      : Braintrust Attachment (the PDF document)
- input.question : the question to answer
- expected       : the ground-truth answer (used by the LLM scorer)

Two task modes:
  direct  (default) – calls GPT-4o with the PDF bytes directly; fast baseline
  agent             – routes each case through the full EarningsCallAnalyst
                      agent (tool call → PDF load → GPT-4o); tests the whole
                      pipeline including multi-turn tool use

Usage:
    python eval.py                  # direct eval (GPT-4o baseline)
    python eval.py --agent          # agent eval (full pipeline)
    python eval.py --upload-dataset # upload dataset only, skip eval
"""

import argparse
import asyncio
import base64
import os
import pathlib

from dotenv import load_dotenv

import openai as openai_sdk
import braintrust
from braintrust import Attachment, EvalCase, ReadonlyAttachment
from autoevals import Factuality

_ATTACHMENT_TYPES = (Attachment, ReadonlyAttachment)


def PDFFactuality(output, expected=None, input=None, **kwargs):
    """Factuality scorer that strips PDF attachments before scoring."""
    if isinstance(input, dict):
        input = {k: v for k, v in input.items() if not isinstance(v, _ATTACHMENT_TYPES)}
    return Factuality(base_url="https://api.openai.com/v1")(output=output, expected=expected, input=input, **kwargs)

from agents import Runner
from earnings_agent import earnings_agent

load_dotenv()

# ── OpenAI client (Braintrust-wrapped for tracing) ────────────────────────────
_oai = braintrust.wrap_openai(
    openai_sdk.AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url="https://api.openai.com/v1",
    )
)

PROJECT = os.environ.get("BRAINTRUST_PROJECT", "earnings-pdf-agent")

# ── Earnings PDF catalog (same as earnings_agent.py) ─────────────────────────
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

# ── Eval dataset ──────────────────────────────────────────────────────────────
# Each case: which company PDF + a question + a reference answer.
# Reference answers are intentionally concise; Factuality scorer will check
# that the model answer is consistent with (not necessarily identical to) them.
EVAL_CASES = [
    {
        "company_key": "meta",
        "question": "What was Meta's revenue in Q4 2024 and how did it compare to analyst expectations?",
        "expected": "Meta reported Q4 2024 revenue of approximately $48.4 billion, above analyst consensus.",
    },
    {
        "company_key": "meta",
        "question": "What forward guidance did Meta provide for the next quarter?",
        "expected": "Meta guided Q1 2025 revenue in the range of $39.5 to $41.8 billion.",
    },
    {
        "company_key": "jpmorgan",
        "question": "What were JPMorgan's key financial highlights for Q4 2024?",
        "expected": "JPMorgan reported strong net income with healthy net interest income driven by higher rates.",
    },
    {
        "company_key": "att",
        "question": "What did AT&T report for postpaid phone net adds in Q4 2024?",
        "expected": "AT&T reported solid postpaid phone net subscriber additions in Q4 2024.",
    },
    {
        "company_key": "qualcomm",
        "question": "How did Qualcomm's Automotive segment perform in Q1 FY2025?",
        "expected": "Qualcomm's Automotive segment showed strong year-over-year revenue growth.",
    },
    {
        "company_key": "homeDepot",
        "question": "What did Home Depot say about comparable store sales in Q4 2024?",
        "expected": "Home Depot reported comparable sales were approximately flat or slightly negative in Q4 2024.",
    },
    {
        "company_key": "keybank",
        "question": "What were KeyBank's key financial results in Q4 2024?",
        "expected": "KeyBank reported Q4 2024 results including net income and net interest income figures reflecting its regional banking performance.",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_dataset() -> list[EvalCase]:
    """
    Read each local PDF once, wrap it in a Braintrust Attachment, and
    return a list of EvalCase objects ready for braintrust.Eval.
    """
    # Cache bytes so each PDF file is read from disk only once
    pdf_cache: dict[str, bytes] = {}

    cases: list[EvalCase] = []
    for row in EVAL_CASES:
        key = row["company_key"]
        entry = EARNINGS_PDFS[key]
        pdf_path: pathlib.Path = entry["file"]

        if key not in pdf_cache:
            print(f"  Loading {entry['company']} {entry['quarter']} PDF…")
            pdf_cache[key] = pdf_path.read_bytes()

        pdf_bytes = pdf_cache[key]
        filename = pdf_path.name

        # Braintrust Attachment – rendered as a clickable PDF in the UI
        attachment = Attachment(
            data=pdf_bytes,
            filename=filename,
            content_type="application/pdf",
        )

        cases.append(
            EvalCase(
                input={
                    "company": entry["company"],
                    "quarter": entry["quarter"],
                    "question": row["question"],
                    "pdf_filename": filename,
                    # The attachment is stored here so it appears in the
                    # experiment's input column and is viewable in the playground
                    "pdf": attachment,
                },
                expected=row["expected"],
                metadata={"company_key": key},
            )
        )

    return cases


# ── Task function (runs for every eval case) ──────────────────────────────────

async def earnings_task(input: dict) -> str:
    """
    Call GPT-4o with the PDF attachment and return the answer.
    Braintrust automatically traces this call via wrap_openai.
    """
    pdf_attachment: Attachment = input["pdf"]
    question: str = input["question"]
    company: str = input["company"]
    quarter: str = input["quarter"]

    # Attachment.data holds the raw bytes we passed in at dataset-build time
    pdf_bytes: bytes = pdf_attachment.data  # type: ignore[assignment]
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    filename: str = input.get("pdf_filename") or "earnings.pdf"

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
                            f"This is the {quarter} earnings document for {company}.\n\n"
                            f"{question}"
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

    return response.choices[0].message.content or "(no response)"


# ── Agent task function ───────────────────────────────────────────────────────

async def agent_task(input: dict) -> str:
    """
    Run the full EarningsCallAnalyst agent for one eval case.

    The agent receives a natural-language user message asking about the company
    and quarter. It calls the `fetch_and_analyze_earnings` tool, which loads
    the PDF from disk, logs it as a Braintrust Attachment, and asks GPT-4o.
    The entire tool-call pipeline is traced in Braintrust automatically.
    """
    company: str = input["company"]
    quarter: str = input["quarter"]
    question: str = input["question"]

    user_message = (
        f"Please look up the {quarter} earnings for {company} and answer: {question}"
    )

    result = await Runner.run(
        earnings_agent,
        input=[{"role": "user", "content": user_message}],
    )

    return result.final_output


# ── Upload dataset ────────────────────────────────────────────────────────────

DATASET_NAME = "earnings-pdfs"


def upload_dataset() -> None:
    """
    Upload the eval cases (with PDF attachments) to a Braintrust dataset so
    they can be browsed in the UI and reused across experiments without
    re-running the evaluation.
    """
    cases = _build_dataset()
    if not cases:
        print("No cases to upload – check that pdfs/ directory is populated.")
        return

    dataset = braintrust.init_dataset(
        project=PROJECT,
        name=DATASET_NAME,
        description="Earnings call PDF QA evaluation cases",
    )

    for case in cases:
        dataset.insert(
            input=case.input,
            expected=case.expected,
            metadata=case.metadata,
        )

    dataset.flush()
    print(f"Uploaded {len(cases)} cases to dataset '{DATASET_NAME}' in project '{PROJECT}'.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Earnings Call PDF Eval")
    parser.add_argument(
        "--upload-dataset",
        action="store_true",
        help="Upload the dataset to Braintrust without running the evaluation.",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Run the eval through the full EarningsCallAnalyst agent pipeline instead of calling GPT-4o directly.",
    )
    args = parser.parse_args()

    if args.upload_dataset:
        upload_dataset()
        return

    print("Building eval dataset (reading local PDFs)…")
    dataset = _build_dataset()
    print(f"Dataset ready: {len(dataset)} cases\n")

    if not dataset:
        print("No cases to evaluate – check that pdfs/ directory is populated.")
        return

    if args.agent:
        task = agent_task
        eval_type = "pdf-qa-agent"
        print("Mode: agent (full pipeline)\n")
    else:
        task = earnings_task
        eval_type = "pdf-qa-direct"
        print("Mode: direct (GPT-4o baseline)\n")

    await braintrust.Eval(
        name=PROJECT,
        data=dataset,
        task=task,
        scores=[PDFFactuality],
        metadata={"model": "gpt-4o", "eval_type": eval_type},
    )


if __name__ == "__main__":
    asyncio.run(main())
