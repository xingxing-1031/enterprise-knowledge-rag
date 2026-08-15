from collections.abc import Sequence
from statistics import fmean, pstdev

from pydantic import Field

from enterprise_knowledge_rag.models import StrictModel

from .models import EvaluationReport, EvaluationSplit, EvaluationStrategy

SUMMARY_METRICS = (
    "execution_success_rate",
    "core_pass_rate",
    "recall_at_k",
    "citation_accuracy",
    "citation_recall",
    "access_leakage_rate",
    "evidence_need_coverage",
    "need_coverage_precision",
    "second_hop_trigger_accuracy",
    "second_hop_success",
    "irrelevant_evidence_ratio",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "total_model_calls",
)


class MetricDistribution(StrictModel):
    count: int = Field(ge=1)
    mean: float
    minimum: float
    maximum: float
    population_stddev: float = Field(ge=0.0)


class StrategyDevelopmentSummary(StrictModel):
    strategy: EvaluationStrategy
    repetitions: list[int]
    metrics: dict[str, MetricDistribution]


class DevelopmentSummary(StrictModel):
    dataset_id: str
    dataset_version: str
    corpus_snapshot: str
    code_commit: str
    llm_model: str
    strategies: list[StrategyDevelopmentSummary]


def _single_value(reports: Sequence[EvaluationReport], field: str) -> str:
    values = {str(getattr(report, field)) for report in reports}
    if len(values) != 1:
        raise ValueError(f"reports must share one {field}")
    return values.pop()


def _single_experiment_value(
    reports: Sequence[EvaluationReport],
    field: str,
) -> str:
    values = {str(getattr(report.experiment, field)) for report in reports}
    if len(values) != 1:
        raise ValueError(f"reports must share one {field}")
    return values.pop()


def _distribution(values: Sequence[float]) -> MetricDistribution:
    return MetricDistribution(
        count=len(values),
        mean=fmean(values),
        minimum=min(values),
        maximum=max(values),
        population_stddev=pstdev(values),
    )


def summarize_development_reports(
    reports: Sequence[EvaluationReport],
) -> DevelopmentSummary:
    if not reports:
        raise ValueError("development reports must not be empty")
    if any(report.split is not EvaluationSplit.DEVELOPMENT for report in reports):
        raise ValueError("summary accepts development reports only")

    dataset_id = _single_value(reports, "dataset_id")
    dataset_version = _single_value(reports, "dataset_version")
    corpus_snapshot = _single_value(reports, "corpus_snapshot")
    code_commit = _single_experiment_value(reports, "code_commit")
    llm_model = _single_experiment_value(reports, "llm_model")

    pairs = [
        (report.strategy, report.experiment.repetition) for report in reports
    ]
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate strategy and repetition pair")

    present_strategies = {report.strategy for report in reports}
    expected_strategies = set(EvaluationStrategy)
    if present_strategies != expected_strategies:
        raise ValueError("reports must contain all evaluation strategies")

    expected_repetitions: list[int] | None = None
    strategies: list[StrategyDevelopmentSummary] = []
    for strategy in EvaluationStrategy:
        strategy_reports = sorted(
            (report for report in reports if report.strategy is strategy),
            key=lambda report: report.experiment.repetition,
        )
        repetitions = [report.experiment.repetition for report in strategy_reports]
        if repetitions != list(range(1, len(repetitions) + 1)):
            raise ValueError("strategy repetitions must be contiguous from 1")
        if expected_repetitions is None:
            expected_repetitions = repetitions
        elif repetitions != expected_repetitions:
            raise ValueError("strategies must share the same repetitions")

        metrics: dict[str, MetricDistribution] = {}
        for metric_name in SUMMARY_METRICS:
            values = [
                float(value)
                for report in strategy_reports
                if (value := getattr(report.metrics, metric_name)) is not None
            ]
            if values:
                metrics[metric_name] = _distribution(values)
        strategies.append(
            StrategyDevelopmentSummary(
                strategy=strategy,
                repetitions=repetitions,
                metrics=metrics,
            )
        )

    return DevelopmentSummary(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        corpus_snapshot=corpus_snapshot,
        code_commit=code_commit,
        llm_model=llm_model,
        strategies=strategies,
    )
