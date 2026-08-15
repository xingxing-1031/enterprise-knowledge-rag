from enterprise_knowledge_rag.documents.repository import ParentDocumentMatch
from enterprise_knowledge_rag.models import DocumentType
from enterprise_knowledge_rag.retrieval.routing import DocumentRouter


class FakeRouteRepository:
    def __init__(self, sources, vector_matches):
        self.sources = sources
        self.vector_matches = vector_matches
        self.received_keys = None
        self.vector_received_keys = None

    def list_document_route_sources(self, document_keys):
        self.received_keys = document_keys
        return self.sources

    def search_documents(self, query_vector, *, document_keys, limit):
        self.vector_received_keys = document_keys
        return self.vector_matches[:limit]


class FakeQueryEmbeddings:
    def __init__(self):
        self.calls = []

    def embed_query(self, query):
        self.calls.append(query)
        return [0.1, 0.2]


def source(document_id, version, title, search_text):
    return {
        "document_id": document_id,
        "version": version,
        "title": title,
        "document_type": DocumentType.POLICY,
        "department": "hr",
        "document_search_text": search_text,
    }


def vector_match(document_id, version, title, similarity):
    return ParentDocumentMatch(
        document_id=document_id,
        version=version,
        title=title,
        document_type=DocumentType.POLICY,
        department="hr",
        similarity=similarity,
    )


def test_router_never_returns_document_outside_authorized_keys() -> None:
    repository = FakeRouteRepository(
        [
            source("hr-leave-policy", "2.0", "请假制度", "请假制度\n病假\n材料"),
            source("finance-payment", "1.0", "付款制度", "付款制度\n付款\n审批"),
        ],
        [
            vector_match("finance-payment", "1.0", "付款制度", 0.99),
            vector_match("hr-leave-policy", "2.0", "请假制度", 0.88),
        ],
    )
    embeddings = FakeQueryEmbeddings()
    router = DocumentRouter(repository, embeddings)

    routes = router.route(
        "病假需要什么材料",
        document_keys=frozenset({("hr-leave-policy", "2.0")}),
        limit=4,
    )

    assert {(item.document_id, item.version) for item in routes} == {
        ("hr-leave-policy", "2.0")
    }
    assert repository.received_keys == frozenset({("hr-leave-policy", "2.0")})
    assert repository.vector_received_keys == frozenset({("hr-leave-policy", "2.0")})


def test_empty_authorized_set_does_no_embedding_or_repository_work() -> None:
    repository = FakeRouteRepository([], [])
    embeddings = FakeQueryEmbeddings()
    router = DocumentRouter(repository, embeddings)

    assert router.route("任意问题", document_keys=frozenset(), limit=4) == ()
    assert repository.received_keys is None
    assert repository.vector_received_keys is None
    assert embeddings.calls == []


def test_router_preserves_lexical_and_vector_channel_metadata() -> None:
    repository = FakeRouteRepository(
        [source("hr-leave-policy", "2.0", "请假制度", "请假制度\n病假\n材料")],
        [vector_match("hr-leave-policy", "2.0", "请假制度", 0.88)],
    )
    router = DocumentRouter(repository, FakeQueryEmbeddings())

    routes = router.route(
        "病假材料",
        document_keys=frozenset({("hr-leave-policy", "2.0")}),
    )

    assert len(routes) == 1
    assert routes[0].channels == {"bm25", "vector"}
    assert routes[0].lexical_rank == 1
    assert routes[0].vector_rank == 1
    assert routes[0].fused_score > 0


def test_router_uses_section_summary_for_fine_grained_asset_question() -> None:
    repository = FakeRouteRepository(
        [
            source(
                "admin-asset-management",
                "1.0",
                "固定资产领用与归还流程",
                "固定资产领用与归还流程\n异常处理\n资产遗失后应在发现后1个工作日内报备",
            ),
            source("hr-leave-policy", "2.0", "员工请假制度", "员工请假制度\n病假"),
        ],
        [],
    )
    router = DocumentRouter(repository, FakeQueryEmbeddings())

    routes = router.route(
        "资产遗失后最迟什么时候报备",
        document_keys=frozenset(
            {("admin-asset-management", "1.0"), ("hr-leave-policy", "2.0")}
        ),
    )

    assert routes[0].document_id == "admin-asset-management"
    assert routes[0].lexical_rank == 1
