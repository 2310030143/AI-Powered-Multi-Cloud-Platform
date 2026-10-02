"""Provider-neutral LLM interface.

The RAG pipeline talks to the LLM through this abstraction so the provider
can be swapped (NVIDIA today, anything else later) without touching the
retrieval, context-building or API layers. Provider-specific HTTP logic
lives only in the provider implementation.
"""
from abc import ABC, abstractmethod


class LLMError(Exception):
    """Raised when answer generation fails (config, API or response errors)."""


class LLMProvider(ABC):
    model: str

    @abstractmethod
    def generate_answer(self, system_prompt: str, user_message: str) -> str:
        """Generate a final answer for the user message under the system prompt."""
        raise NotImplementedError
