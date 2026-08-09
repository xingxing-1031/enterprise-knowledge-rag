from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from enterprise_knowledge_rag.models import (
    DocumentRecord,
    RetrievalCandidate,
    UserContext,
)
from enterprise_knowledge_rag.policy import (
    VersionResolutionStatus,
    can_access,
    resolve_effective_versions,
)

from .lexical import LexicalRetriever
from .reranker import Reranker
from .rrf import reciprocal_rank_fusion
from .vector import VectorRetriever


class RetrievalStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VERSION_AMBIGUOUS = "version_ambiguous"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    status: RetrievalStatus
    candidates: tuple[RetrievalCandidate, ...]
    authorized_document_keys: frozenset[tuple[str, str]]
    ambiguous_document_ids: tuple[str, ...] = ()


class CorpusSnapshot(Protocol):
    def list_documents(self) -> list[DocumentRecord]: ...

    def list_candidates(
        self,
        document_keys: frozenset[tuple[str, str]],
    ) -> list[RetrievalCandidate]: ...


class QueryEmbeddingProvider(Protocol):
    def embed_query(self, query: str) -> Sequence[float]: ...


class RetrievalService:
    def __init__(
        self,
        corpus: CorpusSnapshot,
        vector: VectorRetriever,
        query_embeddings: QueryEmbeddingProvider,
        reranker: Reranker,
    ) -> None:
        self._corpus = corpus
        self._vector = vector
        self._query_embeddings = query_embeddings
        self._reranker = reranker

    def retrieve(
        self,
        query: str,
        *,
        user: UserContext,
        as_of: datetime,
        requested_versions: Mapping[str, str] | None = None,
        pool_limit: int = 10,
        final_limit: int = 5,
    ) -> RetrievalResult:
        requested_versions = requested_versions or {}
        grouped: dict[str, list[DocumentRecord]] = defaultdict(list)
        for document in self._corpus.list_documents():
            if can_access(user, document):
                grouped[document.document_id].append(document)

        authorized_keys: set[tuple[str, str]] = set()
        ambiguous_ids: list[str] = []
        for document_id, documents in grouped.items():
            resolution = resolve_effective_versions(
                documents,
                as_of=as_of,
                requested_version=requested_versions.get(document_id),
            )
            if resolution.status is VersionResolutionStatus.SELECTED:
                selected = resolution.document
                authorized_keys.add((selected.document_id, selected.version))
            elif resolution.status is VersionResolutionStatus.AMBIGUOUS:
                ambiguous_ids.append(document_id)

        frozen_keys = frozenset(authorized_keys)
        lexical_candidates = self._corpus.list_candidates(frozen_keys)
        lexical = LexicalRetriever(lexical_candidates).search(
            query,
            limit=pool_limit,
        )
        vector = self._vector.search(
            self._query_embeddings.embed_query(query),
            document_keys=frozen_keys,
            limit=pool_limit,
        )
        fused = reciprocal_rank_fusion(
            {"bm25": lexical, "vector": vector},
            limit=pool_limit,
        )
        reranked = self._reranker.rerank(query, fused, limit=final_limit)

        if reranked:
            status = RetrievalStatus.READY
        elif ambiguous_ids:
            status = RetrievalStatus.VERSION_AMBIGUOUS
        else:
            status = RetrievalStatus.INSUFFICIENT_EVIDENCE
        return RetrievalResult(
            status=status,
            candidates=tuple(reranked),
            authorized_document_keys=frozen_keys,
            ambiguous_document_ids=tuple(sorted(ambiguous_ids)),
        )
