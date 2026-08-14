import json
from datetime import UTC, datetime
from pathlib import Path

from enterprise_knowledge_rag.models import (
    ChatRequest,
    ChatResult,
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    IndexingSummary,
    UserContext,
    UserRole,
    Visibility,
)
from enterprise_knowledge_rag.runtime import (
    EnterpriseDomainClassifier,
    RuntimeChatService,
)
from enterprise_knowledge_rag.workflow import WorkflowRun

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def make_document(*, restricted=False):
    return DocumentRecord(
        document_id="finance-payment" if restricted else "finance-expense",
        title="付款审批权限表" if restricted else "费用报销制度",
        document_type=DocumentType.POLICY,
        department="finance",
        visibility=Visibility.RESTRICTED if restricted else Visibility.PUBLIC,
        allowed_roles={UserRole.DEPARTMENT_ADMIN} if restricted else set(),
        version="1.0",
        status=DocumentStatus.ACTIVE,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash=("b" if restricted else "a") * 64,
        source_path="finance/policy.md",
        indexed_at=NOW,
    )


class FakeRepository:
    def __init__(self):
        self.documents = [make_document(), make_document(restricted=True)]

    def ready(self):
        return True

    def list_documents(self):
        return self.documents


class FakeIndexing:
    def __init__(self):
        self.paths = None

    def index_paths(self, paths):
        self.paths = list(paths)
        return IndexingSummary(
            discovered=len(paths),
            indexed=len(paths),
            skipped=0,
            failed=0,
            chunk_count=3,
        )


class RecordingRunner:
    def __init__(self):
        self.histories = []

    def __call__(self, graph, request, user, *, as_of, history):
        self.histories.append(list(history))
        return WorkflowRun(
            result=ChatResult(status="success", answer=f"回答：{request.question}"),
            trace=(),
        )


def make_service(tmp_path: Path):
    report = tmp_path / "latest.json"
    report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "policy.md").write_text("policy", encoding="utf-8")
    runner = RecordingRunner()
    indexing = FakeIndexing()
    service = RuntimeChatService(
        graph=object(),
        repository=FakeRepository(),
        indexing=indexing,
        knowledge_dir=knowledge,
        latest_evaluation_path=report,
        chat_runner=runner,
        clock=lambda: NOW,
    )
    return service, runner, indexing


def test_service_keeps_history_isolated_and_can_clear_it(tmp_path: Path) -> None:
    service, runner, _ = make_service(tmp_path)
    user = UserContext(
        user_id="employee-1",
        role=UserRole.EMPLOYEE,
        departments={"finance"},
    )
    request = ChatRequest(question="报销期限", session_id="session-a")

    service.run(request, user)
    service.run(request.model_copy(update={"question": "票据呢"}), user)
    service.clear_session(user, "session-a")
    service.run(request, user)

    assert runner.histories[0] == []
    assert runner.histories[1][-2:] == [
        {"role": "user", "content": "报销期限"},
        {"role": "assistant", "content": "回答：报销期限"},
    ]
    assert runner.histories[2] == []


def test_runtime_always_uses_governed_rag_without_agent_dependencies(
    tmp_path: Path,
) -> None:
    service, runner, _ = make_service(tmp_path)
    user = UserContext(
        user_id="employee-1",
        role=UserRole.EMPLOYEE,
        departments={"finance"},
    )

    result = service.run(
        ChatRequest(question="查询公司昨天销售额", session_id="rag-only"),
        user,
    )

    assert result.result.answer == "回答：查询公司昨天销售额"
    assert len(runner.histories) == 1
    assert not hasattr(service, "_supervisor")
    assert not hasattr(service, "_retail_agent")


def test_documents_overview_hides_inaccessible_metadata(tmp_path: Path) -> None:
    service, _, _ = make_service(tmp_path)
    employee = UserContext(
        user_id="employee-1",
        role=UserRole.EMPLOYEE,
        departments={"finance"},
    )

    documents = service.documents_overview(employee)

    assert [item["document_id"] for item in documents] == ["finance-expense"]
    assert "付款审批权限表" not in json.dumps(documents, ensure_ascii=False)


def test_admin_indexing_and_latest_report_use_configured_paths(tmp_path: Path) -> None:
    service, _, indexing = make_service(tmp_path)
    admin = UserContext(
        user_id="admin-1",
        role=UserRole.KNOWLEDGE_ADMIN,
        departments=set(),
    )

    summary = service.index_documents(admin)

    assert summary["indexed"] == 1
    assert indexing.paths[0].name == "policy.md"
    assert service.latest_evaluation() == {"status": "completed"}
    assert service.ready() is True


def test_domain_classifier_accepts_enterprise_topics_and_rejects_general_chat() -> None:
    classifier = EnterpriseDomainClassifier()

    assert classifier.is_in_scope("公司年终奖按几个月工资计算？") is True
    assert classifier.is_in_scope("采购到货以后怎么验收？") is True
    assert classifier.is_in_scope("红烧肉怎么做？") is False


def test_domain_classifier_accepts_all_in_scope_development_questions() -> None:
    dataset_path = Path(__file__).parents[1] / "evaluation" / "development.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    classifier = EnterpriseDomainClassifier()

    rejected = [
        case["case_id"]
        for case in dataset["cases"]
        if case["expected_in_scope"] and not classifier.is_in_scope(case["question"])
    ]

    assert rejected == []
