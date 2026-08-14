from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enterprise_knowledge_rag.admin_audit import AdminAuditRepository
from enterprise_knowledge_rag.admin_models import (
    AdminOverview,
    DeleteResult,
    ManagedDocument,
)
from enterprise_knowledge_rag.documents.indexing import IndexingService
from enterprise_knowledge_rag.documents.repository import KnowledgeRepository
from enterprise_knowledge_rag.models import (
    DocumentRecord,
    DocumentStatus,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.retrieval.service import (
    RetrievalService,
    RetrievalStrategy,
)


class DocumentNotFoundError(LookupError):
    pass


class DocumentConfirmationError(ValueError):
    pass


class UnsafeSourcePathError(ValueError):
    pass


def _managed(row: dict[str, Any]) -> ManagedDocument:
    source_path = str(row.get("source_path") or "")
    return ManagedDocument(
        document_id=row["document_id"],
        version=row["version"],
        title=row["title"],
        document_type=row["document_type"],
        department=row["department"],
        visibility=row["visibility"],
        status=row["status"],
        effective_from=row["effective_from"],
        effective_to=row.get("effective_to"),
        topic_tags=tuple(row.get("topic_tags") or ()),
        source_filename=Path(source_path).name,
        chunk_count=int(row.get("chunk_count") or 0),
        indexed=int(row.get("chunk_count") or 0) > 0,
        indexed_at=row.get("indexed_at"),
    )


class KnowledgeAdminService:
    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        indexing: IndexingService,
        audit: AdminAuditRepository,
        knowledge_dir: Path,
        upload_storage_dir: Path,
        import_repository: Any | None = None,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self._repository = repository
        self._indexing = indexing
        self._audit = audit
        self._knowledge_dir = knowledge_dir.resolve()
        self._upload_storage_dir = upload_storage_dir.resolve()
        self._imports = import_repository
        self._retrieval = retrieval

    @staticmethod
    def _require_admin(actor: UserContext) -> None:
        if actor.role is not UserRole.KNOWLEDGE_ADMIN:
            raise PermissionError("knowledge administrator role required")

    def overview(self, actor: UserContext) -> AdminOverview:
        self._require_admin(actor)
        counts = self._repository.admin_overview()
        if self._imports is not None:
            try:
                counts["needs_review_count"] = sum(
                    item.status.value == "needs_review"
                    for item in self._imports.list_imports(limit=100)
                )
            except Exception:
                counts["needs_review_count"] = 0
        counts["recent_audit_count"] = len(self._audit.list_recent(limit=10))
        return AdminOverview.model_validate(counts)

    def documents(self, actor: UserContext) -> tuple[ManagedDocument, ...]:
        self._require_admin(actor)
        return tuple(_managed(row) for row in self._repository.admin_documents())

    def _change_status(
        self,
        document_id: str,
        version: str,
        status: DocumentStatus,
        actor: UserContext,
    ) -> ManagedDocument:
        self._require_admin(actor)
        document = self._repository.set_document_status(document_id, version, status)
        if document is None:
            self._audit.record(
                action=f"document.{status.value}",
                actor_id=actor.user_id,
                document_id=document_id,
                version=version,
                result="not_found",
                reason_code="document_not_found",
            )
            raise DocumentNotFoundError(document_id)
        self._audit.record(
            action=f"document.{status.value}",
            actor_id=actor.user_id,
            document_id=document_id,
            version=version,
        )
        return self._to_managed(document)

    def deactivate(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument:
        return self._change_status(document_id, version, DocumentStatus.INACTIVE, actor)

    def restore(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument:
        return self._change_status(document_id, version, DocumentStatus.ACTIVE, actor)

    def _to_managed(self, document: DocumentRecord) -> ManagedDocument:
        row = document.model_dump(mode="python")
        row["document_type"] = document.document_type.value
        row["visibility"] = document.visibility.value
        row["status"] = document.status.value
        row["chunk_count"] = 0
        return _managed(row)

    def reindex(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument:
        self._require_admin(actor)
        document = self._repository.get_document_version(document_id, version)
        if document is None:
            raise DocumentNotFoundError(document_id)
        source = Path(document.source_path)
        resolved = self._safe_source(source)
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        self._indexing.index_paths([resolved])
        self._audit.record(
            action="document.reindex",
            actor_id=actor.user_id,
            document_id=document_id,
            version=version,
        )
        refreshed = self._repository.get_document_version(document_id, version)
        return self._to_managed(refreshed or document)

    def delete(
        self,
        document_id: str,
        version: str,
        *,
        confirmation: str,
        actor: UserContext,
    ) -> DeleteResult:
        self._require_admin(actor)
        document = self._repository.get_document_version(document_id, version)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if confirmation != document.title:
            self._audit.record(
                action="document.delete",
                actor_id=actor.user_id,
                document_id=document_id,
                version=version,
                result="rejected",
                reason_code="title_confirmation_mismatch",
            )
            raise DocumentConfirmationError(
                "document title confirmation does not match"
            )
        resolved = self._safe_source(
            Path(document.source_path),
            allow_missing=True,
        )
        deleted = self._repository.delete_document_version(document_id, version)
        if deleted is None:
            raise DocumentNotFoundError(document_id)
        removed = False
        if resolved.is_file():
            resolved.unlink()
            removed = True
        self._audit.record(
            action="document.delete",
            actor_id=actor.user_id,
            document_id=document_id,
            version=version,
        )
        return DeleteResult(
            deleted=True,
            document_id=document_id,
            version=version,
            chunk_count=int(deleted["chunk_count"]),
            source_removed=removed,
        )

    def _safe_source(self, path: Path, *, allow_missing: bool = False) -> Path:
        candidate = path if path.is_absolute() else (Path.cwd() / path)
        resolved = candidate.resolve()
        allowed = (self._knowledge_dir, self._upload_storage_dir)
        if not any(resolved == root or root in resolved.parents for root in allowed):
            raise UnsafeSourcePathError("source path is outside configured storage")
        if not allow_missing and not resolved.exists():
            raise FileNotFoundError(resolved)
        return resolved

    def audit(self, actor: UserContext, *, limit: int = 50):
        self._require_admin(actor)
        return self._audit.list_recent(limit=limit)

    def debug_retrieve(self, request: Any, actor: UserContext):
        self._require_admin(actor)
        if self._retrieval is None:
            raise RuntimeError("retrieval debug is not configured")
        simulated = UserContext(
            user_id=f"simulation:{actor.user_id}",
            role=request.simulated_role,
            departments=set(request.simulated_departments),
        )
        as_of = request.as_of or datetime.now(UTC)
        return self._retrieval.debug_retrieve(
            request.query,
            user=simulated,
            as_of=as_of,
            top_k=request.top_k,
            strategy=RetrievalStrategy(request.strategy),
        )
