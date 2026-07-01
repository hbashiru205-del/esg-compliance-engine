import anthropic
from config.settings import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS


SYSTEM_PROMPT = """You are a regulatory compliance analyst. Your job is to answer questions
strictly based on the document excerpts provided to you.

RULES YOU MUST FOLLOW:
1. Only use information from the provided excerpts to answer.
2. If the answer is not in the excerpts, say: "This information is not found in the uploaded documents."
3. Always cite your source using this format: [Source: filename, Chunk #N]
4. Never guess, infer, or use external knowledge.
5. Be precise. Compliance answers must be accurate and unambiguous.
6. If multiple excerpts are relevant, synthesize them and cite each one used.
"""


def build_context(retrieved_chunks: list) -> str:
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        source = chunk.get("source", "Unknown")
        text   = chunk.get("text", "")
        context_parts.append(
            f"--- Excerpt {i} [Source: {source}, Chunk #{chunk.get('index', i)}] ---\n{text}"
        )
    return "\n\n".join(context_parts)


def query_compliance(
    question: str,
    retrieved_chunks: list,
    api_key: str = None,
    chat_history: list = None,
) -> dict:
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        return {
            "answer": "No API key provided. Please enter your Anthropic API key in the sidebar.",
            "sources_used": [],
            "chunks_retrieved": 0,
        }

    if not retrieved_chunks:
        return {
            "answer": "No relevant document sections found. Please upload a regulatory document first.",
            "sources_used": [],
            "chunks_retrieved": 0,
        }

    context = build_context(retrieved_chunks)

    user_message = f"""Use ONLY the excerpts below to answer the question.

DOCUMENT EXCERPTS:
{context}

QUESTION: {question}

Provide a clear, cited answer based solely on the excerpts above."""

    messages = []
    if chat_history:
        for turn in chat_history[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    client = anthropic.Anthropic(api_key=key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    answer = response.content[0].text

    import re
    sources = list(set(re.findall(r'\[Source:[^\]]+\]', answer)))

    return {
        "answer":           answer,
        "sources_used":     sources,
        "chunks_retrieved": len(retrieved_chunks),
                            }
