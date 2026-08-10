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

from .lexical import LexicalRetriever, tokenize
from .reranker import Reranker
from .rrf import reciprocal_rank_fusion
from .vector import VectorRetriever


class RetrievalStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VERSION_AMBIGUOUS = "version_ambiguous"
    PERMISSION_DENIED = "permission_denied"


class RetrievalStrategy(StrEnum):
    VECTOR_BASELINE = "vector_baseline"
    HYBRID_RRF = "hybrid_rrf"
    HYBRID_RRF_RERANKER = "hybrid_rrf_reranker"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    status: RetrievalStatus
    candidates: tuple[RetrievalCandidate, ...]
    authorized_document_keys: frozenset[tuple[str, str]]
    ambiguous_document_ids: tuple[str, ...] = ()
    denied_match_count: int = 0


def _metadata_matches(query: str, document: DocumentRecord) -> bool:
    query_tokens = {token for token in tokenize(query) if len(token) >= 2}
    metadata_tokens = {
        token
        for token in tokenize(
            f"{document.title} {document.document_id} {document.department}"
        )
        if len(token) >= 2
    }
    overlap = query_tokens & metadata_tokens
    return len(overlap) >= 2 or any(len(token) >= 4 for token in overlap)


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
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER,
    ) -> RetrievalResult:
        requested_versions = requested_versions or {}
        grouped: dict[str, list[DocumentRecord]] = defaultdict(list)
        for document in self._corpus.list_documents():
            grouped[document.document_id].append(document)

        authorized_keys: set[tuple[str, str]] = set()
        ambiguous_ids: list[str] = []
        denied_match_count = 0
        for document_id, documents in grouped.items():
            resolution = resolve_effective_versions(
                documents,
                as_of=as_of,
                requested_version=requested_versions.get(document_id),
            )
            if resolution.status is VersionResolutionStatus.SELECTED:
                selected = resolution.document
                if can_access(user, selected):
                    authorized_keys.add((selected.document_id, selected.version))
                elif _metadata_matches(query, selected):
                    denied_match_count += 1
            elif resolution.status is VersionResolutionStatus.AMBIGUOUS:
                if any(can_access(user, document) for document in documents):
                    ambiguous_ids.append(document_id)

        frozen_keys = frozenset(authorized_keys)
        vector = self._vector.search(
            self._query_embeddings.embed_query(query),
            document_keys=frozen_keys,
            limit=pool_limit,
        )
        if strategy is RetrievalStrategy.VECTOR_BASELINE:
            selected = vector[:final_limit]
        else:
            lexical_candidates = self._corpus.list_candidates(frozen_keys)
            lexical = LexicalRetriever(lexical_candidates).search(
                query,
                limit=pool_limit,
            )
            fused = reciprocal_rank_fusion(
                {"bm25": lexical, "vector": vector},
                limit=pool_limit,
            )
            selected = (
                fused[:final_limit]
                if strategy is RetrievalStrategy.HYBRID_RRF
                else self._reranker.rerank(query, fused, limit=final_limit)
            )

        if selected:
            status = RetrievalStatus.READY
        elif ambiguous_ids:
            status = RetrievalStatus.VERSION_AMBIGUOUS
        elif denied_match_count:
            status = RetrievalStatus.PERMISSION_DENIED
        else:
            status = RetrievalStatus.INSUFFICIENT_EVIDENCE
        return RetrievalResult(
            status=status,
            candidates=tuple(selected),
            authorized_document_keys=frozen_keys,
            ambiguous_document_ids=tuple(sorted(ambiguous_ids)),
            denied_match_count=denied_match_count,
        )
