"""
Abstract base class for RAG text embedders.
"""
from abc import ABC, abstractmethod
from typing import List


class BaseEmbedder(ABC):
    """Abstract embedder interface."""

    def __init__(self, model: str = ""):
        self.model = model

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string into a vector."""
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text documents into vectors."""
        pass
