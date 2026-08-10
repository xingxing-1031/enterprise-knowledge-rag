from enterprise_knowledge_rag.documents.source_models import EvidenceKind, RetrievalPlan
from enterprise_knowledge_rag.retrieval.planning import RetrievalPlanner


class FakeStructuredProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, *, prompt, schema):
        self.calls.append((prompt, schema))
        return schema.model_validate(self.payload)


class FailingProvider:
    def generate(self, *, prompt, schema):
        raise RuntimeError("provider unavailable")


def test_planner_decomposes_material_and_exception_needs() -> None:
    provider = FakeStructuredProvider(
        {
            "primary_query": "病假超过两天交什么材料，紧急就医怎么办？",
            "topic": "员工请假",
            "departments": ["hr"],
            "evidence_needs": [
                {
                    "need_id": "material",
                    "kind": "material",
                    "query": "病假超过两天需要什么材料",
                },
                {
                    "need_id": "exception",
                    "kind": "exception",
                    "query": "紧急就医无法提前申请怎么办",
                },
            ],
            "requires_multi_hop": True,
            "max_hops": 2,
        }
    )
    planned = RetrievalPlanner(provider).plan(
        "病假超过两天交什么材料，紧急就医怎么办？", []
    )

    assert planned.status == "planned"
    assert {need.kind for need in planned.plan.evidence_needs} == {
        EvidenceKind.MATERIAL,
        EvidenceKind.EXCEPTION,
    }
    assert planned.plan.max_hops == 2
    assert planned.model_call_count == 1


def test_planner_failure_falls_back_to_one_rule_need() -> None:
    planned = RetrievalPlanner(FailingProvider()).plan("出差怎么报销？", [])

    assert planned.status == "degraded"
    assert planned.plan.max_hops == 1
    assert planned.plan.evidence_needs[0].kind is EvidenceKind.RULE
    assert planned.plan.evidence_needs[0].query == "出差怎么报销？"
    assert planned.model_call_count == 1


def test_planner_rejects_provider_plan_with_forbidden_scope_fields() -> None:
    provider = FakeStructuredProvider(
        {
            "primary_query": "请假规则",
            "topic": "请假",
            "departments": ["hr"],
            "evidence_needs": [
                {
                    "need_id": "rule",
                    "kind": "rule",
                    "query": "请假规则",
                    "document_keys": ["secret-policy"],
                }
            ],
            "requires_multi_hop": False,
            "max_hops": 1,
        }
    )

    planned = RetrievalPlanner(provider).plan("请假规则", [])

    assert planned.status == "degraded"
    assert planned.plan == RetrievalPlan(
        primary_query="请假规则",
        topic="未分类",
        evidence_needs=[
            {"need_id": "rule", "kind": "rule", "query": "请假规则"}
        ],
        requires_multi_hop=False,
        max_hops=1,
    )
