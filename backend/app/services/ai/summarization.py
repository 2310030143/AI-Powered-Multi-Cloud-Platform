"""Feature A — document summarization.

Summarizes a document's extracted/chunked content (the authoritative
PostgreSQL chunks, deterministically ordered) through the centralized LLM
manager, reusing the Phase 5 bounded, injection-hardened context builder.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import Document, User
from app.services.ai.context import build_bounded_context, load_document_chunks, to_retrieved_chunks
from app.services.ai.prompts import SUMMARY_SYSTEM_PROMPT
from app.services.llm.manager import get_llm_provider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def summarize_document(db: Session, user: User, document: Document) -> dict:
    """Generate a concise summary for one owned document.

    Returns ``{"document_id", "filename", "summary", "sources", "provider"}``.
    If the document has no usable text, a deterministic 409 is raised — the
    LLM is never called unnecessarily.
    """
    chunks = load_document_chunks(db, document.id, settings.AI_CHUNKS_PER_DOCUMENT)
    if not chunks:
        raise HTTPException(
            status_code=409,
            detail="Document has no chunks to summarize — process it first "
            "(POST /api/v1/documents/{id}/process)",
        )

    context, sources = build_bounded_context([to_retrieved_chunks(document, chunks)])
    if not sources:
        raise HTTPException(
            status_code=503,
            detail="Document content does not fit within the configured context limits",
        )

    provider = get_llm_provider()
    user_message = (
        f"CONTEXT:\n{context}\n\n"
        "TASK:\nSummarize the document above concisely and faithfully."
    )
    summary = provider.generate_answer(system_prompt=SUMMARY_SYSTEM_PROMPT, user_message=user_message)

    logger.info(
        "Summary generated for document %s (%d chars, provider=%s)",
        document.id, len(summary), provider.last_provider,
    )
    return {
        "document_id": str(document.id),
        "filename": document.file_name,
        "summary": summary,
        "sources": [source.as_dict() for source in sources],
        "provider": provider.last_provider,
    }
