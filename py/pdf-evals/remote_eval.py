"""
Earnings Call PDF — Remote Eval
================================
Exposes the EarningsCallAnalyst agent as a Braintrust remote evaluator.

Start the dev server:
    braintrust eval remote_eval.py --dev

Then open the Braintrust UI, select the "earnings-pdfs" dataset, and click
"Run Eval" to trigger the agent against each PDF case remotely.

Parameters (configurable in the Braintrust UI):
  - company  : filter eval to a single company, or "all" to run every row
  - provider : "openai" (gpt-4o) or "anthropic" (claude-opus-4-5)

How it works:
- Braintrust calls this server for each dataset row, passing input that
  contains a `pdf` field which is an already-uploaded AttachmentReference
  (i.e. {"type": "braintrust_attachment", "key": "...", ...})
- We resolve it to bytes via ReadonlyAttachment, then call the selected
  model with the PDF attached inline

Prerequisites:
    pip install -r requirements.txt
    cp .env.example .env  # fill in OPENAI_API_KEY, ANTHROPIC_API_KEY, BRAINTRUST_API_KEY

    # Upload the dataset first (if not already done):
    python eval.py --upload-dataset
"""

import base64
import os
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

import anthropic as anthropic_sdk
import openai as openai_sdk
import braintrust
from braintrust import Attachment, ReadonlyAttachment
from braintrust.devserver.eval_hooks import EvalHooks
from autoevals import Factuality

load_dotenv()

PROJECT = os.environ.get("BRAINTRUST_PROJECT", "earnings-pdf-agent")
DATASET_NAME = "earnings-pdfs"

SYSTEM_PROMPT = (
    "You are a financial analyst. Answer questions about earnings calls "
    "clearly and concisely. Focus on: revenue & EPS vs. expectations, "
    "key business highlights or challenges, and forward guidance."
)

# Company keys that match the dataset metadata — used to filter rows
COMPANY_KEYS = ["meta", "jpmorgan", "att", "qualcomm", "homeDepot", "keybank"]

_ATTACHMENT_TYPES = (Attachment, ReadonlyAttachment)


def _strip_attachments(d: dict) -> dict:
    """Return a copy of *d* with any Attachment/ReadonlyAttachment values removed."""
    return {k: v for k, v in d.items() if not isinstance(v, _ATTACHMENT_TYPES)}


def PDFFactuality(output, expected=None, input=None, **kwargs):
    """
    Factuality scorer that strips PDF attachments from `input` before
    passing it to the LLM — attachments are not JSON-serializable and
    are not useful text context for the scorer anyway.
    """
    sanitized_input = _strip_attachments(input) if isinstance(input, dict) else input
    return Factuality(base_url="https://api.openai.com/v1")(output=output, expected=expected, input=sanitized_input, **kwargs)


# ── Parameters ────────────────────────────────────────────────────────────────

class CompanyParam(BaseModel):
    value: Literal["all", "meta", "jpmorgan", "att", "qualcomm", "homeDepot", "keybank"] = Field(
        default="all",
        description="Which company to evaluate. Choose 'all' to run every dataset row.",
    )


class ProviderParam(BaseModel):
    value: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="Which provider to use for this eval run.",
    )


class OpenAIModelParam(BaseModel):
    value: Literal["gpt-4o", "gpt-4o-mini", "gpt-4.5-preview", "o3"] = Field(
        default="gpt-4o",
        description="OpenAI model to use when provider is 'openai'.",
    )


class AnthropicModelParam(BaseModel):
    value: Literal["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5-20251001"] = Field(
        default="claude-sonnet-4-5",
        description="Anthropic model to use when provider is 'anthropic'.",
    )


# ── Model clients ─────────────────────────────────────────────────────────────

_oai = braintrust.wrap_openai(
    openai_sdk.AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url="https://api.openai.com/v1",
    )
)

# Anthropic client — traced via the active Braintrust span; wrap_openai is
# OpenAI-only so we use the Anthropic SDK directly.
_anthropic = anthropic_sdk.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ── Model dispatch ────────────────────────────────────────────────────────────

async def _call_openai(pdf_b64: str, pdf_filename: str, company: str, quarter: str, question: str, model: str = "gpt-4o") -> str:
    response = await _oai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"This is the {quarter} earnings document for {company}.\n\n{question}",
                    },
                    {
                        "type": "file",
                        "file": {
                            "filename": pdf_filename,
                            "file_data": f"data:application/pdf;base64,{pdf_b64}",
                        },
                    },
                ],
            },
        ],
    )
    return response.choices[0].message.content or "(no response)"


async def _call_anthropic(pdf_b64: str, pdf_filename: str, company: str, quarter: str, question: str, model: str = "claude-sonnet-4-5") -> str:
    response = await _anthropic.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "title": pdf_filename,
                    },
                    {
                        "type": "text",
                        "text": f"This is the {quarter} earnings document for {company}.\n\n{question}",
                    },
                ],
            }
        ],
    )
    return response.content[0].text if response.content else "(no response)"


# ── Task ──────────────────────────────────────────────────────────────────────

async def task(input: dict, hooks: EvalHooks) -> str | None:
    """
    Remote eval task — called once per dataset row by the Braintrust dev server.

    `input` contains:
      - pdf          : AttachmentReference dict (resolved via ReadonlyAttachment)
      - pdf_filename : original filename string
      - question     : the question to answer
      - company      : company display name
      - quarter      : reporting quarter

    `hooks.parameters` contains the UI-configured CompanyParam and ProviderParam.
    Returns None to skip a row (when company filter is active), or the answer string.
    """
    # ── Read parameters from Braintrust UI ───────────────────────────────────
    # The framework unwraps single-field `value` Pydantic models to plain
    # strings before placing them in hooks.parameters, so we read them
    # directly as strings and fall back to defaults if absent.
    params = hooks.parameters or {}
    selected_company: str = params.get("company", "all")
    provider: str = params.get("provider", "openai")
    openai_model: str = params.get("openai_model", "gpt-4o")
    anthropic_model: str = params.get("anthropic_model", "claude-sonnet-4-5")

    # ── Filter rows by company ────────────────────────────────────────────────
    row_company_key: str = (input.get("metadata") or {}).get("company_key", "")
    if selected_company != "all" and row_company_key != selected_company:
        return None  # skip this row

    question: str = input["question"]
    company: str = input["company"]
    quarter: str = input["quarter"]
    pdf_filename: str = input.get("pdf_filename", "earnings.pdf")
    pdf_ref = input.get("pdf")

    # ── Resolve PDF bytes from the Braintrust attachment reference ────────────
    # Also normalise input["pdf"] back to its plain reference dict so the
    # Eval framework can JSON-serialize the full input row when logging.
    if isinstance(pdf_ref, ReadonlyAttachment):
        input["pdf"] = pdf_ref.reference  # replace object with serializable dict
        pdf_bytes = pdf_ref.data
    elif isinstance(pdf_ref, dict) and pdf_ref.get("type") == "braintrust_attachment":
        pdf_bytes = ReadonlyAttachment(pdf_ref).data
    else:
        raise ValueError(
            f"Expected a braintrust_attachment reference in input['pdf'], got: {type(pdf_ref)}"
        )

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    # ── Call the selected model ───────────────────────────────────────────────
    if provider == "anthropic":
        return await _call_anthropic(pdf_b64, pdf_filename, company, quarter, question, model=anthropic_model)
    else:
        return await _call_openai(pdf_b64, pdf_filename, company, quarter, question, model=openai_model)


# ── Register the remote evaluator ─────────────────────────────────────────────
braintrust.Eval(
    name=PROJECT,
    data=braintrust.init_dataset(project=PROJECT, name=DATASET_NAME),
    task=task,
    scores=[PDFFactuality],
    parameters={
        "company": CompanyParam,
        "provider": ProviderParam,
        "openai_model": OpenAIModelParam,
        "anthropic_model": AnthropicModelParam,
    },
    metadata={"eval_type": "pdf-qa-remote"},
)
