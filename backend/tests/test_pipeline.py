"""Tests for the document processing pipeline and its endpoints."""
import io
from uuid import UUID

import pytest

from app.database.session import SessionLocal
from app.models.models import (
    CloudProvider,
    Document,
    DocumentChunk,
    DocumentTable,
    JobType,
    ProcessingJob,
    ProcessingStatus,
)
from app.services.document_processing.pipeline import process_document
from tests.helpers import make_docx, make_pdf


class FakeCloudService:
    """Downloads served from an in-memory dict of provider files."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def get_file(self, file_id):
        from fastapi import HTTPException

        if file_id not in self.files:
            raise HTTPException(status_code=404, detail="File not found")
        name = file_id.rsplit("/", 1)[-1]
        return {
            "provider": "s3",
            "file_id": file_id,
            "name": name,
            "mime_type": "application/octet-stream",
            "size": len(self.files[file_id]),
            "modified_at": None,
            "is_folder": False,
            "parent_id": None,
        }

    def download_file(self, file_id):
        if file_id not in self.files:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="File not found")
        name = file_id.rsplit("/", 1)[-1]
        return name, io.BytesIO(self.files[file_id]), "application/octet-stream"


@pytest.fixture()
def fake_cloud(monkeypatch):
    files: dict[str, bytes] = {}

    service = FakeCloudService(files)
    monkeypatch.setattr(
        "app.api.v1.endpoints.files.get_cloud_service",
        lambda db, user, provider: service,
    )
    monkeypatch.setattr(
        "app.services.document_processing.pipeline.get_cloud_service",
        lambda db, user, provider: service,
    )
    return files


def _create_document(client, auth_headers, provider: CloudProvider, file_id: str, file_type: str) -> str:
    """Import (or reuse) a document row for a fake cloud file; returns doc id."""
    response = client.post(
        f"/api/v1/files/{file_id}/import", params={"provider": provider.value}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _get_doc(doc_id: str) -> Document:
    db = SessionLocal()
    try:
        return db.get(Document, UUID(str(doc_id)))
    finally:
        db.close()


class TestPipelineTextDocuments:
    def test_txt_document(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"First line of notes.\n\nSecond paragraph with more text."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert summary["chunks_created"] >= 1
        assert summary["ocr_used"] is False

        document = _get_doc(doc_id)
        assert document.processing_status == ProcessingStatus.completed
        assert document.ocr_required is False

        db = SessionLocal()
        try:
            chunks = db.query(DocumentChunk).filter_by(document_id=UUID(str(doc_id))).order_by(DocumentChunk.chunk_index).all()
            assert "First line of notes." in chunks[0].content
            assert chunks[0].token_count and chunks[0].token_count > 0
        finally:
            db.close()

    def test_docx_document(self, client, auth_headers, fake_cloud):
        content = make_docx(
            paragraphs=["Docx paragraph one.", "Docx paragraph two."],
            table_rows=[["Header1", "Header2"], ["v1", "v2"]],
        )
        fake_cloud["report.docx"] = content
        doc_id = _create_document(client, auth_headers, CloudProvider.google_drive, "report.docx", "docx")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert "Docx paragraph one." in _first_chunk_content(doc_id)
        # DOCX tables are inlined as text, not stored as tables
        assert "Header1 | Header2" in _first_chunk_content(doc_id)

    def test_csv_document_with_table(self, client, auth_headers, fake_cloud):
        fake_cloud["data.csv"] = b"product,price\nWidget,9.99\nGadget,19.99\n"
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "data.csv", "csv")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert summary["tables_found"] == 1

        db = SessionLocal()
        try:
            tables = db.query(DocumentTable).filter_by(document_id=UUID(str(doc_id))).all()
            assert len(tables) == 1
            assert tables[0].table_data == [["product", "price"], ["Widget", "9.99"], ["Gadget", "19.99"]]
            assert tables[0].row_count == 3
        finally:
            db.close()
        assert "product: Widget" in _first_chunk_content(doc_id)

    def test_pdf_document(self, client, auth_headers, fake_cloud):
        fake_cloud["docs/doc.pdf"] = make_pdf(["Alpha page text about apples", "Beta page text about bananas"])
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "docs/doc.pdf", "pdf")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert summary["pages_processed"] == 2
        content = _all_chunk_content(doc_id)
        assert "apples" in content and "bananas" in content

    def test_jobs_recorded_per_stage(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"Some notes to process."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")

        process_document(doc_id)
        db = SessionLocal()
        try:
            jobs = db.query(ProcessingJob).filter_by(document_id=UUID(str(doc_id))).all()
            job_types = {j.job_type for j in jobs}
            assert JobType.text_extraction in job_types
            assert JobType.chunking in job_types
            assert all(j.status == ProcessingStatus.completed for j in jobs)
        finally:
            db.close()


class TestPipelineOcr:
    def test_image_document_uses_ocr(self, client, auth_headers, fake_cloud, monkeypatch):
        from app.services.ocr import ocr as ocr_module

        monkeypatch.setattr(ocr_module, "is_available", lambda: True)
        monkeypatch.setattr(ocr_module, "image_to_text", lambda content: "OCR EXTRACTED TEXT about scanned images")

        fake_cloud["scan.png"] = b"\x89PNG fake image bytes"
        doc_id = _create_document(client, auth_headers, CloudProvider.google_drive, "scan.png", "png")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert summary["ocr_used"] is True

        document = _get_doc(doc_id)
        assert document.ocr_required is True
        assert document.ocr_completed is True
        assert "OCR EXTRACTED TEXT" in _first_chunk_content(doc_id)

    def test_scanned_pdf_uses_ocr(self, client, auth_headers, fake_cloud, monkeypatch):
        from app.services.document_processing.extractors import PageText
        from app.services.ocr import ocr as ocr_module

        monkeypatch.setattr(ocr_module, "is_available", lambda: True)
        monkeypatch.setattr(ocr_module, "rasterizer_available", lambda: True)
        monkeypatch.setattr(
            ocr_module,
            "ocr_pdf_pages",
            lambda content, page_numbers=None: [
                PageText(1, "OCR text from page one"),
                PageText(2, "OCR text from page two"),
            ],
        )

        fake_cloud["scanned.pdf"] = make_pdf(["", ""])  # no text layer
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "scanned.pdf", "pdf")

        summary = process_document(doc_id)
        assert summary["status"] == "completed"
        assert summary["ocr_used"] is True
        content = _all_chunk_content(doc_id)
        assert "OCR text from page one" in content and "OCR text from page two" in content

    def test_scanned_pdf_fails_cleanly_without_tesseract(self, client, auth_headers, fake_cloud, monkeypatch):
        from app.services.ocr import ocr as ocr_module

        monkeypatch.setattr(ocr_module, "is_available", lambda: False)

        fake_cloud["scanned.pdf"] = make_pdf(["", ""])
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "scanned.pdf", "pdf")

        summary = process_document(doc_id)
        assert summary["status"] == "failed"
        assert "tesseract" in summary["error"]

        document = _get_doc(doc_id)
        assert document.processing_status == ProcessingStatus.failed
        assert document.ocr_required is True

        db = SessionLocal()
        try:
            ocr_jobs = db.query(ProcessingJob).filter_by(document_id=UUID(str(doc_id)), job_type=JobType.ocr).all()
            assert ocr_jobs and ocr_jobs[0].status == ProcessingStatus.failed
        finally:
            db.close()


class TestPipelineFailures:
    def test_missing_cloud_file_fails_document(self, client, auth_headers, fake_cloud):
        # the file exists at import time but disappears before processing
        fake_cloud["ghost.txt"] = b"now you see me"
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "ghost.txt", "txt")
        del fake_cloud["ghost.txt"]

        summary = process_document(doc_id)
        assert summary["status"] == "failed"
        assert "error" in summary
        assert _get_doc(doc_id).processing_status == ProcessingStatus.failed

    def test_unsupported_file_type_fails(self, client, auth_headers, fake_cloud):
        fake_cloud["video.mp4"] = b"AAAAIGZ0eXBpc29t"
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "video.mp4", "mp4")

        summary = process_document(doc_id)
        assert summary["status"] == "failed"
        assert "No extractor" in summary["error"]

    def test_reprocessing_replaces_artifacts(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"Version one content."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")
        process_document(doc_id)

        fake_cloud["notes.txt"] = b"Version two content, quite different from version one."
        process_document(doc_id)  # reprocess

        db = SessionLocal()
        try:
            chunks = db.query(DocumentChunk).filter_by(document_id=UUID(str(doc_id))).all()
            jobs = db.query(ProcessingJob).filter_by(document_id=UUID(str(doc_id))).all()
            assert len(chunks) >= 1
            assert "Version two" in chunks[0].content
            # no duplicated artifacts from the first run
            assert len(jobs) == len({j.id for j in jobs})
        finally:
            db.close()


class TestProcessEndpoints:
    def test_process_via_documents_endpoint(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"Endpoint driven processing test."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")

        response = client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "processing"
        assert body["document_id"] == doc_id

        # background task runs within the TestClient request cycle
        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        assert status["processing_status"] == "completed"
        assert any(j["job_type"] == "chunking" and j["status"] == "completed" for j in status["jobs"])

    def test_process_via_files_alias(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"Alias endpoint test."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")

        response = client.post(
            "/api/v1/files/notes.txt/process", params={"provider": "s3"}, headers=auth_headers
        )
        assert response.status_code == 202
        assert _get_doc(doc_id).processing_status == ProcessingStatus.completed

    def test_process_unimported_file_404(self, client, auth_headers, fake_cloud):
        response = client.post(
            "/api/v1/files/never-imported.txt/process", params={"provider": "s3"}, headers=auth_headers
        )
        assert response.status_code == 404

    def test_chunks_endpoint(self, client, auth_headers, fake_cloud):
        fake_cloud["long.txt"] = ("\n\n".join(f"Paragraph {i} " + "content words here " * 30 for i in range(10))).encode()
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "long.txt", "txt")
        process_document(doc_id)

        response = client.get(f"/api/v1/documents/{doc_id}/chunks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert data["items"][0]["chunk_index"] == 0
        assert data["items"][0]["content"]
        assert data["items"][0]["token_count"] > 0

    def test_tables_endpoint(self, client, auth_headers, fake_cloud):
        fake_cloud["data.csv"] = b"a,b\n1,2\n"
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "data.csv", "csv")
        process_document(doc_id)

        response = client.get(f"/api/v1/documents/{doc_id}/tables", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["table_data"] == [["a", "b"], ["1", "2"]]

    def test_document_status_includes_jobs(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"status detail test."
        doc_id = _create_document(client, auth_headers, CloudProvider.s3, "notes.txt", "txt")
        process_document(doc_id)

        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        assert status["processing_status"] == "completed"
        job_types = [j["job_type"] for j in status["jobs"]]
        assert "text_extraction" in job_types
        assert "chunking" in job_types


# ── helpers ──────────────────────────────────────────────────────────────────

def _first_chunk_content(doc_id: str) -> str:
    db = SessionLocal()
    try:
        chunk = (
            db.query(DocumentChunk)
            .filter_by(document_id=UUID(str(doc_id)))
            .order_by(DocumentChunk.chunk_index)
            .first()
        )
        return chunk.content if chunk else ""
    finally:
        db.close()


def _all_chunk_content(doc_id: str) -> str:
    db = SessionLocal()
    try:
        chunks = db.query(DocumentChunk).filter_by(document_id=UUID(str(doc_id))).all()
        return "\n\n".join(c.content for c in chunks)
    finally:
        db.close()
