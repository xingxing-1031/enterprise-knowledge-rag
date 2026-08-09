from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.retrieval import LexicalRetriever, tokenize


def test_tokenize_keeps_policy_terms_and_numbers() -> None:
    tokens = tokenize("付款申请超过100000元需要谁审批")
    assert "付款" in tokens
    assert "100000" in tokens


def test_exact_policy_name_ranks_first() -> None:
    candidates = [
        make_candidate(
            "leave:1",
            title="员工请假管理制度",
            content="员工请假需要提前提交申请。",
        ),
        make_candidate(
            "expense:1",
            title="差旅与费用报销管理制度",
            content="出差结束后提交报销申请。",
        ),
    ]
    results = LexicalRetriever(candidates).search("差旅费用报销制度", limit=2)
    assert results[0].chunk.chunk_id == "expense:1"
    assert results[0].channel_ranks == {"bm25": 1}


def test_empty_corpus_returns_no_results() -> None:
    assert LexicalRetriever([]).search("请假") == []
