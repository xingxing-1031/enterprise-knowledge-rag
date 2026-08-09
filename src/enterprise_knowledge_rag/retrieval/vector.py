from collections.abc import Sequence
from typing import Protocol

from enterprise_knowledge_rag.models import RetrievalCandidate


class VectorSearchBackend(Protocol):
    def search_authorized(
        self,
        query_vector: Sequence[float],
        *,
        document_keys: frozenset[tuple[str, str]],
        limit: int,
    ) -> list[RetrievalCandidate]: ...


class VectorRetriever:
    """Adapter that requires authorized document-version keys on every query."""

    def __init__(self, backend: VectorSearchBackend) -> None:
        self._backend = backend

    def search(
        self,
        query_vector: Sequence[float],
        *,
        document_keys: frozenset[tuple[str, str]],
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not document_keys:
            return []

        candidates = self._backend.search_authorized(
            query_vector,
            document_keys=document_keys,
            limit=limit,
        )
        return [
            candidate.model_copy(
                update={
                    "channels": {"vector"},
                    "channel_ranks": {"vector": rank},
                }
            )
            for rank, candidate in enumerate(candidates, start=1)
        ]
