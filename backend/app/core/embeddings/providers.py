"""Concrete vector embedding provider implementations."""

import hashlib
import logging
import re
from typing import List, Optional
import numpy as np

from app.core.embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger("aegis.embeddings")


class DeterministicMockProvider(BaseEmbeddingProvider):
    """Deterministic, zero-dependency unit-vector generator for offline tests and CI.
    
    Generates word-level hashed Gaussian projections normalized to unit Euclidean length.
    Preserves basic cosine similarity properties: texts sharing words will have higher
    similarity than unrelated texts.
    """

    def __init__(self, dimension: int = 768, model_name: str = "mock/deterministic-768"):
        self._dimension = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _word_to_vector(self, word: str) -> np.ndarray:
        """Deterministically maps a single token to a pseudo-random Gaussian vector."""
        seed = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        vec = rng.randn(self._dimension).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def embed_text(self, text: str) -> List[float]:
        """Embeds text into a 768-dim unit-normalized vector."""
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            vec = np.zeros(self._dimension, dtype=np.float32)
            vec[0] = 1.0
            return vec.tolist()

        vec_sum = np.zeros(self._dimension, dtype=np.float32)
        for token in tokens:
            vec_sum += self._word_to_vector(token)

        norm = np.linalg.norm(vec_sum)
        final_vec = (vec_sum / norm) if norm > 0 else vec_sum
        return final_vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Google Gemini vector embedding provider via LangChain."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "models/text-embedding-004",
        dimension: int = 768,
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._dimension = dimension
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from langchain_google_genai import GoogleGenAIEmbeddings
                self._client = GoogleGenAIEmbeddings(
                    model=self._model_name,
                    google_api_key=self._api_key,
                )
            except Exception as e:
                logger.error(f"Failed to initialize GoogleGenAIEmbeddings: {e}")
                raise
        return self._client

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        return client.embed_query(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        return client.embed_documents(texts)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI vector embedding provider via LangChain."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        dimension: int = 768,
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._dimension = dimension
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from langchain_openai import OpenAIEmbeddings
                self._client = OpenAIEmbeddings(
                    model=self._model_name,
                    openai_api_key=self._api_key,
                    dimensions=self._dimension,
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAIEmbeddings: {e}")
                raise
        return self._client

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        return client.embed_query(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        return client.embed_documents(texts)


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Local Ollama REST API embedding provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "nomic-embed-text",
        dimension: int = 768,
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_text(self, text: str) -> List[float]:
        import httpx
        url = f"{self._base_url}/api/embeddings"
        payload = {"model": self._model_name, "prompt": text}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding", [])
            return embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]
