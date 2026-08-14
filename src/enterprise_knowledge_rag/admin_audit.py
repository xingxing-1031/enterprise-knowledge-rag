from __future__ import annotations

import hashlib
import hmac
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from enterprise_knowledge_rag.admin_models import AdminAuditEvent


def document_reference_hash(document_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), document_id.encode(), hashlib.sha256).hexdigest()


class AdminAuditRepository:
    def __init__(self, connection_factory: Any, *, secret: str) -> None:
        self._connection_factory = connection_factory
        self._secret = secret

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._connection_factory() as connection:
            yield connection

    def record(
        self,
        *,
        action: str,
        actor_id: str,
        document_id: str | None = None,
        version: str | None = None,
        result: str = "success",
        reason_code: str | None = None,
    ) -> AdminAuditEvent:
        from psycopg.rows import dict_row

        ref_hash = (
            document_reference_hash(document_id, self._secret)
            if document_id is not None
            else None
        )
        event_id = str(uuid.uuid4())
        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                INSERT INTO knowledge_admin_audit
                    (event_id, action, actor_id, document_ref_hash, version,
                     result, reason_code)
                VALUES (%(event_id)s, %(action)s, %(actor_id)s, %(document_ref_hash)s,
                        %(version)s, %(result)s, %(reason_code)s)
                RETURNING event_id::text AS event_id, action, actor_id,
                    document_ref_hash, version, result, reason_code, created_at
                """,
                {
                    "event_id": event_id,
                    "action": action,
                    "actor_id": actor_id,
                    "document_ref_hash": ref_hash,
                    "version": version,
                    "result": result,
                    "reason_code": reason_code,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("audit event was not persisted")
        return AdminAuditEvent.model_validate(row)

    def list_recent(self, *, limit: int = 50) -> list[AdminAuditEvent]:
        from psycopg.rows import dict_row

        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
                SELECT event_id::text AS event_id, action, actor_id, document_ref_hash,
                    version, result, reason_code, created_at
                FROM knowledge_admin_audit
                ORDER BY created_at DESC
                LIMIT %(limit)s
                """,
                {"limit": max(1, min(limit, 100))},
            )
            rows = cursor.fetchall()
        return [AdminAuditEvent.model_validate(row) for row in rows]
