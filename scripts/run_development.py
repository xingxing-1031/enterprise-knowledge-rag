import json
import os
from pathlib import Path

from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.evaluation import (
    EvaluationReport,
    EvaluationRunner,
    EvaluationStrategy,
    WorkflowEvaluationExecutor,
    load_dataset,
    summarize_development_reports,
)
from enterprise_knowledge_rag.evaluation.models import ExperimentMetadata

try:
    from scripts.evaluation_support import (
        build_live_services,
        code_commit,
        corpus_snapshot,
    )
except ModuleNotFoundError:
    from evaluation_support import build_live_services, code_commit, corpus_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = get_settings()
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development-v2.json")
    repetitions = int(os.getenv("EVAL_REPETITIONS", "1"))
    if repetitions < 1:
        raise ValueError("EVAL_REPETITIONS must be positive")

    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        services = build_live_services(settings, pool.connection)
        if not all(service.ready() for service in services.values()):
            raise RuntimeError("knowledge database is not ready for evaluation")

        snapshot = corpus_snapshot(PROJECT_ROOT)
        commit = code_commit(PROJECT_ROOT)
        selected_strategy = EvaluationStrategy(settings.retrieval_strategy)
        reports_dir = PROJECT_ROOT / "evaluation" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        generated_reports: list[EvaluationReport] = []
        for repetition in range(1, repetitions + 1):
            executor = WorkflowEvaluationExecutor(services)
            for strategy in EvaluationStrategy:
                metadata = ExperimentMetadata(
                    code_commit=commit,
                    embedding_model=settings.embedding_model,
                    reranker_model=(
                        settings.reranker_model
                        if strategy is EvaluationStrategy.HYBRID_RRF_RERANKER
                        else None
                    ),
                    llm_model=settings.model_name,
                    prompt_version="generation-v1",
                    temperature=0.0,
                    repetition=repetition,
                    environment=settings.app_env,
                )
                report = EvaluationRunner(
                    executor,
                ).run(
                    dataset,
                    strategy=strategy,
                    corpus_snapshot=snapshot,
                    experiment=metadata,
                )
                generated_reports.append(report)
                output = reports_dir / (
                    f"development-{strategy.value}-r{repetition}.json"
                )
                output.write_text(
                    report.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                if strategy is selected_strategy:
                    (reports_dir / "latest-development.json").write_text(
                        report.model_dump_json(indent=2),
                        encoding="utf-8",
                    )
                print(
                    json.dumps(
                        {
                            "strategy": strategy.value,
                            "repetition": repetition,
                            "core_pass_rate": report.metrics.core_pass_rate,
                            "execution_success_rate": (
                                report.metrics.execution_success_rate
                            ),
                        },
                        ensure_ascii=False,
                    )
                )
        summary = summarize_development_reports(generated_reports)
        (reports_dir / "development-summary.json").write_text(
            summary.model_dump_json(indent=2),
            encoding="utf-8",
        )
    finally:
        pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
