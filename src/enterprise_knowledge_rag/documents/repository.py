from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, Iterator

from enterprise_knowledge_rag.models import ChunkRecord, DocumentRecord


class KnowledgeRepository:
    """PostgreSQL persistence with one transaction per document version."""

    def __init__(self, connection_factory: Any) -> None:
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._connection_factory() as connection:
            yield connection

    def get_content_hash(self, document_id: str, version: str) -> str | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT content_hash
                FROM knowledge_documents
                WHERE document_id = %s AND version = %s
                """,
                (document_id, version),
            )
            row = cursor.fetchone()
        return row[0].strip() if row else None

    def find_document_by_hash(self, content_hash: str) -> tuple[str, str] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT document_id, version
                FROM knowledge_documents
                WHERE content_hash = %s
                LIMIT 1
                """,
                (content_hash,),
            )
            row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def upsert_document(
        self,
        document: DocumentRecord,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, version, title, document_type, department,
                    visibility, allowed_roles, status, effective_from,
                    effective_to, supersedes_id, content_hash, source_path,
                    indexed_at
                ) VALUES (
                    %(document_id)s, %(version)s, %(title)s, %(document_type)s,
                    %(department)s, %(visibility)s, %(allowed_roles)s,
                    %(status)s, %(effective_from)s, %(effective_to)s,
                    %(supersedes_id)s, %(content_hash)s, %(source_path)s,
                    %(indexed_at)s
                )
                ON CONFLICT (document_id, version) DO UPDATE SET
                    title = EXCLUDED.title,
                    document_type = EXCLUDED.document_type,
                    department = EXCLUDED.department,
                    visibility = EXCLUDED.visibility,
                    allowed_roles = EXCLUDED.allowed_roles,
                    status = EXCLUDED.status,
                    effective_from = EXCLUDED.effective_from,
                    effective_to = EXCLUDED.effective_to,
                    supersedes_id = EXCLUDED.supersedes_id,
                    content_hash = EXCLUDED.content_hash,
                    source_path = EXCLUDED.source_path,
                    indexed_at = EXCLUDED.indexed_at
                """,
                {
                    **document.model_dump(mode="python"),
                    "document_type": document.document_type.value,
                    "visibility": document.visibility.value,
                    "allowed_roles": sorted(
                        role.value for role in document.allowed_roles
                    ),
                    "status": document.status.value,
                },
            )
            cursor.execute(
                """
                DELETE FROM knowledge_chunks
                WHERE document_id = %s AND document_version = %s
                """,
                (document.document_id, document.version),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                cursor.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, document_id, document_version, section_path,
                        chunk_index, content, token_count, content_hash,
                        embedding_model, embedding
                    ) VALUES (
                        %(chunk_id)s, %(document_id)s, %(document_version)s,
                        %(section_path)s, %(chunk_index)s, %(content)s,
                        %(token_count)s, %(content_hash)s, %(embedding_model)s,
                        %(embedding)s::vector
                    )
                    """,
                    {**chunk.model_dump(), "embedding": list(embedding)},
                )
