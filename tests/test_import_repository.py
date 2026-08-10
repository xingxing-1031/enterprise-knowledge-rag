from datetime import UTC, datetime

from enterprise_knowledge_rag.documents.import_repository import ImportRepository
from enterprise_knowledge_rag.documents.source_models import IngestionStatus


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.executions.append((query, params))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self, **kwargs):
        return self._cursor


def make_repository(rows: list[dict[str, object]]):
    cursor = FakeCursor(rows)
    repository = ImportRepository(lambda: FakeConnection(cursor))
    return repository, cursor


def import_row() -> dict[str, object]:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    return {
        "import_id": "c9cd565d-351f-48c3-b64c-cb6229fe8861",
        "original_filename": "leave-policy.pdf",
        "source_hash": "a" * 64,
        "storage_path": "data/uploads/c9cd565d/source.pdf",
        "media_type": "application/pdf",
        "suffix": ".pdf",
        "size_bytes": 4096,
        "page_count": 3,
        "status": "needs_review",
        "metadata": {
            "document_id": "hr-leave-policy",
            "title": "员工请假制度",
            "document_type": "policy",
            "department": "hr",
            "visibility": "restricted",
            "allowed_roles": ["employee"],
            "version": "2.0",
            "effective_from": now.isoformat(),
        },
        "cleaning_report": {
            "characters_before": 100,
            "characters_after": 90,
            "blocks_before": 5,
            "blocks_after": 4,
            "table_count": 0,
            "content_hash": "b" * 64,
            "issues": [],
        },
        "normalized_preview": "# 员工请假制度",
        "failure_type": None,
        "created_at": now,
        "updated_at": now,
    }


def test_import_repository_maps_safe_preview_without_storage_path() -> None:
    repository, _ = make_repository([import_row()])

    preview = repository.get_import("c9cd565d-351f-48c3-b64c-cb6229fe8861")

    assert preview is not None
    assert preview.status is IngestionStatus.NEEDS_REVIEW
    assert "storage" not in preview.model_dump_json()


def test_import_repository_list_is_newest_first() -> None:
    repository, cursor = make_repository([import_row()])

    previews = repository.list_imports(limit=20)

    assert len(previews) == 1
    query, params = cursor.executions[0]
    assert "ORDER BY created_at DESC" in query
    assert params == {"limit": 20}


def test_status_update_uses_stable_failure_type_not_raw_exception() -> None:
    repository, cursor = make_repository([import_row()])

    repository.update_status(
        "c9cd565d-351f-48c3-b64c-cb6229fe8861",
        IngestionStatus.QUARANTINED,
        failure_type="scanned_pdf",
    )

    params = cursor.executions[0][1]
    assert params["failure_type"] == "scanned_pdf"
    assert params["status"] == "quarantined"
