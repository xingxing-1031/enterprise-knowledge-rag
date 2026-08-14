from test_app import make_client

from enterprise_knowledge_rag.models import UserRole


def test_browser_chat_stream_is_not_exposed() -> None:
    client, _ = make_client(UserRole.EMPLOYEE)
    response = client.post(
        "/chat/stream",
        json={"question": "报销多久提交"},
    )
    assert response.status_code == 404
