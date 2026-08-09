import pytest
from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.retrieval import Reranker


class FixedScores:
    def __init__(self, scores):
        self.scores = scores

    def score(self, query, passages):
        return self.scores


def test_reranker_only_reorders_existing_candidates() -> None:
    first = make_candidate("a:1", title="A制度", content="A规则")
    second = make_candidate("b:1", title="B制度", content="B规则")
    results = Reranker(FixedScores([0.1, 0.9])).rerank(
        "B怎么处理",
        [first, second],
    )
    assert [item.chunk.chunk_id for item in results] == ["b:1", "a:1"]
    assert {item.chunk.chunk_id for item in results} == {"a:1", "b:1"}


def test_reranker_rejects_score_count_mismatch() -> None:
    candidate = make_candidate("a:1", title="A制度", content="A规则")
    with pytest.raises(ValueError, match="different number"):
        Reranker(FixedScores([])).rerank("A", [candidate])
