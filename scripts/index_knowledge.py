import json
import os
from collections.abc import Sequence
from hashlib import sha256
from math import sqrt

from enterprise_knowledge_rag.bootstrap import build_runtime_service
from enterprise_knowledge_rag.config import Settings, get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.models import UserContext, UserRole
from enterprise_knowledge_rag.providers import SentenceTransformerEmbeddingProvider


class DeterministicTestEmbeddings:
    """Dependency-free vectors for infrastructure CI, never for quality claims."""

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    def _embed(self, text: str) -> list[float]:
        seed = sha256(text.encode("utf-8")).digest()
        values = [
            (seed[index % len(seed)] - 127.5) / 127.5
            for index in range(self._dimension)
        ]
        norm = sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query)


def _test_embeddings_enabled(settings: Settings) -> bool:
    requested = os.getenv("DETERMINISTIC_TEST_EMBEDDINGS", "").lower() == "true"
    if requested and settings.app_env != "ci":
        raise RuntimeError("deterministic embeddings are restricted to APP_ENV=ci")
    return requested


def build_embedding_provider(settings: Settings):
    if _test_embeddings_enabled(settings):
        return DeterministicTestEmbeddings(settings.embedding_dimension)
    return SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        expected_dimension=settings.embedding_dimension,
    )


def main() -> int:
    settings = get_settings()
    embeddings = build_embedding_provider(settings)
    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        service = build_runtime_service(
            settings,
            connection_factory=pool.connection,
            embeddings=embeddings,
        )
        result = service.index_documents(
            UserContext(
                user_id="system-indexer",
                role=UserRole.KNOWLEDGE_ADMIN,
                departments=set(),
            )
        )
    finally:
        pool.close()
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
