"""Factory and caching service facade for generic vector embeddings."""

from functools import lru_cache
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.embeddings.base import BaseEmbeddingProvider
from app.core.embeddings.providers import (
    DeterministicMockProvider,
    GeminiEmbeddingProvider,
    OpenAIEmbeddingProvider,
    OllamaEmbeddingProvider,
)

logger = logging.getLogger("aegis.embeddings")


class EmbeddingProviderFactory:
    """Instantiates embedding providers based on settings and available API keys."""

    @staticmethod
    def create(provider_name: Optional[str] = None) -> BaseEmbeddingProvider:
        provider = (provider_name or settings.embedding_provider).lower().strip()

        if provider == "gemini":
            if settings.gemini_api_key:
                logger.info(f"Initializing Gemini Embedding Provider ({settings.embedding_model_name})...")
                return GeminiEmbeddingProvider(
                    api_key=settings.gemini_api_key,
                    model_name=settings.embedding_model_name,
                    dimension=settings.embedding_dimension,
                )
            logger.warning("Gemini API key missing. Gracefully falling back to DeterministicMockProvider.")

        elif provider == "openai":
            if settings.openai_api_key:
                logger.info(f"Initializing OpenAI Embedding Provider ({settings.embedding_model_name})...")
                return OpenAIEmbeddingProvider(
                    api_key=settings.openai_api_key,
                    model_name=settings.embedding_model_name,
                    dimension=settings.embedding_dimension,
                )
            logger.warning("OpenAI API key missing. Gracefully falling back to DeterministicMockProvider.")

        elif provider == "ollama":
            logger.info(f"Initializing Ollama Embedding Provider ({settings.ollama_base_url})...")
            return OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url,
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
            )

        logger.info(f"Using DeterministicMockProvider (dimension={settings.embedding_dimension}).")
        return DeterministicMockProvider(
            dimension=settings.embedding_dimension,
            model_name="mock/deterministic-768",
        )


class CachedEmbeddingService:
    """Service facade providing in-memory LRU caching and async wrappers over providers."""

    def __init__(self, provider: Optional[BaseEmbeddingProvider] = None):
        self._provider = provider or EmbeddingProviderFactory.create()
        self._cache = {}
        self._max_cache = settings.embedding_cache_size

    @property
    def provider(self) -> BaseEmbeddingProvider:
        return self._provider

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def get_info(self) -> Dict[str, Any]:
        """Returns metadata about the active provider and cache status."""
        return {
            "provider_type": self._provider.__class__.__name__,
            "model_name": self.model_name,
            "dimension": self.dimension,
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache,
        }

    def set_provider(self, provider: BaseEmbeddingProvider) -> None:
        """Dynamically reassigns the underlying provider and clears the cache."""
        self._provider = provider
        self.clear_cache()

    def clear_cache(self) -> None:
        """Clears the in-memory embedding cache."""
        self._cache.clear()

    def embed_text(self, text: str) -> List[float]:
        """Embeds text, checking the in-memory cache first."""
        if text in self._cache:
            return self._cache[text]

        vec = self._provider.embed_text(text)
        if len(self._cache) < self._max_cache:
            self._cache[text] = vec
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embeds texts, leveraging cached results where available."""
        missing_indices = []
        missing_texts = []
        results = [None] * len(texts)

        for i, t in enumerate(texts):
            if t in self._cache:
                results[i] = self._cache[t]
            else:
                missing_indices.append(i)
                missing_texts.append(t)

        if missing_texts:
            fresh_vectors = self._provider.embed_batch(missing_texts)
            for idx, vec in zip(missing_indices, fresh_vectors):
                results[idx] = vec
                if len(self._cache) < self._max_cache:
                    self._cache[texts[idx]] = vec

        return results

    async def aembed_text(self, text: str) -> List[float]:
        import asyncio
        return await asyncio.to_thread(self.embed_text, text)

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        return await asyncio.to_thread(self.embed_batch, texts)


# Global singleton instance
embedding_service = CachedEmbeddingService()
