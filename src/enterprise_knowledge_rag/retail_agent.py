from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

import httpx

from enterprise_knowledge_rag.models import DataAgentResult, UserContext


class HttpClient(Protocol):
    def post(self, url: str, **kwargs: Any): ...


class RetailAgentClient:
    def __init__(
        self,
        base_url: str,
        client: HttpClient,
        *,
        service_token: str,
        timeout_seconds: float = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._service_token = service_token
        self._timeout_seconds = timeout_seconds

    def run(
        self,
        question: str,
        user: UserContext,
        *,
        session_id: str | None,
        as_of: datetime | None,
    ) -> DataAgentResult:
        try:
            response = self._client.post(
                f"{self._base_url}/internal/agent",
                headers={"X-Internal-Token": self._service_token},
                json={
                    "request_id": f"multi-{uuid4()}",
                    "session_id": session_id,
                    "user_id": user.user_id,
                    "role": user.role.value,
                    "departments": sorted(user.departments),
                    "question": question,
                    "as_of": as_of.isoformat() if as_of else None,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return DataAgentResult.model_validate(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return DataAgentResult(
                status="failed",
                limitations=[f"经营数据 Agent 暂时不可用：{type(exc).__name__}"],
            )
