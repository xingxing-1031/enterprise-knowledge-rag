from datetime import UTC, datetime

from enterprise_knowledge_rag.models import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    RetrievalCandidate,
    Visibility,
)


def make_candidate(
    chunk_id: str,
    *,
    title: str,
    content: str,
    document_id: str | None = None,
) -> RetrievalCandidate:
    doc_id = document_id or chunk_id.split(":", 1)[0]
    document = DocumentRecord(
        document_id=doc_id,
        title=title,
        document_type=DocumentType.POLICY,
        department="hr",
        visibility=Visibility.PUBLIC,
        version="1.0",
        status=DocumentStatus.ACTIVE,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="a" * 64,
        source_path=f"hr/{doc_id}.md",
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        document_id=doc_id,
        document_version="1.0",
        section_path=[title, "办理规则"],
        chunk_index=0,
        content=content,
        token_count=max(1, len(content)),
        content_hash="b" * 64,
        embedding_model="fake",
    )
    return RetrievalCandidate(chunk=chunk, document=document)
