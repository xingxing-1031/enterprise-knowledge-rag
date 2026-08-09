from datetime import UTC, datetime

from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.generation import AnswerGenerator
from enterprise_knowledge_rag.models import (
    ChatRequest,
    RefusalReason,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.retrieval import RetrievalResult, RetrievalStatus
from enterprise_knowledge_rag.workflow import (
    WorkflowDependencies,
    build_workflow,
    run_chat,
)


class FixedDomain:
    def __init__(self, in_scope=True):
        self.in_scope = in_scope

    def is_in_scope(self, question):
        return self.in_scope


class FixedRewriter:
    def rewrite(self, question, history):
        return question.replace("它", "差旅报销制度")


class FixedRetrieval:
    def __init__(self, status=RetrievalStatus.READY):
        self.status = status

    def retrieve(self, query, *, user, as_of):
        candidate = make_candidate(
            "expense:1",
            title="差旅与费用报销管理制度",
            content="出差结束后15个自然日内提交报销申请。",
            document_id="finance-expense-policy",
        ).model_copy(
            update={
                "channels": {"bm25", "vector"},
                "reranker_score": 0.9,
            }
        )
        return RetrievalResult(
            status=self.status,
            candidates=(candidate,) if self.status is RetrievalStatus.READY else (),
            authorized_document_keys=frozenset({("finance-expense-policy", "1.0")}),
        )


class FixedAnswerProvider:
    def __init__(self, invalid=False):
        self.invalid = invalid

    def generate(self, *, prompt, schema):
        evidence_id = "ev:expense:1"
        return {
            "answer": "请在30天内提交。" if self.invalid else "请在15个自然日内提交。",
            "claims": [
                {
                    "text": "请在30天内提交。"
                    if self.invalid
                    else "请在15个自然日内提交。",
                    "evidence_ids": [evidence_id],
                }
            ],
        }


def make_graph(
    *,
    in_scope=True,
    retrieval_status=RetrievalStatus.READY,
    invalid_answer=False,
):
    return build_workflow(
        WorkflowDependencies(
            domain=FixedDomain(in_scope),
            rewriter=FixedRewriter(),
            retrieval=FixedRetrieval(retrieval_status),
            generator=AnswerGenerator(FixedAnswerProvider(invalid_answer)),
        )
    )


def run(graph):
    return run_chat(
        graph,
        ChatRequest(question="它需要多久提交"),
        UserContext(user_id="u1", role=UserRole.EMPLOYEE),
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_workflow_success_returns_evidence_and_safe_trace() -> None:
    result = run(make_graph())
    assert result.result.status == "success"
    assert result.result.evidence
    assert result.result.citations
    assert [event.component for event in result.trace] == [
        "domain",
        "rewrite",
        "retrieve",
        "evidence",
        "generate",
        "finalize",
    ]


def test_out_of_scope_stops_before_retrieval() -> None:
    result = run(make_graph(in_scope=False))
    assert result.result.refusal_reason is RefusalReason.OUT_OF_SCOPE
    assert [event.component for event in result.trace] == ["domain", "refusal"]


def test_insufficient_retrieval_returns_refusal() -> None:
    result = run(make_graph(retrieval_status=RetrievalStatus.INSUFFICIENT_EVIDENCE))
    assert result.result.refusal_reason is RefusalReason.INSUFFICIENT_EVIDENCE
    assert "generate" not in {event.component for event in result.trace}


def test_version_ambiguity_returns_specific_refusal() -> None:
    result = run(make_graph(retrieval_status=RetrievalStatus.VERSION_AMBIGUOUS))
    assert result.result.refusal_reason is RefusalReason.VERSION_AMBIGUOUS


def test_invalid_generation_degrades_after_bounded_retry() -> None:
    result = run(make_graph(invalid_answer=True))
    assert result.result.status == "degraded"
    assert result.result.degradation_reason
    assert result.result.evidence
