import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.documents.source_models import (
    CleaningReport,
    ImportPreview,
    IngestionStatus,
)
from enterprise_knowledge_rag.models import ChatResult, UserContext, UserRole
from enterprise_knowledge_rag.tracing import TraceEvent
from enterprise_knowledge_rag.workflow import WorkflowRun


class FixedResolver:
    def __init__(self, role=UserRole.EMPLOYEE):
        self.role = role

    def resolve(self, request):
        return UserContext(
            user_id="trusted-user",
            role=self.role,
            departments={"finance"},
        )


class FakeService:
    def __init__(self):
        self.received_user = None

    def ready(self):
        return True

    def run(self, request, user):
        self.received_user = user
        return WorkflowRun(
            result=ChatResult(status="success", answer="可信回答"),
            trace=(
                TraceEvent(
                    component="retrieve",
                    status="ready",
                    occurred_at=datetime(2026, 8, 10, tzinfo=UTC),
                    duration_ms=12.0,
                    candidate_count=3,
                ),
            ),
        )

    def clear_session(self, user, session_id):
        return None

    def documents_overview(self, user):
        return [{"status": "active", "count": 7}]

    def index_documents(self, user):
        return {"indexed": 1}

    def latest_evaluation(self):
        return {"status": "not_run"}

    def preview_import(self, source, metadata, user):
        now = datetime(2026, 8, 10, tzinfo=UTC)
        return ImportPreview(
            import_id="import-001",
            original_filename=source.original_filename,
            source_hash=source.source_hash,
            media_type=source.media_type,
            size_bytes=source.size_bytes,
            status=IngestionStatus.NEEDS_REVIEW,
            metadata=metadata,
            cleaning_report=CleaningReport(
                characters_before=10,
                characters_after=10,
                blocks_before=1,
                blocks_after=1,
                table_count=0,
                content_hash="a" * 64,
            ),
            normalized_preview="制度正文",
            created_at=now,
            updated_at=now,
        )

    def list_imports(self, user):
        return []

    def get_import(self, import_id, user):
        return None

    def approve_import(self, import_id, metadata, user):
        return self.preview_import(
            type("Source", (), {
                "original_filename": "policy.txt",
                "source_hash": "a" * 64,
                "media_type": "text/plain",
                "size_bytes": 10,
            })(),
            metadata,
            user,
        ).model_copy(update={"status": IngestionStatus.INDEXED})


def make_client(role=UserRole.EMPLOYEE):
    service = FakeService()
    app = create_app(
        service,
        settings=Settings(app_env="test"),
        session_resolver=FixedResolver(role),
    )
    return TestClient(app), service


def test_chat_uses_server_resolved_identity() -> None:
    client, service = make_client()
    response = client.post("/chat", json={"question": "报销多久提交"})
    assert response.status_code == 200
    assert service.received_user.user_id == "trusted-user"
    assert service.received_user.role is UserRole.EMPLOYEE


def test_request_cannot_escalate_role() -> None:
    client, _ = make_client()
    response = client.post(
        "/chat",
        json={"question": "付款审批", "role": "knowledge_admin"},
    )
    assert response.status_code == 422


def test_employee_cannot_trigger_indexing() -> None:
    client, _ = make_client()
    response = client.post("/documents/index")
    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号无管理权限"


def test_admin_can_trigger_indexing() -> None:
    client, _ = make_client(UserRole.KNOWLEDGE_ADMIN)
    response = client.post("/documents/index")
    assert response.status_code == 200
    assert response.json() == {"indexed": 1}


def import_metadata_form() -> dict[str, str]:
    return {
        "metadata": json.dumps(
            {
                "document_id": "hr-leave-policy",
                "title": "员工请假制度",
                "document_type": "policy",
                "department": "hr",
                "visibility": "restricted",
                "allowed_roles": ["employee"],
                "version": "2.0",
                "effective_from": "2026-08-10T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
    }


def test_employee_cannot_upload_enterprise_document() -> None:
    client, _ = make_client()

    response = client.post(
        "/knowledge/imports",
        files={"file": ("policy.txt", b"policy body", "text/plain")},
        data=import_metadata_form(),
    )

    assert response.status_code == 403


def test_admin_can_upload_and_receive_safe_preview() -> None:
    client, _ = make_client(UserRole.KNOWLEDGE_ADMIN)

    response = client.post(
        "/knowledge/imports",
        files={"file": ("policy.txt", "制度正文".encode(), "text/plain")},
        data=import_metadata_form(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert "storage_path" not in payload


def test_admin_import_metadata_is_strictly_validated() -> None:
    client, _ = make_client(UserRole.KNOWLEDGE_ADMIN)

    response = client.post(
        "/knowledge/imports",
        files={"file": ("policy.txt", b"policy body", "text/plain")},
        data={"metadata": json.dumps({"title": "缺少其他字段"})},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "文档元数据不合法"


def test_session_reports_trusted_role() -> None:
    client, _ = make_client()
    response = client.get("/session")
    assert response.json()["role"] == "employee"
    assert response.json()["departments"] == ["finance"]


def test_oversized_request_is_rejected() -> None:
    client, _ = make_client()
    response = client.post(
        "/chat",
        content=b"x" * 20_000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_built_frontend_is_served_without_shadowing_api(tmp_path) -> None:
    frontend = tmp_path / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text(
        "<html><body>企业知识工作台</body></html>", encoding="utf-8"
    )
    (assets / "app.js").write_text("console.log('ready')", encoding="utf-8")
    app = create_app(
        FakeService(),
        settings=Settings(app_env="test"),
        session_resolver=FixedResolver(),
        static_dir=frontend,
    )
    client = TestClient(app)

    assert client.get("/").text == "<html><body>企业知识工作台</body></html>"
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
