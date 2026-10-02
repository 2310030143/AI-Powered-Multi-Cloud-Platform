"""Embedding orchestration: embed a document's chunks and store the vectors
in Qdrant. Used by the processing pipeline (automatic stage) and the
POST /documents/{id}/embed endpoint (manual / backfill / retry)."""
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import Document, DocumentChunk, User
from app.services.embeddings.base import EmbeddingError, EmbeddingProvider
from app.services.embeddings.jina import JinaEmbeddingService
from app.services.vector_store.qdrant_store import QdrantVectorStore
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def get_embedding_provider() -> EmbeddingProvider:
    """DI point: swap the real Jina provider for a fake in tests."""
    return JinaEmbeddingService()


def embedding_available() -> bool:
    """True when embeddings are configured (Jina API key present)."""
    return bool(settings.JINA_API_KEY)


def embed_document_chunks(db: Session, document: Document) -> dict:
    """Embed all of a document's chunks via Jina and upsert them into Qdrant.

    - Point IDs are the chunk UUIDs (mirrored into DocumentChunk.embedding_id)
    - Existing points for the document are deleted first → safe to retry,
      never leaves duplicate vectors
    - Payloads carry metadata only (chunk text stays in PostgreSQL)
    - Sets document.embedding_completed = True on success
    """
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    if not chunks:
        raise EmbeddingError(
            "Document has no chunks — process it first (POST /api/v1/documents/{id}/process)"
        )

    user = db.get(User, document.user_id)
    if user is None:
        raise EmbeddingError("Document owner no longer exists")

    provider = get_embedding_provider()
    store = QdrantVectorStore.from_settings()
    store.ensure_collection()

    vectors = provider.embed_texts([chunk.content for chunk in chunks])
    if len(vectors) != len(chunks):
        raise EmbeddingError(
            f"Embedding provider returned {len(vectors)} vectors for {len(chunks)} chunks"
        )

    store.delete_document_points(document.id)
    stored = store.upsert_document_chunks(document, user, chunks, vectors)

    for chunk in chunks:
        chunk.embedding_id = str(chunk.id)
    document.embedding_completed = True
    db.commit()

    logger.info("Embedded %d chunks for document %s (model=%s)", stored, document.id, provider.model)
    return {"chunks_embedded": stored, "model": provider.model}
