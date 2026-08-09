from collections.abc import Iterable

import jieba
from rank_bm25 import BM25Okapi

from enterprise_knowledge_rag.models import RetrievalCandidate


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese while retaining policy identifiers and numbers."""

    normalized = text.lower().strip()
    return [
        token.strip() for token in jieba.lcut_for_search(normalized) if token.strip()
    ]


class LexicalRetriever:
    """In-memory BM25 index rebuilt from an authorized corpus snapshot."""

    def __init__(self, candidates: Iterable[RetrievalCandidate]) -> None:
        self._candidates = list(candidates)
        self._corpus_tokens = [
            tokenize(
                " ".join(
                    [
                        candidate.document.title,
                        candidate.document.document_id,
                        ">".join(candidate.chunk.section_path),
                        candidate.chunk.content,
                    ]
                )
            )
            for candidate in self._candidates
        ]
        self._bm25 = BM25Okapi(self._corpus_tokens) if self._corpus_tokens else None

    def search(self, query: str, *, limit: int = 10) -> list[RetrievalCandidate]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if self._bm25 is None:
            return []

        query_tokens = tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        query_set = set(query_tokens)
        overlaps = [
            len(query_set.intersection(tokens)) for tokens in self._corpus_tokens
        ]
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: (-float(scores[index]), -overlaps[index], index),
        )
        results: list[RetrievalCandidate] = []
        for index in ranked_indices:
            score = float(scores[index])
            if overlaps[index] == 0:
                continue
            rank = len(results) + 1
            results.append(
                self._candidates[index].model_copy(
                    update={
                        "channels": {"bm25"},
                        "channel_ranks": {"bm25": rank},
                        "retrieval_score": score,
                    }
                )
            )
            if len(results) >= limit:
                break
        return results
