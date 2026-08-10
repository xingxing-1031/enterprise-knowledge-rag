import json

from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.database import create_connection_pool
from enterprise_knowledge_rag.documents.repository import KnowledgeRepository
from scripts.index_knowledge import build_embedding_provider


def main() -> int:
    settings = get_settings()
    pool = create_connection_pool(settings)
    pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
    try:
        repository = KnowledgeRepository(
            pool.connection,
            embedding_model=settings.embedding_model,
        )
        documents = repository.list_documents()
        document_keys = frozenset(
            (document.document_id, document.version) for document in documents
        )
        query_vector = build_embedding_provider(settings).embed_query("报销期限")
        routes = repository.search_documents(
            query_vector,
            document_keys=document_keys,
            limit=settings.document_route_limit,
        )
        route_keys = frozenset((item.document_id, item.version) for item in routes)
        candidates = repository.search_authorized(
            query_vector,
            document_keys=route_keys or document_keys,
            limit=3,
        )
        if not repository.ready() or not routes or not candidates:
            raise RuntimeError("indexed pgvector retrieval smoke failed")
        result = {
            "status": "passed",
            "document_count": len(documents),
            "route_count": len(routes),
            "candidate_count": len(candidates),
            "top_chunk_id": candidates[0].chunk.chunk_id,
        }
    finally:
        pool.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
