"""Jina AI hosted embedding API client.

Endpoint: POST {JINA_API_URL} (default https://api.jina.ai/v1/embeddings)
Auth:     Authorization: Bearer {JINA_API_KEY}

Uses the project's existing httpx HTTP client — no provider SDK dependency.
Document passages use the ``retrieval.passage`` task; search queries use
``retrieval.query`` (jina-embeddings-v3 supports both explicitly).
"""
import httpx

from app.config.settings import get_settings
from app.services.embeddings.base import EmbeddingError, EmbeddingProvider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Jina retrieval-oriented tasks (kept distinct on purpose)
TASK_PASSAGE = "retrieval.passage"
TASK_QUERY = "retrieval.query"

# Jina rejects inputs longer than 8192 tokens; chunks are far below this —
# this guard (~4 chars/token) is a safety net for pathological inputs.
_MAX_CHARS_PER_INPUT = 30_000
_REQUEST_TIMEOUT_SECONDS = 30.0


class JinaEmbeddingService(EmbeddingProvider):
    """Talks to the hosted Jina embeddings API in batches."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key or settings.JINA_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        # An injected client (tests / alternative transports) bypasses the
        # API-key requirement — no real request is made without one.
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            if not self.api_key:
                raise EmbeddingError(
                    "JINA_API_KEY is not configured on this server — "
                    "get a free key at https://jina.ai/ and set it in .env"
                )
            self._client = httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS)
        return self._client

    # ── public API ─────────────────────────────────────────────────────────

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed document passages in batches, preserving input order."""
        if not texts:
            return []
        prepared = [self._prepare(text) for text in texts]
        return self._embed(prepared, task=TASK_PASSAGE)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query with the retrieval.query task."""
        return self._embed([self._prepare(text)], task=TASK_QUERY)[0]

    # ── internals ──────────────────────────────────────────────────────────

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = max(1, self.batch_size)
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(self._embed_batch(batch, task))
        return vectors

    def _embed_batch(self, batch: list[str], task: str) -> list[list[float]]:
        payload = {
            "model": self.model,
            "task": task,
            "dimensions": self.dimensions,
            "input": batch,
        }
        try:
            response = self.client.post(
                settings.JINA_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:  # timeouts, connection failures, ...
            raise EmbeddingError(f"Jina API request failed: {exc}") from exc

        if response.status_code != 200:
            # Never include request headers (the API key) in errors or logs
            raise EmbeddingError(
                f"Jina API returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingError("Jina API returned a non-JSON response") from exc

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(batch):
            raise EmbeddingError(
                f"Malformed Jina API response: expected {len(batch)} embeddings, got "
                f"{len(data) if isinstance(data, list) else type(data).__name__}"
            )

        try:
            ordered = sorted(data, key=lambda item: item["index"])
        except (KeyError, TypeError) as exc:
            raise EmbeddingError("Malformed Jina API response: missing embedding index") from exc

        vectors = []
        for item in ordered:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingError("Malformed Jina API response: missing embedding vector")
            if len(embedding) != self.dimensions:
                raise EmbeddingError(
                    f"Jina API returned {len(embedding)}-dimensional vectors, "
                    f"expected {self.dimensions} (check EMBEDDING_DIMENSIONS)"
                )
            vectors.append([float(value) for value in embedding])

        logger.debug("Jina embeddings: %d texts, task=%s, model=%s", len(batch), task, self.model)
        return vectors

    @staticmethod
    def _prepare(text: str) -> str:
        # The API rejects empty strings; truncate as a safety net
        return (text or " ").strip()[:_MAX_CHARS_PER_INPUT] or " "
