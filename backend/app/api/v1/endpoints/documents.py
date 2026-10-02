from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.models import (
    CloudProvider,
    Document,
    DocumentChunk,
    DocumentTable,
    JobType,
    ProcessingJob,
    ProcessingStatus,
    User,
)
from app.schemas.ai_features import SummarizeResponse
from app.schemas.files import DocumentListResponse, DocumentRead
from app.schemas.processing import ChunkListResponse, ProcessResponse, TableListResponse
from app.schemas.search import EmbedResponse
from app.services.ai.summarization import summarize_document as summarize_document_service
from app.services.document_processing.pipeline import start_processing
from app.services.llm.base import LLMError
from app.services.llm.manager import llm_configured
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.manager import embed_document_chunks, embedding_available
from app.services.vector_store.qdrant_store import VectorStoreError
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _get_document_or_404(db: Session, user: User, doc_id: UUID) -> Document:
    document = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("", response_model=DocumentListResponse)
def list_documents(
    provider: CloudProvider | None = None,
    processing_status: ProcessingStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the file metadata tracked by the platform for the current user."""
    query = db.query(Document).filter(Document.user_id == current_user.id)
    if provider is not None:
        query = query.filter(Document.provider == provider)
    if processing_status is not None:
        query = query.filter(Document.processing_status == processing_status)
    total = query.count()
    items = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    return DocumentListResponse(total=total, items=items)


@router.get("/{doc_id}", response_model=DocumentRead)
def get_document(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_document_or_404(db, current_user, doc_id)


@router.get("/{doc_id}/status")
def document_status(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Processing status of a tracked document, with per-stage job details."""
    document = _get_document_or_404(db, current_user, doc_id)
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_id == document.id)
        .order_by(ProcessingJob.started_at.asc())
        .all()
    )
    return {
        "document_id": str(document.id),
        "file_name": document.file_name,
        "processing_status": document.processing_status.value if document.processing_status else None,
        "ocr_required": document.ocr_required,
        "ocr_completed": document.ocr_completed,
        "embedding_completed": document.embedding_completed,
        "jobs": [
            {
                "job_type": job.job_type.value if job.job_type else None,
                "status": job.status.value if job.status else None,
                "error_message": job.error_message,
            }
            for job in jobs
        ],
    }


@router.post("/{doc_id}/process", response_model=ProcessResponse, status_code=202)
def process_document(
    doc_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the processing pipeline: download → extract text → OCR (if needed)
    → extract tables → chunk → embed (when configured). Runs in the
    background; poll the status endpoint."""
    document = _get_document_or_404(db, current_user, doc_id)
    result = start_processing(db, document, background_tasks)
    logger.info("Processing triggered for document %s", document.id)
    return result


@router.post("/{doc_id}/embed", response_model=EmbedResponse)
def embed_document(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """(Re-)embed a processed document's chunks into the vector database.

    Generates Jina embeddings for every chunk and upserts the vectors into
    Qdrant (existing vectors for the document are replaced — safe to retry,
    never duplicates). Records an `embedding` processing job.
    """
    document = _get_document_or_404(db, current_user, doc_id)
    if not embedding_available():
        raise HTTPException(
            status_code=503,
            detail="Embeddings are not configured — set JINA_API_KEY (and QDRANT_URL) on the server",
        )
    if document.processing_status == ProcessingStatus.processing:
        raise HTTPException(status_code=409, detail="Document is currently being processed")
    chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
    if chunk_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Document has no chunks to embed — process it first (POST /documents/{id}/process)",
        )

    job = ProcessingJob(
        document_id=document.id,
        job_type=JobType.embedding,
        status=ProcessingStatus.processing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    try:
        result = embed_document_chunks(db, document)
    except (EmbeddingError, VectorStoreError) as exc:
        job.status = ProcessingStatus.failed
        job.error_message = str(exc)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("Embedding failed for document %s: %s", document.id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    job.status = ProcessingStatus.completed
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Embedded document %s via endpoint (%d chunks)", document.id, result["chunks_embedded"])
    return EmbedResponse(
        document_id=str(document.id),
        status="completed",
        chunks_embedded=result["chunks_embedded"],
        model=result["model"],
        message="Embeddings stored in the vector database. Use POST /api/v1/search to query.",
    )


@router.get("/{doc_id}/chunks", response_model=ChunkListResponse)
def list_chunks(
    doc_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the text chunks produced by processing (feeds Phase 4 embeddings)."""
    document = _get_document_or_404(db, current_user, doc_id)
    query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id)
    total = query.count()
    items = (
        query.order_by(DocumentChunk.chunk_index.asc()).offset(offset).limit(limit).all()
    )
    return ChunkListResponse(total=total, items=items)


@router.get("/{doc_id}/tables", response_model=TableListResponse)
def list_tables(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the tables extracted from the document."""
    document = _get_document_or_404(db, current_user, doc_id)
    items = (
        db.query(DocumentTable)
        .filter(DocumentTable.document_id == document.id)
        .order_by(DocumentTable.page_number.asc().nullsfirst(), DocumentTable.table_index.asc())
        .all()
    )
    return TableListResponse(total=len(items), items=items)


@router.post("/{doc_id}/summarize", response_model=SummarizeResponse)
def summarize_document(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a concise AI summary of a processed document (owned by the
    authenticated user) from its extracted chunk content."""
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="AI features are not configured — set NVIDIA_API_KEY or OLLAMA_MODEL on the server",
        )
    document = _get_document_or_404(db, current_user, doc_id)
    try:
        return summarize_document_service(db=db, user=current_user, document=document)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected summarization failure for document %s", doc_id)
        raise HTTPException(
            status_code=500, detail="An internal error occurred while summarizing the document"
        )
