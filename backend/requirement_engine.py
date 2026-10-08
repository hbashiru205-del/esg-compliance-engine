"""
Structured regulatory requirement engine.

This layer sits between document retrieval and the user-facing workflows.

Flow:

Regulation
    ↓
Retrieved regulatory text
    ↓
Structured requirement
    ↓
Regulatory Research OR Gap Analysis

The engine extracts the meaning of a requirement into explicit fields such as:
- subject
- action
- object
- conditions
- exceptions
- scope
- cross-references

It does not expose or store hidden chain-of-thought.
"""

import json
import re
from typing import Any

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY, MODEL, MAX_TOKENS


def _extract_json(text: str) -> Any:
    """Safely extract JSON from an LLM response."""

    text = (text or "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Sometimes a model wraps JSON in markdown.
    match = re.search(r"\{.*\}|\[.*\]", text, flags=re.DOTALL)

    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return None


def _chunk_source(chunk: dict) -> dict:
    """Return citation metadata from a retrieved chunk."""

    return {
        "filename": chunk.get("source", "Unknown"),
        "page": chunk.get("page"),
        "reference": chunk.get("regulatory_reference", ""),
    }


def _build_context(chunks: list[dict]) -> str:
    """Build a controlled context for requirement extraction."""

    parts = []

    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "Unknown")
        page = chunk.get("page", "unknown")
        reference = chunk.get("regulatory_reference", "")
        text = chunk.get("text", "")

        parts.append(
            f"--- EXCERPT {i} ---\n"
            f"DOCUMENT: {source}\n"
            f"PAGE: {page}\n"
            f"REGULATORY REFERENCE: {reference or 'not identified'}\n"
            f"TEXT:\n{text}"
        )

    return "\n\n".join(parts)


def extract_requirements(
    chunks: list[dict],
    api_key: str | None = None,
    max_requirements: int = 10,
) -> list[dict]:
    """
    Extract structured regulatory requirements from retrieved excerpts.

    Only information explicitly present in the supplied excerpts may be used.
    """

    if not chunks:
        return []

    key = api_key or GEMINI_API_KEY

    if not key:
        return []

    context = _build_context(chunks)

    prompt = f"""
You are a regulatory requirements analyst.

Your task is to identify the actual regulatory requirements contained in the
supplied excerpts.

Use ONLY the supplied excerpts.

Do not use outside legal knowledge.

For every distinct requirement that is explicitly stated, identify:

1. requirement
   A concise plain-English description of what is required.

2. subject
   Who or what the requirement applies to.

3. action
   What the subject must, should, or may do.

4. object
   What the action concerns.

5. conditions
   Explicit conditions, thresholds, dates, triggers, or qualifications.

6. exceptions
   Explicit exceptions or carve-outs.

7. scope
   Explicit jurisdiction, entity, activity, threshold, or applicability scope.

8. cross_references
   Any Article, paragraph, definition, regulation, standard, or other provision
   referenced by the requirement.

9. source
   The document, page, and regulatory reference supporting the requirement.

IMPORTANT RULES:

- Never invent an Article number.
- Never invent a paragraph number.
- Never invent an exception.
- Never assume that a missing exception does not exist.
- Preserve phrases such as "where applicable", "subject to", "unless",
  "provided that", and numerical thresholds.
- If the requirement references another provision that is not present in the
  supplied excerpts, record that reference as a cross-reference.
- Return no more than {max_requirements} requirements.
- Return JSON only.

Use this structure:

[
  {{
    "requirement": "string",
    "subject": "string",
    "action": "string",
    "object": "string",
    "conditions": [],
    "exceptions": [],
    "scope": "string",
    "cross_references": [],
    "source": {{
      "filename": "string",
      "page": 1,
      "reference": "string"
    }}
  }}
]

SUPPLIED EXCERPTS:

{context}
"""

    try:
        client = genai.Client(api_key=key)

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                )
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
            ),
        )

        parsed = _extract_json(response.text)

    except Exception:
        return []

    if not isinstance(parsed, list):
        return []

    requirements = []

    for item in parsed[:max_requirements]:

        if not isinstance(item, dict):
            continue

        requirement_text = str(
            item.get("requirement", "")
        ).strip()

        if not requirement_text:
            continue

        source = item.get("source")

        if not isinstance(source, dict):
            source = {}

        requirements.append(
            {
                "id": f"REQ-{len(requirements) + 1:03d}",

                "requirement": requirement_text,

                "subject": str(
                    item.get("subject", "")
                ).strip(),

                "action": str(
                    item.get("action", "")
                ).strip(),

                "object": str(
                    item.get("object", "")
                ).strip(),

                "conditions": (
                    item.get("conditions", [])
                    if isinstance(item.get("conditions", []), list)
                    else []
                ),

                "exceptions": (
                    item.get("exceptions", [])
                    if isinstance(item.get("exceptions", []), list)
                    else []
                ),

                "scope": str(
                    item.get("scope", "")
                ).strip(),

                "cross_references": (
                    item.get("cross_references", [])
                    if isinstance(
                        item.get("cross_references", []),
                        list,
                    )
                    else []
                ),

                "source": {
                    "filename": (
                        source.get("filename")
                        or chunks[0].get("source", "Unknown")
                    ),
                    "page": source.get("page"),
                    "reference": (
                        source.get("reference")
                        or chunks[0].get(
                            "regulatory_reference",
                            "",
                        )
                    ),
                },
            }
        )

    return requirements


def _build_evidence_context(
    evidence_chunks: list[dict],
    max_chars: int = 5000,
) -> str:
    """Build controlled client-evidence context."""

    if not evidence_chunks:
        return "NO MATCHING CLIENT EVIDENCE WAS RETRIEVED."

    parts = []
    total_chars = 0

    for i, chunk in enumerate(evidence_chunks, 1):

        text = chunk.get("text", "")

        part = (
            f"--- CLIENT EVIDENCE {i} ---\n"
            f"DOCUMENT: {chunk.get('source', 'Unknown')}\n"
            f"PAGE: {chunk.get('page', 'unknown')}\n"
            f"REFERENCE: "
            f"{chunk.get('regulatory_reference', '') or 'not identified'}\n"
            f"TEXT:\n{text}\n"
        )

        if total_chars + len(part) > max_chars:
            break

        parts.append(part)
        total_chars += len(part)

    return "\n".join(parts)


def assess_requirement(
    requirement: dict,
    evidence_chunks: list[dict],
    api_key: str | None = None,
) -> dict:
    """
    Assess a structured requirement against client evidence.

    This is an evidence assessment, not a legal conclusion.
    """

    key = api_key or GEMINI_API_KEY

    if not key:
        return {
            "status": "Potential gap",
            "assessment": "AI assessment unavailable.",
            "evidence": [],
            "missing_elements": [],
        }

    evidence_context = _build_evidence_context(evidence_chunks)

    prompt = f"""
You are reviewing client evidence against one regulatory requirement.

This is an evidence review, NOT a legal opinion.

Use ONLY the requirement and client evidence supplied below.

Return JSON with:

{{
  "status": "Addressed | Partially addressed | Potential gap",
  "assessment": "1-3 sentence explanation",
  "evidence_used": [
    {{
      "filename": "string",
      "page": 1,
      "reference": "string",
      "quote": "short quote from the supplied evidence"
    }}
  ],
  "missing_elements": [
    "specific requirement element not demonstrated"
  ]
}}

STATUS RULES:

Addressed:
The supplied evidence clearly demonstrates the requirement.

Partially addressed:
The evidence demonstrates some, but not all, important elements.

Potential gap:
No relevant evidence was found, OR the evidence clearly does not
demonstrate an important requirement element.

IMPORTANT:

- Never invent evidence.
- Never invent a quotation.
- Never claim that a company is legally non-compliant.
- Use the phrase "potential gap in the provided evidence" when appropriate.
- Preserve uncertainty when evidence is ambiguous.
- If there is no evidence, say that no matching evidence was identified.

STRUCTURED REQUIREMENT:

{json.dumps(requirement, indent=2)}

CLIENT EVIDENCE:

{evidence_context}
"""

    try:
        client = genai.Client(api_key=key)

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                )
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
            ),
        )

        parsed = _extract_json(response.text)

    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        parsed = {}

    status = parsed.get("status")

    if status not in {
        "Addressed",
        "Partially addressed",
        "Potential gap",
    }:
        status = (
            "Potential gap"
            if not evidence_chunks
            else "Partially addressed"
        )

    evidence = parsed.get("evidence_used", [])

    if not isinstance(evidence, list):
        evidence = []

    missing_elements = parsed.get("missing_elements", [])

    if not isinstance(missing_elements, list):
        missing_elements = []

    return {
        "status": status,

        "assessment": str(
            parsed.get("assessment")
            or "No reliable assessment was returned."
        ).strip(),

        "evidence": evidence,

        "missing_elements": missing_elements,
    }


def run_gap_analysis(
    requirements: list[dict],
    client_store,
    api_key: str | None = None,
    evidence_top_k: int = 4,
) -> list[dict]:
    """
    Match structured requirements against client evidence.
    """

    results = []

    for requirement in requirements:

        query_parts = [
            requirement.get("requirement", ""),
            requirement.get("subject", ""),
            requirement.get("action", ""),
            requirement.get("object", ""),
        ]

        conditions = requirement.get("conditions", [])

        if isinstance(conditions, list):
            query_parts.extend(conditions)

        query = " ".join(
            str(part)
            for part in query_parts
            if part
        ).strip()

        evidence = []

        if query:
            evidence = client_store.retrieve(
                query,
                top_k=evidence_top_k,
            )

        assessment = assess_requirement(
            requirement,
            evidence,
            api_key=api_key,
        )

        results.append(
            {
                **requirement,
                "assessment": assessment,
            }
        )

    return results
