from typing import Any

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.config import Settings, get_settings
from enterprise_knowledge_rag.database import (
    connection_pool_lifespan,
    create_connection_pool,
)
from enterprise_knowledge_rag.documents.import_repository import ImportRepository
from enterprise_knowledge_rag.documents.indexing import IndexingService
from enterprise_knowledge_rag.documents.ingestion import IngestionService
from enterprise_knowledge_rag.documents.repository import KnowledgeRepository
from enterprise_knowledge_rag.general_chat import GeneralChatAgent, SynthesisAgent
from enterprise_knowledge_rag.generation import AnswerGenerator
from enterprise_knowledge_rag.providers import (
    CrossEncoderRerankerProvider,
    NullRerankerProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleStructuredProvider,
    RemoteRerankerProvider,
    SentenceTransformerEmbeddingProvider,
)
from enterprise_knowledge_rag.retail_agent import RetailAgentClient
from enterprise_knowledge_rag.retrieval import (
    DocumentRouter,
    EvidenceCoverageService,
    HierarchicalRetrievalService,
    Reranker,
    RetrievalPlanner,
    RetrievalService,
    RetrievalStrategy,
    VectorRetriever,
)
from enterprise_knowledge_rag.runtime import (
    EnterpriseDomainClassifier,
    IdentityQueryRewriter,
    RuntimeChatService,
)
from enterprise_knowledge_rag.supervisor import Supervisor
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


def _default_embedding_client(settings: Settings):
    from openai import OpenAI

    return OpenAI(
        api_key=settings.embedding_api_key or settings.model_api_key,
        base_url=settings.embedding_base_url or settings.model_base_url,
    )


def _default_embedding_provider(settings: Settings):
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            _default_embedding_client(settings),
            model=settings.embedding_model,
            expected_dimension=settings.embedding_dimension,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.model_timeout_seconds,
        )
    if settings.embedding_provider == "local":
        return SentenceTransformerEmbeddingProvider(
            settings.embedding_model,
            expected_dimension=settings.embedding_dimension,
        )
    raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")


def _default_reranker_client(settings: Settings):
    from openai import OpenAI

    return OpenAI(
        api_key=settings.reranker_api_key or settings.model_api_key,
        base_url=settings.reranker_base_url or settings.model_base_url,
        timeout=settings.model_timeout_seconds,
    )


def _default_reranker_provider(settings: Settings):
    if settings.reranker_provider == "openai_compatible":
        return RemoteRerankerProvider(
            _default_reranker_client(settings),
            model=settings.reranker_model,
            timeout_seconds=settings.model_timeout_seconds,
        )
    if settings.reranker_provider == "none":
        return NullRerankerProvider()
    if settings.reranker_provider == "local":
        return CrossEncoderRerankerProvider(settings.reranker_model)
    raise ValueError(f"unsupported reranker provider: {settings.reranker_provider}")


def _resolve_retrieval_strategy(
    settings: Settings,
    override: RetrievalStrategy | None,
) -> RetrievalStrategy:
    return override or RetrievalStrategy(settings.retrieval_strategy)


def build_runtime_service(
    settings: Settings,
    *,
    connection_factory: Any | None = None,
    chat_client: Any | None = None,
    embeddings: Any | None = None,
    reranker_scores: Any | None = None,
    retrieval_strategy: RetrievalStrategy | None = None,
) -> RuntimeChatService:
    resolved_retrieval_strategy = _resolve_retrieval_strategy(
        settings,
        retrieval_strategy,
    )
    connection_factory = connection_factory or _default_connection_factory(
        settings.database_url
    )
    chat_client = chat_client or _default_chat_client(settings)
    embeddings = embeddings or _default_embedding_provider(settings)
    reranker_scores = reranker_scores or _default_reranker_provider(settings)
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
    structured_provider = OpenAICompatibleStructuredProvider(
        chat_client,
        model=settings.model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )
    general_agent = GeneralChatAgent(
        chat_client,
        model=settings.model_name,
        timeout_seconds=settings.model_timeout_seconds,
    )
    retail_agent = None
    if settings.retail_agent_url:
        import httpx

        assert settings.retail_agent_token is not None
        retail_agent = RetailAgentClient(
            settings.retail_agent_url,
            httpx.Client(),
            service_token=settings.retail_agent_token.get_secret_value(),
            timeout_seconds=settings.retail_agent_timeout_seconds,
        )
    generator = AnswerGenerator(structured_provider)
    planner = RetrievalPlanner(structured_provider)
    hierarchical = HierarchicalRetrievalService(
        corpus=repository,
        router=DocumentRouter(repository, embeddings),
        section_retrieval=retrieval,
        coverage=EvidenceCoverageService(
            min_reranker_score=settings.reranker_min_score
        ),
        route_limit=settings.document_route_limit,
        evidence_max_items=settings.evidence_max_items,
        evidence_max_tokens=settings.evidence_max_tokens,
    )
    graph = build_workflow(
        WorkflowDependencies(
            domain=EnterpriseDomainClassifier(),
            rewriter=IdentityQueryRewriter(),
            retrieval=retrieval,
            generator=generator,
            planner=planner,
            hierarchical=hierarchical,
            min_reranker_score=settings.reranker_min_score,
            retrieval_strategy=resolved_retrieval_strategy,
        )
    )
    indexing = IndexingService(repository, embeddings, settings)
    ingestion = IngestionService(
        repository=ImportRepository(connection_factory),
        indexing=indexing,
        upload_dir=settings.upload_storage_dir,
        knowledge_dir=settings.knowledge_dir,
    )
    return RuntimeChatService(
        graph=graph,
        repository=repository,
        indexing=indexing,
        ingestion=ingestion,
        knowledge_dir=settings.knowledge_dir,
        latest_evaluation_path=settings.latest_evaluation_path,
        history_max_messages=settings.history_max_messages,
        supervisor=Supervisor(structured_provider),
        general_agent=general_agent,
        retail_agent=retail_agent,
        synthesis_agent=SynthesisAgent(general_agent),
    )


def create_runtime_app(settings: Settings | None = None):
    resolved = settings or get_settings()
    pool = create_connection_pool(resolved)
    service = build_runtime_service(
        resolved,
        connection_factory=pool.connection,
    )
    return create_app(
        service,
        settings=resolved,
        lifespan=connection_pool_lifespan(
            pool,
            timeout_seconds=resolved.database_pool_timeout_seconds,
        ),
        static_dir=resolved.frontend_dist_dir,
    )
