from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from enterprise_knowledge_rag.models import RefusalReason, StrictModel, UserContext


class EvaluationSplit(StrEnum):
    DEVELOPMENT = "development"
    FROZEN_HOLDOUT = "frozen_holdout"


class ExpectedOutcome(StrEnum):
    ANSWER = "answer"
    REFUSAL = "refusal"


class EvaluationStrategy(StrEnum):
    VECTOR_BASELINE = "vector_baseline"
    HYBRID_RRF = "hybrid_rrf"
    HYBRID_RRF_RERANKER = "hybrid_rrf_reranker"


class ObservedEvidence(StrictModel):
    evidence_key: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EvaluationCase(StrictModel):
    case_id: str = Field(min_length=1)
    split: EvaluationSplit
    question: str = Field(min_length=1)
    as_of: datetime
    user: UserContext
    expected_in_scope: bool
    expected_outcome: ExpectedOutcome
    expected_refusal_reason: RefusalReason | None = None
    gold_evidence_keys: set[str] = Field(default_factory=set)
    expected_versions: dict[str, str] = Field(default_factory=dict)
    forbidden_document_ids: set[str] = Field(default_factory=set)
    required_answer_facts: list[str] = Field(default_factory=list)
    required_need_ids: set[str] = Field(default_factory=set)
    expected_retrieval_hops: int = Field(default=1, ge=1, le=2)
    tags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_expected_outcome(self) -> "EvaluationCase":
        if self.expected_outcome is ExpectedOutcome.REFUSAL:
            if self.expected_refusal_reason is None:
                raise ValueError("refusal cases require expected_refusal_reason")
        elif self.expected_refusal_reason is not None:
            raise ValueError("answer cases cannot define expected_refusal_reason")
        return self


class EvaluationDataset(StrictModel):
    dataset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    split: EvaluationSplit
    frozen_at: datetime | None = None
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> "EvaluationDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        if any(case.split is not self.split for case in self.cases):
            raise ValueError("all cases must match the dataset split")
        if self.split is EvaluationSplit.FROZEN_HOLDOUT and self.frozen_at is None:
            raise ValueError("frozen holdout requires frozen_at")
        if self.split is EvaluationSplit.DEVELOPMENT and self.frozen_at is not None:
            raise ValueError("development dataset cannot define frozen_at")
        return self


class EvaluationObservation(StrictModel):
    in_scope: bool
    retrieved: list[ObservedEvidence] = Field(default_factory=list)
    citations: set[str] = Field(default_factory=set)
    status: str = Field(min_length=1)
    refusal_reason: RefusalReason | None = None
    answer: str = ""
    latency_ms: float = Field(ge=0.0)
    model_calls: int = Field(ge=0)
    routed_document_keys: list[str] = Field(default_factory=list)
    retrieval_hops: int = Field(default=0, ge=0, le=2)
    required_need_ids: set[str] = Field(default_factory=set)
    covered_need_ids: set[str] = Field(default_factory=set)
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    stage_error_code: str | None = None


class ExperimentMetadata(StrictModel):
    code_commit: str = Field(min_length=7)
    embedding_model: str = Field(min_length=1)
    reranker_model: str | None = None
    llm_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    temperature: float
    repetition: int = Field(ge=1)
    environment: str = Field(min_length=1)


class RankingMetrics(StrictModel):
    recall_at_k: float = Field(ge=0.0, le=1.0)
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)


class CaseMetrics(StrictModel):
    domain_accuracy: float = Field(ge=0.0, le=1.0)
    ranking: RankingMetrics | None = None
    access_leakage: float = Field(ge=0.0, le=1.0)
    version_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    correct_refusal: float | None = Field(default=None, ge=0.0, le=1.0)
    false_refusal: float = Field(ge=0.0, le=1.0)
    automated_answer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    document_route_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_need_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    need_coverage_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    second_hop_trigger_accuracy: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    second_hop_success: float | None = Field(default=None, ge=0.0, le=1.0)
    irrelevant_evidence_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    core_pass: bool


class CaseEvaluation(StrictModel):
    case_id: str = Field(min_length=1)
    observation: EvaluationObservation | None = None
    metrics: CaseMetrics | None = None
    error_type: str | None = None
    error_code: str | None = None


class AggregateMetrics(StrictModel):
    case_count: int = Field(ge=1)
    execution_success_rate: float = Field(ge=0.0, le=1.0)
    core_pass_rate: float = Field(ge=0.0, le=1.0)
    domain_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    reciprocal_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    access_leakage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    version_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    correct_refusal_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    false_refusal_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    automated_answer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    document_route_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_need_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    need_coverage_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    second_hop_trigger_accuracy: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    second_hop_success: float | None = Field(default=None, ge=0.0, le=1.0)
    irrelevant_evidence_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    p50_latency_ms: float | None = Field(default=None, ge=0.0)
    p95_latency_ms: float | None = Field(default=None, ge=0.0)
    p99_latency_ms: float | None = Field(default=None, ge=0.0)
    refusal_reason_confusion: dict[str, int] = Field(default_factory=dict)
    total_model_calls: int = Field(ge=0)


class EvaluationReport(StrictModel):
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    split: EvaluationSplit
    strategy: EvaluationStrategy
    corpus_snapshot: str = Field(min_length=1)
    ranking_k: int = Field(ge=1)
    experiment: ExperimentMetadata
    started_at: datetime
    completed_at: datetime
    holdout_consumed_at: datetime | None = None
    metrics: AggregateMetrics
    cases: list[CaseEvaluation]
