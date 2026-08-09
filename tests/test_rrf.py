from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.retrieval import reciprocal_rank_fusion


def candidates():
    return {
        name: make_candidate(
            f"{name}:1",
            title=f"{name}制度",
            content=f"{name}办理规则",
        )
        for name in ("a", "b", "c")
    }


def test_candidate_present_in_both_channels_ranks_first() -> None:
    items = candidates()
    results = reciprocal_rank_fusion(
        {
            "bm25": [items["a"], items["b"]],
            "vector": [items["b"], items["c"]],
        },
        k=60,
    )
    assert results[0].chunk.chunk_id == "b:1"
    assert results[0].channels == {"bm25", "vector"}
    assert results[0].channel_ranks == {"bm25": 2, "vector": 1}


def test_duplicate_in_one_channel_only_counts_once() -> None:
    items = candidates()
    results = reciprocal_rank_fusion(
        {"bm25": [items["a"], items["a"], items["b"]]},
        k=10,
    )
    assert [result.chunk.chunk_id for result in results] == ["a:1", "b:1"]
    assert results[0].retrieval_score == 1 / 11


def test_limit_is_applied_after_fusion() -> None:
    items = candidates()
    results = reciprocal_rank_fusion(
        {"bm25": list(items.values())},
        limit=2,
    )
    assert len(results) == 2
