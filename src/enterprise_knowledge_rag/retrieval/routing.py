from collections.abc import Sequence
from typing import Protocol

from pydantic import Field
from rank_bm25 import BM25Okapi

from enterprise_knowledge_rag.documents.repository import (
    ParentDocumentMatch,
    ParentDocumentSource,
)
from enterprise_knowledge_rag.models import DocumentType, StrictModel

from .lexical import tokenize


class DocumentRouteCandidate(StrictModel):
    """A routed parent document with explainable channel ranks."""

    document_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_type: DocumentType
    department: str = Field(min_length=1)
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_rank: int | None = Field(default=None, ge=1)
    channels: set[str] = Field(default_factory=set)
    fused_score: float = 0.0


class DocumentRouteRepository(Protocol):
    def list_document_route_sources(
        self,
        document_keys: frozenset[tuple[str, str]],
    ) -> Sequence[ParentDocumentSource]: ...

    def search_documents(
        self,
        query_vector: Sequence[float],
        *,
        document_keys: frozenset[tuple[str, str]],
        limit: int,
    ) -> Sequence[ParentDocumentMatch]: ...


class QueryEmbeddingProvider(Protocol):
    def embed_query(self, query: str) -> Sequence[float]: ...


class DocumentRouter:
    """Route questions to authorized parent documents with BM25 + vector RRF."""

    def __init__(
        self,
        repository: DocumentRouteRepository,
        query_embeddings: QueryEmbeddingProvider,
        *,
        rrf_k: int = 60,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        self._repository = repository
        self._query_embeddings = query_embeddings
        self._rrf_k = rrf_k

    @staticmethod
    def _lexical_rank(
        query: str,
        sources: Sequence[ParentDocumentSource],
        *,
        limit: int,
    ) -> list[ParentDocumentSource]:
        if not sources:
            return []
        corpus = [tokenize(source.document_search_text) for source in sources]
        bm25 = BM25Okapi(corpus)
        query_tokens = tokenize(query)
        scores = bm25.get_scores(query_tokens)
        query_set = set(query_tokens)
        overlaps = [len(query_set.intersection(tokens)) for tokens in corpus]
        ranked = sorted(
            range(len(sources)),
            key=lambda index: (-float(scores[index]), -overlaps[index], index),
        )
        return [
            sources[index]
            for index in ranked
            if overlaps[index] > 0
        ][:limit]

    def route(
        self,
        query: str,
        document_keys: frozenset[tuple[str, str]],
        *,
        limit: int = 4,
    ) -> tuple[DocumentRouteCandidate, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not document_keys:
            return ()

        # The caller supplies server-resolved authorization and versions. Keep
        # that set as the security boundary for every channel and final merge.
        authorized = frozenset(document_keys)
        raw_sources = self._repository.list_document_route_sources(authorized)
        sources = [
            ParentDocumentSource.model_validate(source) for source in raw_sources
        ]
        sources = [
            source
            for source in sources
            if (source.document_id, source.version) in authorized
        ]
        source_by_key = {(item.document_id, item.version): item for item in sources}

        lexical = self._lexical_rank(query, sources, limit=limit)
        lexical_ranks = {
            (item.document_id, item.version): rank
            for rank, item in enumerate(lexical, start=1)
        }

        vector_matches = self._repository.search_documents(
            self._query_embeddings.embed_query(query),
            document_keys=authorized,
            limit=limit,
        )
        vector = [
            ParentDocumentMatch.model_validate(item)
            for item in vector_matches
            if (item.document_id, item.version) in authorized
        ]
        vector_ranks = {
            (item.document_id, item.version): rank
            for rank, item in enumerate(vector, start=1)
        }
        vector_by_key = {(item.document_id, item.version): item for item in vector}

        keys = set(lexical_ranks) | set(vector_ranks)
        scores = {
            key: sum(
                1.0 / (self._rrf_k + rank)
                for rank in (lexical_ranks.get(key), vector_ranks.get(key))
                if rank is not None
            )
            for key in keys
        }
        ordered_keys = sorted(
            keys,
            key=lambda key: (
                -scores[key],
                min(
                    rank
                    for rank in (lexical_ranks.get(key), vector_ranks.get(key))
                    if rank is not None
                ),
                key,
            ),
        )[:limit]

        routes: list[DocumentRouteCandidate] = []
        for key in ordered_keys:
            source = source_by_key.get(key)
            match = vector_by_key.get(key)
            if source is None and match is None:
                continue
            metadata = source or match
            assert metadata is not None
            routes.append(
                DocumentRouteCandidate(
                    document_id=metadata.document_id,
                    version=metadata.version,
                    title=metadata.title,
                    document_type=metadata.document_type,
                    department=metadata.department,
                    lexical_rank=lexical_ranks.get(key),
                    vector_rank=vector_ranks.get(key),
                    channels={
                        channel
                        for channel, rank in (
                            ("bm25", lexical_ranks.get(key)),
                            ("vector", vector_ranks.get(key)),
                        )
                        if rank is not None
                    },
                    fused_score=scores[key],
                )
            )
        return tuple(routes)
