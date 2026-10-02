"""Feature B — multi-document analysis.

Answers an analysis question across multiple owned documents through the
centralized LLM manager. Document boundaries stay explicit (each source block
is labeled with its document), context stays bounded, and source attribution
is application-side. Cross-user document access is impossible.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import User
from app.services.ai.context import (
    build_bounded_context,
    load_document_chunks,
    load_owned_documents,
    to_retrieved_chunks,
)
from app.services.ai.prompts import MULTI_DOCUMENT_SYSTEM_PROMPT
from app.services.llm.manager import get_llm_provider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def run_multi_document_analysis(db: Session, user: User, document_ids: list[UUID], question: str) -> dict:
    """Analyze multiple owned documents against a question.

    Returns ``{"question", "analysis", "sources", "provider"}``.
    """
    documents = load_owned_documents(db, user, document_ids)

    per_document = []
    for document in documents:
        chunks = load_document_chunks(db, document.id, settings.AI_CHUNKS_PER_DOCUMENT)
        if not chunks:
            raise HTTPException(
                status_code=409,
                detail=f"Document '{document.file_name}' has no chunks — process it first "
                "(POST /api/v1/documents/{id}/process)",
            )
        per_document.append(to_retrieved_chunks(document, chunks))

    context, sources = build_bounded_context(per_document)
    if not sources:
        raise HTTPException(
            status_code=503,
            detail="Document content does not fit within the configured context limits",
        )

    provider = get_llm_provider()
    user_message = f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"
    analysis = provider.generate_answer(
        system_prompt=MULTI_DOCUMENT_SYSTEM_PROMPT, user_message=user_message
    )

    logger.info(
        "Multi-document analysis for user %s across %d documents (provider=%s)",
        user.email, len(documents), provider.last_provider,
    )
    return {
        "question": question,
        "analysis": analysis,
        "sources": [source.as_dict() for source in sources],
        "provider": provider.last_provider,
    }
