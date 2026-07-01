"""
Accuracy test suite.
Run this after uploading a document to evaluate system performance.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.vector_store import VectorStore
from backend.query_engine import query_compliance


SAMPLE_QA = [
    {
        "question": "What are the main disclosure requirements?",
        "keywords": ["disclosure", "report", "require"],
    },
    {
        "question": "What penalties or fines apply for non-compliance?",
        "keywords": ["penalty", "fine", "sanction", "breach"],
    },
    {
        "question": "What is the reporting deadline or timeline?",
        "keywords": ["deadline", "date", "period", "annual", "quarterly"],
    },
    {
        "question": "Who is responsible for compliance oversight?",
        "keywords": ["officer", "board", "responsible", "management", "committee"],
    },
    {
        "question": "What data or metrics must be collected?",
        "keywords": ["data", "metric", "measure", "indicator", "scope"],
    },
]


def run_accuracy_test(store: VectorStore, api_key: str, top_k: int = 5):
    """Run all sample questions and return a results report."""
    results = []
    passed  = 0

    for qa in SAMPLE_QA:
        question = qa["question"]
        keywords = qa["keywords"]

        chunks   = store.retrieve(question, top_k=top_k)
        response = query_compliance(question, chunks, api_key=api_key)
        answer   = response["answer"].lower()

        found  = "not found in the uploaded" not in answer
        kw_hit = any(kw in answer for kw in keywords)
        cited  = "[source:" in answer.lower()

        status = "PASS" if (found and cited) else "PARTIAL" if found else "FAIL"
        if status == "PASS":
            passed += 1

        results.append({
            "question":   question,
            "status":     status,
            "cited":      cited,
            "kw_hit":     kw_hit,
            "answer":     response["answer"],
            "n_chunks":   response["chunks_retrieved"],
        })

    accuracy = round((passed / len(SAMPLE_QA)) * 100, 1)
    return {"accuracy_pct": accuracy, "passed": passed,
            "total": len(SAMPLE_QA), "results": results}
