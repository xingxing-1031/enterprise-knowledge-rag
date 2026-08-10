from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from pydantic import Field

from enterprise_knowledge_rag.documents.source_models import RetrievalPlan
from enterprise_knowledge_rag.models import (
    DocumentRecord,
    RetrievalCandidate,
    StrictModel,
    UserContext,
)
from enterprise_knowledge_rag.policy import (
    VersionResolutionStatus,
    can_access,
    resolve_effective_versions,
)

from .coverage import CoverageResult, EvidenceCoverageService
from .routing import DocumentRouteCandidate, DocumentRouter
from .service import RetrievalService, RetrievalStatus, RetrievalStrategy


class DocumentCorpus(Protocol):
    def list_documents(self) -> list[DocumentRecord]: ...


class HierarchicalRetrievalResult(StrictModel):
    status: RetrievalStatus
    routes: tuple[DocumentRouteCandidate, ...] = ()
    evidence_candidates: tuple[RetrievalCandidate, ...] = ()
    coverage: CoverageResult
    hop_count: int = Field(ge=0, le=2)


def _merge_candidates(
    *groups: Sequence[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    merged: list[RetrievalCandidate] = []
    positions: dict[str, int] = {}
    content_hashes: set[str] = set()
    versions: dict[str, str] = {}
    for candidate in (item for group in groups for item in group):
        document = candidate.document
        selected_version = versions.setdefault(
            document.document_id,
            document.version,
        )
        if selected_version != document.version:
            continue
        existing_index = positions.get(candidate.chunk.chunk_id)
        if existing_index is not None:
            existing = merged[existing_index]
            merged[existing_index] = existing.model_copy(
                update={
                    "supports_need_ids": (
                        existing.supports_need_ids | candidate.supports_need_ids
                    )
                }
            )
            continue
        if candidate.chunk.content_hash in content_hashes:
            continue
        positions[candidate.chunk.chunk_id] = len(merged)
        content_hashes.add(candidate.chunk.content_hash)
        merged.append(candidate)
    return merged


def _allocate_evidence(
    candidates: Sequence[RetrievalCandidate],
    plan: RetrievalPlan,
    *,
    max_items: int = 6,
    max_tokens: int = 1200,
) -> tuple[RetrievalCandidate, ...]:
    selected: list[RetrievalCandidate] = []
    selected_ids: set[str] = set()
    used_tokens = 0

    def add(candidate: RetrievalCandidate) -> bool:
        nonlocal used_tokens
        if candidate.chunk.chunk_id in selected_ids:
            return False
        if len(selected) >= max_items:
            return False
        if used_tokens + candidate.chunk.token_count > max_tokens:
            return False
        selected.append(candidate)
        selected_ids.add(candidate.chunk.chunk_id)
        used_tokens += candidate.chunk.token_count
        return True

    for need in plan.evidence_needs:
        if not need.required:
            continue
        for candidate in candidates:
            if need.need_id in candidate.supports_need_ids and add(candidate):
                break
    for candidate in candidates:
        add(candidate)
    return tuple(selected)


class HierarchicalRetrievalService:
    """Route parent documents, retrieve sections, then fill uncovered needs once."""

    def __init__(
        self,
        *,
        corpus: DocumentCorpus,
        router: DocumentRouter,
        section_retrieval: RetrievalService,
        coverage: EvidenceCoverageService,
        route_limit: int = 4,
    ) -> None:
        self._corpus = corpus
        self._router = router
        self._section_retrieval = section_retrieval
        self._coverage = coverage
        self._route_limit = route_limit

    def _authorized_keys(
        self,
        user: UserContext,
        as_of: datetime,
        requested_versions: Mapping[str, str],
    ) -> tuple[frozenset[tuple[str, str]], bool, int]:
        grouped: dict[str, list[DocumentRecord]] = defaultdict(list)
        for document in self._corpus.list_documents():
            grouped[document.document_id].append(document)
        authorized: set[tuple[str, str]] = set()
        ambiguous = False
        denied = 0
        for document_id, documents in grouped.items():
            resolution = resolve_effective_versions(
                documents,
                as_of=as_of,
                requested_version=requested_versions.get(document_id),
            )
            if resolution.status is VersionResolutionStatus.AMBIGUOUS:
                ambiguous = True
                continue
            if resolution.status is not VersionResolutionStatus.SELECTED:
                continue
            document = resolution.document
            assert document is not None
            if can_access(user, document):
                authorized.add((document.document_id, document.version))
            else:
                denied += 1
        return frozenset(authorized), ambiguous, denied

    def retrieve(
        self,
        plan: RetrievalPlan,
        user: UserContext,
        as_of: datetime,
        *,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER,
        requested_versions: Mapping[str, str] | None = None,
    ) -> HierarchicalRetrievalResult:
        keys, ambiguous, denied = self._authorized_keys(
            user,
            as_of,
            requested_versions or {},
        )
        empty_coverage = self._coverage.cover(plan, [])
        if not keys:
            status = (
                RetrievalStatus.VERSION_AMBIGUOUS
                if ambiguous
                else (
                    RetrievalStatus.PERMISSION_DENIED
                    if denied
                    else RetrievalStatus.INSUFFICIENT_EVIDENCE
                )
            )
            return HierarchicalRetrievalResult(
                status=status,
                coverage=empty_coverage,
                hop_count=0,
            )

        routes = self._router.route(
            plan.primary_query,
            keys,
            limit=self._route_limit,
        )
        route_keys = frozenset(
            (route.document_id, route.version)
            for route in routes
            if (route.document_id, route.version) in keys
        )
        if not route_keys:
            return HierarchicalRetrievalResult(
                status=RetrievalStatus.INSUFFICIENT_EVIDENCE,
                routes=routes,
                coverage=empty_coverage,
                hop_count=1,
            )

        first = self._section_retrieval.retrieve_within_documents(
            plan.primary_query,
            document_keys=route_keys,
            strategy=strategy,
        )
        first_candidates = [
            item.model_copy(update={"retrieval_hop": 1})
            for item in first.candidates
            if (item.document.document_id, item.document.version) in route_keys
        ]
        first_coverage = self._coverage.cover(plan, first_candidates)
        merged = list(first_coverage.annotated_candidates)
        hop_count = 1

        missing = first_coverage.missing_required_need_ids
        if missing and plan.max_hops == 2:
            titles = " ".join(route.title for route in routes)
            supplemental: list[RetrievalCandidate] = []
            needs = {need.need_id: need for need in plan.evidence_needs}
            for need_id in sorted(missing):
                need = needs[need_id]
                query = f"{plan.topic} {need.kind.value} {need.query} {titles}".strip()
                result = self._section_retrieval.retrieve_within_documents(
                    query,
                    document_keys=route_keys,
                    strategy=strategy,
                )
                supplemental.extend(
                    item.model_copy(
                        update={
                            "retrieval_hop": 2,
                            "supports_need_ids": {need_id},
                        }
                    )
                    for item in result.candidates
                    if (item.document.document_id, item.document.version)
                    in route_keys
                )
            merged = _merge_candidates(merged, supplemental)
            hop_count = 2

        final_coverage = self._coverage.cover(plan, merged)
        allocated = _allocate_evidence(
            final_coverage.annotated_candidates,
            plan,
        )
        status = (
            RetrievalStatus.READY
            if allocated and not final_coverage.missing_required_need_ids
            else RetrievalStatus.INSUFFICIENT_EVIDENCE
        )
        return HierarchicalRetrievalResult(
            status=status,
            routes=routes,
            evidence_candidates=allocated,
            coverage=final_coverage,
            hop_count=hop_count,
        )
