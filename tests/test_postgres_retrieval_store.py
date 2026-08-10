from datetime import UTC, datetime

from enterprise_knowledge_rag.documents.repository import KnowledgeRepository
from enterprise_knowledge_rag.models import DocumentStatus, Visibility

DOCUMENT_ROW = {
    "document_id": "finance-expense-policy",
    "version": "2.0",
    "title": "差旅与费用报销管理制度",
    "document_type": "policy",
    "department": "finance",
    "visibility": "public",
    "allowed_roles": [],
    "status": "active",
    "effective_from": datetime(2026, 6, 1, tzinfo=UTC),
    "effective_to": None,
    "supersedes_id": "finance-expense-policy-v1",
    "content_hash": "a" * 64,
    "source_path": "finance/expense-policy-v2.md",
    "indexed_at": datetime(2026, 8, 10, tzinfo=UTC),
}

CHUNK_ROW = {
    **DOCUMENT_ROW,
    "chunk_id": "expense:deadline",
    "document_version": "2.0",
    "section_path": ["差旅与费用报销管理制度", "报销期限"],
    "chunk_index": 1,
    "content": "出差结束后15个自然日内提交报销申请。",
    "token_count": 20,
    "chunk_content_hash": "b" * 64,
    "embedding_model": "BAAI/bge-m3",
    "similarity": 0.88,
}


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self, **kwargs):
        return self._cursor


def make_repository(rows):
    cursor = FakeCursor(rows)
    repository = KnowledgeRepository(lambda: FakeConnection(cursor))
    return repository, cursor


def test_list_documents_maps_database_metadata() -> None:
    repository, _ = make_repository([DOCUMENT_ROW])

    documents = repository.list_documents()

    assert len(documents) == 1
    assert documents[0].status is DocumentStatus.ACTIVE
    assert documents[0].visibility is Visibility.PUBLIC
    assert documents[0].allowed_roles == set()


def test_has_embeddings_is_scoped_to_document_version_and_model() -> None:
    repository, cursor = make_repository([(True,)])

    assert repository.has_embeddings(
        "finance-expense-policy",
        "2.0",
        "BAAI/bge-m3",
    )
    assert cursor.executions[0][1] == (
        "finance-expense-policy",
        "2.0",
        "BAAI/bge-m3",
    )


def test_list_candidates_requires_authorized_document_versions() -> None:
    repository, cursor = make_repository([CHUNK_ROW])

    candidates = repository.list_candidates(
        frozenset({("finance-expense-policy", "2.0")})
    )

    assert candidates[0].chunk.chunk_id == "expense:deadline"
    assert candidates[0].document.version == "2.0"
    serialized_keys = cursor.executions[0][1]["authorized"]
    assert "finance-expense-policy" in serialized_keys
    assert "2.0" in serialized_keys


def test_vector_search_maps_similarity_and_embedding_model() -> None:
    repository, cursor = make_repository([CHUNK_ROW])

    candidates = repository.search_authorized(
        [0.1, 0.2, 0.3],
        document_keys=frozenset({("finance-expense-policy", "2.0")}),
        limit=5,
    )

    assert candidates[0].retrieval_score == 0.88
    params = cursor.executions[0][1]
    assert params["embedding_model"] == "BAAI/bge-m3"
    assert params["limit"] == 5


def test_empty_authorization_never_queries_database() -> None:
    repository, cursor = make_repository([])

    assert repository.list_candidates(frozenset()) == []
    assert repository.search_authorized([], document_keys=frozenset(), limit=5) == []
    assert cursor.executions == []


def test_ready_requires_documents_and_chunks() -> None:
    ready_repository, cursor = make_repository(
        [{"document_count": 10, "chunk_count": 24, "indexed_document_count": 10}]
    )
    empty_repository, _ = make_repository(
        [{"document_count": 0, "chunk_count": 0, "indexed_document_count": 0}]
    )

    assert ready_repository.ready() is True
    assert empty_repository.ready() is False
    assert cursor.executions[0][1] == {"embedding_model": "BAAI/bge-m3"}
