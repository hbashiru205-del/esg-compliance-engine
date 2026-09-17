from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY, MODEL, MAX_TOKENS


SYSTEM_PROMPT = """You are a regulatory compliance analyst. Your job is to answer questions
strictly based on the document excerpts provided to you, using careful step-by-step legal
reasoning rather than simple keyword lookup.

REASONING PROCESS — follow this for every answer:
1. Identify the general rule that applies to the question, citing its source.
2. Check the provided excerpts for any exceptions, conditions, or qualifications that might
   modify that general rule (phrases like "unless", "except where", "subject to", "provided that").
3. Check for any cross-references to other sections/articles (e.g. "as defined in Article X") —
   if a referenced section is NOT included in the excerpts provided, explicitly flag this rather
   than assuming the exception doesn't apply.
4. If excerpts come from MORE THAN ONE source document, explicitly compare them: state what each
   document says on the relevant point, label which document each claim comes from, and note
   where they align, differ, or where one is stricter or more specific than the other.
5. Apply the rule, any relevant exceptions, and any cross-document comparison to reach a final answer.

RULES YOU MUST FOLLOW:
1. Only use information from the provided excerpts to answer.
2. If the answer is not in the excerpts, say: "This information is not found in the uploaded documents."
3. Always cite your source using this format: [Source: filename, Chunk #N]
4. Never guess, infer, or use external knowledge.
5. If you identify a cross-reference to a section not included in the excerpts, explicitly note:
   "This may be qualified by [reference], which is not included in the retrieved excerpts —
   recommend verifying."
6. If multiple excerpts are relevant, synthesize them and cite each one used.
7. If the question asks how requirements differ between documents (e.g. between a baseline
   standard and a specific jurisdiction's implementation), structure your answer to address
   each document's position explicitly, by name, before giving a combined conclusion.

OUTPUT FORMAT — structure your response EXACTLY like this, with these two labels on their own lines:
REASONING: [Your step-by-step reasoning process — 2-4 sentences walking through the rule,
any exceptions found, any cross-references checked, and any cross-document comparison made]
ANSWER: [Your final, clear answer with citations]
"""


def build_context(retrieved_chunks: list) -> str:
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        source = chunk.get("source", "Unknown")
        text   = chunk.get("text", "")
        context_parts.append(
            f"--- Excerpt {i} [DOCUMENT: {source}, Chunk #{chunk.get('index', i)}] ---\n{text}"
        )

    unique_sources = sorted(set(c.get("source", "Unknown") for c in retrieved_chunks))
    if len(unique_sources) > 1:
        header = (
            f"NOTE: These excerpts come from {len(unique_sources)} different documents: "
            f"{', '.join(unique_sources)}. Compare them explicitly where relevant.\n\n"
        )
        return header + "\n\n".join(context_parts)

    return "\n\n".join(context_parts)


def parse_reasoning_response(raw_text: str) -> dict:
    reasoning = ""
    answer = raw_text.strip()

    if "REASONING:" in raw_text and "ANSWER:" in raw_text:
        try:
            after_reasoning = raw_text.split("REASONING:", 1)[1]
            reasoning_part, answer_part = after_reasoning.split("ANSWER:", 1)
            reasoning = reasoning_part.strip()
            answer = answer_part.strip()
        except (IndexError, ValueError):
            reasoning = ""
            answer = raw_text.strip()

    return {"reasoning": reasoning, "answer": answer}


def query_compliance(
    question: str,
    retrieved_chunks: list,
    api_key: str = None,
    chat_history: list = None,
) -> dict:
    key = api_key or GEMINI_API_KEY
    if not key:
        return {
            "answer": "No API key provided. Please contact support.",
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": 0,
        }

    if not retrieved_chunks:
        return {
            "answer": "No relevant document sections found. Please upload a regulatory document first.",
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": 0,
        }

    context = build_context(retrieved_chunks)

    user_message = f"""Use ONLY the excerpts below to answer the question.

DOCUMENT EXCERPTS:
{context}

QUESTION: {question}

Follow the REASONING PROCESS from your instructions, then provide your answer in the
REASONING: / ANSWER: format specified."""

    contents = []
    if chat_history:
        for turn in chat_history[-6:]:
            role = "model" if turn["role"] == "assistant" else "user"
            content_text = turn.get("answer_only", turn.get("content", ""))
            contents.append(
                types.Content(role=role, parts=[types.Part(text=content_text)])
            )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=user_message)])
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

        raw_text = response.text

    except Exception as e:
        return {
            "answer": f"Error calling Gemini API: {str(e)}",
            "reasoning": "",
            "sources_used": [],
            "chunks_retrieved": len(retrieved_chunks),
        }

    parsed = parse_reasoning_response(raw_text)

    import re
    sources = list(set(re.findall(r'\[Source:[^\]]+\]', parsed["answer"])))

    return {
        "answer":           parsed["answer"],
        "reasoning":        parsed["reasoning"],
        "sources_used":     sources,
        "chunks_retrieved": len(retrieved_chunks),
    }
