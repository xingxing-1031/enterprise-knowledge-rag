from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_knowledge_rag.documents.ingestion import (
    ImportNotApprovableError,
    IngestionService,
)
from enterprise_knowledge_rag.documents.source_models import (
    CleaningIssue,
    ExtractedDocument,
    ImportMetadata,
    IngestionStatus,
    IssueSeverity,
    SourceFile,
)
from enterprise_knowledge_rag.models import (
    DocumentType,
    IndexingSummary,
    UserContext,
    UserRole,
    Visibility,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)
ADMIN = UserContext(
    user_id="knowledge-admin-1",
    role=UserRole.KNOWLEDGE_ADMIN,
    departments=set(),
)
EMPLOYEE = UserContext(
    user_id="employee-1",
    role=UserRole.EMPLOYEE,
    departments={"hr"},
)


def metadata() -> ImportMetadata:
    return ImportMetadata(
        document_id="hr-leave-policy",
        title="员工请假制度",
        document_type=DocumentType.POLICY,
        department="hr",
        visibility=Visibility.RESTRICTED,
        allowed_roles={UserRole.EMPLOYEE},
        version="2.0",
        effective_from=NOW,
    )


class FakeImportRepository:
    def __init__(self) -> None:
        self.previews = {}
        self.storage_paths: list[str] = []

    def find_by_hash(self, source_hash):
        return next(
            (
                preview
                for preview in self.previews.values()
                if preview.source_hash == source_hash
            ),
            None,
        )

    def create_import(self, preview, *, suffix, storage_path, uploaded_by):
        self.previews[preview.import_id] = preview
        self.storage_paths.append(storage_path)
        return preview

    def get_import(self, import_id):
        return self.previews.get(import_id)

    def approve_import(self, import_id, metadata, *, approved_by):
        preview = self.previews[import_id].model_copy(
            update={
                "metadata": metadata,
                "status": IngestionStatus.APPROVED,
                "updated_at": NOW,
            }
        )
        self.previews[import_id] = preview
        return preview

    def update_status(self, import_id, status, *, failure_type=None):
        preview = self.previews[import_id].model_copy(
            update={
                "status": status,
                "failure_type": failure_type,
                "updated_at": NOW,
            }
        )
        self.previews[import_id] = preview
        return preview


class FakeIndexing:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def index_paths(self, paths):
        self.paths.extend(paths)
        return IndexingSummary(
            discovered=len(paths),
            indexed=len(paths),
            skipped=0,
            failed=0,
            chunk_count=len(paths),
        )


class ScannedExtractor:
    def extract(self, source):
        return ExtractedDocument(
            original_filename=source.original_filename,
            source_hash=source.source_hash,
            media_type=source.media_type,
            page_count=1,
            issues=[
                CleaningIssue(
                    code="scanned_or_low_text_pdf",
                    severity=IssueSeverity.BLOCKING,
                    message="PDF 缺少可提取文本。",
                )
            ],
        )


def make_service(tmp_path: Path, *, extractor=None):
    repository = FakeImportRepository()
    indexing = FakeIndexing()
    service = IngestionService(
        repository=repository,
        extractor=extractor,
        indexing=indexing,
        upload_dir=tmp_path / "uploads",
        knowledge_dir=tmp_path / "knowledge",
        clock=lambda: NOW,
    )
    return service, repository, indexing


def text_source() -> SourceFile:
    return SourceFile.from_bytes(
        original_filename="leave-policy.txt",
        media_type="text/plain",
        content="员工应在请假前提交申请。".encode(),
    )


def long_text_source() -> SourceFile:
    return SourceFile.from_bytes(
        original_filename="long-policy.txt",
        media_type="text/plain",
        content=(("制度正文。" * 5_000) + "末尾关键条款").encode(),
    )


def test_employee_cannot_preview_enterprise_document(tmp_path: Path) -> None:
    service, _, _ = make_service(tmp_path)

    with pytest.raises(PermissionError, match="administrator"):
        service.preview(text_source(), metadata(), EMPLOYEE)


def test_duplicate_upload_returns_existing_preview(tmp_path: Path) -> None:
    service, repository, _ = make_service(tmp_path)

    first = service.preview(text_source(), metadata(), ADMIN)
    second = service.preview(text_source(), metadata(), ADMIN)

    assert second.import_id == first.import_id
    assert len(repository.storage_paths) == 1


def test_scanned_pdf_is_quarantined_and_never_indexed(tmp_path: Path) -> None:
    service, _, indexing = make_service(tmp_path, extractor=ScannedExtractor())
    source = SourceFile.from_bytes(
        original_filename="scan.pdf",
        media_type="application/pdf",
        content=b"%PDF-scanned-placeholder",
    )

    preview = service.preview(source, metadata(), ADMIN)

    assert preview.status is IngestionStatus.QUARANTINED
    with pytest.raises(ImportNotApprovableError):
        service.approve(preview.import_id, metadata(), ADMIN)
    assert indexing.paths == []


def test_approval_writes_canonical_document_and_is_idempotent(tmp_path: Path) -> None:
    service, _, indexing = make_service(tmp_path)
    preview = service.preview(text_source(), metadata(), ADMIN)

    first = service.approve(preview.import_id, metadata(), ADMIN)
    second = service.approve(preview.import_id, metadata(), ADMIN)

    assert first.status is IngestionStatus.INDEXED
    assert second.status is IngestionStatus.INDEXED
    assert len(indexing.paths) == 1
    canonical = indexing.paths[0].read_text(encoding="utf-8")
    assert "document_id: hr-leave-policy" in canonical
    assert "# 员工请假制度" in canonical


def test_approval_indexes_full_text_not_preview(tmp_path: Path) -> None:
    service, _, indexing = make_service(tmp_path)
    preview = service.preview(long_text_source(), metadata(), ADMIN)

    service.approve(preview.import_id, metadata(), ADMIN)

    assert len(preview.normalized_preview) == 20_000
    canonical = indexing.paths[0].read_text(encoding="utf-8")
    assert "末尾关键条款" in canonical
