"""RAG orchestration: query processing → semantic retrieval → context
construction → LLM generation, with application-side source attribution.

The service orchestrates; provider-specific HTTP logic lives in the LLM
provider and embedding provider behind the manager DI points.
"""
from sqlalchemy.orm import Session

from app.models.models import User
from app.services.llm.manager import get_llm_provider
from app.services.rag.context_builder import build_context
from app.services.rag.prompts import RAG_SYSTEM_PROMPT
from app.services.rag.query_processing import prepare_query
from app.services.rag.retrieval import retrieve_chunks
from app.utils.logger import get_logger

logger = get_logger(__name__)

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your documents to answer this question."
)


def answer_question(
    db: Session,
    user: User,
    message: str,
    limit: int = 5,
    min_score: float | None = None,
) -> dict:
    """Run the full RAG flow for one user message.

    Returns ``{"message": ..., "answer": ..., "sources": [...]}``.
    With no relevant chunks (or nothing surviving the context limits), returns
    a controlled answer and no sources — the LLM is not called.
    """
    query = prepare_query(message)

    chunks = retrieve_chunks(db=db, user=user, query=query, limit=limit, min_score=min_score)
    if not chunks:
        logger.info("RAG: no relevant chunks for user %s — skipping LLM", user.email)
        return {"message": message, "answer": NO_CONTEXT_ANSWER, "sources": []}

    context, sources = build_context(chunks)
    if not sources:  # nothing fit within the context limits
        logger.info("RAG: context limits excluded all %d retrieved chunks", len(chunks))
        return {"message": message, "answer": NO_CONTEXT_ANSWER, "sources": []}

    provider = get_llm_provider()
    user_message = f"CONTEXT:\n{context}\n\nQUESTION:\n{query}"
    answer = provider.generate_answer(system_prompt=RAG_SYSTEM_PROMPT, user_message=user_message)

    logger.info(
        "RAG answer for %s: %d chunks retrieved, %d in context, answer %d chars",
        user.email, len(chunks), len(sources), len(answer),
    )
    # Source attribution is application-side, built from the retrieval
    # results — never from anything the model produced.
    return {
        "message": message,
        "answer": answer,
        "sources": [source.as_dict() for source in sources],
    }
