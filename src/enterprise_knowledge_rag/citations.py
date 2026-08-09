import re
from collections.abc import Sequence
from dataclasses import dataclass

from enterprise_knowledge_rag.generation import AnswerGenerator, DraftAnswer
from enterprise_knowledge_rag.models import Citation, RetrievalEvidence

NUMBER_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:万元|元|个自然日|个工作日|小时|天|%|年|月|日)?"
)
APPROVAL_TERMS = (
    "直属主管",
    "部门负责人",
    "财务负责人",
    "总经理",
    "知识库管理员",
)


@dataclass(frozen=True, slots=True)
class CitationValidation:
    valid: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    status: str
    answer: str
    citations: tuple[Citation, ...]
    retry_count: int
    degradation_reason: str | None = None


def _normalized_numbers(text: str) -> set[str]:
    return {match.replace(" ", "") for match in NUMBER_PATTERN.findall(text)}


def validate_citations(
    draft: DraftAnswer,
    evidence: Sequence[RetrievalEvidence],
) -> CitationValidation:
    by_id = {item.evidence_id: item for item in evidence}
    errors: list[str] = []

    for index, claim in enumerate(draft.claims, start=1):
        missing = [
            evidence_id
            for evidence_id in claim.evidence_ids
            if evidence_id not in by_id
        ]
        if missing:
            errors.append(f"claim {index} references unknown evidence: {missing}")
            continue
        quoted = "\n".join(
            by_id[evidence_id].quote for evidence_id in claim.evidence_ids
        )
        unsupported_numbers = _normalized_numbers(claim.text) - _normalized_numbers(
            quoted
        )
        if unsupported_numbers:
            errors.append(
                f"claim {index} has unsupported numbers: {sorted(unsupported_numbers)}"
            )
        unsupported_terms = [
            term for term in APPROVAL_TERMS if term in claim.text and term not in quoted
        ]
        if unsupported_terms:
            errors.append(
                f"claim {index} has unsupported approval terms: {unsupported_terms}"
            )

    return CitationValidation(valid=not errors, errors=tuple(errors))


def _citations(
    draft: DraftAnswer,
    evidence: Sequence[RetrievalEvidence],
) -> tuple[Citation, ...]:
    by_id = {item.evidence_id: item for item in evidence}
    ordered_ids = dict.fromkeys(
        evidence_id
        for claim in draft.claims
        for evidence_id in claim.evidence_ids
        if evidence_id in by_id
    )
    return tuple(
        Citation(
            evidence_id=evidence_id,
            label=(
                f"{by_id[evidence_id].title} · "
                f"{' > '.join(by_id[evidence_id].section_path)} · "
                f"v{by_id[evidence_id].version}"
            ),
        )
        for evidence_id in ordered_ids
    )


def _evidence_summary(evidence: Sequence[RetrievalEvidence]) -> str:
    lines = ["回答生成未通过引用校验，以下为已验证的检索依据："]
    for item in evidence:
        section = " > ".join(item.section_path)
        lines.append(f"- {item.title}（v{item.version}，{section}）：{item.quote}")
    return "\n".join(lines)


def generate_validated_answer(
    generator: AnswerGenerator,
    *,
    question: str,
    evidence: Sequence[RetrievalEvidence],
    history: Sequence[dict[str, str]] | None = None,
    max_regenerations: int = 1,
) -> GroundedAnswer:
    if not evidence:
        raise ValueError("validated answer requires evidence")

    last_errors: tuple[str, ...] = ()
    for attempt in range(max_regenerations + 1):
        draft = generator.generate(question, evidence, history)
        validation = validate_citations(draft, evidence)
        if validation.valid:
            return GroundedAnswer(
                status="success",
                answer=draft.answer,
                citations=_citations(draft, evidence),
                retry_count=attempt,
            )
        last_errors = validation.errors

    return GroundedAnswer(
        status="degraded",
        answer=_evidence_summary(evidence),
        citations=tuple(
            Citation(
                evidence_id=item.evidence_id,
                label=(
                    f"{item.title} · {' > '.join(item.section_path)} · v{item.version}"
                ),
            )
            for item in evidence
        ),
        retry_count=max_regenerations,
        degradation_reason="; ".join(last_errors),
    )
