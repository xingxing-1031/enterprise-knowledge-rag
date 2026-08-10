from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import yaml

from enterprise_knowledge_rag.models import UserContext, UserRole

from .cleaning import DocumentCleaningService
from .extractors import ExtractorRegistry, SourceValidationError
from .source_models import (
    CleanedDocument,
    CleaningIssue,
    CleaningReport,
    ImportMetadata,
    ImportPreview,
    IngestionStatus,
    IssueSeverity,
    SourceFile,
)


class ImportNotFoundError(LookupError):
    pass


class ImportNotApprovableError(ValueError):
    pass


class IngestionRepository(Protocol):
    def find_by_hash(self, source_hash: str) -> ImportPreview | None: ...

    def create_import(
        self,
        preview: ImportPreview,
        *,
        suffix: str,
        storage_path: str,
        uploaded_by: str,
    ) -> ImportPreview: ...

    def get_import(self, import_id: str) -> ImportPreview | None: ...

    def list_imports(self, *, limit: int = 50) -> list[ImportPreview]: ...

    def approve_import(
        self,
        import_id: str,
        metadata: ImportMetadata,
        *,
        approved_by: str,
    ) -> ImportPreview | None: ...

    def update_status(
        self,
        import_id: str,
        status: IngestionStatus,
        *,
        failure_type: str | None = None,
    ) -> ImportPreview | None: ...


class ImportIndexer(Protocol):
    def index_paths(self, paths: list[Path]) -> Any: ...


class IngestionService:
    def __init__(
        self,
        *,
        repository: IngestionRepository,
        indexing: ImportIndexer,
        upload_dir: Path,
        knowledge_dir: Path,
        extractor: Any | None = None,
        cleaner: DocumentCleaningService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._indexing = indexing
        self._upload_dir = upload_dir
        self._knowledge_dir = knowledge_dir
        self._extractor = extractor or ExtractorRegistry.default()
        self._cleaner = cleaner or DocumentCleaningService()
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _require_admin(actor: UserContext) -> None:
        if actor.role is not UserRole.KNOWLEDGE_ADMIN:
            raise PermissionError("knowledge administrator role required")

    def preview(
        self,
        source: SourceFile,
        metadata: ImportMetadata,
        actor: UserContext,
    ) -> ImportPreview:
        self._require_admin(actor)
        existing = self._repository.find_by_hash(source.source_hash)
        if existing is not None:
            return existing

        import_id = str(uuid4())
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = self._upload_dir / f"{import_id}{source.suffix.value}"
        storage_path.write_bytes(source.content)

        cleaned = self._extract_and_clean(source)
        normalized_path = self._upload_dir / f"{import_id}.normalized.md"
        normalized_path.write_text(cleaned.normalized_markdown, encoding="utf-8")
        status = (
            IngestionStatus.QUARANTINED
            if cleaned.report.has_blocking_issues
            else IngestionStatus.NEEDS_REVIEW
        )
        now = self._clock()
        preview = ImportPreview(
            import_id=import_id,
            original_filename=source.original_filename,
            source_hash=source.source_hash,
            media_type=source.media_type,
            size_bytes=source.size_bytes,
            page_count=(
                None
                if not cleaned.blocks
                else max(
                    (
                        block.page_number or 0
                        for block in cleaned.blocks
                    ),
                    default=0,
                )
                or None
            ),
            status=status,
            metadata=metadata,
            cleaning_report=cleaned.report,
            normalized_preview=cleaned.normalized_markdown[:20_000],
            failure_type=(
                next(
                    (
                        issue.code
                        for issue in cleaned.report.issues
                        if issue.severity is IssueSeverity.BLOCKING
                    ),
                    None,
                )
            ),
            created_at=now,
            updated_at=now,
        )
        return self._repository.create_import(
            preview,
            suffix=source.suffix.value,
            storage_path=str(storage_path),
            uploaded_by=actor.user_id,
        )

    def approve(
        self,
        import_id: str,
        metadata: ImportMetadata,
        actor: UserContext,
    ) -> ImportPreview:
        self._require_admin(actor)
        preview = self._repository.get_import(import_id)
        if preview is None:
            raise ImportNotFoundError(import_id)
        if preview.status is IngestionStatus.INDEXED:
            return preview
        if not preview.can_approve:
            raise ImportNotApprovableError("import is not ready for approval")

        approved = self._repository.approve_import(
            import_id,
            metadata,
            approved_by=actor.user_id,
        )
        if approved is None:
            raise ImportNotFoundError(import_id)

        canonical_path = self._write_canonical_document(approved, metadata)
        summary = self._indexing.index_paths([canonical_path])
        if summary.failed or summary.indexed + summary.skipped != 1:
            failed = self._repository.update_status(
                import_id,
                IngestionStatus.FAILED,
                failure_type="indexing_failed",
            )
            if failed is None:
                raise ImportNotFoundError(import_id)
            return failed
        indexed = self._repository.update_status(import_id, IngestionStatus.INDEXED)
        if indexed is None:
            raise ImportNotFoundError(import_id)
        return indexed

    def list_imports(self, actor: UserContext) -> list[ImportPreview]:
        self._require_admin(actor)
        return self._repository.list_imports(limit=50)

    def get_import(
        self,
        import_id: str,
        actor: UserContext,
    ) -> ImportPreview | None:
        self._require_admin(actor)
        return self._repository.get_import(import_id)

    def _extract_and_clean(self, source: SourceFile) -> CleanedDocument:
        try:
            extracted = self._extractor.extract(source)
            return self._cleaner.clean(extracted)
        except SourceValidationError:
            issue = CleaningIssue(
                code="source_validation_failed",
                severity=IssueSeverity.BLOCKING,
                message="文件格式或安全校验未通过，需要人工处理。",
            )
            empty_hash = hashlib.sha256(b"").hexdigest()
            return CleanedDocument(
                original_filename=source.original_filename,
                source_hash=source.source_hash,
                report=CleaningReport(
                    characters_before=0,
                    characters_after=0,
                    blocks_before=0,
                    blocks_after=0,
                    table_count=0,
                    content_hash=empty_hash,
                    issues=[issue],
                ),
            )

    def _write_canonical_document(
        self,
        preview: ImportPreview,
        metadata: ImportMetadata,
    ) -> Path:
        imported_dir = self._knowledge_dir / "imported"
        imported_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{metadata.document_id}-v{metadata.version}.md"
        path = imported_dir / filename
        source_path = path.relative_to(self._knowledge_dir).as_posix()
        front_matter = {
            "document_id": metadata.document_id,
            "title": metadata.title,
            "document_type": metadata.document_type.value,
            "department": metadata.department,
            "visibility": metadata.visibility.value,
            "allowed_roles": sorted(role.value for role in metadata.allowed_roles),
            "topic_tags": sorted(metadata.topic_tags),
            "version": metadata.version,
            "status": "active",
            "effective_from": metadata.effective_from,
            "effective_to": metadata.effective_to,
            "supersedes_id": metadata.supersedes_id,
            "source_path": source_path,
        }
        full_text_path = self._upload_dir / f"{preview.import_id}.normalized.md"
        body = (
            full_text_path.read_text(encoding="utf-8").strip()
            if full_text_path.is_file()
            else preview.normalized_preview.strip()
        )
        if not body.startswith("#"):
            body = f"# {metadata.title}\n\n{body}".strip()
        yaml_text = yaml.safe_dump(
            front_matter,
            allow_unicode=True,
            sort_keys=False,
        ).strip()
        path.write_text(f"---\n{yaml_text}\n---\n{body}\n", encoding="utf-8")
        return path
