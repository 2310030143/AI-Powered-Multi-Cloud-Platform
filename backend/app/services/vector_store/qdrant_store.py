"""Qdrant vector store: collection management, upserts, similarity search
with metadata filtering, and per-document cleanup.

Works with:
- Local Qdrant server / Docker  → QDRANT_URL=http://localhost:6333
- Qdrant Cloud                  → QDRANT_URL=https://<cluster> + QDRANT_API_KEY
- Embedded in-memory mode       → QDRANT_URL=:memory: (tests, no server needed)

Payloads carry *metadata only* (chunk text stays in PostgreSQL and is
hydrated on search) and always include user_id — searches are never
cross-tenant.
"""
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.config.settings import get_settings
from app.models.models import Document, DocumentChunk, User
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Payload fields that get an index for fast metadata filtering
_FILTER_INDEXES: list[tuple[str, models.PayloadSchemaType]] = [
    ("user_id", models.PayloadSchemaType.KEYWORD),
    ("document_id", models.PayloadSchemaType.KEYWORD),
    ("source", models.PayloadSchemaType.KEYWORD),
    ("mime_type", models.PayloadSchemaType.KEYWORD),
    ("page_number", models.PayloadSchemaType.INTEGER),
]


class VectorStoreError(Exception):
    """Raised when the vector database cannot be reached or queried."""


class QdrantVectorStore:
    def __init__(self, client: QdrantClient, collection_name: str | None = None):
        self.client = client
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME

    @classmethod
    def from_settings(cls) -> "QdrantVectorStore":
        url = settings.QDRANT_URL
        try:
            if url == ":memory:":
                client = QdrantClient(location=":memory:")
            else:
                client = QdrantClient(url=url, api_key=settings.QDRANT_API_KEY or None, timeout=15)
        except Exception as exc:
            raise VectorStoreError(f"Could not create a Qdrant client for {url}: {exc}") from exc
        return cls(client)

    # ── collection management ─────────────────────────────────────────────

    def ensure_collection(self, dimensions: int | None = None) -> bool:
        """Create the collection (cosine distance, filter indexes) if missing.

        The vector size always follows EMBEDDING_DIMENSIONS — never hardcoded.
        """
        dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        try:
            if self.client.collection_exists(self.collection_name):
                return False
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
            )
            for field, schema in _FILTER_INDEXES:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name, field_name=field, field_schema=schema
                    )
                except Exception as exc:  # index may already exist — not fatal
                    logger.debug("Payload index %s: %s", field, exc)
            logger.info(
                "Created Qdrant collection '%s' (%d dimensions, cosine)",
                self.collection_name, dimensions,
            )
            return True
        except Exception as exc:
            raise VectorStoreError(f"Could not ensure Qdrant collection: {exc}") from exc

    # ── writes ────────────────────────────────────────────────────────────

    def upsert_document_chunks(
        self,
        document: Document,
        user: User,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> int:
        """Store one vector per chunk. Point ID = chunk UUID. Payloads are
        metadata-only (content lives in PostgreSQL)."""
        if len(chunks) != len(vectors):
            raise VectorStoreError(
                f"Chunk/vector count mismatch: {len(chunks)} chunks vs {len(vectors)} vectors"
            )
        points = [
            models.PointStruct(
                id=str(chunk.id),
                vector=vector,
                payload=self.build_payload(document, user, chunk),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        try:
            self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc
        return len(points)

    @staticmethod
    def build_payload(document: Document, user: User, chunk: DocumentChunk) -> dict:
        return {
            "user_id": str(user.id),
            "document_id": str(document.id),
            "chunk_id": str(chunk.id),
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "source": document.provider.value if document.provider else None,
            "file_name": document.file_name,
            "mime_type": document.mime_type,
        }

    def delete_document_points(self, document_id: UUID | str) -> None:
        """Remove all vectors belonging to a document (reprocessing/retry)."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id", match=models.MatchValue(value=str(document_id))
                            )
                        ]
                    )
                ),
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant delete failed: {exc}") from exc

    # ── search ────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        user_id: UUID | str,
        limit: int = 10,
        document_id: UUID | str | None = None,
        mime_type: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        """Cosine similarity search, always scoped to the owning user, with
        optional metadata filters (document_id, mime_type, source)."""
        conditions = [
            models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id)))
        ]
        if document_id is not None:
            conditions.append(
                models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id)))
            )
        if mime_type is not None:
            conditions.append(
                models.FieldCondition(key="mime_type", match=models.MatchValue(value=mime_type))
            )
        if source is not None:
            conditions.append(
                models.FieldCondition(key="source", match=models.MatchValue(value=str(source)))
            )
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                query_filter=models.Filter(must=conditions),
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc

        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                {
                    "score": point.score,
                    "chunk_id": payload.get("chunk_id"),
                    "chunk_index": payload.get("chunk_index"),
                    "page_number": payload.get("page_number"),
                    "document_id": payload.get("document_id"),
                    "file_name": payload.get("file_name"),
                    "mime_type": payload.get("mime_type"),
                    "source": payload.get("source"),
                }
            )
        return results
