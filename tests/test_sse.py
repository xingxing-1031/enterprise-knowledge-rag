from test_app import make_client

from enterprise_knowledge_rag.models import UserRole


def test_sse_contains_safe_chinese_progress_and_result() -> None:
    client, _ = make_client(UserRole.EMPLOYEE)
    response = client.post(
        "/chat/stream",
        json={"question": "报销多久提交"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert "检索企业知识" in response.text
    assert "event: result" in response.text
    assert "可信回答" in response.text
    assert "prompt" not in response.text.lower()
