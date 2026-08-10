import json
import os
from collections.abc import Sequence
from pathlib import Path

from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.evaluation import (
    EvaluationCase,
    EvaluationStrategy,
    WorkflowEvaluationExecutor,
    load_dataset,
)

try:
    from scripts.evaluation_support import build_live_services, corpus_snapshot
except ModuleNotFoundError:
    from evaluation_support import build_live_services, corpus_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_ID = "dev-hr-leave-emergency-two-hop"


def select_case(
    cases: Sequence[EvaluationCase],
    case_id: str,
) -> EvaluationCase:
    matches = [case for case in cases if case.case_id == case_id]
    if len(matches) != 1:
        raise LookupError(f"expected exactly one development case for {case_id!r}")
    return matches[0]


def main() -> int:
    case_id = os.getenv("EVAL_CASE_ID", DEFAULT_CASE_ID).strip()
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development.json")
    case = select_case(dataset.cases, case_id)

    settings = get_settings()
    strategy = EvaluationStrategy(settings.retrieval_strategy)
    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        services = build_live_services(settings, pool.connection)
        service = services[strategy]
        if not service.ready():
            raise RuntimeError("knowledge database is not ready for evaluation")
        observation = WorkflowEvaluationExecutor({strategy: service}).run(
            case,
            strategy=strategy,
            corpus_snapshot=corpus_snapshot(PROJECT_ROOT),
        )
    finally:
        pool.close()

    print(
        json.dumps(
            {
                "case_id": case.case_id,
                "strategy": strategy.value,
                "status": observation.status,
                "hop_count": observation.retrieval_hops,
                "required_need_ids": sorted(observation.required_need_ids),
                "covered_need_ids": sorted(observation.covered_need_ids),
                "citations": sorted(observation.citations),
                "routed_document_keys": observation.routed_document_keys,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
