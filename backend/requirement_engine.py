"""
Structured regulatory requirement extraction and evidence assessment.

This module sits between retrieval and the user-facing workflows:

    PDF -> retrieval -> structured requirement -> research / gap analysis

It deliberately asks the model for a compact, auditable representation of a
requirement rather than exposing or storing hidden chain-of-thought.
"""

import json
import re
from typing import Any

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY, MODEL, MAX_TOKENS


REQUIREMENT_SCHEMA_HINT = {
    "requirement": "short plain-English statement of what must/should be done",
    "subject": "who or what the requirement applies to",
    "action": "the required or permitted action",
    "object": "what the action concerns",
    "conditions": ["conditions that must be satisfied"],
    "exceptions": ["exceptions or carve-outs explicitly stated"],
    "scope": "jurisdiction, entity, activity, threshold, or applicability scope stated in the excerpt",
    "cross_references": ["articles, paragraphs, definitions, standards, or laws referenced by the requirement"],
    "source": {
        "filename": "source filename",
        "page": "page number if visible in the excerpt, otherwise null",
        "reference": "Article/paragraph/section reference if visible, otherwise null",
    },
}


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _source_reference(chunk: dict) -> dict:
    return {
        "filename": chunk.get("source", "Unknown"),
        "page": chunk.get("page_start"),
        "reference": chunk.get("section_reference"),
    }


def _build_requirement_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"--- EXCERPT {i} ---\n"
            f"DOCUMENT: {chunk.get('source', 'Unknown')}\n"
            f"PAGE: {chunk.get('page_start') or 'unknown'}\n"
            f"REFERENCE: {chunk.get('section_reference') or 'not identified'}\n"
            f"TEXT:\n{chunk.get('text', '')}"
        )
    return "\n\n".join(parts)


def extract_requirements(
    chunks: list[dict],
    api_key: str | None = None,
    max_requirements: int = 10,
) -> list[dict]:
    """Extract structured requirements from retrieved regulatory excerpts."""
    if not chunks:
        return []

    key = api_key or GEMINI_API_KEY
    if not key:
        return []

    context = _build_requirement_context(chunks)
    prompt = f"""
You are extracting regulatory requirements for an evidence-led compliance
workflow.

Use ONLY the supplied excerpts. Do not add outside legal knowledge.

For each distinct obligation or requirement that is actually stated in the
excerpts, return a structured object with:
- requirement: concise plain-English statement
- subject: who/what is subject to it
- action: required/allowed action
- object: what the action concerns
- conditions: explicit conditions or thresholds
- exceptions: explicit exceptions/carve-outs
- scope: explicit applicability scope
- cross_references: references that may affect interpretation
- source: filename, page, and Article/paragraph/section reference if visible

Important:
1. Do not infer an exception merely because none is shown.
2. Preserve "where applicable", thresholds, dates, conditions, and qualifiers.
3. If a cross-reference is present but its target text is not supplied, record it.
4. Do not invent article or paragraph numbers.
5. Return at most {max_requirements} requirements.
6. Return JSON only as an array.

Example shape:
{json.dumps([REQUIREMENT_SCHEMA_HINT], indent=2)}

EXCERPTS:
{context}
"""

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
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

    output = []
    for item in parsed[:max_requirements]:
        if not isinstance(item, dict) or not item.get("requirement"):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        output.append({
            "id": f"REQ-{len(output)+1:03d}",
            "requirement": str(item.get("requirement", "")).strip(),
            "subject": str(item.get("subject", "")).strip(),
            "action": str(item.get("action", "")).strip(),
            "object": str(item.get("object", "")).strip(),
            "conditions": item.get("conditions", []) if isinstance(item.get("conditions", []), list) else [],
            "exceptions": item.get("exceptions", []) if isinstance(item.get("exceptions", []), list) else [],
            "scope": str(item.get("scope", "")).strip(),
            "cross_references": item.get("cross_references", []) if isinstance(item.get("cross_references", []), list) else [],
            "source": {
                "filename": source.get("filename") or chunks[0].get("source", "Unknown"),
                "page": source.get("page"),
                "reference": source.get("reference"),
            },
        })
    return output


def _evidence_context(evidence_chunks: list[dict], max_chars: int = 4500) -> str:
    parts = []
    used = 0
    for i, chunk in enumerate(evidence_chunks, 1):
        text = chunk.get("text", "")
        part = (
            f"--- EVIDENCE {i} ---\n"
            f"DOCUMENT: {chunk.get('source', 'Unknown')}\n"
            f"PAGE: {chunk.get('page_start') or 'unknown'}\n"
            f"REFERENCE: {chunk.get('section_reference') or 'not identified'}\n"
            f"TEXT:\n{text}\n"
        )
        if used + len(part) > max_chars:
            break
        parts.append(part)
        used += len(part)
    return "\n".join(parts) if parts else "No matching evidence was retrieved."


def assess_requirement(
    requirement: dict,
    evidence_chunks: list[dict],
    api_key: str | None = None,
) -> dict:
    """Assess a requirement against client evidence without making a legal conclusion."""
    key = api_key or GEMINI_API_KEY
    if not key:
        return {
            "status": "Potential gap",
            "assessment": "AI assessment unavailable.",
            "evidence": [],
        }

    prompt = f"""
Assess one regulatory requirement against the supplied client-document evidence.

This is an evidence review, not a legal opinion. Use ONLY the requirement and
evidence below.

Return JSON only with:
- status: exactly one of "Addressed", "Partially addressed", "Potential gap"
- assessment: 1-3 sentence explanation grounded in the supplied evidence
- evidence_used: array of objects with filename, page, reference, and short quote
- missing_elements: array of specific elements of the requirement not demonstrated

Rules:
1. Addressed only when the supplied evidence clearly demonstrates the requirement.
2. Partially addressed when some, but not all, required elements are evidenced.
3. Potential gap when no relevant evidence is found or the evidence clearly misses
   a material requirement element.
4. Never invent client evidence.
5. Do not say that a company is legally non-compliant. Say "potential gap in the
   provided evidence" instead.
6. Preserve uncertainty where the evidence is ambiguous.

REQUIREMENT:
{json.dumps(requirement, indent=2)}

CLIENT EVIDENCE:
{_evidence_context(evidence_chunks)}
"""

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
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
    if status not in {"Addressed", "Partially addressed", "Potential gap"}:
        status = "Potential gap" if not evidence_chunks else "Partially addressed"

    return {
        "status": status,
        "assessment": str(parsed.get("assessment") or "No reliable assessment was returned.").strip(),
        "evidence": parsed.get("evidence_used", []) if isinstance(parsed.get("evidence_used", []), list) else [],
        "missing_elements": parsed.get("missing_elements", []) if isinstance(parsed.get("missing_elements", []), list) else [],
    }


def run_gap_analysis(
    requirements: list[dict],
    client_store,
    api_key: str | None = None,
    evidence_top_k: int = 4,
) -> list[dict]:
    """Match structured requirements to client evidence and assess each one."""
    results = []
    for requirement in requirements:
        query = " ".join([
            requirement.get("requirement", ""),
            requirement.get("subject", ""),
            requirement.get("action", ""),
            requirement.get("object", ""),
            " ".join(requirement.get("conditions", [])),
        ]).strip()

        evidence = client_store.retrieve(query, top_k=evidence_top_k) if query else []
        assessment = assess_requirement(requirement, evidence, api_key=api_key)
        results.append({
            **requirement,
            "assessment": assessment,
        })
    return results
