from test_citations import make_evidence

from enterprise_knowledge_rag.citations import generate_validated_answer
from enterprise_knowledge_rag.generation import AnswerGenerator
from enterprise_knowledge_rag.models import RefusalReason
from enterprise_knowledge_rag.refusal import build_refusal


class SequenceProvider:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def generate(self, *, prompt, schema):
        self.calls += 1
        return next(self.results)


def invalid_answer():
    return {
        "answer": "需要30天内提交。",
        "claims": [
            {
                "text": "需要30天内提交。",
                "evidence_ids": ["ev:missing"],
            }
        ],
    }


def test_two_invalid_generations_degrade_to_evidence_summary() -> None:
    provider = SequenceProvider([invalid_answer(), invalid_answer()])
    result = generate_validated_answer(
        AnswerGenerator(provider),
        question="报销多久提交",
        evidence=[make_evidence()],
        max_regenerations=1,
    )
    assert result.status == "degraded"
    assert provider.calls == 2
    assert "已验证的检索依据" in result.answer
    assert "15个自然日" in result.answer


def test_second_valid_generation_is_returned() -> None:
    evidence = make_evidence()
    valid = {
        "answer": "请在15个自然日内提交报销申请。",
        "claims": [
            {
                "text": "请在15个自然日内提交报销申请。",
                "evidence_ids": [evidence.evidence_id],
            }
        ],
    }
    provider = SequenceProvider([invalid_answer(), valid])
    result = generate_validated_answer(
        AnswerGenerator(provider),
        question="报销多久提交",
        evidence=[evidence],
        max_regenerations=1,
    )
    assert result.status == "success"
    assert result.retry_count == 1
    assert result.citations[0].evidence_id == evidence.evidence_id


def test_refusal_has_no_evidence_or_citations() -> None:
    result = build_refusal(RefusalReason.INSUFFICIENT_EVIDENCE)
    assert result.status == "refused"
    assert result.evidence == []
    assert result.citations == []
    assert "没有足够依据" in result.answer
