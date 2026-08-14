from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from time import perf_counter
from typing import Protocol

from enterprise_knowledge_rag.admin_models import (
    RetrievalDebugResponse,
    RetrievalDebugStage,
    SafeDebugCandidate,
)
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

    def retrieve_within_documents(
        self,
        query: str,
        *,
        document_keys: frozenset[tuple[str, str]],
        pool_limit: int = 10,
        final_limit: int = 5,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER,
    ) -> RetrievalResult:
        """Retrieve sections without resolving or expanding authorization."""

        if not document_keys:
            return RetrievalResult(
                status=RetrievalStatus.INSUFFICIENT_EVIDENCE,
                candidates=(),
                authorized_document_keys=frozenset(),
            )
        vector = self._vector.search(
            self._query_embeddings.embed_query(query),
            document_keys=document_keys,
            limit=pool_limit,
        )
        if strategy is RetrievalStrategy.VECTOR_BASELINE:
            selected = vector[:final_limit]
        else:
            lexical_candidates = self._corpus.list_candidates(document_keys)
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
        return RetrievalResult(
            status=(
                RetrievalStatus.READY
                if selected
                else RetrievalStatus.INSUFFICIENT_EVIDENCE
            ),
            candidates=tuple(selected),
            authorized_document_keys=document_keys,
        )

    def debug_retrieve(
        self,
        query: str,
        *,
        user: UserContext,
        as_of: datetime,
        top_k: int = 5,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER,
    ) -> RetrievalDebugResponse:
        """Return explainable retrieval telemetry without exposing chunk text."""

        started = perf_counter()

        def safe(candidate: RetrievalCandidate) -> SafeDebugCandidate:
            return SafeDebugCandidate(
                document_id=candidate.document.document_id,
                version=candidate.document.version,
                title=candidate.document.title,
                department=candidate.document.department,
                chunk_id=candidate.chunk.chunk_id,
                channels=tuple(sorted(candidate.channels)),
                channel_ranks=dict(candidate.channel_ranks),
                retrieval_score=round(float(candidate.retrieval_score), 6),
                reranker_score=(
                    round(float(candidate.reranker_score), 6)
                    if candidate.reranker_score is not None
                    else None
                ),
            )

        grouped: dict[str, list[DocumentRecord]] = defaultdict(list)
        for document in self._corpus.list_documents():
            grouped[document.document_id].append(document)
        authorized: set[tuple[str, str]] = set()
        denied = 0
        for document_id, documents in grouped.items():
            resolution = resolve_effective_versions(documents, as_of=as_of)
            if (
                resolution.status is VersionResolutionStatus.SELECTED
                and resolution.document
            ):
                if can_access(user, resolution.document):
                    authorized.add((document_id, resolution.document.version))
                elif _metadata_matches(query, resolution.document):
                    denied += 1
        auth_duration = int((perf_counter() - started) * 1000)
        stages: list[RetrievalDebugStage] = [
            RetrievalDebugStage(
                name="authorization",
                candidate_count=len(authorized),
                excluded_count=denied,
                duration_ms=auth_duration,
                note="仅统计授权后的文档数量，不返回被拒绝文档正文",
            )
        ]
        pool_limit = max(top_k * 2, 10)
        stage_started = perf_counter()
        query_vector = self._query_embeddings.embed_query(query)
        vector = self._vector.search(
            query_vector, document_keys=frozenset(authorized), limit=pool_limit
        )
        stages.append(
            RetrievalDebugStage(
                name="vector",
                candidate_count=len(vector),
                duration_ms=int((perf_counter() - stage_started) * 1000),
                candidates=tuple(safe(item) for item in vector[:top_k]),
            )
        )
        stage_started = perf_counter()
        lexical_candidates = self._corpus.list_candidates(frozenset(authorized))
        lexical = LexicalRetriever(lexical_candidates).search(query, limit=pool_limit)
        stages.insert(
            1,
            RetrievalDebugStage(
                name="bm25",
                candidate_count=len(lexical),
                duration_ms=int((perf_counter() - stage_started) * 1000),
                candidates=tuple(safe(item) for item in lexical[:top_k]),
            ),
        )
        stage_started = perf_counter()
        fused = reciprocal_rank_fusion(
            {"bm25": lexical, "vector": vector}, limit=pool_limit
        )
        stages.append(
            RetrievalDebugStage(
                name="rrf",
                candidate_count=len(fused),
                duration_ms=int((perf_counter() - stage_started) * 1000),
                candidates=tuple(safe(item) for item in fused[:top_k]),
            )
        )
        if strategy is RetrievalStrategy.VECTOR_BASELINE:
            final = vector[:top_k]
            reranked: list[RetrievalCandidate] = []
        elif strategy is RetrievalStrategy.HYBRID_RRF:
            final = fused[:top_k]
            reranked = []
        else:
            stage_started = perf_counter()
            reranked = self._reranker.rerank(query, fused, limit=top_k)
            final = reranked
        stages.append(
            RetrievalDebugStage(
                name="rerank",
                candidate_count=len(reranked) if reranked else len(final),
                duration_ms=(
                    int((perf_counter() - stage_started) * 1000)
                    if reranked
                    else 0
                ),
                candidates=tuple(safe(item) for item in final[:top_k]),
                note="向量基线和 RRF 方案跳过重排",
            )
        )
        stages.append(
            RetrievalDebugStage(
                name="evidence",
                candidate_count=len(final),
                duration_ms=0,
                candidates=tuple(safe(item) for item in final[:top_k]),
            )
        )
        return RetrievalDebugResponse(
            query=query,
            strategy=strategy.value,
            simulated_role=user.role.value,
            simulated_departments=tuple(sorted(user.departments)),
            status="ready"
            if final
            else ("permission_denied" if denied else "insufficient_evidence"),
            stages=tuple(stages),
            total_duration_ms=int((perf_counter() - started) * 1000),
        )
