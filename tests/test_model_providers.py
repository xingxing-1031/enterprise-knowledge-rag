import json
from types import SimpleNamespace

import pytest

from enterprise_knowledge_rag.generation import DraftAnswer
from enterprise_knowledge_rag.providers import (
    CrossEncoderRerankerProvider,
    ModelProviderError,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleStructuredProvider,
    SentenceTransformerEmbeddingProvider,
)


class FakeEmbeddingModel:
    def __init__(self, dimension=4):
        self.dimension = dimension
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return [[float(index + 1)] * self.dimension for index, _ in enumerate(texts)]


def test_sentence_transformer_provider_normalizes_documents_and_query() -> None:
    model = FakeEmbeddingModel()
    provider = SentenceTransformerEmbeddingProvider(
        "fake-bge",
        expected_dimension=4,
        model_loader=lambda _: model,
    )

    documents = provider.embed_documents(["制度一", "制度二"])
    query = provider.embed_query("怎么报销")

    assert documents == [[1.0] * 4, [2.0] * 4]
    assert query == [1.0] * 4
    assert all(call[1]["normalize_embeddings"] is True for call in model.calls)


def test_embedding_provider_rejects_wrong_vector_dimension() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        "fake-bge",
        expected_dimension=4,
        model_loader=lambda _: FakeEmbeddingModel(dimension=3),
    )

    with pytest.raises(ModelProviderError, match="dimension"):
        provider.embed_query("请假")


def test_openai_compatible_embedding_provider_orders_and_validates_results() -> None:
    class FakeEmbeddings:
        def create(self, **kwargs):
            assert kwargs["model"] == "text-embedding-v4"
            assert kwargs["input"] == ["first", "second"]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                    SimpleNamespace(index=0, embedding=[1.0, 0.0]),
                ]
            )

    provider = OpenAICompatibleEmbeddingProvider(
        SimpleNamespace(embeddings=FakeEmbeddings()),
        model="text-embedding-v4",
        expected_dimension=2,
    )

    assert provider.embed_documents(["first", "second"]) == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]


class FakeCrossEncoder:
    def __init__(self):
        self.pairs = None

    def predict(self, pairs):
        self.pairs = pairs
        return [0.2, 0.9]


def test_cross_encoder_scores_only_supplied_passages() -> None:
    model = FakeCrossEncoder()
    provider = CrossEncoderRerankerProvider(
        "fake-reranker",
        model_loader=lambda _: model,
    )

    scores = provider.score("报销期限", ["票据要求", "十五天内提交"])

    assert scores == [0.2, 0.9]
    assert model.pairs == [
        ("报销期限", "票据要求"),
        ("报销期限", "十五天内提交"),
    ]


class FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_chat_client(content):
    completions = FakeCompletions(content)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def test_openai_compatible_provider_returns_validated_structured_answer() -> None:
    payload = {
        "answer": "出差结束后十五个自然日内提交。",
        "claims": [
            {
                "text": "十五个自然日内提交",
                "evidence_ids": ["ev:expense"],
            }
        ],
    }
    client, completions = make_chat_client(json.dumps(payload, ensure_ascii=False))
    provider = OpenAICompatibleStructuredProvider(client, model="qwen-plus")

    result = provider.generate(prompt="只根据证据回答", schema=DraftAnswer)

    assert result.answer == payload["answer"]
    assert completions.kwargs["temperature"] == 0
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in completions.kwargs["messages"][0]["content"]


def test_openai_compatible_provider_normalizes_invalid_response_error() -> None:
    client, _ = make_chat_client("not json")
    provider = OpenAICompatibleStructuredProvider(client, model="qwen-plus")

    with pytest.raises(ModelProviderError, match="structured response"):
        provider.generate(prompt="prompt", schema=DraftAnswer)
