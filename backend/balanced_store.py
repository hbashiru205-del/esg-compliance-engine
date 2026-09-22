"""Balanced retrieval: every document with a matching chunk gets a slot,
and unused slots are handed to the other documents (round-robin).

Also replaces the base tokenizer, which keeps only letter runs and so
drops every regulation number, article number and year (a query for
"Article 19a" or "Regulation 2022/2464" would score no better than one
with those numbers removed). Numeric/identifier tokens are added
alongside the original word tokens; nothing that matched before stops
matching.
"""
import math
import re
from collections import Counter
from backend.vector_store import VectorStore, _tfidf_vector, _cosine

_WORD_RE = re.compile(r'\b[a-zA-Z]{2,}\b')
# Article/section numbers ("19a", "24"), regulation and directive
# numbers ("2022/2464"), years, dotted section numbers ("6.3.1").
_NUM_RE = re.compile(r'\b\d{1,4}(?:[/.\-]\d{1,4})*[a-zA-Z]?\b')
# The actual start of an article -- "Article 24" on its own line,
# immediately followed by a title line -- as opposed to any of the many
# places a real document mentions "Article 24" in passing (a
# cross-reference to a clause earlier in the same document, or, just as
# often, to a completely different law's Article 24). A chunk matching
# this is almost certainly the article's own text, not a passing
# mention of it, which the plain number-token check two paragraphs down
# can't tell apart. Confirmed against two real EU regulation PDFs: every
# real article heading in both (39/39 and 20/20) matches this pattern.
_HEADING_RE = re.compile(r'\bArticle\s+(\d{1,4}[a-zA-Z]?)\s*\n\s*[A-Z][^\n]{2,150}\n')
# Page markers our own document_processor inserts (e.g. "[Page 12]") are
# excluded from number tokens only, so a page break isn't indexed as if
# "12" were a figure from the regulation's own text. Word tokens (e.g.
# "page" itself) are left untouched, so content with no real numbers in
# it tokenizes exactly as it did before this file existed.
_PAGE_TAG_RE = re.compile(r'\[Page\s+\d+\]', re.IGNORECASE)


def _tokenize(text: str):
    words = _WORD_RE.findall(text.lower())
    nums_source = _PAGE_TAG_RE.sub(" ", text)
    nums = [t.lower() for t in _NUM_RE.findall(nums_source)]
    return words + nums


def _heading_numbers(text: str):
    return {n.lower() for n in _HEADING_RE.findall(text)}


class BalancedStore(VectorStore):
    def _build_index(self):
        """Same as the base class, but indexing with the tokenizer above."""
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
        # Precomputed once per chunk, not per query -- see _heading_numbers.
        self._heading_nums = [_heading_numbers(c["text"]) for c in self.chunks]
        self._built = True

    def retrieve(self, query: str, top_k: int = 5):
        if not self._built:
            self._build_index()
        q_tokens = _tokenize(query)
        q_vec = _tfidf_vector(q_tokens, self.vocab)

        # A query token that IS a number/identifier ("24", "2022/2464").
        # Two tiers of match on it, checked in order:
        #  1. heading: this chunk is the actual start of that numbered
        #     article/section, not just a chunk that happens to mention
        #     it -- necessary because real documents cross-reference
        #     article numbers constantly, including to completely
        #     different laws, so the number alone is often ambiguous
        #     among a dozen+ chunks.
        #  2. exact: the token appears in the chunk somewhere, but not
        #     confirmed as that chunk being the article's own text.
        # Either tier is pulled ahead of chunks that only share generic
        # words with the question; heading beats exact beats neither.
        q_nums = {t for t in q_tokens if _NUM_RE.fullmatch(t)}

        def rank(i):
            cos = _cosine(q_vec, self.vectors[i])
            exact = bool(q_nums) and any(n in self.vectors[i] for n in q_nums)
            heading = bool(q_nums) and bool(q_nums & self._heading_nums[i])
            return (heading, exact, cos)

        scored = [(rank(i), i) for i in range(len(self.vectors))]
        scored.sort(reverse=True)

        by_src = {}
        for key, i in scored:
            heading, exact, cos = key
            if not heading and not exact and cos <= 0:
                continue
            src = self.chunks[i].get("source", "unknown")
            by_src.setdefault(src, []).append((key, i))
        if not by_src:
            return []

        # Documents ordered by their best match, then one chunk each per round.
        order = sorted(by_src, key=lambda k: by_src[k][0][0], reverse=True)
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
        return [{**self.chunks[i], "score": round(key[2], 4)}
                for key, i in picked]
