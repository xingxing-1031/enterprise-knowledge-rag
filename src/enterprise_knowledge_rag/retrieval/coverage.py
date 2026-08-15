from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from enterprise_knowledge_rag.documents.source_models import RetrievalPlan
from enterprise_knowledge_rag.models import RetrievalCandidate, StrictModel

from .lexical import tokenize


class CoverageResult(StrictModel):
    covered_need_ids: frozenset[str] = Field(default_factory=frozenset)
    missing_required_need_ids: frozenset[str] = Field(default_factory=frozenset)
    annotated_candidates: tuple[RetrievalCandidate, ...] = ()


class EvidenceNeedScoreProvider(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class EvidenceCoverageService:
    """Deterministically map retrieved sections to required evidence needs."""

    def __init__(
        self,
        *,
        min_reranker_score: float = 0.0,
        min_query_token_overlap: float = 0.3,
        min_hit_tokens: int = 2,
        min_primary_reranker_score: float = 0.5,
        min_primary_overlap: float = 0.5,
        need_score_provider: EvidenceNeedScoreProvider | None = None,
        min_need_score: float = 0.5,
    ) -> None:
        if min_reranker_score < 0:
            raise ValueError("min_reranker_score must not be negative")
        if not 0 <= min_query_token_overlap <= 1:
            raise ValueError("min_query_token_overlap must be between 0 and 1")
        if min_hit_tokens < 1:
            raise ValueError("min_hit_tokens must be positive")
        if not 0 <= min_primary_overlap <= 1:
            raise ValueError("min_primary_overlap must be between 0 and 1")
        if not 0 <= min_need_score <= 1:
            raise ValueError("min_need_score must be between 0 and 1")
        self._min_reranker_score = min_reranker_score
        self._min_query_token_overlap = min_query_token_overlap
        self._min_hit_tokens = min_hit_tokens
        self._min_primary_reranker_score = min_primary_reranker_score
        self._min_primary_overlap = min_primary_overlap
        self._need_score_provider = need_score_provider
        self._min_need_score = min_need_score

    def cover(
        self,
        plan: RetrievalPlan,
        candidates: Sequence[RetrievalCandidate],
    ) -> CoverageResult:
        needs = {need.need_id: need for need in plan.evidence_needs}
        required_need_count = sum(need.required for need in plan.evidence_needs)
        primary_tokens = {
            token for token in tokenize(plan.primary_query) if len(token) >= 2
        }
        annotated: list[RetrievalCandidate] = []
        covered: set[str] = set()
        for candidate in candidates:
            score = candidate.reranker_score
            if score is None and self._min_reranker_score > 0:
                continue
            if score is not None and score < self._min_reranker_score:
                continue
            haystack = " ".join(
                [" ".join(candidate.chunk.section_path), candidate.chunk.content]
            )
            haystack_tokens = set(tokenize(haystack))
            # 覆盖必须由 token 重叠验证：不采纳候选自带/此前轮次标注的
            # supports_need_ids（explicit），避免无关文档被上一跳标注后一直假覆盖。
            matched: set[str] = set()
            unresolved_needs = []
            for need in needs.values():
                query_tokens = {
                    token for token in tokenize(need.query) if len(token) >= 2
                }
                if not query_tokens:
                    continue
                hits = query_tokens & haystack_tokens
                overlap = len(hits) / len(query_tokens)
                if (
                    len(hits) >= self._min_hit_tokens
                    and overlap >= self._min_query_token_overlap
                ):
                    matched.add(need.need_id)
                    continue
                unresolved_needs.append(need)
                # 主查询语义桥接：候选与用户原问题被 reranker 认可为强相关，
                # 且与主查询 token 重叠充分，即使与 LLM 形式化的 need 查询字面差异
                # 较大，也视为该 need 的依据（如"加班费"对"加班补偿"）。
                if (
                    required_need_count == 1
                    and score is not None
                    and score >= self._min_primary_reranker_score
                    and primary_tokens
                ):
                    primary_hits = primary_tokens & haystack_tokens
                    primary_overlap = len(primary_hits) / len(primary_tokens)
                    if (
                        len(primary_hits) >= self._min_hit_tokens
                        and primary_overlap >= self._min_primary_overlap
                    ):
                        matched.add(need.need_id)
            if self._need_score_provider is not None and unresolved_needs:
                passage = " ".join(
                    [" ".join(candidate.chunk.section_path), candidate.chunk.content]
                )
                for need in unresolved_needs:
                    try:
                        scores = self._need_score_provider.score(
                            need.query,
                            [passage],
                        )
                    except Exception:
                        continue
                    if scores and scores[0] >= self._min_need_score:
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
