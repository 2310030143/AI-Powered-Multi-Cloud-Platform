"""Document processing pipeline.

Stages: download → text extraction → OCR (when needed) → table extraction →
chunking. Every stage is recorded in ``processing_jobs``; the document's
``processing_status`` moves pending → processing → completed/failed.

Designed to run in a FastAPI background task: ``process_document(doc_id)``
creates its own DB session.
"""
import os
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.models import (
    Document,
    DocumentChunk,
    DocumentTable,
    JobType,
    ProcessingJob,
    ProcessingStatus,
    User,
)
from app.services.ocr import ocr
from app.services.document_processing import extractors
from app.services.document_processing.chunking import chunk_pages
from app.services.registry import get_cloud_service
from app.services.table_extraction import extractor as table_extractor
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name or "file")
    return cleaned[:180] or "file"


def _read_stream(stream_or_bytes) -> bytes:
    """Google downloads return bytes; S3 returns a botocore StreamingBody."""
    if isinstance(stream_or_bytes, (bytes, bytearray)):
        return bytes(stream_or_bytes)
    return stream_or_bytes.read()


def _run_job(db: Session, document: Document, job_type: JobType, fn):
    """Run one stage wrapped in a ProcessingJob record."""
    job_record = _new_job(db, document, job_type)
    try:
        result = fn()
        job_record.status = ProcessingStatus.completed
        job_record.completed_at = _utcnow()
        db.commit()
        return result
    except Exception as exc:
        job_record.status = ProcessingStatus.failed
        job_record.completed_at = _utcnow()
        job_record.error_message = str(exc)[:2000]
        db.commit()
        raise


def _new_job(db: Session, document: Document, job_type: JobType, error: str | None = None):
    job = ProcessingJob(
        document_id=document.id,
        job_type=job_type,
        status=ProcessingStatus.failed if error else ProcessingStatus.processing,
        error_message=error,
        started_at=_utcnow(),
        completed_at=_utcnow() if error else None,
    )
    db.add(job)
    db.commit()
    return job


def _download_document_content(db: Session, document: Document) -> tuple[bytes, str]:
    """Download the file bytes from its cloud provider."""
    user = db.get(User, document.user_id)
    if user is None:
        raise ValueError("Document owner no longer exists")
    service = get_cloud_service(db, user, document.provider)
    result = service.download_file(document.external_file_id)
    filename, stream, _content_type = result
    return _read_stream(stream), filename


def _cache_locally(document: Document, filename: str, content: bytes) -> str:
    """Store a local copy under LOCAL_STORAGE_PATH/<document_id>/ for later phases."""
    directory = os.path.join(settings.LOCAL_STORAGE_PATH, str(document.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _safe_filename(filename))
    with open(path, "wb") as handle:
        handle.write(content)
    return path


def _clear_previous_artifacts(db: Session, document: Document) -> None:
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    db.query(DocumentTable).filter(DocumentTable.document_id == document.id).delete()
    db.query(ProcessingJob).filter(ProcessingJob.document_id == document.id).delete()
    db.commit()


def process_document(document_id: UUID | str) -> dict:
    """Run the full pipeline for one document (own DB session)."""
    db = SessionLocal()
    try:
        document = db.get(Document, UUID(str(document_id)))
        if document is None:
            logger.warning("Processing requested for unknown document %s", document_id)
            return {"status": "skipped", "reason": "document not found"}

        summary = _run_pipeline(db, document)
        db.commit()
        return summary
    except Exception as exc:  # safety net — the pipeline handles its own failures
        db.rollback()
        logger.exception("Unexpected error processing document %s", document_id)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def _run_pipeline(db: Session, document: Document) -> dict:
    summary = {
        "document_id": str(document.id),
        "file_name": document.file_name,
        "provider": document.provider.value if document.provider else None,
        "file_type": document.file_type,
        "ocr_used": False,
    }

    document.processing_status = ProcessingStatus.processing
    document.ocr_required = False
    document.ocr_completed = False
    db.commit()
    _clear_previous_artifacts(db, document)

    try:
        # ── Stage 1: download from cloud ────────────────────────────────────
        content, filename = _download_document_content(db, document)
        summary["file_size_bytes"] = len(content)
        try:
            _cache_locally(document, filename, content)
        except OSError as exc:
            logger.warning("Could not cache file locally: %s", exc)

        # ── Stage 2: text extraction ───────────────────────────────────────
        try:
            extraction = _run_job(
                db, document, JobType.text_extraction,
                lambda: extractors.extract(content, document.file_type),
            )
        except extractors.UnsupportedFileType as exc:
            document.processing_status = ProcessingStatus.failed
            db.commit()
            summary.update(status="failed", error=str(exc))
            return summary

        pages = list(extraction.pages)
        ocr_used = False

        # ── Stage 3: OCR when required ────────────────────────────────────
        needs_ocr = extraction.ocr_recommended

        if needs_ocr:
            document.ocr_required = True

            def _do_ocr():
                if document.file_type in extractors.IMAGE_TYPES:
                    return [
                        extractors.PageText(
                            page_number=1,
                            text=ocr.image_to_text(content),
                        )
                    ]

                return ocr.ocr_pdf_pages(
                    content,
                    page_numbers=extraction.ocr_page_numbers,
                )

            try:
                ocr_pages = _run_job(
                    db,
                    document,
                    JobType.ocr,
                    _do_ocr,
                )

                ocr_by_page = {
                    page.page_number: page
                    for page in ocr_pages
                }

                if document.file_type in extractors.IMAGE_TYPES:
                    pages = ocr_pages
                else:
                    pages = [
                        ocr_by_page.get(page.page_number, page)
                        for page in pages
                    ]

                ocr_used = True
                document.ocr_completed = True
                summary["ocr_used"] = ocr_used

            except ocr.OCRError as exc:
                # OCR unavailable — only fatal when there is no usable text at all.
                if not extraction.text.strip():
                    document.processing_status = ProcessingStatus.failed
                    db.commit()
                    summary.update(status="failed", error=str(exc))
                    return summary

                logger.warning("OCR skipped: %s", exc)

        # ── Stage 4: table extraction ──────────────────────────────────────
        tables: list[dict] = []
        if document.file_type == "pdf":
            try:
                tables = _run_job(
                    db, document, JobType.table_extraction,
                    lambda: table_extractor.extract_tables_from_pdf(content),
                )
            except table_extractor.TableExtractionError as exc:
                logger.warning("Table extraction failed for %s: %s", document.id, exc)
        elif document.file_type == "csv" and extraction.csv_rows:
            tables = _run_job(
                db, document, JobType.table_extraction,
                lambda: table_extractor.table_from_csv_rows(extraction.csv_rows),
            )

        for table in tables:
            db.add(DocumentTable(
                document_id=document.id,
                page_number=table["page_number"],
                table_index=table["table_index"],
                table_data=table["rows"],
                row_count=table["row_count"],
                col_count=table["col_count"],
            ))
        db.commit()
        summary["tables_found"] = len(tables)

        # ── Stage 5: chunking ──────────────────────────────────────────────
        chunks = _run_job(
            db, document, JobType.chunking,
            lambda: chunk_pages(pages) if pages else [],
        )
        for index, chunk in enumerate(chunks):
            db.add(DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                page_number=chunk["page_number"],
                content=chunk["content"],
                token_count=chunk["token_count"],
            ))
        db.commit()
        summary.update(
            status="completed",
            pages_processed=len(pages),
            characters_extracted=sum(len(p.text) for p in pages),
            chunks_created=len(chunks),
        )

        document.processing_status = ProcessingStatus.completed
        db.commit()
        logger.info(
            "Processed document %s (%s): %d chars, %d tables, %d chunks",
            document.id, document.file_name,
            summary["characters_extracted"], len(tables), len(chunks),
        )
        return summary

    except HTTPException as exc:
        document.processing_status = ProcessingStatus.failed
        db.commit()
        error = str(exc.detail)
        summary.update(status="failed", error=error)
        logger.warning("Processing failed for document %s: %s", document.id, error)
        return summary
    except Exception as exc:
        db.rollback()
        document.processing_status = ProcessingStatus.failed
        db.commit()
        summary.update(status="failed", error=str(exc)[:500])
        logger.exception("Processing failed for document %s", document.id)
        return summary


def start_processing(db: Session, document: Document, background_tasks: BackgroundTasks) -> dict:
    """Validate + schedule processing; shared by the /files and /documents endpoints."""
    if document.processing_status == ProcessingStatus.processing:
        raise HTTPException(status_code=409, detail="Document is already being processed")
    background_tasks.add_task(process_document, document.id)
    return {
        "document_id": str(document.id),
        "status": "processing",
        "message": "Processing started in the background. Poll GET /api/v1/documents/{id}/status for progress.",
    }
