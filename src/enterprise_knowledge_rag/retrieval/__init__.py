"""Filtered lexical, vector and fused retrieval adapters."""

from .lexical import LexicalRetriever, tokenize
from .reranker import Reranker, RerankerScoreProvider
from .rrf import reciprocal_rank_fusion
from .routing import DocumentRouteCandidate, DocumentRouter
from .service import (
    RetrievalResult,
    RetrievalService,
    RetrievalStatus,
    RetrievalStrategy,
)
from .vector import VectorRetriever, VectorSearchBackend

__all__ = [
    "LexicalRetriever",
    "Reranker",
    "RerankerScoreProvider",
    "RetrievalResult",
    "RetrievalService",
    "RetrievalStatus",
    "RetrievalStrategy",
    "VectorRetriever",
    "VectorSearchBackend",
    "reciprocal_rank_fusion",
    "DocumentRouteCandidate",
    "DocumentRouter",
    "tokenize",
]
