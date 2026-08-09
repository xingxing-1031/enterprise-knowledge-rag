from datetime import UTC, datetime

from fastapi.testclient import TestClient

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.config import Settings
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
