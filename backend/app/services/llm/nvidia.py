"""NVIDIA hosted LLM client (RAG answer generation).

Endpoint: POST https://integrate.api.nvidia.com/v1/chat/completions
Auth:     Authorization: Bearer {NVIDIA_API_KEY}

OpenAI-compatible chat-completions format via the project's existing httpx
client — no SDK dependency. The reasoning/thinking mode is disabled
(``chat_template_kwargs.enable_thinking=false``) because the RAG application
only needs the final answer.
"""
import httpx

from app.config.settings import get_settings
from app.services.llm.base import LLMError, LLMProvider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
_MAX_OUTPUT_TOKENS = 1024


class NvidiaProvider(LLMProvider):
    """Calls the NVIDIA hosted chat-completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key or settings.NVIDIA_API_KEY
        self.model = model or settings.NVIDIA_MODEL
        self.timeout_seconds = timeout_seconds or settings.NVIDIA_TIMEOUT_SECONDS
        # An injected client (tests / alternative transports) bypasses the
        # API-key requirement — no real request is made without one.
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            if not self.api_key:
                raise LLMError(
                    "NVIDIA_API_KEY is not configured on this server — set it in .env "
                    "(build.nvidia.com API key)"
                )
            self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    def generate_answer(self, system_prompt: str, user_message: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "temperature": 0.2,  # small, near-deterministic generation
            "stream": False,
            # Reasoning/thinking disabled — only the final answer is wanted.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = self.client.post(
                _ENDPOINT,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:  # timeouts, connection failures, ...
            raise LLMError(f"NVIDIA API request failed: {exc}") from exc

        if response.status_code != 200:
            # Never include request headers (the API key) in errors or logs
            raise LLMError(
                f"NVIDIA API returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMError("NVIDIA API returned a non-JSON response") from exc

        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise LLMError("Malformed NVIDIA response: no choices returned")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMError("NVIDIA response contained no answer content")

        answer = content.strip()
        logger.debug("NVIDIA generated an answer (%d chars, model=%s)", len(answer), self.model)
        return answer
