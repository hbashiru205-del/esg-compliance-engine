# ClariX Intelligence — implementation notes

This version adds a shared structured regulatory requirement layer.

Flow:
PDF -> retrieval -> structured requirement -> Regulatory Intelligence
                                      -> client evidence -> Gap Analysis

New:
- backend/requirement_engine.py
- page_start/page_end/section_reference metadata on extracted chunks
- Regulatory Intelligence tab
- client evidence upload + evidence assessment
- no hidden chain-of-thought is stored by the new requirement/gap workflow

The existing Ask Questions, trial, exports, and accuracy-test flows remain in place.
