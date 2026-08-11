import json
from collections.abc import Callable, Sequence
from math import isfinite
from typing import Any

from pydantic import BaseModel


class ModelProviderError(RuntimeError):
    """Stable model boundary error without provider response details."""


def _default_embedding_loader(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _default_reranker_loader(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


def _as_vectors(raw: Any) -> list[list[float]]:
    values = raw.tolist() if hasattr(raw, "tolist") else raw
    try:
        return [[float(value) for value in vector] for vector in values]
    except (TypeError, ValueError) as exc:
        raise ModelProviderError("model returned invalid embedding vectors") from exc


def _validate_vectors(
    vectors: list[list[float]],
    texts: Sequence[str],
    expected_dimension: int,
) -> list[list[float]]:
    if len(vectors) != len(texts):
        raise ModelProviderError("embedding result count does not match input")
    if any(len(vector) != expected_dimension for vector in vectors):
        raise ModelProviderError("embedding vector dimension does not match schema")
    if any(not isfinite(value) for vector in vectors for value in vector):
        raise ModelProviderError("embedding vectors must contain finite values")
    return vectors


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        model_name: str,
        *,
        expected_dimension: int = 1024,
        model_loader: Callable[[str], Any] = _default_embedding_loader,
    ) -> None:
        self.model_name = model_name
        self.expected_dimension = expected_dimension
        self._model_loader = model_loader
        self._model: Any | None = None

    def _load_model(self):
        if self._model is None:
            self._model = self._model_loader(self.model_name)
        return self._model

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        input_texts = list(texts)
        if not input_texts:
            return []
        if any(not text.strip() for text in input_texts):
            raise ModelProviderError("embedding input must not be empty")
        try:
            raw = self._load_model().encode(
                input_texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vectors = _as_vectors(raw)
        except ModelProviderError:
            raise
        except Exception as exc:
            raise ModelProviderError("embedding model request failed") from exc
        return _validate_vectors(vectors, input_texts, self.expected_dimension)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._embed([query])[0]


class OpenAICompatibleEmbeddingProvider:
    """Embedding provider for OpenAI-compatible vendor APIs."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        expected_dimension: int = 1024,
        batch_size: int = 20,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._expected_dimension = expected_dimension
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        input_texts = list(texts)
        if not input_texts:
            return []
        if any(not text.strip() for text in input_texts):
            raise ModelProviderError("embedding input must not be empty")
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(input_texts), self._batch_size):
                batch = input_texts[start : start + self._batch_size]
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                    dimensions=self._expected_dimension,
                    timeout=self._timeout_seconds,
                )
                data = sorted(response.data, key=lambda item: item.index)
                vectors.extend(_as_vectors([item.embedding for item in data]))
        except ModelProviderError:
            raise
        except Exception as exc:
            raise ModelProviderError("embedding API request failed") from exc
        return _validate_vectors(vectors, input_texts, self._expected_dimension)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._embed([query])[0]


class CrossEncoderRerankerProvider:
    def __init__(
        self,
        model_name: str,
        *,
        model_loader: Callable[[str], Any] = _default_reranker_loader,
    ) -> None:
        self.model_name = model_name
        self._model_loader = model_loader
        self._model: Any | None = None

    def _load_model(self):
        if self._model is None:
            self._model = self._model_loader(self.model_name)
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        values = list(passages)
        if not values:
            return []
        try:
            raw_scores = self._load_model().predict(
                [(query, passage) for passage in values]
            )
            raw_scores = (
                raw_scores.tolist() if hasattr(raw_scores, "tolist") else raw_scores
            )
            scores = [float(score) for score in raw_scores]
        except Exception as exc:
            raise ModelProviderError("reranker model request failed") from exc
        if len(scores) != len(values) or any(not isfinite(score) for score in scores):
            raise ModelProviderError("reranker returned invalid scores")
        return scores


class OpenAICompatibleStructuredProvider:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                timeout=self._timeout_seconds,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "只输出符合以下 JSON Schema 的 JSON 对象，"
                            f"不要输出 Markdown 或解释。JSON Schema: {schema_json}"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
            return schema.model_validate(payload)
        except Exception as exc:
            raise ModelProviderError(
                "model returned an invalid structured response"
            ) from exc


class RemoteRerankerProvider:
    """Rerank provider backed by an OpenAI-compatible /reranks endpoint."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        values = list(passages)
        if not values:
            return []
        try:
            response = self._client.post(
                "/reranks",
                body={
                    "model": self._model,
                    "query": query,
                    "documents": values,
                    "top_n": len(values),
                },
                timeout=self._timeout_seconds,
            )
            payload = response.json() if hasattr(response, "json") else response
        except Exception as exc:
            raise ModelProviderError("reranker model request failed") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if results is None:
            raise ModelProviderError("reranker returned no results")
        by_index: dict[int, float] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            if isinstance(index, int):
                by_index[index] = float(item.get("relevance_score", 0.0))
        scores = [by_index.get(index, 0.0) for index in range(len(values))]
        if len(scores) != len(values) or any(not isfinite(score) for score in scores):
            raise ModelProviderError("reranker returned invalid scores")
        return scores


class NullRerankerProvider:
    """Fail-fast placeholder when reranking is disabled; never called on hybrid_rrf."""

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        raise ModelProviderError("reranker is disabled")
