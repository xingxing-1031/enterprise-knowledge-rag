from pathlib import Path

import pytest

from enterprise_knowledge_rag.bootstrap import (
    _resolve_retrieval_strategy,
    build_runtime_service,
)
from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.retrieval import RetrievalStrategy
from enterprise_knowledge_rag.runtime import RuntimeChatService


class UnusedConnection:
    def __call__(self):
        raise AssertionError("bootstrap must not connect eagerly")


class FakeEmbeddings:
    def embed_documents(self, texts):
        raise AssertionError("bootstrap must not embed eagerly")

    def embed_query(self, query):
        raise AssertionError("bootstrap must not embed eagerly")


class FakeReranker:
    def score(self, query, passages):
        raise AssertionError("bootstrap must not rerank eagerly")


class FakeChatClient:
    pass


def test_bootstrap_wires_runtime_without_eager_external_calls(tmp_path: Path) -> None:
    settings = Settings(
        knowledge_dir=tmp_path / "knowledge",
        latest_evaluation_path=tmp_path / "latest.json",
    )

    service = build_runtime_service(
        settings,
        connection_factory=UnusedConnection(),
        chat_client=FakeChatClient(),
        embeddings=FakeEmbeddings(),
        reranker_scores=FakeReranker(),
    )

    assert isinstance(service, RuntimeChatService)


def test_bootstrap_resolves_configured_strategy_and_explicit_override() -> None:
    settings = Settings(_env_file=None, retrieval_strategy="vector_baseline")

    assert (
        _resolve_retrieval_strategy(settings, None)
        is RetrievalStrategy.VECTOR_BASELINE
    )
    assert (
        _resolve_retrieval_strategy(
            settings,
            RetrievalStrategy.HYBRID_RRF_RERANKER,
        )
        is RetrievalStrategy.HYBRID_RRF_RERANKER
    )


def test_settings_reject_none_reranker_with_reranker_strategy() -> None:
    with pytest.raises(ValueError, match="reranker"):
        Settings(
            _env_file=None,
            reranker_provider="none",
            retrieval_strategy="hybrid_rrf_reranker",
        )


def test_settings_allow_none_reranker_without_reranker_strategy() -> None:
    settings = Settings(
        _env_file=None,
        reranker_provider="none",
        retrieval_strategy="hybrid_rrf",
    )

    assert settings.reranker_provider == "none"
