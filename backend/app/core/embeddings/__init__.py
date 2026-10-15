"""Generic, multi-provider vector embedding package for AegisGraph."""

from app.core.embeddings.base import BaseEmbeddingProvider
from app.core.embeddings.factory import (
    EmbeddingProviderFactory,
    CachedEmbeddingService,
    embedding_service,
)
from app.core.embeddings.providers import (
    DeterministicMockProvider,
    GeminiEmbeddingProvider,
    OpenAIEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from app.core.embeddings.reindexer import reindex_tenant_embeddings

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingProviderFactory",
    "CachedEmbeddingService",
    "embedding_service",
    "DeterministicMockProvider",
    "GeminiEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "reindex_tenant_embeddings",
]
