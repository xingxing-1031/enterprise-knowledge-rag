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
    HierarchicalRetrievalResult,
    HierarchicalRetrievalService,
    PlannedRetrieval,
    RetrievalPlanner,
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
    planned_retrieval: PlannedRetrieval | None
    hierarchical_retrieval: HierarchicalRetrievalResult | None
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
    planner: RetrievalPlanner | None = None
    hierarchical: HierarchicalRetrievalService | None = None
    min_reranker_score: float = 0.0
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RRF_RERANKER


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    result: ChatResult
    trace: tuple[TraceEvent, ...]
    in_scope: bool = False
    retrieval_candidates: tuple = ()
    model_calls: int = 0
    retrieval_hops: int = 0
    routed_document_keys: tuple[tuple[str, str], ...] = ()
    required_need_ids: tuple[str, ...] = ()
    covered_need_ids: tuple[str, ...] = ()


def build_workflow(dependencies: WorkflowDependencies):
    def domain_node(state: WorkflowState) -> dict:
        timer = StageTimer("domain")
        in_scope = dependencies.domain.is_in_scope(state["rewritten_query"])
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

    def retrieval_plan_node(state: WorkflowState) -> dict:
        timer = StageTimer("retrieval_plan")
        planned = dependencies.planner.plan(
            state["rewritten_query"],
            state["history"],
        )
        return {
            "planned_retrieval": planned,
            "trace": [
                *state["trace"],
                timer.event(
                    planned.status,
                    need_count=len(planned.plan.evidence_needs),
                ),
            ],
        }

    def hierarchical_retrieve_node(state: WorkflowState) -> dict:
        planned = state["planned_retrieval"]
        hierarchical = dependencies.hierarchical.retrieve(
            planned.plan,
            state["user"],
            state["as_of"],
            strategy=dependencies.retrieval_strategy,
        )
        route_timer = StageTimer("document_route")
        section_timer = StageTimer("section_retrieve")
        coverage_timer = StageTimer("evidence_coverage")
        trace = [
            *state["trace"],
            route_timer.event(
                "success" if hierarchical.routes else "empty",
                route_count=len(hierarchical.routes),
            ),
            section_timer.event(
                hierarchical.status.value,
                candidate_count=len(hierarchical.evidence_candidates),
                hop_count=hierarchical.hop_count,
            ),
            coverage_timer.event(
                (
                    "complete"
                    if not hierarchical.coverage.missing_required_need_ids
                    else "incomplete"
                ),
                need_count=len(hierarchical.coverage.covered_need_ids),
            ),
        ]
        if hierarchical.hop_count == 2:
            trace.append(
                StageTimer("supplemental_retrieve").event(
                    hierarchical.status.value,
                    candidate_count=sum(
                        item.retrieval_hop == 2
                        for item in hierarchical.evidence_candidates
                    ),
                    hop_count=2,
                )
            )
        retrieval = RetrievalResult(
            status=hierarchical.status,
            candidates=hierarchical.evidence_candidates,
            authorized_document_keys=frozenset(
                (route.document_id, route.version)
                for route in hierarchical.routes
            ),
        )
        return {
            "hierarchical_retrieval": hierarchical,
            "retrieval": retrieval,
            "trace": trace,
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
            required_need_ids=frozenset(
                need.need_id
                for need in (
                    state["planned_retrieval"].plan.evidence_needs
                    if state["planned_retrieval"] is not None
                    else []
                )
                if need.required
            ),
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
    if dependencies.planner is not None and dependencies.hierarchical is not None:
        graph.add_node("retrieval_plan", retrieval_plan_node)
        graph.add_node("hierarchical_retrieve", hierarchical_retrieve_node)
    graph.add_node("reject_retrieval", reject_retrieval)
    graph.add_node("evidence", evidence_node)
    graph.add_node("reject_empty_evidence", reject_empty_evidence)
    graph.add_node("generate", generate_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "rewrite")
    graph.add_edge("reject_out_of_scope", END)
    if dependencies.planner is not None and dependencies.hierarchical is not None:
        graph.add_edge("rewrite", "domain")
        graph.add_edge("retrieval_plan", "hierarchical_retrieve")
        retrieval_entry = "retrieval_plan"
        retrieval_source = "hierarchical_retrieve"
    else:
        graph.add_edge("rewrite", "domain")
        retrieval_entry = "retrieve"
        retrieval_source = "retrieve"
    graph.add_conditional_edges(
        "domain",
        lambda state: retrieval_entry
        if state["in_scope"]
        else "reject_out_of_scope",
    )
    graph.add_conditional_edges(
        retrieval_source,
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
        "planned_retrieval": None,
        "hierarchical_retrieval": None,
        "evidence": [],
        "grounded": None,
        "result": None,
        "trace": [],
    }
    final = graph.invoke(initial)
    retrieval = final.get("retrieval")
    grounded = final.get("grounded")
    planned = final.get("planned_retrieval")
    hierarchical = final.get("hierarchical_retrieval")
    return WorkflowRun(
        result=final["result"],
        trace=tuple(final["trace"]),
        in_scope=final["in_scope"],
        retrieval_candidates=(
            tuple(retrieval.candidates) if retrieval is not None else ()
        ),
        model_calls=(
            (planned.model_call_count if planned is not None else 0)
            + (grounded.retry_count + 1 if grounded is not None else 0)
        ),
        retrieval_hops=(hierarchical.hop_count if hierarchical is not None else 0),
        routed_document_keys=(
            tuple(
                (route.document_id, route.version)
                for route in hierarchical.routes
            )
            if hierarchical is not None
            else ()
        ),
        required_need_ids=(
            tuple(
                need.need_id
                for need in planned.plan.evidence_needs
                if need.required
            )
            if planned is not None
            else ()
        ),
        covered_need_ids=(
            tuple(sorted(hierarchical.coverage.covered_need_ids))
            if hierarchical is not None
            else ()
        ),
    )
