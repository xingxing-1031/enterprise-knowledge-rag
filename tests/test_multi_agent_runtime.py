import json
from pathlib import Path

from enterprise_knowledge_rag.models import (
    AgentMode,
    ChatRequest,
    ChatResult,
    Citation,
    DataAgentResult,
    IndexingSummary,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.runtime import RuntimeChatService
from enterprise_knowledge_rag.supervisor import Supervisor
from enterprise_knowledge_rag.workflow import WorkflowRun


class FakeRepository:
    def ready(self):
        return True

    def list_documents(self):
        return []


class FakeIndexing:
    def index_paths(self, paths):
        return IndexingSummary(
            discovered=0, indexed=0, skipped=0, failed=0, chunk_count=0
        )


class GeneralAgent:
    def answer(self, question, history):
        return f"通用回答：{question}"


class RetailAgent:
    def __init__(self, *, with_evidence=True):
        self.calls = []
        self.with_evidence = with_evidence

    def run(self, question, user, *, session_id, as_of):
        self.calls.append(question)
        return DataAgentResult(
            status="succeeded",
            answer="退款率上升 2 个百分点。",
            evidence_ids=["query:r1"] if self.with_evidence else [],
        )


class SynthesisAgent:
    def synthesize(self, question, knowledge_answer, data_answer):
        return f"综合结论：{data_answer} {knowledge_answer}"


def knowledge_runner(graph, request, user, *, as_of, history):
    return WorkflowRun(
        result=ChatResult(
            status="success",
            answer="制度规定退款异常需要复盘。",
            citations=[Citation(evidence_id="ev:policy", label="退款制度")],
        ),
        trace=(),
        in_scope=True,
    )


def make_service(tmp_path: Path, *, retail=None):
    report = tmp_path / "latest.json"
    report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    return RuntimeChatService(
        graph=object(),
        repository=FakeRepository(),
        indexing=FakeIndexing(),
        knowledge_dir=knowledge,
        latest_evaluation_path=report,
        chat_runner=knowledge_runner,
        supervisor=Supervisor(),
        general_agent=GeneralAgent(),
        retail_agent=retail or RetailAgent(),
        synthesis_agent=SynthesisAgent(),
    )


USER = UserContext(
    user_id="employee-1",
    role=UserRole.EMPLOYEE,
    departments={"finance"},
)


def test_runtime_dispatches_general_and_data_without_rag(tmp_path: Path) -> None:
    retail = RetailAgent()
    service = make_service(tmp_path, retail=retail)

    general = service.run(ChatRequest(question="你好"), USER).result
    data = service.run(ChatRequest(question="分析最近30天各渠道销售额"), USER).result

    assert general.agent_mode is AgentMode.GENERAL
    assert general.citations == []
    assert data.agent_mode is AgentMode.DATA
    assert data.review is not None and data.review.passed is True
    assert retail.calls == ["分析最近30天各渠道销售额"]


def test_runtime_collaboration_combines_two_governed_sources(tmp_path: Path) -> None:
    result = make_service(tmp_path).run(
        ChatRequest(question="分析退款率变化，并判断是否触发售后制度"), USER
    ).result

    assert result.agent_mode is AgentMode.COLLABORATION
    assert result.status == "success"
    assert result.answer.startswith("综合结论")
    assert result.citations[0].evidence_id == "ev:policy"
    assert result.data_result is not None
    assert result.data_result.evidence_ids == ["query:r1"]
    assert result.review is not None and result.review.passed is True


def test_runtime_review_degrades_collaboration_without_data_evidence(
    tmp_path: Path,
) -> None:
    result = make_service(tmp_path, retail=RetailAgent(with_evidence=False)).run(
        ChatRequest(question="分析退款率变化，并判断是否触发售后制度"), USER
    ).result

    assert result.status == "degraded"
    assert result.review is not None and result.review.passed is False
    assert result.review.checks["data_evidence_present"] is False
