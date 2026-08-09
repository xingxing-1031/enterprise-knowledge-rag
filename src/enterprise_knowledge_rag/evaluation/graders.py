from collections.abc import Sequence, Set
from math import log2

from .models import (
    CaseMetrics,
    EvaluationCase,
    EvaluationObservation,
    ExpectedOutcome,
    RankingMetrics,
)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def grade_ranking(
    relevant_keys: Set[str],
    retrieved_keys: Sequence[str],
    *,
    k: int,
) -> RankingMetrics:
    if k < 1:
        raise ValueError("k must be positive")
    if not relevant_keys:
        raise ValueError("ranking metrics require at least one relevant key")

    ranked = _unique(retrieved_keys)[:k]
    hits = [key in relevant_keys for key in ranked]
    recall = len({key for key in ranked if key in relevant_keys}) / len(relevant_keys)
    first_hit = next((rank for rank, hit in enumerate(hits, start=1) if hit), None)
    reciprocal_rank = 0.0 if first_hit is None else 1.0 / first_hit
    dcg = sum(1.0 / log2(rank + 1) for rank, hit in enumerate(hits, 1) if hit)
    ideal_hits = min(len(relevant_keys), k)
    ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg
    return RankingMetrics(
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
    )


def _grade_versions(
    case: EvaluationCase,
    observation: EvaluationObservation,
) -> float | None:
    if not case.expected_versions:
        return None
    for document_id, expected in case.expected_versions.items():
        observed = {
            item.version
            for item in observation.retrieved
            if item.document_id == document_id
        }
        if observed != {expected}:
            return 0.0
    return 1.0


def _grade_citations(
    case: EvaluationCase,
    observation: EvaluationObservation,
) -> float | None:
    if case.expected_outcome is ExpectedOutcome.REFUSAL:
        return None
    if not observation.citations:
        return 0.0
    correct = observation.citations & case.gold_evidence_keys
    return len(correct) / len(observation.citations)


def _grade_answer_facts(
    case: EvaluationCase,
    observation: EvaluationObservation,
) -> float | None:
    if case.expected_outcome is ExpectedOutcome.REFUSAL:
        return None
    if not case.required_answer_facts:
        return None
    normalized_answer = "".join(observation.answer.split())
    matched = sum(
        "".join(fact.split()) in normalized_answer
        for fact in case.required_answer_facts
    )
    return matched / len(case.required_answer_facts)


def grade_case(
    case: EvaluationCase,
    observation: EvaluationObservation,
    *,
    k: int,
) -> CaseMetrics:
    retrieved_keys = [item.evidence_key for item in observation.retrieved]
    ranking = (
        grade_ranking(case.gold_evidence_keys, retrieved_keys, k=k)
        if case.gold_evidence_keys
        else None
    )
    leaked = any(
        item.document_id in case.forbidden_document_ids
        for item in observation.retrieved
    )
    version_accuracy = _grade_versions(case, observation)
    citation_accuracy = _grade_citations(case, observation)
    correct_refusal = (
        float(observation.refusal_reason is case.expected_refusal_reason)
        if case.expected_outcome is ExpectedOutcome.REFUSAL
        else None
    )
    false_refusal = float(
        case.expected_outcome is ExpectedOutcome.ANSWER
        and observation.status == "refused"
    )
    domain_accuracy = float(observation.in_scope is case.expected_in_scope)
    if case.expected_outcome is ExpectedOutcome.REFUSAL:
        core_pass = domain_accuracy == 1.0 and not leaked and correct_refusal == 1.0
    else:
        core_pass = (
            domain_accuracy == 1.0
            and not leaked
            and false_refusal == 0.0
            and ranking is not None
            and ranking.recall_at_k == 1.0
            and version_accuracy in (None, 1.0)
            and citation_accuracy == 1.0
        )
    return CaseMetrics(
        domain_accuracy=domain_accuracy,
        ranking=ranking,
        access_leakage=float(leaked),
        version_accuracy=version_accuracy,
        citation_accuracy=citation_accuracy,
        correct_refusal=correct_refusal,
        false_refusal=false_refusal,
        automated_answer_score=_grade_answer_facts(case, observation),
        core_pass=core_pass,
    )
