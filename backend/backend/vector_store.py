"""
Lightweight in-memory vector store using TF-IDF style scoring.
No external API needed — works offline.
For production, swap retrieve() with a Pinecone call.
"""
import re
import math
from collections import Counter


def _tokenize(text: str):
    return re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())


def _tfidf_vector(tokens: list, vocab: dict):
    counts = Counter(tokens)
    vec = {}
    for term, count in counts.items():
        if term in vocab:
            tf  = count / max(len(tokens), 1)
            idf = vocab[term]["idf"]
            vec[term] = tf * idf
    return vec


def _cosine(v1: dict, v2: dict):
    shared = set(v1) & set(v2)
    if not shared:
        return 0.0
    dot  = sum(v1[t] * v2[t] for t in shared)
    mag1 = math.sqrt(sum(x**2 for x in v1.values()))
    mag2 = math.sqrt(sum(x**2 for x in v2.values()))
    return dot / (mag1 * mag2 + 1e-9)


class VectorStore:
    def __init__(self):
        self.chunks  = []
        self.vectors = []
        self.vocab   = {}
        self._built  = False

    def add_chunks(self, chunks: list):
        self.chunks.extend(chunks)
        self._built = False

    def _build_index(self):
        N = len(self.chunks)
        if N == 0:
            return

        df = Counter()
        token_lists = []
        for c in self.chunks:
            tokens = _tokenize(c["text"])
            token_lists.append(tokens)
            for t in set(tokens):
                df[t] += 1

        self.vocab = {
            term: {"idf": math.log((N + 1) / (count + 1)) + 1}
            for term, count in df.items()
        }

        self.vectors = [_tfidf_vector(tl, self.vocab) for tl in token_lists]
        self._built = True

    def retrieve(self, query: str, top_k: int = 5):
        if not self._built:
            self._build_index()

        q_tokens = _tokenize(query)
        q_vec    = _tfidf_vector(q_tokens, self.vocab)

        scores = [(_cosine(q_vec, v), i) for i, v in enumerate(self.vectors)]
        scores.sort(reverse=True)

        results = []
        for score, idx in scores[:top_k]:
            if score > 0:
                results.append({**self.chunks[idx], "score": round(score, 4)})

        return results

    def clear(self):
        self.chunks  = []
        self.vectors = []
        self.vocab   = {}
        self._built  = False

    @property
    def doc_count(self):
        return len(self.chunks)
