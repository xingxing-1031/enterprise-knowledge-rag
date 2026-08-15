import json
import os
from hashlib import sha256
from pathlib import Path

from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.evaluation import (
    EvaluationRunner,
    EvaluationStrategy,
    ExperimentMetadata,
    WorkflowEvaluationExecutor,
    load_dataset,
)

try:
    from scripts.evaluation_support import (
        build_live_services,
        code_commit,
        corpus_snapshot,
    )
except ModuleNotFoundError:
    from evaluation_support import build_live_services, code_commit, corpus_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA256 = "9e21768f777e61cccd27adc2555ec6e71233aeb6a65db6e83442e836b1b27fb3"


def verify_frozen_hash(dataset_path: Path) -> None:
    actual = sha256(dataset_path.read_bytes()).hexdigest()
    if actual != FROZEN_SHA256:
        raise RuntimeError(
            f"frozen holdout hash mismatch: expected {FROZEN_SHA256}, got {actual}"
        )


def require_frozen_confirmation(confirmation: str, output_path: Path) -> None:
    if confirmation != "CONSUME_ONCE":
        raise RuntimeError(
            "set FROZEN_HOLDOUT_CONFIRM=CONSUME_ONCE for final acceptance"
        )
    if output_path.exists():
        raise FileExistsError(f"final holdout report already exists: {output_path}")


def main() -> int:
    dataset_path = PROJECT_ROOT / "evaluation" / "frozen-holdout-v2.json"
    output_path = PROJECT_ROOT / "evaluation" / "reports" / "final-holdout-v2.json"
    verify_frozen_hash(dataset_path)
    require_frozen_confirmation(
        os.getenv("FROZEN_HOLDOUT_CONFIRM", ""),
        output_path,
    )
    dataset = load_dataset(dataset_path)
    max_workers = int(os.getenv("EVAL_MAX_WORKERS", "1"))
    if max_workers < 1:
        raise ValueError("EVAL_MAX_WORKERS must be positive")

    settings = get_settings()
    strategy = EvaluationStrategy(settings.retrieval_strategy)
    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        services = build_live_services(settings, pool.connection)
        service = services[strategy]
        if not service.ready():
            raise RuntimeError("knowledge database is not ready for evaluation")
        report = EvaluationRunner(
            WorkflowEvaluationExecutor({strategy: service}),
            allow_frozen=True,
            max_workers=max_workers,
        ).run(
            dataset,
            strategy=strategy,
            corpus_snapshot=corpus_snapshot(PROJECT_ROOT),
            experiment=ExperimentMetadata(
                code_commit=code_commit(PROJECT_ROOT),
                embedding_model=settings.embedding_model,
                reranker_model=(
                    settings.reranker_model
                    if strategy is EvaluationStrategy.HYBRID_RRF_RERANKER
                    else None
                ),
                llm_model=settings.model_name,
                prompt_version="generation-v1",
                temperature=0.0,
                repetition=1,
                environment=settings.app_env,
            ),
        )
    finally:
        pool.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "strategy": strategy.value,
                "case_count": report.metrics.case_count,
                "core_pass_rate": report.metrics.core_pass_rate,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
