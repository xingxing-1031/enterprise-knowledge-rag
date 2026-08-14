from datetime import datetime
from typing import Literal

from pydantic import Field

from enterprise_knowledge_rag.models import (
    DocumentStatus,
    DocumentType,
    StrictModel,
    Visibility,
)


class ManagedDocument(StrictModel):
    document_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_type: DocumentType
    department: str = Field(min_length=1)
    visibility: Visibility
    status: DocumentStatus
    effective_from: datetime
    effective_to: datetime | None = None
    topic_tags: tuple[str, ...] = ()
    source_filename: str = ""
    chunk_count: int = Field(default=0, ge=0)
    indexed: bool = False
    indexed_at: datetime | None = None


class AdminOverview(StrictModel):
    document_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    inactive_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    last_indexed_at: datetime | None = None
    recent_audit_count: int = Field(default=0, ge=0)


class DeleteResult(StrictModel):
    deleted: bool
    document_id: str
    version: str
    chunk_count: int = Field(ge=0)
    source_removed: bool = False
    tombstone_recorded: bool = True


class RetrievalDebugRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    simulated_role: Literal["employee", "department_admin", "knowledge_admin"] = (
        "employee"
    )
    simulated_departments: tuple[str, ...] = ()
    as_of: datetime | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    strategy: Literal["vector_baseline", "hybrid_rrf", "hybrid_rrf_reranker"] = (
        "hybrid_rrf_reranker"
    )


class SafeDebugCandidate(StrictModel):
    document_id: str
    version: str
    title: str
    department: str
    chunk_id: str
    channels: tuple[str, ...] = ()
    channel_ranks: dict[str, int] = Field(default_factory=dict)
    retrieval_score: float = 0.0
    reranker_score: float | None = None


class RetrievalDebugStage(StrictModel):
    name: Literal["authorization", "bm25", "vector", "rrf", "rerank", "evidence"]
    candidate_count: int = Field(ge=0)
    excluded_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)
    candidates: tuple[SafeDebugCandidate, ...] = ()
    note: str | None = None


class RetrievalDebugResponse(StrictModel):
    query: str
    strategy: str
    simulated_role: str
    simulated_departments: tuple[str, ...]
    status: str
    stages: tuple[RetrievalDebugStage, ...]
    total_duration_ms: int = Field(ge=0)


class AdminAuditEvent(StrictModel):
    event_id: str
    action: str
    actor_id: str
    document_ref_hash: str | None = None
    version: str | None = None
    result: str
    reason_code: str | None = None
    created_at: datetime
