import re
from datetime import UTC, datetime
from pathlib import Path

from enterprise_knowledge_rag.documents import (
    EvidenceKind,
    chunk_document,
    parse_document,
)
from enterprise_knowledge_rag.evaluation.runner import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def normalize(value: str) -> str:
    return "".join(value.split())


def corpus_evidence() -> tuple[dict[str, str], set[tuple[str, str]], set[str]]:
    evidence: dict[str, str] = {}
    versions: set[tuple[str, str]] = set()
    document_ids: set[str] = set()
    indexed_at = datetime(2026, 8, 10, tzinfo=UTC)
    for path in sorted((PROJECT_ROOT / "knowledge").rglob("*.md")):
        if path.name == "README.md":
            continue
        document = parse_document(path, indexed_at=indexed_at)
        versions.add((document.record.document_id, document.record.version))
        document_ids.add(document.record.document_id)
        for chunk in chunk_document(document):
            key = (
                f"{chunk.document_id}@{chunk.document_version}#{chunk.section_path[-1]}"
            )
            evidence[key] = f"{evidence.get(key, '')}\n{chunk.content}".strip()
    return evidence, versions, document_ids


def test_gold_evidence_versions_and_facts_exist_in_corpus() -> None:
    evidence, versions, document_ids = corpus_evidence()
    datasets = [
        load_dataset(PROJECT_ROOT / "evaluation" / "development.json"),
        load_dataset(PROJECT_ROOT / "evaluation" / "frozen_holdout.json"),
    ]

    for dataset in datasets:
        for case in dataset.cases:
            assert case.gold_evidence_keys <= evidence.keys(), case.case_id
            assert {
                (document_id, version)
                for document_id, version in case.expected_versions.items()
            } <= versions, case.case_id
            assert case.forbidden_document_ids <= document_ids, case.case_id
            gold_text = normalize(
                "\n".join(evidence[key] for key in case.gold_evidence_keys)
            )
            for fact in case.required_answer_facts:
                assert normalize(fact) in gold_text, (case.case_id, fact)


def test_development_covers_controlled_hierarchical_scenarios() -> None:
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development.json")
    cases = {case.case_id: case for case in dataset.cases}

    expected = {
        "dev-hr-leave-emergency-two-hop",
        "dev-procurement-supplier-two-hop",
        "dev-finance-deadline-single-hop",
        "dev-hr-missing-exception-refusal",
        "dev-finance-restricted-supplement-no-leak",
    }
    assert expected <= cases.keys()
    assert cases["dev-hr-leave-emergency-two-hop"].expected_retrieval_hops == 2
    assert cases["dev-procurement-supplier-two-hop"].expected_retrieval_hops == 2
    assert cases["dev-finance-deadline-single-hop"].expected_retrieval_hops == 1
    assert cases["dev-hr-missing-exception-refusal"].expected_outcome.value == (
        "refusal"
    )
    assert cases[
        "dev-finance-restricted-supplement-no-leak"
    ].forbidden_document_ids == {"finance-payment-approval"}


def test_development_need_ids_use_server_canonical_vocabulary() -> None:
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development.json")
    allowed = {kind.value for kind in EvidenceKind}

    for case in dataset.cases:
        for need_id in case.required_need_ids:
            base = re.sub(r"_\d+$", "", need_id)
            assert base in allowed, (case.case_id, need_id)


def test_v2_datasets_cover_current_corpus_and_capability_slices() -> None:
    development = load_dataset(PROJECT_ROOT / "evaluation" / "development-v2.json")
    holdout = load_dataset(PROJECT_ROOT / "evaluation" / "frozen-holdout-v2.json")
    _, _, document_ids = corpus_evidence()

    positive_documents = {
        key.split("@", 1)[0]
        for case in development.cases
        if case.expected_outcome.value == "answer"
        for key in case.gold_evidence_keys
    }
    roles = {case.user.role.value for case in development.cases}
    departments = {
        department for case in development.cases for department in case.user.departments
    }

    assert 60 <= len(development.cases) <= 80
    assert positive_documents == document_ids
    assert roles == {"employee", "department_admin", "knowledge_admin"}
    assert {"hr", "finance", "admin", "procurement", "security", "operations"} <= (
        departments
    )
    assert sum(case.expected_retrieval_hops == 2 for case in development.cases) >= 12
    refusal_count = sum(
        case.expected_outcome.value == "refusal" for case in development.cases
    )
    assert refusal_count >= 8
    assert {"cross_language", "paraphrase", "multi_hop", "permission"} <= {
        tag for case in development.cases for tag in case.tags
    }

    assert holdout.split.value == "frozen_holdout"
    assert holdout.frozen_at is not None
    assert 20 <= len(holdout.cases) <= 30
    development_questions = {case.question for case in development.cases}
    assert not development_questions & {case.question for case in holdout.cases}
