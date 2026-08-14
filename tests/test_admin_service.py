from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_knowledge_rag.admin_service import (
    DocumentConfirmationError,
    KnowledgeAdminService,
    UnsafeSourcePathError,
)
from enterprise_knowledge_rag.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    UserContext,
    UserRole,
    Visibility,
)


class FakeRepository:
    def __init__(self, document: DocumentRecord):
        self.document = document

    def get_document_version(self, document_id, version):
        if (
            self.document
            and self.document.document_id == document_id
            and self.document.version == version
        ):
            return self.document
        return None

    def set_document_status(self, document_id, version, status):
        document = self.get_document_version(document_id, version)
        if document is None:
            return None
        self.document = document.model_copy(update={"status": status})
        return self.document

    def delete_document_version(self, document_id, version):
        document = self.get_document_version(document_id, version)
        if document is None:
            return None
        self.document = None
        return {"source_path": document.source_path, "chunk_count": 7}


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, **payload):
        self.events.append(payload)

    def list_recent(self, *, limit=50):
        return []


class FakeIndexing:
    def index_paths(self, paths):
        return None


def make_service(tmp_path: Path):
    source = tmp_path / "knowledge" / "leave.md"
    source.parent.mkdir()
    source.write_text("# 员工请假制度", encoding="utf-8")
    document = DocumentRecord(
        document_id="hr-leave-policy",
        version="2.0",
        title="员工请假制度",
        document_type=DocumentType.POLICY,
        department="hr",
        visibility=Visibility.PUBLIC,
        status=DocumentStatus.ACTIVE,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="a" * 64,
        source_path=str(source),
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    repository = FakeRepository(document)
    audit = FakeAudit()
    service = KnowledgeAdminService(
        repository=repository,
        indexing=FakeIndexing(),
        audit=audit,
        knowledge_dir=source.parent,
        upload_storage_dir=tmp_path / "uploads",
    )
    admin = UserContext(user_id="admin", role=UserRole.KNOWLEDGE_ADMIN)
    return service, repository, audit, admin, source


def test_deactivate_and_restore_change_retrieval_status(tmp_path: Path) -> None:
    service, repository, _audit, admin, _source = make_service(tmp_path)
    assert (
        service.deactivate("hr-leave-policy", "2.0", admin).status
        is DocumentStatus.INACTIVE
    )
    assert repository.document.status is DocumentStatus.INACTIVE
    assert (
        service.restore("hr-leave-policy", "2.0", admin).status is DocumentStatus.ACTIVE
    )


def test_delete_requires_exact_title_and_removes_source(tmp_path: Path) -> None:
    service, repository, audit, admin, source = make_service(tmp_path)
    with pytest.raises(DocumentConfirmationError):
        service.delete("hr-leave-policy", "2.0", confirmation="错误标题", actor=admin)
    result = service.delete(
        "hr-leave-policy",
        "2.0",
        confirmation="员工请假制度",
        actor=admin,
    )
    assert result.deleted is True
    assert result.chunk_count == 7
    assert repository.document is None
    assert not source.exists()
    assert audit.events[-1]["action"] == "document.delete"


def test_unmanaged_source_is_rejected_before_database_delete(tmp_path: Path) -> None:
    service, repository, _audit, admin, _source = make_service(tmp_path)
    repository.document = repository.document.model_copy(
        update={"source_path": str(tmp_path.parent / "outside.md")}
    )
    with pytest.raises(UnsafeSourcePathError):
        service.delete(
            "hr-leave-policy",
            "2.0",
            confirmation="员工请假制度",
            actor=admin,
        )
    assert repository.document is not None
