from datetime import UTC, datetime

from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.models import UserContext, UserRole, Visibility
from enterprise_knowledge_rag.retrieval import (
    Reranker,
    RetrievalService,
    RetrievalStatus,
    VectorRetriever,
)


class FakeCorpus:
    def __init__(self, candidates):
        self.candidates = candidates
        self.received_keys = None

    def list_documents(self):
        return [candidate.document for candidate in self.candidates]

    def list_candidates(self, document_keys):
        self.received_keys = document_keys
        return [
            candidate
            for candidate in self.candidates
            if (candidate.document.document_id, candidate.document.version)
            in document_keys
        ]


class FakeVectorBackend:
    def __init__(self, candidates):
        self.candidates = candidates
        self.received_keys = None

    def search_authorized(self, query_vector, *, document_keys, limit):
        self.received_keys = document_keys
        return [
            candidate
            for candidate in self.candidates
            if (candidate.document.document_id, candidate.document.version)
            in document_keys
        ][:limit]


class FakeEmbedding:
    def embed_query(self, query):
        return [0.1, 0.2]


class MatchingScores:
    def score(self, query, passages):
        return [1.0 if "请假" in passage else 0.1 for passage in passages]


def test_service_filters_restricted_document_before_retrieval() -> None:
    public = make_candidate(
        "leave:1",
        title="员工请假管理制度",
        content="员工请假需要提前提交申请。",
        document_id="leave-policy",
    )
    restricted = make_candidate(
        "payment:1",
        title="付款审批权限表",
        content="付款金额超过十万元需要总经理审批。",
        document_id="payment-policy",
    )
    restricted.document.visibility = Visibility.RESTRICTED
    restricted.document.allowed_roles = {UserRole.DEPARTMENT_ADMIN}
    corpus = FakeCorpus([public, restricted])
    backend = FakeVectorBackend([public, restricted])
    service = RetrievalService(
        corpus,
        VectorRetriever(backend),
        FakeEmbedding(),
        Reranker(MatchingScores()),
    )

    result = service.retrieve(
        "请假怎么申请",
        user=UserContext(user_id="u1", role=UserRole.EMPLOYEE),
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert result.status is RetrievalStatus.READY
    assert result.authorized_document_keys == frozenset({("leave-policy", "1.0")})
    assert backend.received_keys == frozenset({("leave-policy", "1.0")})
    assert all(
        item.document.document_id != "payment-policy" for item in result.candidates
    )


def test_service_returns_insufficient_when_no_candidate_matches() -> None:
    corpus = FakeCorpus([])
    service = RetrievalService(
        corpus,
        VectorRetriever(FakeVectorBackend([])),
        FakeEmbedding(),
        Reranker(MatchingScores()),
    )
    result = service.retrieve(
        "公司附近有什么餐厅",
        user=UserContext(user_id="u1", role=UserRole.EMPLOYEE),
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.status is RetrievalStatus.INSUFFICIENT_EVIDENCE
