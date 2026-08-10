import os
import subprocess
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from openai import OpenAI

from enterprise_knowledge_rag.bootstrap import build_runtime_service
from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.evaluation import EvaluationStrategy
from enterprise_knowledge_rag.providers import (
    CrossEncoderRerankerProvider,
    SentenceTransformerEmbeddingProvider,
)
from enterprise_knowledge_rag.retrieval import RetrievalStrategy
from enterprise_knowledge_rag.runtime import RuntimeChatService


def corpus_snapshot(project_root: Path) -> str:
    digest = sha256()
    for path in sorted((project_root / "knowledge").rglob("*.md")):
        if path.name == "README.md":
            continue
        digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def code_commit(project_root: Path) -> str:
    override = os.getenv("EVAL_CODE_COMMIT", "").strip()
    if override:
        return override
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown0"


def build_live_services(
    settings: Settings,
    connection_factory: Callable[[], Any],
) -> Mapping[EvaluationStrategy, RuntimeChatService]:
    chat_client = OpenAI(
        api_key=settings.model_api_key,
        base_url=settings.model_base_url,
    )
    embeddings = SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        expected_dimension=settings.embedding_dimension,
    )
    reranker = CrossEncoderRerankerProvider(settings.reranker_model)
    strategies = {
        EvaluationStrategy.VECTOR_BASELINE: RetrievalStrategy.VECTOR_BASELINE,
        EvaluationStrategy.HYBRID_RRF: RetrievalStrategy.HYBRID_RRF,
        EvaluationStrategy.HYBRID_RRF_RERANKER: (
            RetrievalStrategy.HYBRID_RRF_RERANKER
        ),
    }
    return {
        strategy: build_runtime_service(
            settings,
            connection_factory=connection_factory,
            chat_client=chat_client,
            embeddings=embeddings,
            reranker_scores=reranker,
            retrieval_strategy=retrieval_strategy,
        )
        for strategy, retrieval_strategy in strategies.items()
    }
