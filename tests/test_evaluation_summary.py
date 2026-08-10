from datetime import UTC, datetime

import pytest

from enterprise_knowledge_rag.evaluation.models import (
    AggregateMetrics,
    EvaluationReport,
    EvaluationSplit,
    EvaluationStrategy,
    ExperimentMetadata,
)
from enterprise_knowledge_rag.evaluation.summary import (
    summarize_development_reports,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def make_report(
    strategy: EvaluationStrategy,
    repetition: int,
    *,
    core_pass_rate: float,
    dataset_id: str = "development-v1",
    corpus_snapshot: str = "sha256:corpus-v1",
    code_commit: str = "abc1234",
    llm_model: str = "qwen-plus",
) -> EvaluationReport:
    return EvaluationReport(
        dataset_id=dataset_id,
        dataset_version="1.0",
        split=EvaluationSplit.DEVELOPMENT,
        strategy=strategy,
        corpus_snapshot=corpus_snapshot,
        ranking_k=5,
        experiment=ExperimentMetadata(
            code_commit=code_commit,
            embedding_model="BAAI/bge-m3",
            reranker_model=(
                "BAAI/bge-reranker-v2-m3"
                if strategy is EvaluationStrategy.HYBRID_RRF_RERANKER
                else None
            ),
            llm_model=llm_model,
            prompt_version="generation-v1",
            temperature=0.0,
            repetition=repetition,
            environment="unit-test",
        ),
        started_at=NOW,
        completed_at=NOW,
        metrics=AggregateMetrics(
            case_count=2,
            execution_success_rate=1.0,
            core_pass_rate=core_pass_rate,
            recall_at_k=core_pass_rate,
            citation_accuracy=core_pass_rate,
            access_leakage_rate=0.0,
            evidence_need_coverage=core_pass_rate,
            second_hop_trigger_accuracy=core_pass_rate,
            second_hop_success=core_pass_rate,
            irrelevant_evidence_ratio=1.0 - core_pass_rate,
            p50_latency_ms=100.0 * repetition,
            p95_latency_ms=200.0 * repetition,
            total_model_calls=2 * repetition,
        ),
        cases=[],
    )


def complete_reports() -> list[EvaluationReport]:
    return [
        make_report(strategy, repetition, core_pass_rate=value)
        for strategy in EvaluationStrategy
        for repetition, value in [(1, 0.5), (2, 1.0)]
    ]


def test_summary_aggregates_repeated_strategy_metrics() -> None:
    summary = summarize_development_reports(complete_reports())

    hybrid = next(
        item
        for item in summary.strategies
        if item.strategy is EvaluationStrategy.HYBRID_RRF
    )
    assert hybrid.repetitions == [1, 2]
    assert hybrid.metrics["core_pass_rate"].mean == pytest.approx(0.75)
    assert hybrid.metrics["core_pass_rate"].minimum == 0.5
    assert hybrid.metrics["core_pass_rate"].maximum == 1.0
    assert hybrid.metrics["core_pass_rate"].population_stddev == 0.25


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("dataset_id", "development-v2", "dataset_id"),
        ("corpus_snapshot", "sha256:corpus-v2", "corpus_snapshot"),
        ("code_commit", "def5678", "code_commit"),
        ("llm_model", "another-model", "llm_model"),
    ],
)
def test_summary_rejects_mixed_experiment_identity(
    field: str,
    value: str,
    message: str,
) -> None:
    reports = complete_reports()
    report = reports[-1]
    if field in {"dataset_id", "corpus_snapshot"}:
        reports[-1] = report.model_copy(update={field: value})
    else:
        reports[-1] = report.model_copy(
            update={"experiment": report.experiment.model_copy(update={field: value})}
        )

    with pytest.raises(ValueError, match=message):
        summarize_development_reports(reports)


def test_summary_rejects_duplicate_strategy_repetition_pair() -> None:
    reports = complete_reports()
    reports.append(reports[0])

    with pytest.raises(ValueError, match="duplicate"):
        summarize_development_reports(reports)


def test_summary_requires_every_strategy_and_contiguous_repetitions() -> None:
    reports = complete_reports()

    with pytest.raises(ValueError, match="strategies"):
        summarize_development_reports(
            [
                report
                for report in reports
                if report.strategy is not EvaluationStrategy.VECTOR_BASELINE
            ]
        )

    reports[-1] = reports[-1].model_copy(
        update={
            "experiment": reports[-1].experiment.model_copy(
                update={"repetition": 3}
            )
        }
    )
    with pytest.raises(ValueError, match="contiguous"):
        summarize_development_reports(reports)
