"""Filtered lexical, vector and fused retrieval adapters."""

from .coverage import CoverageResult, EvidenceCoverageService
from .hierarchical import HierarchicalRetrievalResult, HierarchicalRetrievalService
from .lexical import LexicalRetriever, tokenize
from .planning import PlannedRetrieval, RetrievalPlanner
from .reranker import Reranker, RerankerScoreProvider
from .routing import DocumentRouteCandidate, DocumentRouter
from .rrf import reciprocal_rank_fusion
from .service import (
    RetrievalResult,
    RetrievalService,
    RetrievalStatus,
    RetrievalStrategy,
)
from .vector import VectorRetriever, VectorSearchBackend

__all__ = [
    "LexicalRetriever",
    "PlannedRetrieval",
    "Reranker",
    "RerankerScoreProvider",
    "RetrievalResult",
    "RetrievalPlanner",
    "RetrievalService",
    "RetrievalStatus",
    "RetrievalStrategy",
    "VectorRetriever",
    "VectorSearchBackend",
    "reciprocal_rank_fusion",
    "DocumentRouteCandidate",
    "DocumentRouter",
    "CoverageResult",
    "EvidenceCoverageService",
    "HierarchicalRetrievalResult",
    "HierarchicalRetrievalService",
    "tokenize",
]
