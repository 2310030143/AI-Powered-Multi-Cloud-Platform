from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.models import CloudProvider, Document, ProcessingStatus, User
from app.schemas.files import DocumentListResponse, DocumentRead

router = APIRouter()


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
    """Processing status of a tracked document."""
    document = _get_document_or_404(db, current_user, doc_id)
    return {
        "document_id": str(document.id),
        "file_name": document.file_name,
        "processing_status": document.processing_status.value if document.processing_status else None,
        "ocr_required": document.ocr_required,
        "ocr_completed": document.ocr_completed,
        "embedding_completed": document.embedding_completed,
    }


@router.post("/{doc_id}/summarize")
def summarize_document(
    doc_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_document_or_404(db, current_user, doc_id)
    return {"message": f"Summarize {doc_id} — coming in Phase 6"}
