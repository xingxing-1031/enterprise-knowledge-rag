from datetime import UTC, datetime

from enterprise_knowledge_rag.evaluation.executor import WorkflowEvaluationExecutor
from enterprise_knowledge_rag.evaluation.models import (
    EvaluationCase,
    EvaluationSplit,
    EvaluationStrategy,
    ExpectedOutcome,
)
from enterprise_knowledge_rag.models import ChatResult, Citation, UserContext, UserRole
from enterprise_knowledge_rag.workflow import WorkflowRun


class FakeService:
    def __init__(self, run: WorkflowRun) -> None:
        self.run_result = run
        self.cleared = []

    def run(self, request, user):
        return self.run_result

    def clear_session(self, user, session_id):
        self.cleared.append((user.user_id, session_id))


def test_executor_preserves_retrieval_and_citation_keys() -> None:
    candidate = __import__("retrieval_fixtures").make_candidate(
        "expense:1",
        title="费用制度",
        document_id="finance-expense-policy",
        content="出差结束后15个自然日内提交报销申请。",
    )
    result = ChatResult(
        status="success",
        answer="15个自然日内提交。",
        evidence=[
            {
                "evidence_id": "ev:expense:1",
                "chunk_id": "expense:1",
                "document_id": "finance-expense-policy",
                "title": "费用制度",
                "section_path": ["费用制度", "报销期限"],
                "version": "2.0",
                "effective_from": datetime(2026, 1, 1, tzinfo=UTC),
                "quote": "出差结束后15个自然日内提交报销申请。",
                "retrieval_channels": ["vector"],
                "retrieval_rank": 1,
                "reranker_score": None,
            }
        ],
        citations=[Citation(evidence_id="ev:expense:1", label="费用制度")],
    )
    service = FakeService(
        WorkflowRun(
            result=result,
            trace=(),
            in_scope=True,
            retrieval_candidates=(candidate,),
            model_calls=1,
        )
    )
    user = UserContext(user_id="eval-user", role=UserRole.EMPLOYEE)
    case = EvaluationCase(
        case_id="dev-001",
        split=EvaluationSplit.DEVELOPMENT,
        question="多久报销？",
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
        user=user,
        expected_in_scope=True,
        expected_outcome=ExpectedOutcome.ANSWER,
    )

    observation = WorkflowEvaluationExecutor(
        {EvaluationStrategy.VECTOR_BASELINE: service}
    ).run(
        case,
        strategy=EvaluationStrategy.VECTOR_BASELINE,
        corpus_snapshot="sha256:test",
    )

    assert observation.retrieved[0].evidence_key == (
        "finance-expense-policy@1.0#办理规则"
    )
    assert observation.citations == {"finance-expense-policy@2.0#报销期限"}
    assert service.cleared == [("eval-user", "evaluation:dev-001")]
