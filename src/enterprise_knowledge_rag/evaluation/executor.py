from collections.abc import Mapping
from time import perf_counter
from typing import Protocol

from enterprise_knowledge_rag.models import ChatRequest

from .models import (
    EvaluationCase,
    EvaluationObservation,
    EvaluationStrategy,
    ObservedEvidence,
)


def _evidence_key(document_id: str, version: str, section_path: list[str]) -> str:
    return f"{document_id}@{version}#{section_path[-1]}"


class EvaluationRuntime(Protocol):
    def run(self, request: ChatRequest, user): ...

    def clear_session(self, user, session_id: str | None) -> None: ...


class WorkflowEvaluationExecutor:
    """Turn a real RuntimeChatService result into grader-only observations."""

    def __init__(
        self,
        services: Mapping[EvaluationStrategy, EvaluationRuntime],
    ) -> None:
        self._services = services

    def run(
        self,
        case: EvaluationCase,
        *,
        strategy: EvaluationStrategy,
        corpus_snapshot: str,
    ) -> EvaluationObservation:
        del corpus_snapshot
        service = self._services[strategy]
        session_id = f"evaluation:{case.case_id}"
        started = perf_counter()
        try:
            workflow_run = service.run(
                ChatRequest(
                    question=case.question,
                    session_id=session_id,
                    as_of=case.as_of,
                ),
                case.user,
            )
        finally:
            service.clear_session(case.user, session_id)

        evidence_by_id = {
            item.evidence_id: item for item in workflow_run.result.evidence
        }
        citations = {
            _evidence_key(
                evidence_by_id[item.evidence_id].document_id,
                evidence_by_id[item.evidence_id].version,
                evidence_by_id[item.evidence_id].section_path,
            )
            for item in workflow_run.result.citations
            if item.evidence_id in evidence_by_id
        }
        retrieved = [
            ObservedEvidence(
                evidence_key=_evidence_key(
                    candidate.document.document_id,
                    candidate.document.version,
                    candidate.chunk.section_path,
                ),
                document_id=candidate.document.document_id,
                version=candidate.document.version,
            )
            for candidate in workflow_run.retrieval_candidates
        ]
        return EvaluationObservation(
            in_scope=workflow_run.in_scope,
            retrieved=retrieved,
            citations=citations,
            status=workflow_run.result.status,
            refusal_reason=workflow_run.result.refusal_reason,
            answer=workflow_run.result.answer,
            latency_ms=(perf_counter() - started) * 1000,
            model_calls=workflow_run.model_calls,
            routed_document_keys=[
                f"{document_id}@{version}"
                for document_id, version in workflow_run.routed_document_keys
            ],
            retrieval_hops=workflow_run.retrieval_hops,
            required_need_ids=set(workflow_run.required_need_ids),
            covered_need_ids=set(workflow_run.covered_need_ids),
            stage_timings_ms={
                event.component: event.duration_ms for event in workflow_run.trace
            },
        )
