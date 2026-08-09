from enterprise_knowledge_rag.tracing import StageTimer


def test_trace_contains_safe_counts_but_no_content_field() -> None:
    event = StageTimer("retrieve").event(
        "ready",
        candidate_count=5,
        evidence_count=2,
    )
    payload = event.model_dump()
    assert payload["candidate_count"] == 5
    assert payload["evidence_count"] == 2
    assert "content" not in payload
    assert "prompt" not in payload
