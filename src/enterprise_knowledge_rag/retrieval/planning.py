from collections.abc import Sequence
from typing import Any, Literal, Protocol

from pydantic import Field

from enterprise_knowledge_rag.documents.source_models import (
    EvidenceKind,
    EvidenceNeed,
    RetrievalPlan,
)
from enterprise_knowledge_rag.models import StrictModel


class StructuredPlanProvider(Protocol):
    def generate(self, *, prompt: str, schema: type[RetrievalPlan]) -> Any: ...


class PlannedRetrieval(StrictModel):
    plan: RetrievalPlan
    status: Literal["planned", "degraded"]
    model_call_count: int = Field(ge=0, le=1)


def _history_text(history: Sequence[Any]) -> str:
    if not history:
        return "无"
    rendered: list[str] = []
    for item in history[-6:]:
        if isinstance(item, dict):
            role = str(item.get("role", "消息"))
            content = str(item.get("content", ""))
        else:
            role = str(getattr(item, "role", "消息"))
            content = str(getattr(item, "content", item))
        if content.strip():
            rendered.append(f"{role}: {content.strip()[:500]}")
    return "\n".join(rendered) or "无"


def _fallback(question: str) -> RetrievalPlan:
    return RetrievalPlan(
        primary_query=question,
        topic="未分类",
        evidence_needs=[
            EvidenceNeed(
                need_id="rule",
                kind=EvidenceKind.RULE,
                query=question,
            )
        ],
        requires_multi_hop=False,
        max_hops=1,
    )


def normalize_retrieval_plan(plan: RetrievalPlan) -> RetrievalPlan:
    kind_counts: dict[str, int] = {}
    normalized_needs: list[EvidenceNeed] = []
    for need in plan.evidence_needs:
        base = need.kind.value
        count = kind_counts.get(base, 0) + 1
        kind_counts[base] = count
        need_id = base if count == 1 else f"{base}_{count}"
        normalized_needs.append(need.model_copy(update={"need_id": need_id}))
    required_count = sum(need.required for need in normalized_needs)
    allows_supplemental = plan.requires_multi_hop or required_count >= 2
    return RetrievalPlan(
        primary_query=plan.primary_query,
        topic=plan.topic,
        departments=plan.departments,
        evidence_needs=normalized_needs,
        requires_multi_hop=allows_supplemental,
        max_hops=2 if allows_supplemental else 1,
    )


class RetrievalPlanner:
    """Convert a question into bounded evidence needs with a safe fallback."""

    def __init__(self, provider: StructuredPlanProvider) -> None:
        self._provider = provider

    def plan(self, question: str, history: Sequence[Any]) -> PlannedRetrieval:
        normalized = question.strip()
        fallback = _fallback(normalized)
        prompt = f"""你是企业知识检索规划器。将用户问题拆成可检索的证据需求。

约束：
- 最多四个证据需求。
- kind 只能是 rule、procedure、material、exception、approver、deadline、scope。
- need_id 只需在当前计划内唯一；服务端会根据 kind 重新生成最终 ID。
- 金额门槛和适用条件使用 rule；登记证件和提交材料使用 material。
- 常规步骤使用 procedure；紧急、例外或无法遵循常规流程的路径使用 exception。
- 只有问题确实需要不同制度段落共同回答时，requires_multi_hop 才为 true。
- requires_multi_hop 为 true 时 max_hops 必须为 2，否则必须为 1。
- departments 只是语义提示，不是权限过滤条件。
- 禁止输出用户身份、角色、文档 ID、文档版本、可见范围或查询时间。
- 禁止输出任何访问控制条件；这些全部由服务器决定。
- 不回答问题，不生成结论，只输出结构化检索计划。

最近对话：
{_history_text(history)}

当前问题：
{normalized}
"""
        try:
            raw = self._provider.generate(prompt=prompt, schema=RetrievalPlan)
            plan = normalize_retrieval_plan(RetrievalPlan.model_validate(raw))
        except Exception:
            return PlannedRetrieval(
                plan=fallback,
                status="degraded",
                model_call_count=1,
            )
        return PlannedRetrieval(
            plan=plan,
            status="planned",
            model_call_count=1,
        )
