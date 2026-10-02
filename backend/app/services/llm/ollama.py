"""Local Ollama LLM client (optional fallback provider).

Endpoint: POST {OLLAMA_BASE_URL}/api/chat
Auth:     none (local service)

Uses the project's existing httpx client — no SDK dependency. The provider is
strictly optional: with no OLLAMA_MODEL configured it fails fast with ZERO
HTTP requests. It never downloads models (no /api/pull, no shell-outs, no
auto-start) — models are the user's responsibility (`ollama pull <model>`).

Construction is side-effect free: no network I/O happens until
generate_answer() is called.
"""
import httpx

from app.config.settings import get_settings
from app.services.llm.base import LLMError, LLMProvider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

_MAX_OUTPUT_TOKENS = 1024


class OllamaProvider(LLMProvider):
    """Calls a local Ollama server's chat API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model if model is not None else settings.OLLAMA_MODEL
        self.timeout_seconds = timeout_seconds or settings.OLLAMA_TIMEOUT_SECONDS
        # An injected client (tests / alternative transports) bypasses the
        # local-server requirement — no real request is made without one.
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    def generate_answer(self, system_prompt: str, user_message: str) -> str:
        if not self.model:
            # Fail fast — no HTTP request, no download attempt, no shell-out.
            raise LLMError(
                "OLLAMA_MODEL is not configured on this server — the local Ollama "
                "fallback is disabled"
            )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": _MAX_OUTPUT_TOKENS},
        }
        try:
            response = self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:  # timeouts, connection refused, ...
            raise LLMError(f"Ollama API request failed: {exc}") from exc

        if response.status_code != 200:
            # e.g. 404 when the configured model is not present locally —
            # we never auto-download; the user must `ollama pull` themselves.
            raise LLMError(
                f"Ollama API returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMError("Ollama API returned a non-JSON response") from exc

        message = body.get("message") if isinstance(body, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Ollama response contained no answer content")

        answer = content.strip()
        logger.debug("Ollama generated an answer (%d chars, model=%s)", len(answer), self.model)
        return answer
