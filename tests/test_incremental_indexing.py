from pathlib import Path

from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.documents.indexing import IndexingService

CORPUS_DIR = Path(__file__).parents[1] / "knowledge"


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0, 0.0, 0.0] for text in texts]


class FakeRepository:
    def __init__(self):
        self.hashes = {}
        self.by_hash = {}
        self.upserts = []

    def get_content_hash(self, document_id, version):
        return self.hashes.get((document_id, version))

    def find_document_by_hash(self, content_hash):
        return self.by_hash.get(content_hash)

    def upsert_document(self, document, chunks, embeddings):
        key = (document.document_id, document.version)
        self.hashes[key] = document.content_hash
        self.by_hash[document.content_hash] = key
        self.upserts.append((document, list(chunks), list(embeddings)))


def make_service(repository=None):
    return IndexingService(
        repository=repository or FakeRepository(),
        embeddings=FakeEmbeddings(),
        settings=Settings(),
    )


def test_first_index_writes_document_chunks_and_vectors() -> None:
    repository = FakeRepository()
    service = make_service(repository)
    path = CORPUS_DIR / "hr" / "leave-policy-v2.md"

    result = service.index_paths([path])

    assert result.indexed == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert result.chunk_count > 0
    document, chunks, vectors = repository.upserts[0]
    assert document.version == "2.0"
    assert all(chunk.document_version == "2.0" for chunk in chunks)
    assert len(chunks) == len(vectors)


def test_unchanged_document_is_skipped() -> None:
    repository = FakeRepository()
    service = make_service(repository)
    path = CORPUS_DIR / "finance" / "expense-policy-v2.md"

    first = service.index_paths([path])
    second = service.index_paths([path])

    assert first.indexed == 1
    assert second.skipped == 1
    assert len(repository.upserts) == 1


def test_duplicate_content_under_another_identity_is_rejected() -> None:
    repository = FakeRepository()
    service = make_service(repository)
    path = CORPUS_DIR / "admin" / "asset-management-policy.md"
    first = service.index_paths([path])
    document = repository.upserts[0][0]
    repository.hashes.clear()
    repository.by_hash[document.content_hash] = ("other-document", "9.9")

    second = service.index_paths([path])

    assert first.indexed == 1
    assert second.failed == 1
    assert "duplicate content" in second.errors[0]


def test_invalid_document_is_recorded_without_stopping_batch(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.md"
    invalid.write_text("no front matter", encoding="utf-8")
    valid = CORPUS_DIR / "hr" / "onboarding-process.md"

    result = make_service().index_paths([invalid, valid])

    assert result.discovered == 2
    assert result.indexed == 1
    assert result.failed == 1
    assert "invalid.md" in result.errors[0]
