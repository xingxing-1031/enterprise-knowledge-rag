from datetime import UTC, datetime

from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.documents.source_models import (
    EvidenceNeed,
    RetrievalPlan,
)
from enterprise_knowledge_rag.models import UserContext, UserRole, Visibility
from enterprise_knowledge_rag.retrieval.coverage import EvidenceCoverageService
from enterprise_knowledge_rag.retrieval.hierarchical import (
    HierarchicalRetrievalService,
)
from enterprise_knowledge_rag.retrieval.routing import DocumentRouteCandidate
from enterprise_knowledge_rag.retrieval.service import (
    RetrievalResult,
    RetrievalStatus,
)

AS_OF = datetime(2026, 8, 10, tzinfo=UTC)
USER = UserContext(user_id="employee-1", role=UserRole.EMPLOYEE)
PLAN = RetrievalPlan(
    primary_query="病假超过两天交什么材料，紧急就医怎么办？",
    topic="员工请假",
    evidence_needs=[
        EvidenceNeed(need_id="material", kind="material", query="病假材料"),
        EvidenceNeed(need_id="exception", kind="exception", query="紧急就医"),
    ],
    requires_multi_hop=True,
    max_hops=2,
)


class FakeCorpus:
    def __init__(self, documents):
        self.documents = documents

    def list_documents(self):
        return self.documents


class FakeRouter:
    def __init__(self, route, supplemental_routes=None):
        self.route_item = route
        self.supplemental_routes = list(supplemental_routes or [])
        self.received_keys = None
        self.calls = []

    def route(self, query, document_keys, *, limit=4):
        self.received_keys = document_keys
        self.calls.append((query, document_keys))
        index = len(self.calls) - 1
        route_item = (
            self.supplemental_routes[index - 1]
            if index > 0 and index - 1 < len(self.supplemental_routes)
            else self.route_item
        )
        return (route_item,) if route_item else ()


class FakeSectionRetrieval:
    def __init__(self, first, second):
        self.first = first
        self.second = second
        self.calls = []

    def retrieve_within_documents(
        self,
        query,
        *,
        document_keys,
        pool_limit=10,
        final_limit=5,
        strategy=None,
    ):
        self.calls.append((query, document_keys))
        candidates = self.first if len(self.calls) == 1 else self.second
        return RetrievalResult(
            status=(
                RetrievalStatus.READY
                if candidates
                else RetrievalStatus.INSUFFICIENT_EVIDENCE
            ),
            candidates=tuple(candidates),
            authorized_document_keys=document_keys,
        )


def route_for(candidate):
    return DocumentRouteCandidate(
        document_id=candidate.document.document_id,
        version=candidate.document.version,
        title=candidate.document.title,
        document_type=candidate.document.document_type,
        department=candidate.document.department,
        lexical_rank=1,
        channels={"bm25"},
        fused_score=0.1,
    )


def test_missing_exception_need_triggers_one_supplemental_hop() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
        document_id="leave-policy",
    ).model_copy(update={"supports_need_ids": {"material"}})
    exception = make_candidate(
        "leave:exception",
        title="员工请假制度",
        content="紧急就医可先电话报备，返岗后补交材料。",
        document_id="leave-policy",
    ).model_copy(update={"supports_need_ids": {"exception"}})
    restricted = make_candidate(
        "payment:secret",
        title="付款审批权限",
        content="受限审批规则。",
        document_id="payment-policy",
    )
    restricted.document.visibility = Visibility.RESTRICTED
    restricted.document.allowed_roles = {UserRole.DEPARTMENT_ADMIN}
    router = FakeRouter(route_for(material))
    sections = FakeSectionRetrieval([material], [exception])
    service = HierarchicalRetrievalService(
        corpus=FakeCorpus([material.document, restricted.document]),
        router=router,
        section_retrieval=sections,
        coverage=EvidenceCoverageService(),
    )

    result = service.retrieve(PLAN, USER, AS_OF)

    assert result.status is RetrievalStatus.READY
    assert len(sections.calls) == 2
    assert result.hop_count == 2
    assert result.coverage.covered_need_ids == frozenset({"material", "exception"})
    assert result.coverage.missing_required_need_ids == frozenset()
    assert {item.retrieval_hop for item in result.evidence_candidates} == {1, 2}
    allowed = frozenset({("leave-policy", "1.0")})
    assert router.received_keys == allowed
    assert all(document_keys == allowed for _, document_keys in sections.calls)
    assert all("payment-policy" not in str(keys) for _, keys in sections.calls)


def test_one_hop_plan_does_not_retry_when_required_evidence_is_missing() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
        document_id="leave-policy",
    )
    one_hop = PLAN.model_copy(
        update={"requires_multi_hop": False, "max_hops": 1}
    )
    sections = FakeSectionRetrieval([material], [])
    service = HierarchicalRetrievalService(
        corpus=FakeCorpus([material.document]),
        router=FakeRouter(route_for(material)),
        section_retrieval=sections,
        coverage=EvidenceCoverageService(),
    )

    result = service.retrieve(one_hop, USER, AS_OF)

    assert result.status is RetrievalStatus.INSUFFICIENT_EVIDENCE
    assert result.hop_count == 1
    assert len(sections.calls) == 1


def test_missing_need_reroutes_to_another_authorized_parent_document() -> None:
    material = make_candidate(
        "leave:material",
        title="员工请假制度",
        content="病假超过两天需要提交医疗机构证明材料。",
        document_id="leave-policy",
    )
    exception = make_candidate(
        "leave:exception",
        title="Medical emergency process",
        content="紧急就医无法提前申请时，应向直属主管报备。",
        document_id="medical-process",
    )
    first_route = route_for(material)
    second_route = route_for(exception)
    router = FakeRouter(first_route, supplemental_routes=[second_route])
    sections = FakeSectionRetrieval([material], [exception])
    service = HierarchicalRetrievalService(
        corpus=FakeCorpus([material.document, exception.document]),
        router=router,
        section_retrieval=sections,
        coverage=EvidenceCoverageService(),
    )

    result = service.retrieve(PLAN, USER, AS_OF)

    assert result.status is RetrievalStatus.READY
    assert result.hop_count == 2
    assert {route.document_id for route in result.routes} == {
        "leave-policy",
        "medical-process",
    }
    assert router.calls[1][0].startswith("员工请假 exception")
    assert sections.calls[-1][1] == frozenset(
        {("leave-policy", "1.0"), ("medical-process", "1.0")}
    )


def test_related_restricted_document_returns_permission_denied_without_leak() -> None:
    public = make_candidate(
        "expense:public",
        title="差旅与费用报销管理制度",
        content="普通差旅报销规则。",
        document_id="finance-expense-policy",
    )
    restricted = make_candidate(
        "payment:restricted",
        title="付款申请审批权限表",
        content="全员付款审批额度。",
        document_id="finance-payment-approval",
    )
    restricted.document.visibility = Visibility.RESTRICTED
    restricted.document.allowed_roles = {UserRole.DEPARTMENT_ADMIN}
    plan = RetrievalPlan(
        primary_query="普通员工能查询全员付款审批额度吗",
        topic="finance",
        evidence_needs=[
            EvidenceNeed(need_id="rule", kind="rule", query="付款审批额度")
        ],
        requires_multi_hop=False,
        max_hops=1,
    )
    service = HierarchicalRetrievalService(
        corpus=FakeCorpus([public.document, restricted.document]),
        router=FakeRouter(route_for(public)),
        section_retrieval=FakeSectionRetrieval([], []),
        coverage=EvidenceCoverageService(),
    )

    result = service.retrieve(plan, USER, AS_OF)

    assert result.status is RetrievalStatus.PERMISSION_DENIED
    assert all(
        candidate.document.document_id != "finance-payment-approval"
        for candidate in result.evidence_candidates
    )
