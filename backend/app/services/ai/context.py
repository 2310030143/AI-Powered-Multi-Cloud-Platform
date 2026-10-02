"""Shared helpers for the Phase 6 AI features: owned-document loading,
bounded per-document chunk selection from PostgreSQL, and fair multi-document
assembly. Reuses the Phase 5 context builder for formatting, injection
hardening (<document> wrappers, metadata flattening) and global context limits
(RAG_MAX_CONTEXT_CHUNKS / RAG_MAX_CONTEXT_CHARS).
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import Document, DocumentChunk, User
from app.services.rag.context_builder import build_context
from app.services.rag.retrieval import RetrievedChunk

settings = get_settings()


def load_owned_documents(db: Session, user: User, document_ids: list[UUID]) -> list[Document]:
    """Load documents in request order, enforcing ownership for every ID.

    Non-enumerating: any missing/foreign document ID yields the same 404 —
    another user's document existence is never revealed.
    """
    unique_ids = list(dict.fromkeys(document_ids))  # dedupe, preserve order
    if not unique_ids:
        raise HTTPException(status_code=422, detail="At least one document ID is required")
    rows = (
        db.query(Document)
        .filter(Document.id.in_(unique_ids), Document.user_id == user.id)
        .all()
    )
    by_id = {document.id: document for document in rows}
    if len(by_id) != len(unique_ids):
        raise HTTPException(status_code=404, detail="Document not found")
    return [by_id[document_id] for document_id in unique_ids]


def load_document_chunks(db: Session, document_id: UUID, limit: int | None = None) -> list[DocumentChunk]:
    """A document's chunks in deterministic order (authoritative PostgreSQL content)."""
    limit = limit if limit is not None else settings.AI_CHUNKS_PER_DOCUMENT
    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .limit(max(1, limit))
        .all()
    )


def to_retrieved_chunks(document: Document, chunks: list[DocumentChunk]) -> list[RetrievedChunk]:
    """Convert DB chunks to the Phase 5 retrieved-chunk shape (no similarity
    score — selection is sequential, not semantic)."""
    return [
        RetrievedChunk(
            chunk_id=str(chunk.id),
            document_id=str(document.id),
            file_name=document.file_name,
            page_number=chunk.page_number,
            score=None,
            content=chunk.content,
        )
        for chunk in chunks
    ]


def select_round_robin(per_document: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    """Interleave chunks across documents (doc1-c1, doc2-c1, ..., doc1-c2, ...)
    so no single document monopolizes the context budget. Deterministic."""
    result: list[RetrievedChunk] = []
    queues = [list(chunks) for chunks in per_document if chunks]
    while queues:
        for queue in list(queues):
            result.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return result


def build_bounded_context(per_document: list[list[RetrievedChunk]]):
    """Assemble the bounded, injection-hardened multi-document context using
    the Phase 5 context builder (RAG_MAX_CONTEXT_CHUNKS / RAG_MAX_CONTEXT_CHARS)."""
    return build_context(select_round_robin(per_document))
