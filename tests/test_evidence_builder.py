from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.evidence import build_minimal_evidence


def scored(candidate, score=0.8):
    return candidate.model_copy(
        update={
            "channels": {"bm25", "vector"},
            "reranker_score": score,
        }
    )


def test_evidence_deduplicates_same_content_hash() -> None:
    first = scored(make_candidate("a:1", title="A制度", content="相同规则"))
    second = scored(make_candidate("a:2", title="A制度", content="相同规则"))
    second.chunk.content_hash = first.chunk.content_hash
    evidence = build_minimal_evidence([first, second])
    assert len(evidence) == 1


def test_evidence_drops_conflicting_version_of_same_document() -> None:
    first = scored(
        make_candidate(
            "leave-v2:1",
            title="请假制度",
            content="两天以内主管审批",
            document_id="leave-policy",
        )
    )
    second = scored(
        make_candidate(
            "leave-v1:1",
            title="请假制度",
            content="一天以内主管审批",
            document_id="leave-policy",
        )
    )
    second.document.version = "0.9"
    second.chunk.document_version = "0.9"
    evidence = build_minimal_evidence([first, second])
    assert [item.version for item in evidence] == ["1.0"]


def test_evidence_requires_reranker_threshold() -> None:
    candidate = scored(
        make_candidate("a:1", title="A制度", content="低相关规则"),
        score=0.2,
    )
    assert build_minimal_evidence([candidate], min_reranker_score=0.5) == []


def test_evidence_respects_item_and_token_budgets() -> None:
    candidates = [
        scored(make_candidate(f"{name}:1", title=name, content=name * 5))
        for name in ("a", "b", "c")
    ]
    evidence = build_minimal_evidence(candidates, max_items=2, max_tokens=10)
    assert len(evidence) <= 2
    assert sum(len(item.quote) for item in evidence) <= 10
