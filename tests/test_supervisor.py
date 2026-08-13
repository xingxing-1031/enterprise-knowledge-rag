from enterprise_knowledge_rag.models import AgentMode
from enterprise_knowledge_rag.supervisor import Supervisor


def test_supervisor_routes_four_execution_modes() -> None:
    supervisor = Supervisor()

    assert supervisor.plan("你好，帮我解释一下 RAG").mode is AgentMode.GENERAL
    assert supervisor.plan("帮我分析这段文字").mode is AgentMode.GENERAL
    assert supervisor.plan("解释 Python 数据结构").mode is AgentMode.GENERAL
    assert supervisor.plan("查询公司昨天销售额").mode is AgentMode.DATA
    assert supervisor.plan("公司的差旅报销制度是什么？").mode is AgentMode.KNOWLEDGE
    assert supervisor.plan("分析最近30天各渠道销售额").mode is AgentMode.DATA
    assert (
        supervisor.plan("分析退款率变化，并判断是否触发售后制度").mode
        is AgentMode.COLLABORATION
    )


def test_collaboration_plan_has_specialized_agents_and_review() -> None:
    plan = Supervisor().plan("结合退款数据和售后制度生成复盘")

    assert [step.agent for step in plan.steps] == [
        "knowledge_agent",
        "data_agent",
        "synthesis_agent",
        "review_agent",
    ]
