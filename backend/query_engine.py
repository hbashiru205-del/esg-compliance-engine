import re

from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY, MODEL, MAX_TOKENS
from backend.requirement_engine import extract_requirements


SYSTEM_PROMPT = """
You are a regulatory compliance analyst.

Your job is to answer questions strictly from the supplied regulatory
document excerpts.

IMPORTANT:
Do not use outside knowledge.
Do not invent legal requirements.
Do not invent Article numbers, paragraph numbers, exceptions, dates,
thresholds, or definitions.

For every answer:

1. Identify the relevant requirement or rule.
2. Check the supplied excerpts for conditions or qualifications.
3. Check for explicit exceptions.
4. Check for cross-references to other provisions.
5. If multiple documents are present, distinguish which document supports
   each claim.
6. Give a clear answer based only on the evidence supplied.

If the answer is not contained in the supplied excerpts, say:

"This information is not found in the uploaded documents."

Always cite the supplied source using:

[Source: filename, Chunk #N]

If a page number is available, also include:

[Page: N]

If a regulatory Article, paragraph, or section reference is available,
include it in the citation.

Never claim that a company or person is legally compliant or non-compliant
unless the supplied document explicitly establishes that conclusion.
"""


def build_context(retrieved_chunks: list) -> str:
    """
    Build the document context supplied to Gemini.
    """

    context_parts = []

    for i, chunk in enumerate(retrieved_chunks, 1):

        source = chunk.get("source", "Unknown")
        text = chunk.get("text", "")

        page = chunk.get("page")

        reference = chunk.get(
            "regulatory_reference",
            "",
        )

        metadata = (
            f"DOCUMENT: {source}\n"
            f"CHUNK: #{chunk.get('index', i)}\n"
        )

        if page:
            metadata += f"PAGE: {page}\n"

        if reference:
            metadata += (
                f"REGULATORY REFERENCE: {reference}\n"
            )

        context_parts.append(
            f"--- EXCERPT {i} ---\n"
            f"{metadata}"
            f"TEXT:\n{text}"
        )

    return "\n\n".join(context_parts)


def parse_response(raw_text: str) -> dict:
    """
    Clean the model response.
    """

    answer = (raw_text or "").strip()

    return {
        "answer": answer,
    }


def query_compliance(
    question: str,
    retrieved_chunks: list,
    api_key: str = None,
    chat_history: list = None,
) -> dict:
    """
    Main regulatory question-answering function.

    Existing callers can continue using this function.

    In addition to the normal answer, the response now contains structured
    regulatory requirements extracted from the retrieved excerpts.
    """

    key = api_key or GEMINI_API_KEY

    if not key:
        return {
            "answer": "No API key provided. Please contact support.",
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": 0,
            "requirements": [],
        }

    if not retrieved_chunks:
        return {
            "answer": (
                "No relevant document sections found. "
                "Please upload a regulatory document first."
            ),
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": 0,
            "requirements": [],
        }

    context = build_context(retrieved_chunks)

    user_message = f"""
Use ONLY the supplied regulatory excerpts to answer the question.

DOCUMENT EXCERPTS:

{context}

QUESTION:

{question}

Answer clearly and concisely.

For every important statement, cite the supporting source.

If the information cannot be established from the supplied excerpts,
say that it is not found in the uploaded documents.
"""

    contents = []

    if chat_history:
        for turn in chat_history[-6:]:

            role = (
                "model"
                if turn.get("role") == "assistant"
                else "user"
            )

            content_text = turn.get(
                "answer_only",
                turn.get("content", ""),
            )

            contents.append(
                types.Content(
                    role=role,
                    parts=[
                        types.Part(
                            text=content_text
                        )
                    ],
                )
            )

    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text=user_message
                )
            ],
        )
    )

    try:

        client = genai.Client(api_key=key)

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=MAX_TOKENS,
            ),
        )

        raw_text = response.text or ""

    except Exception as e:

        return {
            "answer": f"Error calling Gemini API: {str(e)}",
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": len(
                retrieved_chunks
            ),
            "requirements": [],
        }

    parsed = parse_response(raw_text)

    answer = parsed["answer"]

    sources = list(
        set(
            re.findall(
                r"\[Source:[^\]]+\]",
                answer,
            )
        )
    )

    # ---------------------------------------------------------
    # NEW: STRUCTURED REGULATORY REQUIREMENTS
    # ---------------------------------------------------------
    #
    # This is the layer that lets ClariX move beyond simple RAG.
    #
    # The same retrieved excerpts used for the answer are passed
    # through the requirement engine.
    #
    # This produces structured objects containing:
    # requirement
    # subject
    # action
    # object
    # conditions
    # exceptions
    # scope
    # cross-references
    # source
    #
    # The existing answer remains unchanged for compatibility.
    # ---------------------------------------------------------

    try:

        requirements = extract_requirements(
            retrieved_chunks,
            api_key=key,
            max_requirements=10,
        )

    except Exception:

        requirements = []

    return {
        "answer": answer,
        "reasoning": "",
        "sources_used": sources,
        "chunks_retrieved": len(
            retrieved_chunks
        ),
        "requirements": requirements,
   }
