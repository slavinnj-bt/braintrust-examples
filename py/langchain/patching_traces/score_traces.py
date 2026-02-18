"""
score_traces.py
===============
Separate scoring process that queries Braintrust for unscored customer-service
spans and adds predicted NPS scores as metrics.

Designed to run independently from customer_service_chatbot.py—minutes, hours,
or a day later—as a batch job or triggered pipeline. It discovers spans by tag
("unscored") so it never needs to know span IDs up front.

Workflow
--------
1. Fetch all spans tagged "unscored" from the Braintrust project logs.
2. For each span, use Claude to evaluate the agent response and predict an NPS
   score (0–10, where 9-10 = Promoter, 7-8 = Passive, 0-6 = Detractor).
3. Update each span via REST API with _is_merge=true:
      scores:   { "nps": <0.0–1.0> }   ← Braintrust scores are normalized 0–1
      tags:     swap "unscored" → "scored"
      metadata: nps_score, rationale, scorer_model, scorer_version

Requirements
------------
    pip install anthropic requests

Environment variables
---------------------
    BRAINTRUST_API_KEY   – your Braintrust API key
    BRAINTRUST_PROJECT   – Braintrust project name to query
    ANTHROPIC_API_KEY    – Anthropic API key
"""

import json
import os
import time

import anthropic
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_NAME = os.environ["BRAINTRUST_PROJECT"]
BASE_URL = "https://api.braintrustdata.com"
BTQL_URL = "https://api.braintrust.dev/btql"
SCORER_MODEL = "claude-haiku-4-5-20251001"
SCORER_VERSION = "v1"

BRAINTRUST_API_KEY = os.environ["BRAINTRUST_API_KEY"]
HEADERS = {
    "Authorization": f"Bearer {BRAINTRUST_API_KEY}",
    "Content-Type": "application/json",
}

client = anthropic.Anthropic()


# ===========================================================================
# Step 1 – Resolve project ID from name
# ===========================================================================

def get_project_id(project_name: str) -> str:
    resp = requests.get(
        f"{BASE_URL}/v1/project",
        params={"project_name": project_name},
        headers=HEADERS,
    )
    resp.raise_for_status()
    objects = resp.json().get("objects", [])
    if not objects:
        raise ValueError(
            f"Project '{project_name}' not found. "
            "Run customer_service_chatbot.py first."
        )
    project_id = objects[0]["id"]
    print(f"[Setup] '{project_name}' → project_id={project_id}")
    return project_id


# ===========================================================================
# Step 2 – Fetch unscored customer_service spans
# ===========================================================================

def fetch_unscored_spans(project_id: str) -> list[dict]:
    """
    Query BTQL for spans tagged both "unscored" and "customer_service" that
    have input/output set (i.e. root conversation spans, not LangChain child
    spans).

    Syntax notes:
    - shape => 'spans'  returns individual matching spans. shape => 'traces'
      returns ALL spans from any trace that has a matching span—much larger
      and the source of prior 504 timeouts.
    - INCLUDES is the BTQL array-membership operator (not SQL's IN).
    - Pagination: pass the x-bt-cursor response header as "cursor" in the
      next request body to page through large result sets.
    """
    # BTQL pipe syntax (starts with "select:" not "SELECT", so the parser
    # uses pipe mode where "includes" is valid for array membership).
    # shape: spans  – individual matching spans only (not all spans from
    #                 matching traces, which caused 504s with "traces" shape).
    query = f"""
        select: id, input, output, metadata, tags, scores
        from: project_logs('{project_id}') spans
        filter: tags includes 'unscored' and tags includes 'customer_service'
        limit: 500
    """
    resp = requests.post(
        BTQL_URL,
        json={"query": query, "fmt": "json"},
        headers=HEADERS,
    )
    if not resp.ok:
        raise RuntimeError(f"BTQL {resp.status_code}: {resp.text}")

    # Filter client-side to root spans (have both input and output set).
    rows = [r for r in resp.json().get("data", []) if r.get("input") and r.get("output")]
    print(f"[Step 2] {len(rows)} unscored customer_service span(s) returned by BTQL.")
    return rows


# ===========================================================================
# Step 3 – Score a conversation with Claude
# ===========================================================================

_SCORING_PROMPT = """\
You are a quality-assurance evaluator for a customer service team. \
Assess the agent's response to the customer message below and predict \
the NPS score the customer is likely to give (0–10).

NPS scale:
  9–10  Promoter   – outstanding: empathetic, accurate, and fully resolves the issue
  7–8   Passive    – adequate: helpful but generic or slightly missing the mark
  0–6   Detractor  – poor: dismissive, unhelpful, incorrect, or escalation-worthy

Customer message:
{customer_message}

Agent response:
{agent_response}

Respond with **JSON only**, no markdown:
{{"score": <integer 0-10>, "rationale": "<one concise sentence>"}}"""


def score_conversation(customer_message: str, agent_response: str) -> dict:
    """Call Claude to predict the NPS score for one conversation."""
    prompt = _SCORING_PROMPT.format(
        customer_message=customer_message,
        agent_response=agent_response,
    )
    response = client.messages.create(
        model=SCORER_MODEL,
        max_tokens=256,
        # Prefill the assistant turn with "{" to guarantee a JSON response
        # and prevent the model from adding markdown code fences.
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "{"},
        ],
    )
    # Reconstruct the full JSON string (prefill + completion).
    raw = "{" + response.content[0].text
    return json.loads(raw)


# ===========================================================================
# Step 4 – Update span via REST API (_is_merge=true)
# ===========================================================================

def update_span_with_nps(
    project_id: str,
    span_id: str,
    nps_score: int,
    rationale: str,
) -> None:
    """
    Patch the existing span with NPS data.

    _is_merge=true performs a deep merge, so only the fields listed here
    are written. The original input, output, metadata, LangChain child spans,
    and any other data are left untouched.

    Braintrust scores are normalized to 0–1, so we divide by 10.
    The "unscored" tag is dropped by replacing the tags array entirely.
    """
    url = f"{BASE_URL}/v1/project_logs/{project_id}/insert"
    payload = {
        "events": [
            {
                "id": span_id,
                "_is_merge": True,
                "scores": {
                    "nps": nps_score / 10,  # normalize: 0–1
                },
                "tags": ["customer_service", "scored"],  # replace "unscored"
                "metadata": {
                    "nps_score": nps_score,
                    "nps_rationale": rationale,
                    "scorer_model": SCORER_MODEL,
                    "scorer_version": SCORER_VERSION,
                },
            }
        ]
    }
    resp = requests.post(url, json=payload, headers=HEADERS)
    resp.raise_for_status()


# ===========================================================================
# Main
# ===========================================================================

def main():
    project_id = get_project_id(PROJECT_NAME)

    # Small delay to let any very recent ingestion settle before fetching.
    print("Waiting 3 s for ingestion to settle...")
    time.sleep(3)

    unscored = fetch_unscored_spans(project_id)
    if not unscored:
        print("No unscored spans found. Run customer_service_chatbot.py first.")
        return

    print(f"\nScoring {len(unscored)} conversation(s)...\n")

    results = {"promoter": 0, "passive": 0, "detractor": 0}

    for span in unscored:
        span_id = span["id"]
        ticket_id = (span.get("metadata") or {}).get("ticket_id", span_id[:12])

        # Extract conversation text. BTQL may return input/output as
        # JSON strings rather than parsed objects; handle both forms.
        input_raw = span.get("input") or {}
        if isinstance(input_raw, str):
            try:
                input_raw = json.loads(input_raw)
            except json.JSONDecodeError:
                input_raw = {"message": input_raw}
        customer_message = input_raw.get("message", str(input_raw))

        output_raw = span.get("output") or ""
        if not isinstance(output_raw, str):
            try:
                agent_response = json.dumps(output_raw)
            except Exception:
                agent_response = str(output_raw)
        else:
            agent_response = output_raw

        # Score with Claude.
        scored = score_conversation(customer_message, agent_response)
        nps_score = int(scored["score"])
        rationale = scored["rationale"]

        # Update the span in Braintrust.
        update_span_with_nps(project_id, span_id, nps_score, rationale)

        # Summarize.
        label = "Promoter" if nps_score >= 9 else "Passive" if nps_score >= 7 else "Detractor"
        results[label.lower()] += 1
        print(f"[{ticket_id}] {nps_score}/10 – {label}")
        print(f"  {rationale}\n")

    total = len(unscored)
    print("=" * 50)
    print(f"Scored {total} conversation(s):")
    print(f"  Promoters  (9-10): {results['promoter']}")
    print(f"  Passives   (7-8) : {results['passive']}")
    print(f"  Detractors (0-6) : {results['detractor']}")
    print(f"\nView in Braintrust:")
    print(f"  https://www.braintrust.dev/app/project/{project_id}/logs")


if __name__ == "__main__":
    main()
