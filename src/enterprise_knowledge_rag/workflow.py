from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from enterprise_knowledge_rag.citations import (
    GroundedAnswer,
    generate_validated_answer,
)
from enterprise_knowledge_rag.evidence import build_minimal_evidence
from enterprise_knowledge_rag.generation import AnswerGenerator
from enterprise_knowledge_rag.models import (
    ChatRequest,
    ChatResult,
    RefusalReason,
    RetrievalEvidence,
    UserContext,
)
from enterprise_knowledge_rag.refusal import build_refusal
from enterprise_knowledge_rag.retrieval import (
    RetrievalResult,
    RetrievalService,
    RetrievalStatus,
    RetrievalStrategy,
)
from enterprise_knowledge_rag.tracing import StageTimer, TraceEvent


class DomainClassifier(Protocol):
    def is_in_scope(self, question: str) -> bool: ...


class QueryRewriter(Protocol):
    def rewrite(
        self,
        question: str,
        history: Sequence[dict[str, str]],
    ) -> str: ...


class WorkflowState(TypedDict):
    request: ChatRequest
    user: UserContext
    history: list[dict[str, str]]
    as_of: datetime
    in_scope: bool
    rewritten_query: str
    retrieval: RetrievalResult | None
    evidence: list[RetrievalEvidence]
    grounded: GroundedAnswer | None
    result: ChatResult | None
    trace: list[TraceEvent]


@dataclass(frozen=True, slots=True)
class WorkflowDependencies:
    domain: DomainClassifier
    rewriter: QueryRewriter
    retrieval: RetrievalService
    generator: AnswerGenerator
    min_reranker_score: float = 0.0
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    result: ChatResult
    trace: tuple[TraceEvent, ...]
    in_scope: bool = False
    retrieval_candidates: tuple = ()
    model_calls: int = 0


def build_workflow(dependencies: WorkflowDependencies):
    def domain_node(state: WorkflowState) -> dict:
        timer = StageTimer("domain")
        in_scope = dependencies.domain.is_in_scope(state["request"].question)
        return {
            "in_scope": in_scope,
            "trace": [*state["trace"], timer.event("success")],
        }

    def reject_out_of_scope(state: WorkflowState) -> dict:
        timer = StageTimer("refusal")
        return {
            "result": build_refusal(RefusalReason.OUT_OF_SCOPE),
            "trace": [*state["trace"], timer.event("refused")],
        }

    def rewrite_node(state: WorkflowState) -> dict:
        timer = StageTimer("rewrite")
        rewritten = dependencies.rewriter.rewrite(
            state["request"].question,
            state["history"],
        )
        return {
            "rewritten_query": rewritten,
            "trace": [*state["trace"], timer.event("success")],
        }

    def retrieve_node(state: WorkflowState) -> dict:
        timer = StageTimer("retrieve")
        retrieval = dependencies.retrieval.retrieve(
            state["rewritten_query"],
            user=state["user"],
            as_of=state["as_of"],
            strategy=dependencies.retrieval_strategy,
        )
        return {
            "retrieval": retrieval,
            "trace": [
                *state["trace"],
                timer.event(
                    retrieval.status.value,
                    candidate_count=len(retrieval.candidates),
                ),
            ],
        }

    def reject_retrieval(state: WorkflowState) -> dict:
        timer = StageTimer("refusal")
        retrieval = state["retrieval"]
        if retrieval.status is RetrievalStatus.VERSION_AMBIGUOUS:
            reason = RefusalReason.VERSION_AMBIGUOUS
        elif retrieval.status is RetrievalStatus.PERMISSION_DENIED:
            reason = RefusalReason.PERMISSION_DENIED
        else:
            reason = RefusalReason.INSUFFICIENT_EVIDENCE
        return {
            "result": build_refusal(reason),
            "trace": [*state["trace"], timer.event("refused")],
        }

    def evidence_node(state: WorkflowState) -> dict:
        timer = StageTimer("evidence")
        evidence = build_minimal_evidence(
            state["retrieval"].candidates,
            min_reranker_score=dependencies.min_reranker_score,
        )
        return {
            "evidence": evidence,
            "trace": [
                *state["trace"],
                timer.event(
                    "success" if evidence else "insufficient",
                    evidence_count=len(evidence),
                ),
            ],
        }

    def reject_empty_evidence(state: WorkflowState) -> dict:
        timer = StageTimer("refusal")
        return {
            "result": build_refusal(RefusalReason.INSUFFICIENT_EVIDENCE),
            "trace": [*state["trace"], timer.event("refused")],
        }

    def generate_node(state: WorkflowState) -> dict:
        timer = StageTimer("generate")
        grounded = generate_validated_answer(
            dependencies.generator,
            question=state["request"].question,
            evidence=state["evidence"],
            history=state["history"],
        )
        return {
            "grounded": grounded,
            "trace": [*state["trace"], timer.event(grounded.status)],
        }

    def finalize_node(state: WorkflowState) -> dict:
        timer = StageTimer("finalize")
        grounded = state["grounded"]
        result = ChatResult(
            status=grounded.status,
            answer=grounded.answer,
            citations=list(grounded.citations),
            evidence=state["evidence"],
            degradation_reason=grounded.degradation_reason,
        )
        return {
            "result": result,
            "trace": [*state["trace"], timer.event("success")],
        }

    graph = StateGraph(WorkflowState)
    graph.add_node("domain", domain_node)
    graph.add_node("reject_out_of_scope", reject_out_of_scope)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("reject_retrieval", reject_retrieval)
    graph.add_node("evidence", evidence_node)
    graph.add_node("reject_empty_evidence", reject_empty_evidence)
    graph.add_node("generate", generate_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "domain")
    graph.add_conditional_edges(
        "domain",
        lambda state: "rewrite" if state["in_scope"] else "reject_out_of_scope",
    )
    graph.add_edge("reject_out_of_scope", END)
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        lambda state: (
            "evidence"
            if state["retrieval"].status is RetrievalStatus.READY
            else "reject_retrieval"
        ),
    )
    graph.add_edge("reject_retrieval", END)
    graph.add_conditional_edges(
        "evidence",
        lambda state: "generate" if state["evidence"] else "reject_empty_evidence",
    )
    graph.add_edge("reject_empty_evidence", END)
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_chat(
    graph,
    request: ChatRequest,
    user: UserContext,
    *,
    as_of: datetime,
    history: Sequence[dict[str, str]] | None = None,
) -> WorkflowRun:
    initial: WorkflowState = {
        "request": request,
        "user": user,
        "history": list(history or []),
        "as_of": as_of,
        "in_scope": False,
        "rewritten_query": request.question,
        "retrieval": None,
        "evidence": [],
        "grounded": None,
        "result": None,
        "trace": [],
    }
    final = graph.invoke(initial)
    retrieval = final.get("retrieval")
    grounded = final.get("grounded")
    return WorkflowRun(
        result=final["result"],
        trace=tuple(final["trace"]),
        in_scope=final["in_scope"],
        retrieval_candidates=(
            tuple(retrieval.candidates) if retrieval is not None else ()
        ),
        model_calls=grounded.retry_count + 1 if grounded is not None else 0,
    )
