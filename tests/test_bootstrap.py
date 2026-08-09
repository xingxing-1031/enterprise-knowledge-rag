from pathlib import Path

from enterprise_knowledge_rag.bootstrap import build_runtime_service
from enterprise_knowledge_rag.config import Settings
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
