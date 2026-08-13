from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from enterprise_knowledge_rag.models import AgentMode, AgentStep, StrictModel
from enterprise_knowledge_rag.providers import ModelProviderError


class AgentPlan(StrictModel):
    mode: AgentMode
    reason: str = Field(min_length=1, max_length=300)
    steps: list[AgentStep] = Field(min_length=1, max_length=8)


class StructuredPlanner(Protocol):
    def generate(self, *, prompt: str, schema: type[AgentPlan]): ...


DATA_TERMS = {
    "销售", "销售额", "订单", "退款率", "退款量", "渠道", "商品", "sku",
    "环比", "同比", "趋势", "经营周报", "核心指标", "客单价", "转化率",
    "退款数据", "销售数据", "订单数据", "经营数据",
    "revenue", "sales", "refund rate", "orders",
}
KNOWLEDGE_TERMS = {
    "制度", "流程", "请假", "病假", "休假", "年假", "年终奖",
    "加班", "考勤", "入职", "离职", "报销", "差旅", "出差", "补贴", "发票",
    "付款", "审批", "采购", "供应商", "验收", "权限", "安全事件", "薪酬",
    "工资", "绩效", "社保", "公积金", "福利", "expense", "supplier",
    "售后", "规定", "规范", "政策", "手册", "要求", "阈值", "是否触发",
    "policy", "rule", "procedure",
}


def _contains(question: str, terms: set[str]) -> bool:
    normalized = question.casefold()
    return any(term.casefold() in normalized for term in terms)


def _steps(mode: AgentMode, question: str) -> list[AgentStep]:
    if mode is AgentMode.GENERAL:
        return [AgentStep(agent="general_agent", task=question)]
    if mode is AgentMode.KNOWLEDGE:
        return [AgentStep(agent="knowledge_agent", task="检索并核验企业知识证据")]
    if mode is AgentMode.DATA:
        return [AgentStep(agent="data_agent", task="查询并分析受治理的经营数据")]
    return [
        AgentStep(agent="knowledge_agent", task="检索并核验相关企业制度"),
        AgentStep(agent="data_agent", task="查询并分析相关经营数据"),
        AgentStep(agent="synthesis_agent", task="综合数据与制度证据形成结论"),
        AgentStep(agent="review_agent", task="审核引用、数据证据与任务完整性"),
    ]


class Supervisor:
    def __init__(self, planner: StructuredPlanner | None = None) -> None:
        self._planner = planner

    def plan(
        self,
        question: str,
        history: Sequence[dict[str, str]] = (),
    ) -> AgentPlan:
        has_data = _contains(question, DATA_TERMS)
        has_knowledge = _contains(question, KNOWLEDGE_TERMS)
        if has_data and has_knowledge:
            mode = AgentMode.COLLABORATION
        elif has_data:
            mode = AgentMode.DATA
        elif has_knowledge:
            mode = AgentMode.KNOWLEDGE
        else:
            mode = AgentMode.GENERAL

        # Clear enterprise/data signals are safety boundaries. The model is only
        # allowed to resolve genuinely ambiguous general-looking requests.
        if mode is AgentMode.GENERAL and self._planner is not None:
            prompt = (
                "将用户请求路由为 general、knowledge、data 或 collaboration。"
                "企业事实必须走 knowledge，经营指标必须走 data，"
                "同时需要两者走 collaboration。\n"
                f"最近对话：{list(history)[-4:]}\n用户请求：{question}"
            )
            try:
                candidate = self._planner.generate(prompt=prompt, schema=AgentPlan)
                plan = (
                    candidate
                    if isinstance(candidate, AgentPlan)
                    else AgentPlan.model_validate(candidate)
                )
                if plan.mode is not AgentMode.GENERAL:
                    return plan
            except (ModelProviderError, ValueError, TypeError):
                pass
        return AgentPlan(
            mode=mode,
            reason=f"根据企业知识与经营数据需求路由为 {mode.value}",
            steps=_steps(mode, question),
        )
