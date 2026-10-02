"""LLM provider resolution and centralized fallback (DI point).

Provider order is explicit:
1. NVIDIA (primary, hosted)
2. Ollama (optional, local fallback)

Fallback happens only for provider/runtime/configuration failures — never for
bad user input (non-LLM exceptions propagate untouched). Feature services call
``get_llm_provider()`` and stay unaware of which provider answered
(``last_provider`` reports it).

Construction is side-effect free: providers are created lazily-wired and only
``generate_answer()`` performs network I/O.
"""
from app.config.settings import get_settings
from app.services.llm.base import LLMError, LLMProvider
from app.services.llm.nvidia import NvidiaProvider
from app.services.llm.ollama import OllamaProvider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Explicit fallback order
PROVIDER_ORDER = ("nvidia", "ollama")


class FallbackLLMProvider(LLMProvider):
    """Tries the primary (NVIDIA) provider first, then the Ollama fallback.

    Aggregate errors are sanitized: only the short reason of each failure is
    reported (status line / failure class) — never provider response bodies,
    headers or API keys.
    """

    def __init__(self, primary: LLMProvider | None = None, fallback: LLMProvider | None = None):
        self._primary = primary if primary is not None else NvidiaProvider()
        self._fallback = fallback if fallback is not None else OllamaProvider()
        self.last_provider: str | None = None

    @property
    def model(self) -> str:
        return self._primary.model

    def generate_answer(self, system_prompt: str, user_message: str) -> str:
        attempts: list[str] = []
        for name, provider in (("nvidia", self._primary), ("ollama", self._fallback)):
            try:
                answer = provider.generate_answer(system_prompt, user_message)
                self.last_provider = name
                return answer
            except LLMError as exc:
                # Short, sanitized reason: provider messages carry response
                # bodies after the first ':' — keep only the leading part.
                reason = str(exc).split(":", 1)[0].strip()
                attempts.append(f"{name}: {reason}")
                logger.warning("LLM provider '%s' failed (%s) — trying next provider", name, reason)
        raise LLMError("LLM generation failed — " + "; ".join(attempts))


def get_llm_provider() -> LLMProvider:
    """NVIDIA primary with optional local Ollama fallback (tests patch this)."""
    return FallbackLLMProvider()


def llm_configured() -> bool:
    """True when at least one LLM provider is configured."""
    return bool(settings.NVIDIA_API_KEY or settings.OLLAMA_MODEL)
