from collections.abc import Sequence
from typing import Protocol

from enterprise_knowledge_rag.models import RetrievalCandidate


class RerankerScoreProvider(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class Reranker:
    def __init__(self, provider: RerankerScoreProvider) -> None:
        self._provider = provider

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        *,
        limit: int = 5,
    ) -> list[RetrievalCandidate]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not candidates:
            return []

        scores = self._provider.score(
            query,
            [candidate.chunk.content for candidate in candidates],
        )
        if len(scores) != len(candidates):
            raise ValueError("reranker returned a different number of scores")

        scored = [
            candidate.model_copy(update={"reranker_score": float(score)})
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        return sorted(
            scored,
            key=lambda candidate: (
                -float(candidate.reranker_score),
                -candidate.retrieval_score,
                candidate.chunk.chunk_id,
            ),
        )[:limit]
