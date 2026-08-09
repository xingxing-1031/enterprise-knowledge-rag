from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from statistics import fmean, median
from typing import Protocol

from .graders import grade_case
from .models import (
    AggregateMetrics,
    CaseEvaluation,
    CaseMetrics,
    EvaluationCase,
    EvaluationDataset,
    EvaluationObservation,
    EvaluationReport,
    EvaluationSplit,
    EvaluationStrategy,
)


class FrozenHoldoutLockedError(RuntimeError):
    pass


class EvaluationExecutor(Protocol):
    def run(
        self,
        case: EvaluationCase,
        *,
        strategy: EvaluationStrategy,
        corpus_snapshot: str,
    ) -> EvaluationObservation: ...


def load_dataset(path: Path) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _metric_values(
    results: Sequence[CaseEvaluation],
    field: str,
) -> list[float]:
    values: list[float] = []
    for result in results:
        if result.metrics is None:
            continue
        value = getattr(result.metrics, field)
        if value is not None:
            values.append(value)
    return values


def _ranking_values(
    results: Sequence[CaseEvaluation],
    field: str,
) -> list[float]:
    return [
        getattr(result.metrics.ranking, field)
        for result in results
        if result.metrics is not None and result.metrics.ranking is not None
    ]


def _nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(ceil(len(ordered) * percentile) - 1, 0)
    return ordered[index]


def _aggregate(results: Sequence[CaseEvaluation]) -> AggregateMetrics:
    successful = [result for result in results if result.metrics is not None]
    latencies = [result.observation.latency_ms for result in successful]
    core_passes = sum(
        result.metrics is not None and result.metrics.core_pass for result in results
    )
    return AggregateMetrics(
        case_count=len(results),
        execution_success_rate=len(successful) / len(results),
        core_pass_rate=core_passes / len(results),
        domain_accuracy=_mean(_metric_values(results, "domain_accuracy")),
        recall_at_k=_mean(_ranking_values(results, "recall_at_k")),
        reciprocal_rank=_mean(_ranking_values(results, "reciprocal_rank")),
        ndcg_at_k=_mean(_ranking_values(results, "ndcg_at_k")),
        access_leakage_rate=_mean(_metric_values(results, "access_leakage")),
        version_accuracy=_mean(_metric_values(results, "version_accuracy")),
        citation_accuracy=_mean(_metric_values(results, "citation_accuracy")),
        correct_refusal_rate=_mean(_metric_values(results, "correct_refusal")),
        false_refusal_rate=_mean(_metric_values(results, "false_refusal")),
        automated_answer_score=_mean(_metric_values(results, "automated_answer_score")),
        p50_latency_ms=median(latencies) if latencies else None,
        p95_latency_ms=(
            _nearest_rank_percentile(latencies, 0.95) if latencies else None
        ),
        total_model_calls=sum(result.observation.model_calls for result in successful),
    )


class EvaluationRunner:
    def __init__(
        self,
        executor: EvaluationExecutor,
        *,
        allow_frozen: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._executor = executor
        self._allow_frozen = allow_frozen
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(
        self,
        dataset: EvaluationDataset,
        *,
        strategy: EvaluationStrategy,
        corpus_snapshot: str,
        ranking_k: int = 5,
    ) -> EvaluationReport:
        if dataset.split is EvaluationSplit.FROZEN_HOLDOUT and not self._allow_frozen:
            raise FrozenHoldoutLockedError(
                "frozen holdout requires an explicit final-acceptance runner"
            )
        if ranking_k < 1:
            raise ValueError("ranking_k must be positive")

        started_at = self._clock()
        results: list[CaseEvaluation] = []
        for case in dataset.cases:
            try:
                observation = self._executor.run(
                    case,
                    strategy=strategy,
                    corpus_snapshot=corpus_snapshot,
                )
                metrics: CaseMetrics = grade_case(case, observation, k=ranking_k)
                results.append(
                    CaseEvaluation(
                        case_id=case.case_id,
                        observation=observation,
                        metrics=metrics,
                    )
                )
            except Exception as exc:
                results.append(
                    CaseEvaluation(
                        case_id=case.case_id,
                        error_type=type(exc).__name__,
                    )
                )

        completed_at = self._clock()
        return EvaluationReport(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            split=dataset.split,
            strategy=strategy,
            corpus_snapshot=corpus_snapshot,
            ranking_k=ranking_k,
            started_at=started_at,
            completed_at=completed_at,
            holdout_consumed_at=(
                started_at if dataset.split is EvaluationSplit.FROZEN_HOLDOUT else None
            ),
            metrics=_aggregate(results),
            cases=results,
        )
