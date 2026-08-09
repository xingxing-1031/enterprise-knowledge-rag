import pytest
from test_citations import make_evidence

from enterprise_knowledge_rag.generation import AnswerGenerator, DraftAnswer


class CapturingProvider:
    def __init__(self, result):
        self.result = result
        self.prompt = None

    def generate(self, *, prompt, schema):
        self.prompt = prompt
        return self.result


def test_generation_prompt_contains_only_supplied_evidence() -> None:
    evidence = make_evidence()
    provider = CapturingProvider(
        {
            "answer": "报销需在15个自然日内提交。",
            "claims": [
                {
                    "text": "报销需在15个自然日内提交。",
                    "evidence_ids": [evidence.evidence_id],
                }
            ],
        }
    )
    result = AnswerGenerator(provider).generate("多久提交报销", [evidence])
    assert isinstance(result, DraftAnswer)
    assert evidence.evidence_id in provider.prompt
    assert evidence.quote in provider.prompt


def test_generation_without_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        AnswerGenerator(CapturingProvider({})).generate("问题", [])
