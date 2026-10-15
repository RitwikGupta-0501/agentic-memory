"""Unit tests for the generic vector embedding infrastructure."""

import math
import numpy as np
import pytest

from app.core.config import Settings
from app.core.embeddings import (
    BaseEmbeddingProvider,
    DeterministicMockProvider,
    EmbeddingProviderFactory,
    CachedEmbeddingService,
)


def cosine_similarity(v1: list, v2: list) -> float:
    a = np.array(v1)
    b = np.array(v2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_deterministic_mock_provider_properties():
    """Verifies that DeterministicMockProvider implements the base protocol properly."""
    provider = DeterministicMockProvider(dimension=768)
    assert isinstance(provider, BaseEmbeddingProvider)
    assert provider.dimension == 768
    assert provider.model_name == "mock/deterministic-768"


def test_deterministic_mock_vector_normalization_and_repeatability():
    """Verifies that generated vectors are unit length and deterministic."""
    provider = DeterministicMockProvider(dimension=768)
    text = "Deploying payment gateway microservice to FalkorDB"

    vec1 = provider.embed_text(text)
    vec2 = provider.embed_text(text)

    # Dimension and type check
    assert len(vec1) == 768
    assert len(vec2) == 768

    # Exact repeatability
    assert vec1 == vec2

    # Unit norm check: ||v|| ≈ 1.0
    norm = np.linalg.norm(np.array(vec1))
    assert math.isclose(norm, 1.0, rel_tol=1e-5)


def test_deterministic_mock_semantic_similarity_properties():
    """Verifies that texts sharing tokens have higher cosine similarity than unrelated texts."""
    provider = DeterministicMockProvider(dimension=768)

    text_a = "Database migration from PostgreSQL to FalkorDB cluster"
    text_b = "Database migration cutover to FalkorDB real-time graph"
    text_c = "Delicious apple pie recipe with cinnamon and sugar"

    vec_a = provider.embed_text(text_a)
    vec_b = provider.embed_text(text_b)
    vec_c = provider.embed_text(text_c)

    sim_ab = cosine_similarity(vec_a, vec_b)
    sim_ac = cosine_similarity(vec_a, vec_c)

    # Texts A and B share database DevOps concepts; text C is totally disjoint
    assert sim_ab > sim_ac
    assert sim_ab > 0.40


def test_empty_text_embedding():
    """Verifies that empty string or whitespace does not crash the generator."""
    provider = DeterministicMockProvider(dimension=768)
    vec = provider.embed_text("   ")
    assert len(vec) == 768
    assert math.isclose(np.linalg.norm(vec), 1.0, rel_tol=1e-5)


def test_cached_embedding_service():
    """Verifies LRU caching avoids duplicate calculations."""
    mock_provider = DeterministicMockProvider(dimension=768)
    service = CachedEmbeddingService(provider=mock_provider)

    text = "Cache test string for memory verification"
    vec1 = service.embed_text(text)
    assert text in service._cache

    # Second fetch returns cached object
    vec2 = service.embed_text(text)
    assert vec1 is vec2

    # Batch embedding leverages cache
    batch_texts = [text, "New text not in cache"]
    results = service.embed_batch(batch_texts)
    assert len(results) == 2
    assert results[0] is vec1
    assert len(results[1]) == 768


def test_embedding_provider_factory_fallback():
    """Verifies that factory gracefully falls back to mock provider if API keys are missing."""
    # When provider is gemini but api key is empty
    provider = EmbeddingProviderFactory.create(provider_name="gemini")
    assert isinstance(provider, DeterministicMockProvider)
    assert provider.dimension == 768

    # When provider is openai but api key is empty
    provider_oai = EmbeddingProviderFactory.create(provider_name="openai")
    assert isinstance(provider_oai, DeterministicMockProvider)


@pytest.mark.asyncio
async def test_async_embedding_methods():
    """Verifies aembed_text and aembed_batch execute asynchronously."""
    provider = DeterministicMockProvider(dimension=768)
    service = CachedEmbeddingService(provider=provider)

    vec = await service.aembed_text("Async single text embedding")
    assert len(vec) == 768

    batch_vecs = await service.aembed_batch(["Async text 1", "Async text 2"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 768
    assert len(batch_vecs[1]) == 768
