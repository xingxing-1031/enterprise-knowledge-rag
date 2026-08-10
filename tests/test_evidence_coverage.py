from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.documents.source_models import (
    EvidenceNeed,
    RetrievalPlan,
)
from enterprise_knowledge_rag.retrieval.coverage import EvidenceCoverageService

PLAN = RetrievalPlan(
    primary_query="病假超过两天交什么材料，紧急就医怎么办？",
    topic="员工请假",
    evidence_needs=[
        EvidenceNeed(need_id="material", kind="material", query="病假需要什么材料"),
        EvidenceNeed(need_id="exception", kind="exception", query="紧急就医怎么办"),
    ],
    requires_multi_hop=True,
    max_hops=2,
)


def test_coverage_reports_missing_required_need_ids() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
    )

    result = EvidenceCoverageService().cover(PLAN, [material])

    assert result.covered_need_ids == frozenset({"material"})
    assert result.missing_required_need_ids == frozenset({"exception"})
    assert result.annotated_candidates[0].supports_need_ids == {"material"}


def test_coverage_preserves_explicit_support_from_need_scoped_retrieval() -> None:
    exception = make_candidate(
        "leave:exception",
        title="员工请假制度",
        content="可先电话报备，返岗后补交。",
    ).model_copy(update={"supports_need_ids": {"exception"}, "retrieval_hop": 2})

    result = EvidenceCoverageService().cover(PLAN, [exception])

    assert result.covered_need_ids == frozenset({"exception"})
    assert result.annotated_candidates[0].retrieval_hop == 2


def test_low_reranker_score_does_not_count_as_coverage() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
    ).model_copy(update={"reranker_score": 0.2})

    result = EvidenceCoverageService(min_reranker_score=0.5).cover(PLAN, [material])

    assert result.covered_need_ids == frozenset()
    assert result.missing_required_need_ids == frozenset({"material", "exception"})
