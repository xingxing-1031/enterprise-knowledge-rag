from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator

from enterprise_knowledge_rag.models import (
    DocumentType,
    StrictModel,
    UserRole,
    Visibility,
)


class SourceFormat(StrEnum):
    PDF = ".pdf"
    DOCX = ".docx"
    MARKDOWN = ".md"
    TEXT = ".txt"


class ExtractedBlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class IngestionStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    INDEXED = "indexed"
    QUARANTINED = "quarantined"
    FAILED = "failed"


class EvidenceKind(StrEnum):
    RULE = "rule"
    PROCEDURE = "procedure"
    MATERIAL = "material"
    EXCEPTION = "exception"
    APPROVER = "approver"
    DEADLINE = "deadline"
    SCOPE = "scope"


class SourceFile(StrictModel):
    original_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=120)
    suffix: SourceFormat
    size_bytes: int = Field(ge=0)
    source_hash: str = Field(min_length=64, max_length=64)
    content: bytes = Field(repr=False, exclude=True)

    @field_validator("source_hash")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        normalized = value.lower()
        if any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("source_hash must be lowercase hexadecimal")
        return normalized

    @model_validator(mode="after")
    def validate_content_metadata(self) -> SourceFile:
        if len(self.content) != self.size_bytes:
            raise ValueError("size_bytes must match content length")
        digest = hashlib.sha256(self.content).hexdigest()
        if digest != self.source_hash:
            raise ValueError("source_hash must match content")
        return self

    @classmethod
    def from_bytes(
        cls,
        *,
        original_filename: str,
        media_type: str,
        content: bytes,
    ) -> SourceFile:
        suffix = Path(original_filename).suffix.lower()
        return cls(
            original_filename=Path(original_filename).name,
            media_type=media_type,
            suffix=suffix,
            size_bytes=len(content),
            source_hash=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        media_type: str | None = None,
    ) -> SourceFile:
        content = path.read_bytes()
        detected_type = media_type or mimetypes.guess_type(path.name)[0]
        return cls.from_bytes(
            original_filename=path.name,
            media_type=detected_type or "application/octet-stream",
            content=content,
        )


class ExtractedBlock(StrictModel):
    kind: ExtractedBlockKind
    order: int = Field(ge=0)
    text: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    heading_level: int | None = Field(default=None, ge=1, le=6)
    section_path: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_heading_level(self) -> ExtractedBlock:
        if self.kind is ExtractedBlockKind.HEADING and self.heading_level is None:
            raise ValueError("heading blocks require heading_level")
        if (
            self.kind is not ExtractedBlockKind.HEADING
            and self.heading_level is not None
        ):
            raise ValueError("only heading blocks can define heading_level")
        return self


class ExtractedDocument(StrictModel):
    original_filename: str = Field(min_length=1, max_length=255)
    source_hash: str = Field(min_length=64, max_length=64)
    media_type: str = Field(min_length=1, max_length=120)
    blocks: list[ExtractedBlock] = Field(min_length=1)
    page_count: int | None = Field(default=None, ge=1)
    title_hint: str | None = Field(default=None, max_length=200)


class CleaningIssue(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    severity: IssueSeverity
    message: str = Field(min_length=1, max_length=500)
    block_orders: list[int] = Field(default_factory=list)


class CleaningReport(StrictModel):
    characters_before: int = Field(ge=0)
    characters_after: int = Field(ge=0)
    blocks_before: int = Field(ge=0)
    blocks_after: int = Field(ge=0)
    table_count: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    issues: list[CleaningIssue] = Field(default_factory=list)

    @computed_field(return_type=bool)
    @property
    def has_blocking_issues(self) -> bool:
        return any(issue.severity is IssueSeverity.BLOCKING for issue in self.issues)


class CleanedDocument(StrictModel):
    original_filename: str = Field(min_length=1, max_length=255)
    source_hash: str = Field(min_length=64, max_length=64)
    normalized_markdown: str = Field(min_length=1)
    blocks: list[ExtractedBlock] = Field(min_length=1)
    report: CleaningReport


class ImportMetadata(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    document_type: DocumentType
    department: str = Field(min_length=1, max_length=80)
    visibility: Visibility
    allowed_roles: set[UserRole] = Field(default_factory=set)
    version: str = Field(min_length=1, max_length=40)
    effective_from: datetime
    effective_to: datetime | None = None
    supersedes_id: str | None = Field(default=None, max_length=120)
    topic_tags: set[str] = Field(default_factory=set, max_length=20)

    @model_validator(mode="after")
    def validate_policy_metadata(self) -> ImportMetadata:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        if self.visibility is Visibility.RESTRICTED and not self.allowed_roles:
            raise ValueError("restricted documents require allowed_roles")
        if self.visibility is Visibility.PUBLIC and self.allowed_roles:
            raise ValueError("public documents cannot define allowed_roles")
        return self


class ImportPreview(StrictModel):
    import_id: str = Field(min_length=1, max_length=120)
    original_filename: str = Field(min_length=1, max_length=255)
    source_hash: str = Field(min_length=64, max_length=64)
    media_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=1)
    status: IngestionStatus
    metadata: ImportMetadata | None = None
    cleaning_report: CleaningReport | None = None
    normalized_preview: str = Field(default="", max_length=20_000)
    failure_type: str | None = Field(default=None, max_length=120)
    created_at: datetime
    updated_at: datetime

    @computed_field(return_type=bool)
    @property
    def can_approve(self) -> bool:
        return (
            self.status is IngestionStatus.NEEDS_REVIEW
            and self.metadata is not None
            and self.cleaning_report is not None
            and not self.cleaning_report.has_blocking_issues
        )


class EvidenceNeed(StrictModel):
    need_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    kind: EvidenceKind
    query: str = Field(min_length=2, max_length=300)
    required: bool = True


class RetrievalPlan(StrictModel):
    primary_query: str = Field(min_length=2, max_length=500)
    topic: str = Field(min_length=1, max_length=80)
    departments: set[str] = Field(default_factory=set)
    evidence_needs: list[EvidenceNeed] = Field(min_length=1, max_length=4)
    requires_multi_hop: bool = False
    max_hops: Literal[1, 2] = 1

    @model_validator(mode="after")
    def validate_need_ids_and_hops(self) -> RetrievalPlan:
        need_ids = [need.need_id for need in self.evidence_needs]
        if len(need_ids) != len(set(need_ids)):
            raise ValueError("evidence need_id values must be unique")
        expected_hops = 2 if self.requires_multi_hop else 1
        if self.max_hops != expected_hops:
            raise ValueError("max_hops must match requires_multi_hop")
        return self
