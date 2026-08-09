from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import Field

from enterprise_knowledge_rag.models import RetrievalEvidence, StrictModel


class AnswerClaim(StrictModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class DraftAnswer(StrictModel):
    answer: str = Field(min_length=1)
    claims: list[AnswerClaim] = Field(min_length=1)


class StructuredGenerationProvider(Protocol):
    def generate(self, *, prompt: str, schema: type[DraftAnswer]) -> Any: ...


SYSTEM_RULES = """你是企业制度与流程知识助手。
只允许根据提供的检索证据回答，不得使用常识补充企业规则。
每个事实陈述必须列出实际 evidence_id。
金额、时限、日期、版本和审批角色必须与引用原文一致。
无法从证据回答时，不得编造答案。
"""


def build_generation_prompt(
    question: str,
    evidence: Sequence[RetrievalEvidence],
    history: Sequence[dict[str, str]] | None = None,
) -> str:
    history_lines = [
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in (history or [])[-4:]
    ]
    evidence_lines = [
        "\n".join(
            [
                f"evidence_id: {item.evidence_id}",
                f"document: {item.title}",
                f"version: {item.version}",
                f"section: {' > '.join(item.section_path)}",
                f"quote: {item.quote}",
            ]
        )
        for item in evidence
    ]
    return "\n\n".join(
        [
            SYSTEM_RULES,
            "对话历史：\n" + ("\n".join(history_lines) or "无"),
            f"用户问题：{question}",
            "检索证据：\n" + "\n\n".join(evidence_lines),
        ]
    )


class AnswerGenerator:
    def __init__(self, provider: StructuredGenerationProvider) -> None:
        self._provider = provider

    def generate(
        self,
        question: str,
        evidence: Sequence[RetrievalEvidence],
        history: Sequence[dict[str, str]] | None = None,
    ) -> DraftAnswer:
        if not evidence:
            raise ValueError("answer generation requires evidence")
        result = self._provider.generate(
            prompt=build_generation_prompt(question, evidence, history),
            schema=DraftAnswer,
        )
        if isinstance(result, DraftAnswer):
            return result
        return DraftAnswer.model_validate(result)
