from enterprise_knowledge_rag.models import AgentMode
from enterprise_knowledge_rag.multi_agent_evaluation import (
    MultiAgentCase,
    evaluate_supervisor,
)
from enterprise_knowledge_rag.supervisor import Supervisor


def test_evaluation_keeps_sample_level_route_and_agent_results() -> None:
    report = evaluate_supervisor(
        [
            MultiAgentCase(
                case_id="c1",
                question="查询订单数",
                expected_mode=AgentMode.DATA,
                expected_agents=["data_agent"],
            ),
            MultiAgentCase(
                case_id="c2",
                question="你好",
                expected_mode=AgentMode.GENERAL,
                expected_agents=["general_agent"],
            ),
        ],
        Supervisor(),
        dataset="test",
    )

    assert report.case_count == 2
    assert report.route_accuracy == 1
    assert report.agent_selection_accuracy == 1
    assert all(item.latency_ms >= 0 for item in report.records)
