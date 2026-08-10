from datetime import UTC, datetime
from pathlib import Path

from enterprise_knowledge_rag.documents import chunk_document, parse_document
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
