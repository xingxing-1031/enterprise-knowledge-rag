from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentType(StrEnum):
    POLICY = "policy"
    PROCESS = "process"
    HANDBOOK = "handbook"
    FAQ = "faq"


class Visibility(StrEnum):
    PUBLIC = "public"
    DEPARTMENT = "department"
    RESTRICTED = "restricted"


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class UserRole(StrEnum):
    EMPLOYEE = "employee"
    DEPARTMENT_ADMIN = "department_admin"
    KNOWLEDGE_ADMIN = "knowledge_admin"


class RefusalReason(StrEnum):
    OUT_OF_SCOPE = "out_of_scope"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PERMISSION_DENIED = "permission_denied"
    VERSION_AMBIGUOUS = "version_ambiguous"
    SERVICE_FAILED = "service_failed"


class DocumentRecord(StrictModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_type: DocumentType
    department: str = Field(min_length=1)
    visibility: Visibility
    allowed_roles: set[UserRole] = Field(default_factory=set)
    topic_tags: set[str] = Field(default_factory=set, max_length=20)
    version: str = Field(min_length=1)
    status: DocumentStatus
    effective_from: datetime
    effective_to: datetime | None = None
    supersedes_id: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    source_path: str = Field(min_length=1)
    indexed_at: datetime
    synthetic: bool = False

    @field_validator("content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if any(char not in "0123456789abcdef" for char in value.lower()):
            raise ValueError("content_hash must be lowercase hexadecimal")
        return value.lower()

    @model_validator(mode="after")
    def validate_dates_and_visibility(self) -> "DocumentRecord":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        if self.visibility is Visibility.RESTRICTED and not self.allowed_roles:
            raise ValueError("restricted documents require allowed_roles")
        if self.visibility is Visibility.PUBLIC and self.allowed_roles:
            raise ValueError("public documents cannot define allowed_roles")
        return self


class ChunkRecord(StrictModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    section_path: list[str] = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    token_count: int = Field(gt=0)
    content_hash: str = Field(min_length=64, max_length=64)
    embedding_model: str = Field(min_length=1)


class UserContext(StrictModel):
    user_id: str = Field(min_length=1)
    role: UserRole
    departments: set[str] = Field(default_factory=set)


class RetrievalCandidate(StrictModel):
    chunk: ChunkRecord
    document: DocumentRecord
    channels: set[str] = Field(default_factory=set)
    channel_ranks: dict[str, int] = Field(default_factory=dict)
    retrieval_score: float = 0.0
    reranker_score: float | None = None
    supports_need_ids: set[str] = Field(default_factory=set)
    retrieval_hop: Literal[1, 2] = 1


class RetrievalEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section_path: list[str] = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_from: datetime
    quote: str = Field(min_length=1)
    retrieval_channels: set[str] = Field(default_factory=set)
    retrieval_rank: int = Field(ge=1)
    reranker_score: float | None = None
    supports_need_ids: set[str] = Field(default_factory=set)
    retrieval_hop: Literal[1, 2] = 1


class Citation(StrictModel):
    evidence_id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class ChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=128)
    as_of: datetime | None = None


class ChatResult(StrictModel):
    status: str = Field(min_length=1)
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[RetrievalEvidence] = Field(default_factory=list)
    refusal_reason: RefusalReason | None = None
    degradation_reason: str | None = None


class IndexingSummary(StrictModel):
    discovered: int = Field(ge=0)
    indexed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
