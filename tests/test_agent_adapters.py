from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from enterprise_knowledge_rag.general_chat import GeneralChatAgent
from enterprise_knowledge_rag.models import UserContext, UserRole
from enterprise_knowledge_rag.retail_agent import RetailAgentClient


class FakeCompletions:
    def create(self, **kwargs):
        assert "不得声称了解" in kwargs["messages"][0]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="你好，有什么可以帮你？"))]
        )


def test_general_agent_uses_bounded_system_instruction() -> None:
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    agent = GeneralChatAgent(client, model="demo", timeout_seconds=3)

    assert agent.answer("你好", []) == "你好，有什么可以帮你？"


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": "succeeded",
            "skill_id": "refund_diagnosis",
            "answer": "退款率上升 2 个百分点。",
            "evidence_ids": ["query:r1"],
        }


class FakeHttpClient:
    def __init__(self):
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return FakeResponse()


def test_retail_agent_propagates_identity_and_internal_token() -> None:
    http = FakeHttpClient()
    agent = RetailAgentClient(
        "http://retail", http, service_token="a" * 64, timeout_seconds=5
    )
    user = UserContext(
        user_id="employee-1",
        role=UserRole.EMPLOYEE,
        departments={"finance"},
    )

    result = agent.run(
        "分析退款率",
        user,
        session_id="s1",
        as_of=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert result.evidence_ids == ["query:r1"]
    assert http.request[1]["headers"]["X-Internal-Token"] == "a" * 64
    assert http.request[1]["json"]["departments"] == ["finance"]


class FailingHttpClient:
    def post(self, url, **kwargs):
        raise httpx.ConnectError("offline")


def test_retail_agent_fails_closed_when_service_is_unavailable() -> None:
    result = RetailAgentClient(
        "http://retail", FailingHttpClient(), service_token="a" * 64
    ).run(
        "分析退款率",
        UserContext(user_id="u1", role=UserRole.EMPLOYEE),
        session_id=None,
        as_of=None,
    )

    assert result.status == "failed"
    assert "ConnectError" in result.limitations[0]
