import pytest
from fastapi.testclient import TestClient

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.auth import AuthSessionResolver
from enterprise_knowledge_rag.config import Settings
from tests.test_app import FakeService


def make_auth_client(
    settings: Settings | None = None,
) -> tuple[TestClient, FakeService]:
    service = FakeService()
    resolved = settings or Settings(
        app_env="test",
        auth_session_secret="test-secret-that-is-long-enough-123456",
    )
    app = create_app(
        service,
        settings=resolved,
        session_resolver=AuthSessionResolver(resolved),
    )
    return TestClient(app), service


ACCOUNTS = {
    "employee-demo": ("EmployeeDemo2026!", "employee"),
    "department-admin-demo": ("DepartmentAdmin2026!", "department_admin"),
    "knowledge-admin-demo": ("KnowledgeAdmin2026!", "knowledge_admin"),
}


def login(client: TestClient, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


@pytest.mark.parametrize(
    ("username", "password", "role"),
    [
        ("employee-demo", "EmployeeDemo2026!", "employee"),
        ("department-admin-demo", "DepartmentAdmin2026!", "department_admin"),
        ("knowledge-admin-demo", "KnowledgeAdmin2026!", "knowledge_admin"),
    ],
)
def test_demo_accounts_log_in_with_matching_role(
    username: str, password: str, role: str
) -> None:
    client, _ = make_auth_client()

    response = login(client, username, password)

    assert response.status_code == 200
    assert response.json()["role"] == role
    assert "rag_session" in response.headers.get("set-cookie", "")


def test_login_rejects_wrong_password() -> None:
    client, _ = make_auth_client()

    response = login(client, "employee-demo", "wrong-password")

    assert response.status_code == 401


def test_login_rejects_unknown_username() -> None:
    client, _ = make_auth_client()

    response = login(client, "nobody", "whatever")

    assert response.status_code == 401


def test_session_requires_login() -> None:
    client, _ = make_auth_client()

    response = client.get("/session")

    assert response.status_code == 401


def test_session_returns_identity_after_login() -> None:
    client, _ = make_auth_client()

    login(client, "knowledge-admin-demo", "KnowledgeAdmin2026!")
    response = client.get("/session")

    assert response.status_code == 200
    assert response.json()["role"] == "knowledge_admin"


def test_logout_invalidates_session() -> None:
    client, _ = make_auth_client()

    login(client, "employee-demo", "EmployeeDemo2026!")
    assert client.get("/session").status_code == 200

    logout = client.post("/auth/logout")

    assert logout.status_code == 204
    assert client.get("/session").status_code == 401


def test_employee_cannot_reach_admin_endpoint() -> None:
    client, _ = make_auth_client()

    login(client, "employee-demo", "EmployeeDemo2026!")
    response = client.post("/documents/index")

    assert response.status_code == 403


def test_knowledge_admin_can_reach_admin_endpoint() -> None:
    client, _ = make_auth_client()

    login(client, "knowledge-admin-demo", "KnowledgeAdmin2026!")
    response = client.post("/documents/index")

    assert response.status_code == 200


def test_ready_does_not_require_login() -> None:
    client, _ = make_auth_client()

    response = client.get("/ready")

    assert response.status_code == 200
