from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from .source_models import ImportPreview, IngestionStatus

IMPORT_SELECT = """
    import_id::text AS import_id, original_filename, source_hash,
    media_type, size_bytes, page_count, status, metadata,
    cleaning_report, normalized_preview, failure_type, created_at, updated_at
"""


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _preview_from_row(row: dict[str, Any]) -> ImportPreview:
    return ImportPreview(
        import_id=str(row["import_id"]),
        original_filename=row["original_filename"],
        source_hash=row["source_hash"].strip(),
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        page_count=row["page_count"],
        status=row["status"],
        metadata=_json_value(row.get("metadata")),
        cleaning_report=_json_value(row.get("cleaning_report")),
        normalized_preview=row.get("normalized_preview", ""),
        failure_type=row.get("failure_type"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ImportRepository:
    """Persistence boundary that never returns private upload paths."""

    def __init__(self, connection_factory: Any) -> None:
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._connection_factory() as connection:
            yield connection

    def create_import(
        self,
        preview: ImportPreview,
        *,
        suffix: str,
        storage_path: str,
        uploaded_by: str,
    ) -> ImportPreview:
        from psycopg.rows import dict_row

        metadata = (
            preview.metadata.model_dump(mode="json")
            if preview.metadata is not None
            else None
        )
        cleaning_report = (
            preview.cleaning_report.model_dump(
                mode="json",
                exclude_computed_fields=True,
            )
            if preview.cleaning_report is not None
            else None
        )
        params = {
            **preview.model_dump(
                mode="python",
                exclude={"metadata", "cleaning_report"},
                exclude_computed_fields=True,
            ),
            "suffix": suffix,
            "storage_path": storage_path,
            "uploaded_by": uploaded_by,
            "metadata": json.dumps(metadata) if metadata is not None else None,
            "cleaning_report": (
                json.dumps(cleaning_report) if cleaning_report is not None else None
            ),
        }
        query = f"""
            INSERT INTO knowledge_imports (
                import_id, source_hash, original_filename, storage_path,
                media_type, suffix, size_bytes, page_count, status, metadata,
                cleaning_report, normalized_preview, failure_type, uploaded_by,
                created_at, updated_at
            ) VALUES (
                %(import_id)s, %(source_hash)s, %(original_filename)s,
                %(storage_path)s, %(media_type)s, %(suffix)s, %(size_bytes)s,
                %(page_count)s, %(status)s, %(metadata)s::jsonb,
                %(cleaning_report)s::jsonb, %(normalized_preview)s,
                %(failure_type)s, %(uploaded_by)s, %(created_at)s, %(updated_at)s
            )
            RETURNING {IMPORT_SELECT}
        """
        params["status"] = preview.status.value
        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("import creation returned no record")
        return _preview_from_row(row)

    def get_import(self, import_id: str) -> ImportPreview | None:
        from psycopg.rows import dict_row

        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                f"SELECT {IMPORT_SELECT} FROM knowledge_imports WHERE import_id = %s",
                (import_id,),
            )
            row = cursor.fetchone()
        return _preview_from_row(row) if row is not None else None

    def list_imports(self, *, limit: int = 50) -> list[ImportPreview]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        from psycopg.rows import dict_row

        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                f"""
                SELECT {IMPORT_SELECT}
                FROM knowledge_imports
                ORDER BY created_at DESC
                LIMIT %(limit)s
                """,
                {"limit": limit},
            )
            rows = cursor.fetchall()
        return [_preview_from_row(row) for row in rows]

    def update_status(
        self,
        import_id: str,
        status: IngestionStatus,
        *,
        failure_type: str | None = None,
    ) -> ImportPreview | None:
        from psycopg.rows import dict_row

        params = {
            "import_id": import_id,
            "status": status.value,
            "failure_type": failure_type,
        }
        with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                f"""
                UPDATE knowledge_imports
                SET status = %(status)s,
                    failure_type = %(failure_type)s,
                    updated_at = NOW()
                WHERE import_id = %(import_id)s
                RETURNING {IMPORT_SELECT}
                """,
                params,
            )
            row = cursor.fetchone()
        return _preview_from_row(row) if row is not None else None
