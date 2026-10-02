"""Semantic retrieval for RAG.

Reuses the Phase 4 building blocks — the Jina query embedding
(retrieval.query task), the Qdrant vector store, and PostgreSQL chunk
hydration — without duplicating them. The PostgreSQL chunk content is the
authoritative document text; vector-store payloads are metadata-only.
Retrieval is ALWAYS scoped to the authenticated user.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Document, DocumentChunk, User
from app.services.embeddings.manager import get_embedding_provider
from app.services.vector_store.qdrant_store import QdrantVectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str | None
    file_name: str | None
    page_number: int | None
    score: float
    content: str


def retrieve_chunks(
    db: Session,
    user: User,
    query: str,
    limit: int = 5,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Jina query embedding → Qdrant semantic search → PostgreSQL hydration.

    The Qdrant filter and the hydration query both constrain results to
    ``user.id`` — a user can never retrieve another user's chunks.
    """
    query_vector = get_embedding_provider().embed_query(query)
    store = QdrantVectorStore.from_settings()
    store.ensure_collection()
    hits = store.search(query_vector, user_id=user.id, limit=limit)
    if not hits:
        return []

    # Hydrate the authoritative chunk content from PostgreSQL and re-verify
    # document ownership before using it (defense in depth).
    chunk_ids = [UUID(str(hit["chunk_id"])) for hit in hits if hit.get("chunk_id")]
    rows = (
        db.query(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(DocumentChunk.id.in_(chunk_ids), Document.user_id == user.id)
        .all()
    )
    rows_by_id = {str(row.id): row for row in rows}

    results: list[RetrievedChunk] = []
    for hit in hits:
        if min_score is not None and hit["score"] < min_score:
            continue
        row = rows_by_id.get(str(hit.get("chunk_id")))
        if row is None:  # vector without a live, owned chunk row → skip
            continue
        results.append(
            RetrievedChunk(
                chunk_id=str(row.id),
                document_id=hit.get("document_id"),
                file_name=hit.get("file_name"),
                page_number=hit.get("page_number"),
                score=hit["score"],
                content=row.content,  # authoritative text from PostgreSQL
            )
        )
    return results
