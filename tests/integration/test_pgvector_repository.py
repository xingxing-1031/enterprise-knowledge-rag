import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_knowledge_rag.documents import chunk_document, parse_document
from enterprise_knowledge_rag.documents.repository import KnowledgeRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_PGVECTOR_TESTS"),
    reason="set RUN_PGVECTOR_TESTS=1 after starting the test database",
)


def test_pgvector_repository_contract() -> None:
    psycopg = pytest.importorskip("psycopg")
    database_url = os.environ["DATABASE_URL"]
    repository = KnowledgeRepository(lambda: psycopg.connect(database_url))
    path = Path(__file__).parents[2] / "knowledge" / "hr" / "leave-policy-v2.md"
    document = parse_document(
        path,
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    chunks = chunk_document(document)
    vectors = [[0.0] * 1024 for _ in chunks]

    repository.upsert_document(document.record, chunks, vectors)

    assert (
        repository.get_content_hash(
            document.record.document_id,
            document.record.version,
        )
        == document.record.content_hash
    )
