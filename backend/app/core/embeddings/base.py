"""Base abstract class and protocol for vector embedding providers."""

from abc import ABC, abstractmethod
import asyncio
from typing import List


class BaseEmbeddingProvider(ABC):
    """Abstract interface that all vector embedding providers must implement."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The output vector dimension (e.g., 768, 1536)."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the underlying model (e.g., 'models/text-embedding-004')."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embeds a single text string into a normalized float vector."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embeds a batch of text strings into a list of normalized float vectors."""
        pass

    async def aembed_text(self, text: str) -> List[float]:
        """Asynchronously embeds a single text string."""
        return await asyncio.to_thread(self.embed_text, text)

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        """Asynchronously embeds a batch of text strings."""
        return await asyncio.to_thread(self.embed_batch, texts)
