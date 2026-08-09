from typing import Any

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.config import Settings, get_settings
from enterprise_knowledge_rag.documents.indexing import IndexingService
from enterprise_knowledge_rag.documents.repository import KnowledgeRepository
from enterprise_knowledge_rag.generation import AnswerGenerator
from enterprise_knowledge_rag.providers import (
    CrossEncoderRerankerProvider,
    OpenAICompatibleStructuredProvider,
    SentenceTransformerEmbeddingProvider,
)
from enterprise_knowledge_rag.retrieval import (
    Reranker,
    RetrievalService,
    VectorRetriever,
)
from enterprise_knowledge_rag.runtime import (
    EnterpriseDomainClassifier,
    IdentityQueryRewriter,
    RuntimeChatService,
)
from enterprise_knowledge_rag.workflow import WorkflowDependencies, build_workflow


def _default_connection_factory(database_url: str):
    import psycopg

    return lambda: psycopg.connect(database_url)


def _default_chat_client(settings: Settings):
    from openai import OpenAI

    return OpenAI(
        api_key=settings.model_api_key,
        base_url=settings.model_base_url,
    )


def build_runtime_service(
    settings: Settings,
    *,
    connection_factory: Any | None = None,
    chat_client: Any | None = None,
    embeddings: Any | None = None,
    reranker_scores: Any | None = None,
) -> RuntimeChatService:
    connection_factory = connection_factory or _default_connection_factory(
        settings.database_url
    )
    chat_client = chat_client or _default_chat_client(settings)
    embeddings = embeddings or SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        expected_dimension=settings.embedding_dimension,
    )
    reranker_scores = reranker_scores or CrossEncoderRerankerProvider(
        settings.reranker_model
    )
    repository = KnowledgeRepository(
        connection_factory,
        embedding_model=settings.embedding_model,
    )
    retrieval = RetrievalService(
        repository,
        VectorRetriever(repository),
        embeddings,
        Reranker(reranker_scores),
    )
    generator = AnswerGenerator(
        OpenAICompatibleStructuredProvider(
            chat_client,
            model=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
        )
    )
    graph = build_workflow(
        WorkflowDependencies(
            domain=EnterpriseDomainClassifier(),
            rewriter=IdentityQueryRewriter(),
            retrieval=retrieval,
            generator=generator,
            min_reranker_score=settings.reranker_min_score,
        )
    )
    indexing = IndexingService(repository, embeddings, settings)
    return RuntimeChatService(
        graph=graph,
        repository=repository,
        indexing=indexing,
        knowledge_dir=settings.knowledge_dir,
        latest_evaluation_path=settings.latest_evaluation_path,
        history_max_messages=settings.history_max_messages,
    )


def create_runtime_app(settings: Settings | None = None):
    resolved = settings or get_settings()
    return create_app(build_runtime_service(resolved), settings=resolved)
