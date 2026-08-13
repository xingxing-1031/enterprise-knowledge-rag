from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from pydantic import Field

from enterprise_knowledge_rag.models import AgentMode, StrictModel
from enterprise_knowledge_rag.supervisor import Supervisor


class MultiAgentCase(StrictModel):
    case_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_mode: AgentMode
    expected_agents: list[str] = Field(min_length=1)


class MultiAgentRecord(StrictModel):
    case_id: str
    expected_mode: AgentMode
    actual_mode: AgentMode
    expected_agents: list[str]
    actual_agents: list[str]
    route_correct: bool
    agents_correct: bool
    latency_ms: float = Field(ge=0)


class MultiAgentReport(StrictModel):
    dataset: str
    case_count: int = Field(ge=1)
    route_accuracy: float = Field(ge=0, le=1)
    agent_selection_accuracy: float = Field(ge=0, le=1)
    records: list[MultiAgentRecord]


def load_cases(path: Path) -> list[MultiAgentCase]:
    return [
        MultiAgentCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate_supervisor(
    cases: list[MultiAgentCase], supervisor: Supervisor, *, dataset: str
) -> MultiAgentReport:
    records: list[MultiAgentRecord] = []
    for case in cases:
        started = perf_counter()
        plan = supervisor.plan(case.question)
        latency_ms = (perf_counter() - started) * 1000
        actual_agents = [step.agent for step in plan.steps]
        records.append(
            MultiAgentRecord(
                case_id=case.case_id,
                expected_mode=case.expected_mode,
                actual_mode=plan.mode,
                expected_agents=case.expected_agents,
                actual_agents=actual_agents,
                route_correct=plan.mode is case.expected_mode,
                agents_correct=all(
                    agent in actual_agents for agent in case.expected_agents
                ),
                latency_ms=latency_ms,
            )
        )
    count = len(records)
    return MultiAgentReport(
        dataset=dataset,
        case_count=count,
        route_accuracy=sum(item.route_correct for item in records) / count,
        agent_selection_accuracy=(
            sum(item.agents_correct for item in records) / count
        ),
        records=records,
    )


def save_report(report: MultiAgentReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
