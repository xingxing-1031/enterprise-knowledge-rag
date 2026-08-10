from collections.abc import Sequence

from pydantic import Field

from enterprise_knowledge_rag.documents.source_models import RetrievalPlan
from enterprise_knowledge_rag.models import RetrievalCandidate, StrictModel

from .lexical import tokenize


class CoverageResult(StrictModel):
    covered_need_ids: frozenset[str] = Field(default_factory=frozenset)
    missing_required_need_ids: frozenset[str] = Field(default_factory=frozenset)
    annotated_candidates: tuple[RetrievalCandidate, ...] = ()


class EvidenceCoverageService:
    """Deterministically map retrieved sections to required evidence needs."""

    def __init__(
        self,
        *,
        min_reranker_score: float = 0.0,
        min_query_token_overlap: float = 0.5,
    ) -> None:
        if min_reranker_score < 0:
            raise ValueError("min_reranker_score must not be negative")
        if not 0 <= min_query_token_overlap <= 1:
            raise ValueError("min_query_token_overlap must be between 0 and 1")
        self._min_reranker_score = min_reranker_score
        self._min_query_token_overlap = min_query_token_overlap

    def cover(
        self,
        plan: RetrievalPlan,
        candidates: Sequence[RetrievalCandidate],
    ) -> CoverageResult:
        needs = {need.need_id: need for need in plan.evidence_needs}
        annotated: list[RetrievalCandidate] = []
        covered: set[str] = set()
        for candidate in candidates:
            score = candidate.reranker_score
            if score is None and self._min_reranker_score > 0:
                continue
            if score is not None and score < self._min_reranker_score:
                continue
            explicit = candidate.supports_need_ids & needs.keys()
            haystack = " ".join(
                [" ".join(candidate.chunk.section_path), candidate.chunk.content]
            )
            haystack_tokens = set(tokenize(haystack))
            matched = set(explicit)
            for need in needs.values():
                query_tokens = {
                    token for token in tokenize(need.query) if len(token) >= 2
                }
                if not query_tokens:
                    continue
                overlap = len(query_tokens & haystack_tokens) / len(query_tokens)
                if overlap >= self._min_query_token_overlap:
                    matched.add(need.need_id)
            if not matched:
                continue
            covered.update(matched)
            annotated.append(
                candidate.model_copy(update={"supports_need_ids": matched})
            )

        required = {
            need.need_id for need in plan.evidence_needs if need.required
        }
        return CoverageResult(
            covered_need_ids=frozenset(covered),
            missing_required_need_ids=frozenset(required - covered),
            annotated_candidates=tuple(annotated),
        )
