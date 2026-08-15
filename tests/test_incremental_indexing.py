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
        self.embedding_models = set()
        self.parent_embedding_models = set()
        self.upserts = []

    def get_content_hash(self, document_id, version):
        return self.hashes.get((document_id, version))

    def find_document_by_hash(self, content_hash):
        return self.by_hash.get(content_hash)

    def has_embeddings(self, document_id, version, embedding_model):
        return (document_id, version, embedding_model) in self.embedding_models

    def has_parent_embedding(self, document_id, version, embedding_model):
        return (document_id, version, embedding_model) in self.parent_embedding_models

    def upsert_document(self, document, chunks, embeddings, **parent):
        key = (document.document_id, document.version)
        self.hashes[key] = document.content_hash
        self.by_hash[document.content_hash] = key
        self.embedding_models.add(
            (document.document_id, document.version, chunks[0].embedding_model)
        )
        if parent.get("document_embedding_model"):
            self.parent_embedding_models.add(
                (
                    document.document_id,
                    document.version,
                    parent["document_embedding_model"],
                )
            )
        self.upserts.append((document, list(chunks), list(embeddings), parent))


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
    document, chunks, vectors, _ = repository.upserts[0]
    assert document.version == "2.0"
    assert all(chunk.document_version == "2.0" for chunk in chunks)
    assert len(chunks) == len(vectors)


def test_retail_refund_policy_is_part_of_synthetic_corpus() -> None:
    path = CORPUS_DIR / "operations" / "retail-after-sales-refund-policy.md"

    result = make_service().index_paths([path])

    assert result.indexed == 1
    assert result.failed == 0


def test_index_persists_deterministic_parent_search_text_and_vector(
    tmp_path: Path,
) -> None:
    path = tmp_path / "leave-guide.md"
    path.write_text(
        """---
document_id: hr-leave-guide
title: 员工请假指南
document_type: handbook
department: hr
visibility: public
allowed_roles: []
version: "1.0"
status: active
effective_from: "2026-08-01T00:00:00+08:00"
effective_to: null
supersedes_id: null
source_path: hr/leave-guide.md
topic_tags: [请假, 病假]
---
# 员工请假指南

## 申请流程

员工应在系统中提交申请。

# 紧急情况

紧急就医可先电话报备。
""",
        encoding="utf-8",
    )
    repository = FakeRepository()

    result = make_service(repository).index_paths([path])

    assert result.indexed == 1
    _, chunks, vectors, parent = repository.upserts[0]
    assert parent["document_search_text"] == (
        "员工请假指南\nhandbook\nhr\n病假\n请假\n"
        "申请流程\n员工应在系统中提交申请。\n紧急情况"
    )
    assert parent["document_embedding_model"] == "BAAI/bge-m3"
    assert parent["document_embedding"] == [47.0, 1.0, 0.0, 0.0]
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


def test_embedding_model_change_reindexes_unchanged_document() -> None:
    repository = FakeRepository()
    path = CORPUS_DIR / "finance" / "expense-policy-v2.md"

    first = make_service(repository).index_paths([path])
    changed_model = IndexingService(
        repository=repository,
        embeddings=FakeEmbeddings(),
        settings=Settings(embedding_model="replacement-embedding-model"),
    ).index_paths([path])

    assert first.indexed == 1
    assert changed_model.indexed == 1
    assert changed_model.skipped == 0
    assert repository.upserts[-1][1][0].embedding_model == "replacement-embedding-model"


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
