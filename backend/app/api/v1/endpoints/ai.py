from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.models import Document, DocumentChunk, User
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.search import SearchRequest, SearchResponse, SearchHit
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.manager import embedding_available, get_embedding_provider
from app.services.llm.base import LLMError
from app.services.llm.manager import llm_configured
from app.services.rag.service import answer_question
from app.services.vector_store.qdrant_store import QdrantVectorStore, VectorStoreError
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/search", response_model=SearchResponse)
def semantic_search(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Semantic similarity search over embedded document chunks.

    Flow: query → Jina query embedding (retrieval.query task) → Qdrant cosine
    search with metadata filtering → chunk content hydrated from PostgreSQL.
    The search is ALWAYS scoped to the authenticated user; a client can never
    search another user's vectors.
    """
    if not embedding_available():
        raise HTTPException(
            status_code=503,
            detail="Semantic search is not configured — set JINA_API_KEY (and QDRANT_URL) on the server",
        )

    try:
        query_vector = get_embedding_provider().embed_query(payload.query)
        store = QdrantVectorStore.from_settings()
        store.ensure_collection()
        hits = store.search(
            query_vector,
            user_id=current_user.id,
            limit=payload.limit,
            document_id=payload.document_id,
            mime_type=payload.mime_type,
            source=payload.source.value if payload.source else None,
        )
    except (EmbeddingError, VectorStoreError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Hydrate chunk content from PostgreSQL (payloads are metadata-only) and
    # re-verify ownership while doing so (defense in depth).
    results: list[SearchHit] = []
    if hits:
        chunk_ids = [UUID(str(hit["chunk_id"])) for hit in hits if hit.get("chunk_id")]
        chunks = (
            db.query(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(DocumentChunk.id.in_(chunk_ids), Document.user_id == current_user.id)
            .all()
        )
        chunks_by_id = {str(chunk.id): chunk for chunk in chunks}

        for hit in hits:
            if payload.min_score is not None and hit["score"] < payload.min_score:
                continue
            chunk = chunks_by_id.get(str(hit.get("chunk_id")))
            if chunk is None:  # vector without a live chunk row → skip
                continue
            results.append(
                SearchHit(
                    score=hit["score"],
                    chunk_id=str(chunk.id),
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    document_id=hit.get("document_id"),
                    file_name=hit.get("file_name"),
                    mime_type=hit.get("mime_type"),
                    source=hit.get("source"),
                )
            )

    logger.info(
        "Semantic search by %s (%d chars) → %d hits", current_user.email, len(payload.query), len(results)
    )
    return SearchResponse(query=payload.query, total=len(results), results=results)


@router.post("/chat", response_model=ChatResponse)
def rag_chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieval-augmented chat over the user's own documents.

    Flow: query processing → Jina query embedding → Qdrant semantic retrieval
    (user-scoped) → PostgreSQL chunk hydration → bounded, injection-hardened
    context construction → NVIDIA hosted LLM → answer with application-side
    source attribution. With no relevant chunks a controlled answer is
    returned and the LLM is not called.
    """
    if not embedding_available():
        raise HTTPException(
            status_code=503,
            detail="RAG is not configured — set JINA_API_KEY (and QDRANT_URL) on the server",
        )
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="RAG is not configured — set NVIDIA_API_KEY on the server",
        )

    try:
        result = answer_question(
            db=db,
            user=current_user,
            message=payload.message,
            limit=payload.limit,
            min_score=payload.min_score,
        )
    except (EmbeddingError, VectorStoreError, LLMError) as exc:
        # Upstream failures (Jina / Qdrant / NVIDIA) — sanitized messages only
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected RAG failure for user %s", current_user.email)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing the chat request",
        )

    return ChatResponse(**result)
