import hashlib
import os
import re

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.database.session import get_db
from app.models.models import CloudProvider, Document, User
from app.schemas.files import CloudFile, DocumentRead
from app.services.registry import get_cloud_service
from app.utils.logger import get_logger

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


def _content_disposition(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._() -]", "_", filename) or "download"
    return f'attachment; filename="{safe}"'


def _get_document_or_404(db: Session, user: User, document_id) -> Document:
    from uuid import UUID

    try:
        doc_uuid = UUID(str(document_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found")
    document = db.query(Document).filter(Document.id == doc_uuid, Document.user_id == user.id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("", response_model=list[CloudFile])
def list_files(
    provider: CloudProvider | None = Query(default=None, description="Filter by provider; omit to aggregate all connected providers"),
    folder_id: str | None = Query(default=None, description="Google Drive folder ID or S3 prefix"),
    search: str | None = Query(default=None, description="Filter by name (provider-side search)"),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List files live from the connected cloud providers (not from the local database)."""
    providers = [provider] if provider is not None else list(CloudProvider)
    results: list[dict] = []

    for p in providers:
        try:
            service = get_cloud_service(db, current_user, p)
        except HTTPException:
            if provider is None:
                continue  # provider not connected → skip while aggregating
            raise
        if p == CloudProvider.google_drive:
            results.extend(service.list_files(folder_id=folder_id or "root", search=search, limit=limit))
        else:
            results.extend(service.list_files(folder_id=folder_id or "", search=search, limit=limit))
    return results


@router.get("/{file_id}", response_model=CloudFile)
def get_file(
    file_id: str,
    provider: CloudProvider = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get live metadata for a single cloud file."""
    service = get_cloud_service(db, current_user, provider)
    return service.get_file(file_id)


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    provider: CloudProvider = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a file's content from the cloud provider."""
    service = get_cloud_service(db, current_user, provider)
    result = service.download_file(file_id)

    if provider == CloudProvider.google_drive:
        filename, content, content_type = result
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": _content_disposition(filename)},
        )

    filename, stream, content_type = result
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    provider: CloudProvider = Form(...),
    folder_id: str | None = Form(default=None, description="Google Drive folder ID or S3 prefix"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a local file to the chosen cloud provider and track its metadata."""
    filename = os.path.basename(file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing file name")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{extension or 'unknown'}' is not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit")

    content_hash = hashlib.sha256(content).hexdigest()
    duplicate = (
        db.query(Document)
        .filter(Document.user_id == current_user.id, Document.content_hash == content_hash)
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A file with identical content is already tracked (document_id={duplicate.id}, name={duplicate.file_name})",
        )

    mime_type = file.content_type or "application/octet-stream"
    service = get_cloud_service(db, current_user, provider)
    remote = service.upload_file(filename=filename, content=content, mime_type=mime_type, folder_id=folder_id)

    document = Document(
        user_id=current_user.id,
        provider=provider,
        external_file_id=remote["file_id"],
        file_name=filename,
        file_type=extension,
        file_size=len(content),
        mime_type=mime_type,
        source_path=folder_id,
        content_hash=content_hash,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    logger.info("Uploaded %s to %s (document %s)", filename, provider.value, document.id)
    return document


@router.post("/{file_id}/import", response_model=DocumentRead)
def import_file(
    file_id: str,
    provider: CloudProvider = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Track an existing cloud file in the platform by storing its metadata.

    Idempotent: importing an already-tracked file returns it unchanged.
    """
    existing = (
        db.query(Document)
        .filter(
            Document.user_id == current_user.id,
            Document.provider == provider,
            Document.external_file_id == file_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    service = get_cloud_service(db, current_user, provider)
    remote = service.get_file(file_id)
    if remote.get("is_folder"):
        raise HTTPException(status_code=400, detail="Cannot import a folder — import individual files")

    name = remote.get("name") or file_id
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    document = Document(
        user_id=current_user.id,
        provider=provider,
        external_file_id=file_id,
        file_name=name,
        file_type=extension,
        file_size=remote.get("size"),
        mime_type=remote.get("mime_type"),
        source_path=remote.get("parent_id"),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    logger.info("Imported %s from %s (document %s)", name, provider.value, document.id)
    return document


@router.post("/{file_id}/process")
def process_file(
    file_id: str,
    provider: CloudProvider = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"message": f"Processing {file_id} — coming in Phase 3"}
