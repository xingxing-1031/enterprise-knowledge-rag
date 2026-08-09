import json
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, Iterator

from enterprise_knowledge_rag.models import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    RetrievalCandidate,
    UserRole,
    Visibility,
)

DOCUMENT_SELECT = """
    d.document_id, d.version, d.title, d.document_type, d.department,
    d.visibility, d.allowed_roles, d.status, d.effective_from,
    d.effective_to, d.supersedes_id,
    d.content_hash AS document_content_hash, d.source_path, d.indexed_at
"""


def _document_from_row(row: dict[str, Any]) -> DocumentRecord:
    content_hash = row.get("document_content_hash", row.get("content_hash"))
    return DocumentRecord(
        document_id=row["document_id"],
        version=row["version"],
        title=row["title"],
        document_type=DocumentType(row["document_type"]),
        department=row["department"],
        visibility=Visibility(row["visibility"]),
        allowed_roles={UserRole(role) for role in row["allowed_roles"]},
        status=DocumentStatus(row["status"]),
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        supersedes_id=row["supersedes_id"],
        content_hash=content_hash.strip(),
        source_path=row["source_path"],
        indexed_at=row["indexed_at"],
    )


def _candidate_from_row(row: dict[str, Any]) -> RetrievalCandidate:
    document = _document_from_row(row)
    chunk = ChunkRecord(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_version=row["document_version"],
        section_path=list(row["section_path"]),
        chunk_index=row["chunk_index"],
        content=row["content"],
        token_count=row["token_count"],
        content_hash=row["chunk_content_hash"].strip(),
        embedding_model=row["embedding_model"],
    )
    return RetrievalCandidate(
        chunk=chunk,
        document=document,
        retrieval_score=float(row.get("similarity", 0.0)),
    )


def _authorized_payload(
    document_keys: frozenset[tuple[str, str]],
) -> str:
    return json.dumps(
        [
            {"document_id": document_id, "version": version}
            for document_id, version in sorted(document_keys)
        ]
    )


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


class KnowledgeRepository:
    """PostgreSQL persistence with one transaction per document version."""

    def __init__(
        self,
        connection_factory: Any,
        *,
        embedding_model: str = "BAAI/bge-m3",
    ) -> None:
        self._connection_factory = connection_factory
        self._embedding_model = embedding_model

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

    def list_documents(self) -> list[DocumentRecord]:
        from psycopg.rows import dict_row

        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(f"SELECT {DOCUMENT_SELECT} FROM knowledge_documents d")
            rows = cursor.fetchall()
        return [_document_from_row(row) for row in rows]

    def ready(self) -> bool:
        from psycopg import Error
        from psycopg.rows import dict_row

        try:
            with (
                self._connection() as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM knowledge_documents)
                            AS document_count,
                        (SELECT COUNT(*) FROM knowledge_chunks) AS chunk_count
                    """
                )
                row = cursor.fetchone()
        except Error:
            return False
        return bool(row and row["document_count"] > 0 and row["chunk_count"] > 0)

    def list_candidates(
        self,
        document_keys: frozenset[tuple[str, str]],
    ) -> list[RetrievalCandidate]:
        if not document_keys:
            return []
        from psycopg.rows import dict_row

        query = f"""
            SELECT {DOCUMENT_SELECT},
                c.chunk_id, c.document_version, c.section_path,
                c.chunk_index, c.content, c.token_count,
                c.content_hash AS chunk_content_hash, c.embedding_model
            FROM knowledge_chunks c
            JOIN knowledge_documents d
              ON d.document_id = c.document_id
             AND d.version = c.document_version
            JOIN jsonb_to_recordset(%(authorized)s::jsonb)
              AS allowed(document_id text, version text)
              ON allowed.document_id = d.document_id
             AND allowed.version = d.version
            WHERE c.embedding_model = %(embedding_model)s
            ORDER BY d.document_id, d.version, c.chunk_index
        """
        params = {
            "authorized": _authorized_payload(document_keys),
            "embedding_model": self._embedding_model,
        }
        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [_candidate_from_row(row) for row in rows]

    def search_authorized(
        self,
        query_vector: Sequence[float],
        *,
        document_keys: frozenset[tuple[str, str]],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not document_keys:
            return []
        if not query_vector:
            raise ValueError("query_vector must not be empty")
        from psycopg.rows import dict_row

        query = f"""
            SELECT {DOCUMENT_SELECT},
                c.chunk_id, c.document_version, c.section_path,
                c.chunk_index, c.content, c.token_count,
                c.content_hash AS chunk_content_hash, c.embedding_model,
                1 - (c.embedding <=> %(query_vector)s::vector) AS similarity
            FROM knowledge_chunks c
            JOIN knowledge_documents d
              ON d.document_id = c.document_id
             AND d.version = c.document_version
            JOIN jsonb_to_recordset(%(authorized)s::jsonb)
              AS allowed(document_id text, version text)
              ON allowed.document_id = d.document_id
             AND allowed.version = d.version
            WHERE c.embedding_model = %(embedding_model)s
            ORDER BY c.embedding <=> %(query_vector)s::vector, c.chunk_id
            LIMIT %(limit)s
        """
        params = {
            "authorized": _authorized_payload(document_keys),
            "embedding_model": self._embedding_model,
            "query_vector": _vector_literal(query_vector),
            "limit": limit,
        }
        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [_candidate_from_row(row) for row in rows]

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
