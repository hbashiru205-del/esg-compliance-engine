import re
from backend.query_engine import query_compliance

_REFUSAL_RE = re.compile(
    r"not (?:found|specified|stated|included|available|determin\w*)"
    r"|no (?:information|mention)|cannot (?:be )?(?:determin|confirm|find)"
    r"|does not (?:appear|specify|state|include)",
    re.IGNORECASE,
)

TEST_QUESTIONS = [
    {"question": "What are the main obligations or requirements set out in this document?", "expect": "cite"},
    {"question": "What is the title of this document, and how many pages does it have?", "expect": "cite"},
    {"question": "In plain terms, who does this document apply to, and what do they actually have to do?", "expect": "cite"},
    {"question": "What exact monetary penalty does this document specify for non-compliance?", "expect": "cite_or_refuse"},
    {"question": "If more than one document is loaded, compare how each one addresses a shared topic, such as a specific article or section number that appears in more than one of them. If only one document is loaded, summarize its own position instead.", "expect": "cite"},
]

def _grade(resp, expect):
    cited = bool(resp.get("sources_used"))
    refused = bool(_REFUSAL_RE.search(resp.get("answer", "")))
    if cited:
        return "PASS"
    if expect == "cite_or_refuse" and refused:
        return "PASS"
    if resp.get("chunks_retrieved", 0) == 0:
        return "FAIL"
    if refused:
        return "PARTIAL"
    return "FAIL"

def run_accuracy_test(store, api_key, top_k=8, registry=None):
    results = []
    for item in TEST_QUESTIONS:
        question = item["question"]
        chunks = store.retrieve(question, top_k=top_k)
        if registry is not None:
            chunks = registry.add_identity_context(question, chunks)
        resp = query_compliance(question, chunks, api_key=api_key)
        status = _grade(resp, item["expect"])
        results.append({
            "question": question,
            "status": status,
            "cited": bool(resp.get("sources_used")),
            "n_chunks": len(chunks),
            "answer": resp.get("answer", ""),
        })
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    return {"accuracy_pct": round(100 * passed / total) if total else 0,
            "passed": passed, "total": total, "results": results}
