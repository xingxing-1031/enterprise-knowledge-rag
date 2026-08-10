from datetime import UTC, datetime
from time import perf_counter

from pydantic import Field

from enterprise_knowledge_rag.models import StrictModel


class TraceEvent(StrictModel):
    component: str = Field(min_length=1)
    status: str = Field(min_length=1)
    occurred_at: datetime
    duration_ms: float = Field(ge=0)
    candidate_count: int | None = Field(default=None, ge=0)
    evidence_count: int | None = Field(default=None, ge=0)
    need_count: int | None = Field(default=None, ge=0)
    route_count: int | None = Field(default=None, ge=0)
    hop_count: int | None = Field(default=None, ge=0, le=2)
    error_type: str | None = None


class StageTimer:
    def __init__(self, component: str) -> None:
        self.component = component
        self.started_at = datetime.now(UTC)
        self._started = perf_counter()

    def event(
        self,
        status: str,
        *,
        candidate_count: int | None = None,
        evidence_count: int | None = None,
        need_count: int | None = None,
        route_count: int | None = None,
        hop_count: int | None = None,
        error_type: str | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            component=self.component,
            status=status,
            occurred_at=self.started_at,
            duration_ms=(perf_counter() - self._started) * 1000,
            candidate_count=candidate_count,
            evidence_count=evidence_count,
            need_count=need_count,
            route_count=route_count,
            hop_count=hop_count,
            error_type=error_type,
        )
