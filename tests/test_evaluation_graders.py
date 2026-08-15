from datetime import UTC, datetime
from math import isclose

from enterprise_knowledge_rag.evaluation.graders import grade_case, grade_ranking
from enterprise_knowledge_rag.evaluation.models import (
    EvaluationCase,
    EvaluationObservation,
    EvaluationSplit,
    ExpectedOutcome,
    ObservedEvidence,
)
from enterprise_knowledge_rag.models import RefusalReason, UserContext, UserRole


def test_ranking_metrics_use_independent_gold_evidence() -> None:
    score = grade_ranking(
        relevant_keys={"leave-approval", "leave-materials"},
        retrieved_keys=["expense-deadline", "leave-approval", "asset-return"],
        k=3,
    )

    assert score.recall_at_k == 0.5
    assert score.reciprocal_rank == 0.5
    assert isclose(score.ndcg_at_k, 0.3868528072, rel_tol=1e-9)


def test_duplicate_retrieval_cannot_inflate_ranking_metrics() -> None:
    score = grade_ranking(
        relevant_keys={"leave-approval", "leave-materials"},
        retrieved_keys=["leave-approval", "leave-approval", "leave-materials"],
        k=2,
    )

    assert score.recall_at_k == 1.0
    assert score.reciprocal_rank == 1.0
    assert score.ndcg_at_k == 1.0


def make_case(**updates) -> EvaluationCase:
    values = {
        "case_id": "dev-finance-001",
        "split": EvaluationSplit.DEVELOPMENT,
        "question": "报销需要在多久内提交？",
        "as_of": datetime(2026, 8, 10, tzinfo=UTC),
        "user": UserContext(
            user_id="eval-employee",
            role=UserRole.EMPLOYEE,
            departments={"finance"},
        ),
        "expected_in_scope": True,
        "expected_outcome": ExpectedOutcome.ANSWER,
        "gold_evidence_keys": {"expense-v2-deadline"},
        "expected_versions": {"finance-expense-policy": "2.0"},
        "forbidden_document_ids": {"finance-payment-approval"},
        "required_answer_facts": ["15个自然日"],
    }
    values.update(updates)
    return EvaluationCase.model_validate(values)


def test_case_grading_keeps_business_stages_separate() -> None:
    observation = EvaluationObservation(
        in_scope=True,
        retrieved=[
            ObservedEvidence(
                evidence_key="expense-v2-deadline",
                document_id="finance-expense-policy",
                version="2.0",
            )
        ],
        citations={"expense-v2-deadline"},
        status="success",
        answer="费用应在行程结束后 15个自然日 内提交。",
        latency_ms=840.0,
        model_calls=2,
    )

    score = grade_case(make_case(), observation, k=5)

    assert score.domain_accuracy == 1.0
    assert score.ranking.recall_at_k == 1.0
    assert score.access_leakage == 0.0
    assert score.version_accuracy == 1.0
    assert score.citation_accuracy == 1.0
    assert score.citation_recall == 1.0
    assert score.automated_answer_score == 1.0
    assert score.false_refusal == 0.0
    assert score.core_pass is True


def test_hidden_document_in_candidates_is_an_access_leak() -> None:
    observation = EvaluationObservation(
        in_scope=True,
        retrieved=[
            ObservedEvidence(
                evidence_key="payment-approval-rule",
                document_id="finance-payment-approval",
                version="1.1",
            )
        ],
        status="refused",
        refusal_reason=RefusalReason.INSUFFICIENT_EVIDENCE,
        latency_ms=100.0,
        model_calls=0,
    )

    score = grade_case(make_case(), observation, k=5)

    assert score.access_leakage == 1.0
    assert score.core_pass is False


def test_refusal_is_correct_only_when_reason_matches() -> None:
    case = make_case(
        case_id="dev-permission-001",
        expected_outcome=ExpectedOutcome.REFUSAL,
        expected_refusal_reason=RefusalReason.PERMISSION_DENIED,
        gold_evidence_keys=set(),
        expected_versions={},
        required_answer_facts=[],
    )
    observation = EvaluationObservation(
        in_scope=True,
        status="refused",
        refusal_reason=RefusalReason.PERMISSION_DENIED,
        latency_ms=40.0,
        model_calls=0,
    )

    score = grade_case(case, observation, k=5)

    assert score.correct_refusal == 1.0
    assert score.false_refusal == 0.0
    assert score.core_pass is True


def test_refusing_an_answerable_case_is_a_false_refusal() -> None:
    observation = EvaluationObservation(
        in_scope=True,
        status="refused",
        refusal_reason=RefusalReason.INSUFFICIENT_EVIDENCE,
        latency_ms=40.0,
        model_calls=0,
    )

    score = grade_case(make_case(), observation, k=5)

    assert score.correct_refusal is None
    assert score.false_refusal == 1.0
    assert score.core_pass is False


def test_two_hop_case_grades_route_and_evidence_need_metrics() -> None:
    case = make_case(
        case_id="dev-multihop-001",
        gold_evidence_keys={
            "hr-leave-policy@2.0#materials",
            "hr-medical-process@1.0#emergency",
        },
        required_need_ids={"material", "exception"},
        expected_retrieval_hops=2,
        expected_versions={
            "hr-leave-policy": "2.0",
            "hr-medical-process": "1.0",
        },
    )
    observation = EvaluationObservation(
        in_scope=True,
        retrieved=[
            ObservedEvidence(
                evidence_key="hr-leave-policy@2.0#materials",
                document_id="hr-leave-policy",
                version="2.0",
            ),
            ObservedEvidence(
                evidence_key="hr-medical-process@1.0#emergency",
                document_id="hr-medical-process",
                version="1.0",
            ),
        ],
        citations={
            "hr-leave-policy@2.0#materials",
            "hr-medical-process@1.0#emergency",
        },
        status="success",
        answer="完整事实",
        latency_ms=100.0,
        model_calls=3,
        routed_document_keys=["hr-leave-policy@2.0", "hr-medical-process@1.0"],
        retrieval_hops=2,
        required_need_ids={"material", "exception"},
        covered_need_ids={"material", "exception"},
    )

    score = grade_case(case, observation, k=5)

    assert score.document_route_recall == 1.0
    assert score.evidence_need_coverage == 1.0
    assert score.second_hop_trigger_accuracy == 1.0
    assert score.second_hop_success == 1.0
    assert score.irrelevant_evidence_ratio == 0.0
    assert score.core_pass is True


def test_two_hop_case_fails_core_when_second_hop_does_not_trigger() -> None:
    case = make_case(
        case_id="dev-multihop-missed",
        gold_evidence_keys={"hr-leave-policy@2.0#materials"},
        expected_versions={},
        required_need_ids={"material"},
        expected_retrieval_hops=2,
    )
    observation = EvaluationObservation(
        in_scope=True,
        retrieved=[
            ObservedEvidence(
                evidence_key="hr-leave-policy@2.0#materials",
                document_id="hr-leave-policy",
                version="2.0",
            )
        ],
        citations={"hr-leave-policy@2.0#materials"},
        status="success",
        answer="完整事实",
        latency_ms=100.0,
        model_calls=2,
        routed_document_keys=["hr-leave-policy@2.0"],
        retrieval_hops=1,
        required_need_ids={"material"},
        covered_need_ids={"material"},
    )

    score = grade_case(case, observation, k=5)

    assert score.second_hop_trigger_accuracy == 0.0
    assert score.second_hop_success == 0.0
    assert score.core_pass is False


def test_need_coverage_precision_detects_runtime_overclaim() -> None:
    case = make_case(
        case_id="dev-need-precision-001",
        required_need_ids={"material"},
        gold_evidence_keys={"leave-material"},
    )
    observation = EvaluationObservation(
        in_scope=True,
        retrieved=[
            ObservedEvidence(
                evidence_key="leave-material",
                document_id="hr-leave-policy",
                version="2.0",
            )
        ],
        citations={"leave-material"},
        status="success",
        answer="材料已核验。",
        latency_ms=100.0,
        model_calls=1,
        required_need_ids={"material", "exception"},
        covered_need_ids={"material", "exception"},
    )

    score = grade_case(case, observation, k=5)

    assert score.need_coverage_precision == 0.5
