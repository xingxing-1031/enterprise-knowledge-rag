import pytest
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


def test_coverage_ignores_explicit_support_without_token_overlap() -> None:
    exception = make_candidate(
        "leave:exception",
        title="员工请假制度",
        content="可先电话报备，返岗后补交。",
    ).model_copy(update={"supports_need_ids": {"exception"}, "retrieval_hop": 2})

    result = EvidenceCoverageService().cover(PLAN, [exception])

    # 候选自带/上一跳标注的 supports_need_ids 不再被直接信任：
    # 覆盖必须由 token 重叠重新验证，避免无关文档被假标记为已覆盖。
    assert result.covered_need_ids == frozenset()
    assert result.missing_required_need_ids == frozenset({"material", "exception"})
    assert result.annotated_candidates == ()


def test_low_reranker_score_does_not_count_as_coverage() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
    ).model_copy(update={"reranker_score": 0.2})

    result = EvidenceCoverageService(min_reranker_score=0.5).cover(PLAN, [material])

    assert result.covered_need_ids == frozenset()
    assert result.missing_required_need_ids == frozenset({"material", "exception"})


def test_coverage_does_not_mark_a_need_from_one_generic_shared_token() -> None:
    plan = RetrievalPlan(
        primary_query="new supplier",
        topic="procurement",
        evidence_needs=[
            EvidenceNeed(
                need_id="rule",
                kind="rule",
                query="supplier purchase threshold",
            ),
            EvidenceNeed(
                need_id="material",
                kind="material",
                query="supplier registration package",
            ),
        ],
        requires_multi_hop=True,
        max_hops=2,
    )
    threshold = make_candidate(
        "supplier:threshold",
        title="Supplier policy",
        content="A new supplier purchase threshold is 30,000 yuan.",
    )

    result = EvidenceCoverageService(min_query_token_overlap=0.5).cover(
        plan,
        [threshold],
    )

    assert result.covered_need_ids == frozenset({"rule"})
    assert result.missing_required_need_ids == frozenset({"material"})


OVERTIME_PLAN = RetrievalPlan(
    primary_query="公司有加班吗，加班费怎么算？",
    topic="考勤加班",
    evidence_needs=[
        EvidenceNeed(
            need_id="rule",
            kind="rule",
            query="加班报酬的计发基数与倍数标准",
            required=True,
        ),
    ],
    requires_multi_hop=True,
    max_hops=2,
)

OVERTIME_CONTENT = (
    "公司加班费按加班时长计算：工作日加班按 1.5 倍工资支付，"
    "法定节假日按 3 倍。"
)


def test_primary_query_bridge_covers_need_with_lexical_gap() -> None:
    candidate = make_candidate(
        "attendance:overtime",
        title="考勤与加班管理制度",
        content=OVERTIME_CONTENT,
    ).model_copy(update={"reranker_score": 0.8})

    result = EvidenceCoverageService().cover(OVERTIME_PLAN, [candidate])

    # 直接 token 重叠不足（"报酬/计发/基数" 与文档用词不符），但候选被
    # reranker 认可与主查询强相关、且主查询 token 重叠充分，经语义桥接覆盖。
    assert result.covered_need_ids == frozenset({"rule"})
    assert result.missing_required_need_ids == frozenset()
    assert result.annotated_candidates[0].supports_need_ids == {"rule"}


def test_primary_query_bridge_requires_reranker_approval() -> None:
    candidate = make_candidate(
        "attendance:overtime",
        title="考勤与加班管理制度",
        content=OVERTIME_CONTENT,
    ).model_copy(update={"reranker_score": 0.2})

    result = EvidenceCoverageService().cover(OVERTIME_PLAN, [candidate])

    # reranker 未认可强相关时禁止主查询桥接，避免任意共享词造成假覆盖。
    assert result.covered_need_ids == frozenset()
    assert result.missing_required_need_ids == frozenset({"rule"})


@pytest.mark.parametrize("overlap", [-0.1, 1.1])
def test_query_token_overlap_must_be_between_zero_and_one(overlap: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        EvidenceCoverageService(min_query_token_overlap=overlap)
