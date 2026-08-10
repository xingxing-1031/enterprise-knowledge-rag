import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

from openai import OpenAI

from enterprise_knowledge_rag.bootstrap import build_runtime_service
from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.evaluation import (
    EvaluationRunner,
    EvaluationStrategy,
    WorkflowEvaluationExecutor,
    load_dataset,
)
from enterprise_knowledge_rag.evaluation.models import ExperimentMetadata
from enterprise_knowledge_rag.providers import (
    CrossEncoderRerankerProvider,
    SentenceTransformerEmbeddingProvider,
)
from enterprise_knowledge_rag.retrieval import RetrievalStrategy

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _corpus_snapshot() -> str:
    digest = sha256()
    for path in sorted((PROJECT_ROOT / "knowledge").rglob("*.md")):
        if path.name == "README.md":
            continue
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _code_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown0"


def main() -> int:
    settings = get_settings()
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development.json")
    repetitions = int(os.getenv("EVAL_REPETITIONS", "1"))
    if repetitions < 1:
        raise ValueError("EVAL_REPETITIONS must be positive")

    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        chat_client = OpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
        )
        embeddings = SentenceTransformerEmbeddingProvider(
            settings.embedding_model,
            expected_dimension=settings.embedding_dimension,
        )
        reranker = CrossEncoderRerankerProvider(settings.reranker_model)
        services = {
            strategy: build_runtime_service(
                settings,
                connection_factory=pool.connection,
                chat_client=chat_client,
                embeddings=embeddings,
                reranker_scores=reranker,
                retrieval_strategy=retrieval_strategy,
            )
            for strategy, retrieval_strategy in {
                EvaluationStrategy.VECTOR_BASELINE: RetrievalStrategy.VECTOR_BASELINE,
                EvaluationStrategy.HYBRID_RRF: RetrievalStrategy.HYBRID_RRF,
                EvaluationStrategy.HYBRID_RRF_RERANKER: (
                    RetrievalStrategy.HYBRID_RRF_RERANKER
                ),
            }.items()
        }
        if not all(service.ready() for service in services.values()):
            raise RuntimeError("knowledge database is not ready for evaluation")

        snapshot = _corpus_snapshot()
        reports_dir = PROJECT_ROOT / "evaluation" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        for repetition in range(1, repetitions + 1):
            executor = WorkflowEvaluationExecutor(services)
            for strategy in EvaluationStrategy:
                metadata = ExperimentMetadata(
                    code_commit=_code_commit(),
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
                output = reports_dir / (
                    f"development-{strategy.value}-r{repetition}.json"
                )
                output.write_text(
                    report.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                if strategy is EvaluationStrategy.HYBRID_RRF_RERANKER:
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
    finally:
        pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
