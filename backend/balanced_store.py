"""Balanced retrieval: every document with a matching chunk gets a slot,
and unused slots are handed to the other documents (round-robin)."""
from backend.vector_store import (
    VectorStore, _tokenize, _tfidf_vector, _cosine,
)


class BalancedStore(VectorStore):
    def retrieve(self, query: str, top_k: int = 5):
        if not self._built:
            self._build_index()
        q_vec = _tfidf_vector(_tokenize(query), self.vocab)
        scored = [(_cosine(q_vec, v), i) for i, v in enumerate(self.vectors)]
        scored.sort(reverse=True)

        by_src = {}
        for s, i in scored:
            if s > 0:
                src = self.chunks[i].get("source", "unknown")
                by_src.setdefault(src, []).append((s, i))
        if not by_src:
            return []

        # Documents ordered by their best match, then one chunk each per round.
        order = sorted(by_src, key=lambda k: by_src[k][0], reverse=True)
        picked, depth = [], 0
        while len(picked) < top_k:
            added = False
            for src in order:
                if depth < len(by_src[src]) and len(picked) < top_k:
                    picked.append(by_src[src][depth])
                    added = True
            if not added:
                break
            depth += 1

        picked.sort(reverse=True)
        return [{**self.chunks[i], "score": round(s, 4)} for s, i in picked]
