from retrieval_fixtures import make_candidate

from enterprise_knowledge_rag.retrieval import VectorRetriever


class FakeBackend:
    def __init__(self):
        self.received_keys = None

    def search_authorized(self, query_vector, *, document_keys, limit):
        self.received_keys = document_keys
        return [
            make_candidate(
                "leave:1",
                title="员工请假管理制度",
                content="员工请假需要提前提交申请。",
            )
        ][:limit]


def test_vector_retriever_forwards_authorized_versions() -> None:
    backend = FakeBackend()
    retriever = VectorRetriever(backend)
    keys = frozenset({("leave-policy", "1.0")})
    results = retriever.search([0.1, 0.2], document_keys=keys, limit=3)
    assert backend.received_keys == keys
    assert results[0].channel_ranks == {"vector": 1}


def test_vector_retriever_does_not_query_without_authorized_keys() -> None:
    backend = FakeBackend()
    results = VectorRetriever(backend).search(
        [0.1, 0.2],
        document_keys=frozenset(),
    )
    assert results == []
    assert backend.received_keys is None
