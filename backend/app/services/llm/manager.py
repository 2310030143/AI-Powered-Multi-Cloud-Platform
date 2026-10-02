"""LLM provider resolution (DI point, mirrors embeddings/manager.py)."""
from app.config.settings import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.nvidia import NvidiaProvider

settings = get_settings()


def get_llm_provider() -> LLMProvider:
    """Swap the real NVIDIA provider for a fake in tests."""
    return NvidiaProvider()


def llm_configured() -> bool:
    """True when answer generation is configured (NVIDIA API key present)."""
    return bool(settings.NVIDIA_API_KEY)
