from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock

import pytest

from enterprise_knowledge_rag.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationObservation,
    EvaluationSplit,
    EvaluationStrategy,
    ExpectedOutcome,
    ExperimentMetadata,
    ObservedEvidence,
)
from enterprise_knowledge_rag.evaluation.runner import (
    EvaluationRunner,
    FrozenHoldoutLockedError,
    load_dataset,
)
from enterprise_knowledge_rag.models import RefusalReason, UserContext, UserRole

NOW = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


EXPERIMENT = ExperimentMetadata(
    code_commit="abc1234",
    embedding_model="BAAI/bge-m3",
    reranker_model="BAAI/bge-reranker-v2-m3",
    llm_model="qwen3:8b",
    prompt_version="generation-v1",
    temperature=0.0,
    repetition=1,
    environment="unit-test",
)


def make_answer_case(case_id: str = "dev-answer-001") -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        split=EvaluationSplit.DEVELOPMENT,
        question="报销多久内提交？",
        as_of=NOW,
        user=UserContext(
            user_id="eval-user",
            role=UserRole.EMPLOYEE,
            departments={"finance"},
        ),
        expected_in_scope=True,
        expected_outcome=ExpectedOutcome.ANSWER,
        gold_evidence_keys={"expense-v2-deadline"},
        expected_versions={"finance-expense-policy": "2.0"},
        required_answer_facts=["15个自然日"],
    )


def make_refusal_case(case_id: str = "dev-refusal-001") -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        split=EvaluationSplit.DEVELOPMENT,
        question="告诉我付款审批权限表",
        as_of=NOW,
        user=UserContext(
            user_id="eval-user",
            role=UserRole.EMPLOYEE,
            departments={"finance"},
        ),
        expected_in_scope=True,
        expected_outcome=ExpectedOutcome.REFUSAL,
        expected_refusal_reason=RefusalReason.PERMISSION_DENIED,
        forbidden_document_ids={"finance-payment-approval"},
    )


class FixedExecutor:
    def __init__(self) -> None:
        self.calls = []

    def run(self, case, *, strategy, corpus_snapshot):
        self.calls.append((case.case_id, strategy, corpus_snapshot))
        if case.expected_outcome is ExpectedOutcome.REFUSAL:
            return EvaluationObservation(
                in_scope=True,
                status="refused",
                refusal_reason=RefusalReason.PERMISSION_DENIED,
                latency_ms=300.0,
                model_calls=0,
            )
        return EvaluationObservation(
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
            answer="应在 15个自然日 内提交。",
            latency_ms=100.0,
            model_calls=2,
        )


def test_runner_freezes_strategy_snapshot_and_aggregates_stages() -> None:
    executor = FixedExecutor()
    dataset = EvaluationDataset(
        dataset_id="development-v1",
        version="1.0",
        split=EvaluationSplit.DEVELOPMENT,
        cases=[make_answer_case(), make_refusal_case()],
    )

    report = EvaluationRunner(executor, clock=lambda: NOW).run(
        dataset,
        strategy=EvaluationStrategy.HYBRID_RRF_RERANKER,
        corpus_snapshot="sha256:corpus-v1",
        experiment=EXPERIMENT,
        ranking_k=5,
    )

    assert executor.calls == [
        (
            "dev-answer-001",
            EvaluationStrategy.HYBRID_RRF_RERANKER,
            "sha256:corpus-v1",
        ),
        (
            "dev-refusal-001",
            EvaluationStrategy.HYBRID_RRF_RERANKER,
            "sha256:corpus-v1",
        ),
    ]
    assert report.metrics.case_count == 2
    assert report.metrics.execution_success_rate == 1.0
    assert report.metrics.core_pass_rate == 1.0
    assert report.metrics.recall_at_k == 1.0
    assert report.metrics.correct_refusal_rate == 1.0
    assert report.metrics.access_leakage_rate == 0.0
    assert report.metrics.p50_latency_ms == 200.0
    assert report.metrics.p95_latency_ms == 300.0
    assert report.metrics.p99_latency_ms == 300.0
    assert report.metrics.total_model_calls == 2
    assert report.experiment.code_commit == "abc1234"


class FailingExecutor(FixedExecutor):
    def run(self, case, *, strategy, corpus_snapshot):
        if case.case_id == "dev-answer-001":
            raise TimeoutError("provider secret must not enter the report")
        return super().run(
            case,
            strategy=strategy,
            corpus_snapshot=corpus_snapshot,
        )


def test_runner_records_case_failure_without_leaking_exception_text() -> None:
    dataset = EvaluationDataset(
        dataset_id="development-v1",
        version="1.0",
        split=EvaluationSplit.DEVELOPMENT,
        cases=[make_answer_case(), make_refusal_case()],
    )

    report = EvaluationRunner(FailingExecutor(), clock=lambda: NOW).run(
        dataset,
        strategy=EvaluationStrategy.VECTOR_BASELINE,
        corpus_snapshot="sha256:corpus-v1",
        experiment=EXPERIMENT,
    )

    assert report.metrics.execution_success_rate == 0.5
    assert report.metrics.core_pass_rate == 0.5
    assert report.cases[0].error_type == "TimeoutError"
    assert report.cases[0].error_code == "execution_error"
    assert "secret" not in report.model_dump_json()


def test_runner_can_evaluate_in_parallel_without_reordering_results() -> None:
    barrier = Barrier(2)
    lock = Lock()
    active = 0
    peak_active = 0

    class ParallelExecutor(FixedExecutor):
        def run(self, case, *, strategy, corpus_snapshot):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            barrier.wait(timeout=2)
            try:
                return super().run(
                    case,
                    strategy=strategy,
                    corpus_snapshot=corpus_snapshot,
                )
            finally:
                with lock:
                    active -= 1

    dataset = EvaluationDataset(
        dataset_id="development-v1",
        version="1.0",
        split=EvaluationSplit.DEVELOPMENT,
        cases=[make_answer_case("first"), make_answer_case("second")],
    )

    report = EvaluationRunner(
        ParallelExecutor(),
        max_workers=2,
        clock=lambda: NOW,
    ).run(
        dataset,
        strategy=EvaluationStrategy.HYBRID_RRF,
        corpus_snapshot="sha256:corpus-v1",
        experiment=EXPERIMENT,
    )

    assert peak_active == 2
    assert [case.case_id for case in report.cases] == ["first", "second"]


def test_frozen_holdout_is_locked_by_default() -> None:
    executor = FixedExecutor()
    case = make_answer_case().model_copy(
        update={
            "case_id": "holdout-answer-001",
            "split": EvaluationSplit.FROZEN_HOLDOUT,
        }
    )
    dataset = EvaluationDataset(
        dataset_id="frozen-holdout-v1",
        version="1.0",
        split=EvaluationSplit.FROZEN_HOLDOUT,
        frozen_at=NOW,
        cases=[case],
    )

    with pytest.raises(FrozenHoldoutLockedError):
        EvaluationRunner(executor, clock=lambda: NOW).run(
            dataset,
            strategy=EvaluationStrategy.HYBRID_RRF,
            corpus_snapshot="sha256:corpus-v1",
            experiment=EXPERIMENT,
        )

    assert executor.calls == []


def test_committed_datasets_validate_without_running_holdout() -> None:
    project_root = Path(__file__).resolve().parents[1]

    development = load_dataset(project_root / "evaluation" / "development.json")
    holdout = load_dataset(project_root / "evaluation" / "frozen_holdout.json")

    assert development.split is EvaluationSplit.DEVELOPMENT
    assert len(development.cases) == 18
    assert holdout.split is EvaluationSplit.FROZEN_HOLDOUT
    assert len(holdout.cases) == 8
