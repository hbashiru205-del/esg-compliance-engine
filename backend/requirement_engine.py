"""
Regulatory understanding layer for ClariX.

Pipeline:
    retrieved provisions
        -> structured requirement
        -> local resolution of cross-references / definitions
        -> semantic interpretation
        -> research + evidence-led gap analysis

The module deliberately stores auditable interpretation fields rather than
hidden chain-of-thought. Every resolved provision keeps its source/page/
reference so a consultant can inspect the underlying text.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY, MODEL, MAX_TOKENS


REQUIREMENT_SCHEMA_HINT = {
    "requirement": "short plain-English statement of what must/should be done",
    "subject": "who or what the requirement applies to",
    "action": "the required or permitted action",
    "object": "what the action concerns",
    "conditions": ["explicit conditions, thresholds, dates, or qualifiers"],
    "exceptions": ["explicit exceptions or carve-outs"],
    "scope": "explicit jurisdiction, entity, activity, threshold, or applicability scope",
    "cross_references": ["articles, paragraphs, definitions, standards, or laws referenced"],
    "source": {
        "filename": "source filename",
        "page": "page number if visible",
        "reference": "Article/paragraph/section reference if visible",
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
        match = re.search(r"\[.*\]", text, flags=re.DOTALL)
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


def _normalise_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def extract_requirements(
    chunks: list[dict],
    api_key: str | None = None,
    max_requirements: int = 10,
    corpus_chunks: list[dict] | None = None,
) -> list[dict]:
    """Extract structured requirements, then resolve their regulatory context."""
    if not chunks:
        return []

    key = api_key or GEMINI_API_KEY
    if not key:
        return []

    context = _build_requirement_context(chunks)
    prompt = f"""
You are the regulatory requirement extraction layer of an evidence-led compliance tool.

Use ONLY the supplied excerpts. Do not add outside legal knowledge.

For each distinct obligation or requirement actually stated in the excerpts, return:
- requirement: concise plain-English statement
- subject: who/what is subject to it
- action: required/allowed action
- object: what the action concerns
- conditions: explicit conditions, thresholds, dates, qualifiers
- exceptions: explicit exceptions/carve-outs
- scope: explicit applicability scope
- cross_references: every explicit article, paragraph, definition, annex, standard or law reference
- source: filename, page and Article/paragraph/section reference if visible

Rules:
1. Preserve qualifiers such as "where applicable", thresholds, dates and conditions.
2. Do not infer an exception merely because none is shown.
3. Record a cross-reference even when its target text is not supplied.
4. Do not invent article/paragraph numbers.
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
                max_output_tokens=min(MAX_TOKENS, 1600),
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
            "conditions": _normalise_list(item.get("conditions", [])),
            "exceptions": _normalise_list(item.get("exceptions", [])),
            "scope": str(item.get("scope", "")).strip(),
            "cross_references": _normalise_list(item.get("cross_references", [])),
            "source": {
                "filename": source.get("filename") or chunks[0].get("source", "Unknown"),
                "page": source.get("page"),
                "reference": source.get("reference"),
            },
        })

    if corpus_chunks:
        resolve_regulatory_context(output, corpus_chunks)
    return output


_ARTICLE_RE = re.compile(r"\bArticle\s+(\d{1,4}[A-Za-z]?(?:\([0-9A-Za-z]+\))?)\b", re.I)
_PARAGRAPH_RE = re.compile(r"\b(?:paragraph|para\.?|section)\s+([0-9]{1,4}[A-Za-z]?(?:\([0-9A-Za-z]+\))?)\b", re.I)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC0-9A-Za-z-]+)\b", re.I)


def _references_from_requirement(requirement: dict) -> list[str]:
    refs = []
    for value in requirement.get("cross_references", []):
        refs.append(str(value))
    # Also inspect the structured fields because models sometimes mention a
    # reference in conditions/scope without putting it in cross_references.
    for field in ("requirement", "conditions", "exceptions", "scope", "object"):
        value = requirement.get(field, "")
        text = " ".join(value) if isinstance(value, list) else str(value)
        refs.extend(m.group(0) for m in _ARTICLE_RE.finditer(text))
        refs.extend(m.group(0) for m in _PARAGRAPH_RE.finditer(text))
        refs.extend(m.group(0) for m in _ANNEX_RE.finditer(text))
    # Preserve order and remove duplicates.
    seen = set()
    return [r for r in refs if not (r.lower() in seen or seen.add(r.lower()))]


def _ref_matches(text: str, ref: str) -> bool:
    """Match a referenced provision without treating a number as a loose keyword."""
    ref = ref.strip()
    m = re.search(r"Article\s+([0-9]{1,4}[A-Za-z]?(?:\([0-9A-Za-z]+\))?)", ref, re.I)
    if m:
        number = re.escape(m.group(1))
        return bool(re.search(rf"\bArticle\s+{number}\b", text, re.I))
    m = re.search(r"(?:paragraph|para\.?|section)\s+([0-9]{1,4}[A-Za-z]?(?:\([0-9A-Za-z]+\))?)", ref, re.I)
    if m:
        number = re.escape(m.group(1))
        return bool(re.search(rf"\b(?:paragraph|para\.?|section)\s+{number}\b", text, re.I))
    m = re.search(r"Annex\s+([IVXLC0-9A-Za-z-]+)", ref, re.I)
    if m:
        return bool(re.search(rf"\bAnnex\s+{re.escape(m.group(1))}\b", text, re.I))
    return ref.lower() in text.lower()


def _definition_candidates(requirement: dict, corpus_chunks: list[dict]) -> list[dict]:
    """Find explicit definition passages for important terms in a requirement."""
    terms = set()
    fields = [requirement.get("subject", ""), requirement.get("object", ""), requirement.get("scope", "")]
    for field in fields:
        words = re.findall(r"\b[A-Za-z][A-Za-z -]{2,50}\b", str(field))
        for word in words:
            word = re.sub(r"\s+", " ", word).strip(" .,:;()")
            if len(word.split()) <= 5 and len(word) >= 4:
                terms.add(word)

    candidates = []
    for chunk in corpus_chunks:
        text = chunk.get("text", "")
        lower = text.lower()
        if not re.search(r"\b(?:means|defined as|definition of|for the purposes of)\b", lower):
            continue
        for term in terms:
            pattern = rf"(?:\"{re.escape(term)}\"|\b{re.escape(term)}\b).{{0,100}}\b(?:means|is defined as)\b"
            reverse = rf"\b(?:means|is defined as)\b.{{0,120}}(?:\"{re.escape(term)}\"|\b{re.escape(term)}\b)"
            if re.search(pattern, text, re.I | re.S) or re.search(reverse, text, re.I | re.S):
                candidates.append(chunk)
                break
        if len(candidates) >= 4:
            break
    return candidates


def _compact_context(chunks: list[dict], limit: int = 7000) -> list[dict]:
    out, used = [], 0
    seen = set()
    for chunk in chunks:
        key = (chunk.get("source"), chunk.get("index"))
        if key in seen:
            continue
        seen.add(key)
        text = chunk.get("text", "")
        if used + len(text) > limit:
            break
        out.append(chunk)
        used += len(text)
    return out


def resolve_regulatory_context(requirements: list[dict], corpus_chunks: list[dict]) -> list[dict]:
    """Resolve explicit references/definitions locally against the uploaded corpus.

    This is intentionally deterministic and cheap: it does not call an LLM. It
    creates an auditable context bundle that the semantic interpretation step can
    reason over.
    """
    if not corpus_chunks:
        return requirements

    for requirement in requirements:
        refs = _references_from_requirement(requirement)
        resolved = []
        unresolved = []
        for ref in refs:
            matches = [c for c in corpus_chunks if _ref_matches(c.get("text", ""), ref)]
            matches = _compact_context(matches[:4], limit=4200)
            if matches:
                resolved.append({
                    "reference": ref,
                    "found": True,
                    "provisions": [_source_reference(c) | {"text": c.get("text", "")[:1800]} for c in matches],
                })
            else:
                unresolved.append(ref)

        definitions = []
        for chunk in _definition_candidates(requirement, corpus_chunks):
            definitions.append(_source_reference(chunk) | {"text": chunk.get("text", "")[:1800]})

        requirement["resolved_references"] = resolved
        requirement["unresolved_references"] = unresolved
        requirement["definitions"] = definitions
        requirement["regulatory_context"] = [
            *[p for item in resolved for p in item["provisions"]],
            *definitions,
        ]

    return requirements


def _semantic_context(requirement: dict) -> str:
    resolved = requirement.get("regulatory_context", [])
    if not resolved:
        return "No additional referenced provisions or explicit definitions were located in the uploaded corpus."
    parts = []
    for i, item in enumerate(resolved[:8], 1):
        parts.append(
            f"--- RELATED PROVISION {i} ---\n"
            f"DOCUMENT: {item.get('filename', 'Unknown')}\n"
            f"PAGE: {item.get('page') or 'unknown'}\n"
            f"REFERENCE: {item.get('reference') or 'not identified'}\n"
            f"TEXT:\n{item.get('text', '')}"
        )
    return "\n\n".join(parts)


def _normalise_obligation_elements(value) -> list[dict]:
    """Validate the model's atomic obligation checklist without inventing elements."""
    if not isinstance(value, list):
        return []
    allowed = {"Duty", "Condition", "Threshold", "Deadline", "Exception", "Dependency"}
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        element = str(item.get("element", "")).strip()
        if not element or element.casefold() in seen:
            continue
        seen.add(element.casefold())
        kind = str(item.get("element_type", "Duty")).strip().title()
        if kind not in allowed:
            kind = "Duty"
        result.append({
            "element": element,
            "element_type": kind,
            "evidence_test": str(item.get("evidence_test", "")).strip(),
        })
    return result[:12]


def enrich_requirements(requirements: list[dict], api_key: str | None = None) -> list[dict]:
    """Apply one batched semantic regulatory-understanding pass.

    Batching is deliberate: Andrew's deeper semantic layer should not turn a
    10-requirement analysis into 10 additional API round trips.
    """
    if not requirements:
        return []
    key = api_key or GEMINI_API_KEY
    if not key:
        return requirements

    items = []
    for requirement in requirements:
        items.append({
            "id": requirement.get("id"),
            "requirement": requirement.get("requirement"),
            "subject": requirement.get("subject"),
            "action": requirement.get("action"),
            "object": requirement.get("object"),
            "conditions": requirement.get("conditions", []),
            "exceptions": requirement.get("exceptions", []),
            "scope": requirement.get("scope"),
            "cross_references": requirement.get("cross_references", []),
            "resolved_references": requirement.get("resolved_references", []),
            "unresolved_references": requirement.get("unresolved_references", []),
            "definitions": requirement.get("definitions", []),
        })

    prompt = f"""
You are the regulatory semantics layer of ClariX. Interpret the extracted
requirements below using ONLY their supplied text and the related provisions
resolved from the same uploaded regulatory corpus.

This is not legal advice. Do not invent facts or outside legal rules.
Your job is to make the regulatory meaning explicit so another workflow can
compare the obligation against client evidence.

Return JSON only as an array with one object per input requirement, preserving
its id. Each object must contain:
- id
- applicability: who/what is covered, including thresholds or conditions
- operative_obligation: the actual duty/permission/prohibition in one sentence
- qualifiers: material conditions, timing, thresholds, or "where applicable" limits
- exceptions: explicit carve-outs; do not invent any
- definitions: important terms whose meaning is supplied by related provisions
- dependencies: provisions that must be read together with this requirement
- interpretation_notes: 1-3 short sentences explaining how related provisions
  change, qualify, or clarify the requirement
- obligation_elements: array of atomic, independently checkable elements. Each
  object must have element (one duty/condition/threshold/deadline/exception),
  element_type (Duty, Condition, Threshold, Deadline, Exception, Dependency),
  and evidence_test (what observable evidence would support that element)
- verification_questions: unresolved facts or cross-references that a reviewer
  must verify before a confident applicability or compliance conclusion
- confidence: exactly "High", "Medium", or "Low"

Important:
1. If a referenced provision was not found, do not guess what it says. Mention
   the unresolved reference in interpretation_notes/dependencies.
2. Distinguish applicability from the operative duty.
3. Preserve thresholds, dates, exceptions and conditional language.
4. If the supplied related text does not define a term, do not invent a definition.

INPUT REQUIREMENTS:
{json.dumps(items, indent=2)}
"""
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                max_output_tokens=min(MAX_TOKENS, 2400),
                response_mime_type="application/json",
            ),
        )
        parsed = _extract_json(response.text)
    except Exception:
        parsed = None

    by_id = {}
    if isinstance(parsed, list):
        by_id = {str(x.get("id")): x for x in parsed if isinstance(x, dict) and x.get("id")}

    for requirement in requirements:
        semantic = by_id.get(str(requirement.get("id")), {})
        requirement["interpretation"] = {
            "applicability": str(semantic.get("applicability", "")).strip(),
            "operative_obligation": str(semantic.get("operative_obligation", "")).strip() or requirement.get("requirement", ""),
            "qualifiers": _normalise_list(semantic.get("qualifiers", [])),
            "exceptions": _normalise_list(semantic.get("exceptions", [])) or requirement.get("exceptions", []),
            "definitions": _normalise_list(semantic.get("definitions", [])),
            "dependencies": _normalise_list(semantic.get("dependencies", [])),
            "interpretation_notes": str(semantic.get("interpretation_notes", "")).strip(),
            "obligation_elements": _normalise_obligation_elements(semantic.get("obligation_elements", [])),
            "verification_questions": _normalise_list(semantic.get("verification_questions", [])),
            "confidence": semantic.get("confidence") if semantic.get("confidence") in {"High", "Medium", "Low"} else "Medium",
        }
    return requirements

def prepare_requirements(
    chunks: list[dict],
    api_key: str | None = None,
    max_requirements: int = 10,
    corpus_chunks: list[dict] | None = None,
) -> list[dict]:
    """One public entry point for extraction + resolution + semantic interpretation."""
    requirements = extract_requirements(
        chunks,
        api_key=api_key,
        max_requirements=max_requirements,
        corpus_chunks=corpus_chunks,
    )
    return enrich_requirements(requirements, api_key=api_key)


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


def _quote_in_evidence(quote: str, evidence_chunks: list[dict]) -> bool:
    """True if the quote occurs verbatim (ignoring whitespace/line-break differences) in the evidence."""
    q = " ".join(str(quote).split())
    if not q:
        return False
    return any(q in " ".join(str(c.get("text", "")).split()) for c in evidence_chunks)


def assess_requirement(requirement: dict, evidence_chunks: list[dict], api_key: str | None = None) -> dict:
    """Assess a requirement against client evidence using the resolved regulatory meaning."""
    key = api_key or GEMINI_API_KEY
    if not key:
        return {"status": "Assessment failed", "assessment": "Assessment could not run because the Gemini API key is not configured.", "evidence": [], "missing_elements": [], "error_type": "configuration"}

    prompt = f"""
Assess one regulatory requirement against supplied client-document evidence.
This is an evidence review, not a legal opinion. Use ONLY the requirement,
its regulatory interpretation/context, and the supplied client evidence.

Return JSON only with:
- status: exactly one of "Addressed", "Partially addressed", "Potential gap", "Insufficient evidence"
- assessment: 1-3 sentences grounded in the evidence and the structured obligation
- evidence_used: array of objects with filename, page, reference, and short quote
- missing_elements: specific elements of the obligation not demonstrated
- element_checks: one object per supplied obligation_elements entry, with
  element (copy the element text), status ("Supported", "Partially supported",
  "Not demonstrated", or "Unclear"), evidence_quote (short exact quote from
  supplied evidence, or empty string), source (filename/page/reference if known),
  and note (brief explanation)
- verification_questions: unresolved facts that prevent a confident conclusion

Rules:
1. Test the evidence against the operative obligation AND its applicability/qualifiers.
2. Apply explicit exceptions only when they are actually established in the supplied context.
3. Addressed only when the supplied evidence clearly demonstrates the applicable requirement.
4. Partially addressed when some, but not all, required elements are evidenced.
5. Insufficient evidence when retrieved passages are absent, too weak, or do not permit a defensible assessment.
6. Potential gap only when relevant evidence is available and a material obligation appears not to be met.
7. Never invent client evidence or make a legal conclusion of non-compliance.
8. If a regulatory dependency remains unresolved, flag it as a verification point.
9. Assess each supplied atomic element separately. A related topic is not proof
   that a specific obligation is met. Evidence quotes must be exact substrings
   of supplied evidence; otherwise leave evidence_quote empty and mark Unclear.
10. Do not treat a missing disclosure in the uploaded evidence as proof that the
    organisation failed to comply; distinguish "not found in these documents"
    from an established failure.
11. Copy every obligation element into element_checks exactly once. Do not add
    new obligation elements during evidence assessment.

STRUCTURED REQUIREMENT:
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
                max_output_tokens=min(MAX_TOKENS, 1000),
                response_mime_type="application/json",
            ),
        )
        parsed = _extract_json(response.text)
    except Exception as exc:
        return {"status": "Assessment failed", "assessment": "The assessment model call failed. No compliance conclusion was produced.", "evidence": [], "missing_elements": [], "error_type": type(exc).__name__}

    if not isinstance(parsed, dict):
        return {"status": "Assessment failed", "assessment": "The model returned no valid structured assessment. No compliance conclusion was produced.", "evidence": [], "missing_elements": [], "error_type": "invalid_model_response"}
    status = parsed.get("status")
    allowed_statuses = {"Addressed", "Partially addressed", "Potential gap", "Insufficient evidence"}
    if status not in allowed_statuses:
        status = "Insufficient evidence" if not evidence_chunks else "Insufficient evidence"

    # No retrieved evidence must never be represented as a confirmed gap.
    if not evidence_chunks and status in {"Potential gap", "Partially addressed", "Addressed"}:
        status = "Insufficient evidence"
        assessment_text = "No relevant client evidence was retrieved, so this requirement cannot be assessed from the selected documents."
    else:
        assessment_text = str(parsed.get("assessment") or "The model returned no assessment text.").strip()

    evidence = parsed.get("evidence_used", [])
    if not isinstance(evidence, list):
        evidence = []
    verified_evidence = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        ev = dict(ev)
        quote = str(ev.get("quote", "")).strip()
        # A quotation that is not found in the retrieved evidence must not be shown as a citation.
        if quote and not _quote_in_evidence(quote, evidence_chunks):
            ev["quote"] = ""
            ev["quote_unverified"] = True
        verified_evidence.append(ev)
    evidence = verified_evidence
    element_checks = parsed.get("element_checks", [])
    if not isinstance(element_checks, list):
        element_checks = []
    allowed_element_statuses = {"Supported", "Partially supported", "Not demonstrated", "Unclear"}
    clean_checks = []
    for check in element_checks:
        if not isinstance(check, dict) or not str(check.get("element", "")).strip():
            continue
        quote = str(check.get("evidence_quote", "")).strip()
        # Prevent the model from presenting a fabricated quotation as an exact citation.
        if quote and not _quote_in_evidence(quote, evidence_chunks):
            quote = ""
            check_status = "Unclear"
        else:
            check_status = check.get("status") if check.get("status") in allowed_element_statuses else "Unclear"
        clean_checks.append({
            "element": str(check.get("element", "")).strip(),
            "status": check_status,
            "evidence_quote": quote,
            "source": check.get("source") if isinstance(check.get("source"), dict) else {},
            "note": str(check.get("note", "")).strip(),
        })
    return {
        "status": status,
        "assessment": assessment_text,
        "evidence": evidence,
        "missing_elements": _normalise_list(parsed.get("missing_elements", [])),
        "element_checks": clean_checks,
        "verification_questions": _normalise_list(parsed.get("verification_questions", [])),
    }


def run_gap_analysis(requirements: list[dict], client_store, api_key: str | None = None, evidence_top_k: int = 4, max_workers: int = 4) -> list[dict]:
    """Match requirements to evidence and assess them concurrently."""
    if not requirements:
        return []

    prepared = []
    for requirement in requirements:
        interpretation = requirement.get("interpretation", {})
        query = " ".join([
            requirement.get("requirement", ""),
            requirement.get("subject", ""),
            requirement.get("action", ""),
            requirement.get("object", ""),
            " ".join(requirement.get("conditions", [])),
            interpretation.get("operative_obligation", ""),
            interpretation.get("applicability", ""),
            " ".join(interpretation.get("qualifiers", [])),
        ]).strip()
        evidence = client_store.retrieve(query, top_k=evidence_top_k) if query else []
        prepared.append((requirement, evidence))

    worker_count = max(1, min(max_workers, len(prepared)))
    assessments = [None] * len(prepared)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(assess_requirement, requirement, evidence, api_key): i
            for i, (requirement, evidence) in enumerate(prepared)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                assessments[index] = future.result()
            except Exception as exc:
                assessments[index] = {"status": "Assessment failed", "assessment": "The assessment task failed unexpectedly. No compliance conclusion was produced.", "evidence": [], "missing_elements": [], "error_type": type(exc).__name__}

    results = []
    used_ids = set()
    for i, (requirement, _evidence) in enumerate(prepared):
        item = dict(requirement)
        original_id = str(item.get("id") or "").strip()
        # Enforce unique stable IDs at the result boundary; stale/duplicate IDs
        # from upstream extraction must not collapse findings in the UI.
        candidate = original_id if original_id and original_id not in used_ids else f"REQ-{i + 1:03d}"
        suffix = 2
        base = candidate
        while candidate in used_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1
        item["id"] = candidate
        used_ids.add(candidate)
        item["assessment"] = assessments[i] or {"status": "Assessment failed", "assessment": "No assessment result was returned. No compliance conclusion was produced.", "evidence": [], "missing_elements": [], "error_type": "missing_result"}
        results.append(item)
    return results
