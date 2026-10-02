"""Provider-neutral embedding interface.

The platform talks to embeddings through this abstraction so the provider can
be swapped (Jina today, anything else later) without touching the pipeline,
vector store or API layers.
"""
from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Raised when embeddings cannot be generated (config, API or data errors)."""


class EmbeddingProvider(ABC):
    """Embedding provider contract.

    Implementations MUST distinguish the two retrieval tasks where the
    underlying model supports it:

    - ``embed_texts`` → document *passages* (task: retrieval.passage)
    - ``embed_query`` → search *queries*    (task: retrieval.query)
    """

    model: str

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts, preserving input order."""
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query (retrieval-oriented task)."""
        raise NotImplementedError
