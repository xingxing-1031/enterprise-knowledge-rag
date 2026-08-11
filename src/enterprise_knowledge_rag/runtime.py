import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from enterprise_knowledge_rag.documents.indexing import IndexingService
from enterprise_knowledge_rag.documents.ingestion import IngestionService
from enterprise_knowledge_rag.documents.source_models import (
    ImportMetadata,
    ImportPreview,
    SourceFile,
)
from enterprise_knowledge_rag.models import (
    ChatRequest,
    DocumentRecord,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.policy import can_access
from enterprise_knowledge_rag.workflow import WorkflowRun, run_chat

ENTERPRISE_TERMS = {
    "expense",
    "parental leave",
    "payment approval",
    "sick leave",
    "supplier",
    "公司",
    "制度",
    "流程",
    "员工",
    "请假",
    "病假",
    "休假",
    "年假",
    "放假",
    "节假日",
    "加班",
    "加班费",
    "考勤",
    "迟到",
    "打卡",
    "入职",
    "离职",
    "离职证明",
    "交接",
    "竞业",
    "转岗",
    "报销",
    "差旅",
    "出差",
    "住宿",
    "补贴",
    "餐补",
    "发票",
    "付款",
    "审批",
    "采购",
    "供应商",
    "验收",
    "账号",
    "权限",
    "安全事件",
    "资产",
    "电脑",
    "薪酬",
    "工资",
    "发薪",
    "调薪",
    "绩效",
    "考核",
    "社保",
    "公积金",
    "福利",
    "体检",
    "年终奖",
}


class EnterpriseDomainClassifier:
    def is_in_scope(self, question: str) -> bool:
        normalized = question.strip().lower()
        return any(term in normalized for term in ENTERPRISE_TERMS)


class IdentityQueryRewriter:
    def rewrite(
        self,
        question: str,
        history: Sequence[dict[str, str]],
    ) -> str:
        del history
        return question.strip()


class RuntimeRepository(Protocol):
    def ready(self) -> bool: ...

    def list_documents(self) -> list[DocumentRecord]: ...


class ChatRunner(Protocol):
    def __call__(
        self,
        graph: Any,
        request: ChatRequest,
        user: UserContext,
        *,
        as_of: datetime,
        history: Sequence[dict[str, str]],
    ) -> WorkflowRun: ...


class RuntimeChatService:
    def __init__(
        self,
        *,
        graph: Any,
        repository: RuntimeRepository,
        indexing: IndexingService,
        ingestion: IngestionService | None = None,
        knowledge_dir: Path,
        latest_evaluation_path: Path,
        chat_runner: ChatRunner = run_chat,
        clock: Callable[[], datetime] | None = None,
        history_max_messages: int = 8,
    ) -> None:
        self._graph = graph
        self._repository = repository
        self._indexing = indexing
        self._ingestion = ingestion
        self._knowledge_dir = knowledge_dir
        self._latest_evaluation_path = latest_evaluation_path
        self._chat_runner = chat_runner
        self._clock = clock or (lambda: datetime.now(UTC))
        self._history_max_messages = history_max_messages
        self._histories: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._history_lock = Lock()

    @staticmethod
    def _session_key(user: UserContext, session_id: str | None) -> tuple[str, str]:
        return user.user_id, session_id or "default"

    def ready(self) -> bool:
        return self._repository.ready()

    def run(self, request: ChatRequest, user: UserContext) -> WorkflowRun:
        key = self._session_key(user, request.session_id)
        with self._history_lock:
            history = list(self._histories.get(key, []))
        result = self._chat_runner(
            self._graph,
            request,
            user,
            as_of=request.as_of or self._clock(),
            history=history,
        )
        if result.result.status != "failed" and result.result.answer:
            updated = [
                *history,
                {"role": "user", "content": request.question},
                {"role": "assistant", "content": result.result.answer},
            ][-self._history_max_messages :]
            with self._history_lock:
                self._histories[key] = updated
        return result

    def clear_session(self, user: UserContext, session_id: str | None) -> None:
        key = self._session_key(user, session_id)
        with self._history_lock:
            self._histories.pop(key, None)

    def documents_overview(self, user: UserContext) -> list[dict[str, Any]]:
        visible = [
            document
            for document in self._repository.list_documents()
            if can_access(user, document)
        ]
        return [
            {
                "document_id": document.document_id,
                "title": document.title,
                "version": document.version,
                "department": document.department,
                "visibility": document.visibility.value,
                "status": document.status.value,
                "effective_from": document.effective_from.isoformat(),
                "effective_to": (
                    document.effective_to.isoformat()
                    if document.effective_to is not None
                    else None
                ),
            }
            for document in sorted(
                visible,
                key=lambda item: (item.department, item.document_id, item.version),
            )
        ]

    def index_documents(self, user: UserContext) -> dict[str, Any]:
        if user.role is not UserRole.KNOWLEDGE_ADMIN:
            raise PermissionError("knowledge administrator role required")
        paths = sorted(
            path
            for path in self._knowledge_dir.rglob("*.md")
            if path.name != "README.md"
        )
        return self._indexing.index_paths(paths).model_dump(mode="json")

    def latest_evaluation(self) -> dict[str, Any]:
        if not self._latest_evaluation_path.exists():
            return {"status": "not_run"}
        try:
            return json.loads(self._latest_evaluation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "unavailable"}

    @staticmethod
    def _require_admin(user: UserContext) -> None:
        if user.role is not UserRole.KNOWLEDGE_ADMIN:
            raise PermissionError("knowledge administrator role required")

    def _ingestion_service(self) -> IngestionService:
        if self._ingestion is None:
            raise RuntimeError("document ingestion is not configured")
        return self._ingestion

    def preview_import(
        self,
        source: SourceFile,
        metadata: ImportMetadata,
        user: UserContext,
    ) -> ImportPreview:
        self._require_admin(user)
        return self._ingestion_service().preview(source, metadata, user)

    def list_imports(self, user: UserContext) -> list[ImportPreview]:
        self._require_admin(user)
        return self._ingestion_service().list_imports(user)

    def get_import(self, import_id: str, user: UserContext) -> ImportPreview | None:
        self._require_admin(user)
        return self._ingestion_service().get_import(import_id, user)

    def approve_import(
        self,
        import_id: str,
        metadata: ImportMetadata,
        user: UserContext,
    ) -> ImportPreview:
        self._require_admin(user)
        return self._ingestion_service().approve(import_id, metadata, user)
