import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
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
    AgentMode,
    AgentReview,
    AgentStep,
    ChatRequest,
    ChatResult,
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
    "育儿假",
    "婚假",
    "产假",
    "陪产假",
    "丧假",
    "探亲假",
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
    "五险一金",
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
        supervisor: Any | None = None,
        general_agent: Any | None = None,
        retail_agent: Any | None = None,
        synthesis_agent: Any | None = None,
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
        self._supervisor = supervisor
        self._general_agent = general_agent
        self._retail_agent = retail_agent
        self._synthesis_agent = synthesis_agent

    @staticmethod
    def _session_key(user: UserContext, session_id: str | None) -> tuple[str, str]:
        return user.user_id, session_id or "default"

    def ready(self) -> bool:
        return self._repository.ready()

    def run(self, request: ChatRequest, user: UserContext) -> WorkflowRun:
        key = self._session_key(user, request.session_id)
        with self._history_lock:
            history = list(self._histories.get(key, []))
        if self._supervisor is None:
            result = self._run_knowledge(request, user, history)
        else:
            plan = self._supervisor.plan(request.question, history)
            result = self._run_plan(plan, request, user, history)
        if result.result.status != "failed" and result.result.answer:
            updated = [
                *history,
                {"role": "user", "content": request.question},
                {"role": "assistant", "content": result.result.answer},
            ][-self._history_max_messages :]
            with self._history_lock:
                self._histories[key] = updated
        return result

    def run_knowledge(
        self,
        request: ChatRequest,
        user: UserContext,
    ) -> WorkflowRun:
        """Run governed RAG directly for internal evidence consumers."""
        key = self._session_key(user, request.session_id)
        with self._history_lock:
            history = list(self._histories.get(key, []))
        return self._run_knowledge(request, user, history)

    def _run_knowledge(
        self,
        request: ChatRequest,
        user: UserContext,
        history: Sequence[dict[str, str]],
    ) -> WorkflowRun:
        return self._chat_runner(
            self._graph,
            request,
            user,
            as_of=request.as_of or self._clock(),
            history=history,
        )

    @staticmethod
    def _completed_steps(steps: Sequence[AgentStep], status: str) -> list[AgentStep]:
        step_status = "succeeded" if status == "success" else status
        if step_status not in {"succeeded", "degraded", "refused", "failed"}:
            step_status = "degraded"
        return [item.model_copy(update={"status": step_status}) for item in steps]

    def _run_plan(self, plan, request, user, history) -> WorkflowRun:
        from enterprise_knowledge_rag.tracing import StageTimer

        trace = [StageTimer("supervisor").event("success")]
        if plan.mode is AgentMode.GENERAL:
            try:
                answer = self._general_agent.answer(request.question, history)
                status = "success"
                limitation = None
            except Exception:
                answer = "通用对话服务暂时不可用，请稍后再试。"
                status = "failed"
                limitation = "通用对话模型调用失败。"
            result = ChatResult(
                status=status,
                answer=answer,
                degradation_reason=limitation,
                agent_mode=plan.mode,
                agents=["general_agent", "review_agent"],
                task_plan=self._completed_steps(plan.steps, status),
                review=AgentReview(
                    passed=status == "success",
                    checks={"no_enterprise_claim_without_evidence": True},
                    limitations=[limitation] if limitation else [],
                ),
            )
            trace.extend([
                StageTimer("general_agent").event(status),
                StageTimer("review_agent").event(
                    "passed" if status == "success" else "failed"
                ),
            ])
            return WorkflowRun(result=result, trace=tuple(trace))

        if plan.mode is AgentMode.KNOWLEDGE:
            knowledge = self._run_knowledge(request, user, history)
            reviewed = knowledge.result.model_copy(
                update={
                    "agent_mode": plan.mode,
                    "agents": ["knowledge_agent", "review_agent"],
                    "task_plan": self._completed_steps(
                        plan.steps, knowledge.result.status
                    ),
                    "review": AgentReview(
                        passed=(
                            knowledge.result.status == "success"
                            and bool(knowledge.result.citations)
                        ),
                        checks={
                            "knowledge_citations_present": bool(
                                knowledge.result.citations
                            )
                        },
                    ),
                }
            )
            return knowledge.__class__(
                result=reviewed,
                trace=(
                    trace[0],
                    *knowledge.trace,
                    StageTimer("review_agent").event(
                        "passed" if reviewed.review.passed else "refused"
                    ),
                ),
                in_scope=knowledge.in_scope,
                retrieval_candidates=knowledge.retrieval_candidates,
                model_calls=knowledge.model_calls,
                retrieval_hops=knowledge.retrieval_hops,
                routed_document_keys=knowledge.routed_document_keys,
                required_need_ids=knowledge.required_need_ids,
                covered_need_ids=knowledge.covered_need_ids,
            )

        if plan.mode is AgentMode.DATA:
            if self._retail_agent is None:
                from enterprise_knowledge_rag.models import DataAgentResult

                data = DataAgentResult(
                    status="failed",
                    limitations=["经营数据 Agent 未配置。"],
                )
            else:
                data = self._retail_agent.run(
                    request.question,
                    user,
                    session_id=request.session_id,
                    as_of=request.as_of,
                )
            passed = data.status in {"succeeded", "degraded"} and bool(
                data.evidence_ids
            )
            status = (
                "success"
                if data.status == "succeeded" and passed
                else ("degraded" if data.answer else "failed")
            )
            result = ChatResult(
                status=status,
                answer=data.answer or "经营数据 Agent 暂时无法完成该任务。",
                degradation_reason="；".join(data.limitations) or None,
                agent_mode=plan.mode,
                agents=["data_agent", "review_agent"],
                task_plan=self._completed_steps(plan.steps, status),
                data_result=data,
                review=AgentReview(
                    passed=passed,
                    checks={"data_evidence_present": bool(data.evidence_ids)},
                    limitations=data.limitations,
                ),
            )
            return WorkflowRun(
                result=result,
                trace=(
                    trace[0],
                    StageTimer("data_agent").event(data.status),
                    StageTimer("review_agent").event(
                        "passed" if passed else "degraded"
                    ),
                ),
            )

        if self._retail_agent is None:
            from enterprise_knowledge_rag.models import DataAgentResult

            knowledge = self._run_knowledge(request, user, history)
            data = DataAgentResult(
                status="failed",
                limitations=["经营数据 Agent 未配置。"],
            )
        else:
            with ThreadPoolExecutor(max_workers=2) as executor:
                knowledge_future = executor.submit(
                    self._run_knowledge, request, user, history
                )
                data_future = executor.submit(
                    self._retail_agent.run,
                    request.question,
                    user,
                    session_id=request.session_id,
                    as_of=request.as_of,
                )
                knowledge = knowledge_future.result()
                data = data_future.result()
        knowledge_ok = knowledge.result.status == "success" and bool(
            knowledge.result.citations
        )
        data_ok = data.status in {"succeeded", "degraded"} and bool(
            data.evidence_ids
        )
        limitations = list(data.limitations)
        if not knowledge_ok:
            limitations.append("企业知识证据不足，未形成完整制度判断。")
        if not data_ok:
            limitations.append("经营数据证据不足，未形成完整数据判断。")
        if knowledge_ok and data_ok:
            try:
                answer = self._synthesis_agent.synthesize(
                    request.question, knowledge.result.answer, data.answer
                )
            except Exception:
                answer = (
                    f"数据发现：{data.answer}\n\n制度依据：{knowledge.result.answer}"
                )
                limitations.append("综合模型不可用，已返回两类已验证结果。")
            status = "degraded" if limitations else "success"
        else:
            available = [
                item for item in (data.answer, knowledge.result.answer) if item
            ]
            answer = "\n\n".join(available) or "当前无法获得完成任务所需的充分证据。"
            status = "degraded" if available else "refused"
        review = AgentReview(
            passed=knowledge_ok and data_ok,
            checks={
                "knowledge_citations_present": knowledge_ok,
                "data_evidence_present": data_ok,
                "required_agents_completed": knowledge_ok and data_ok,
            },
            limitations=limitations,
        )
        result = ChatResult(
            status=status,
            answer=answer,
            citations=knowledge.result.citations,
            evidence=knowledge.result.evidence,
            degradation_reason="；".join(limitations) or None,
            agent_mode=plan.mode,
            agents=["knowledge_agent", "data_agent", "synthesis_agent", "review_agent"],
            task_plan=self._completed_steps(plan.steps, status),
            data_result=data,
            review=review,
        )
        return WorkflowRun(
            result=result,
            trace=(
                trace[0],
                StageTimer("knowledge_agent").event(knowledge.result.status),
                StageTimer("data_agent").event(data.status),
                StageTimer("synthesis_agent").event(status),
                StageTimer("review_agent").event(
                    "passed" if review.passed else "degraded"
                ),
            ),
        )

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
