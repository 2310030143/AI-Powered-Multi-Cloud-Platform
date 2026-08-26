"""Tests for the files API (list / download / upload / import) and documents."""
import hashlib
from datetime import datetime, timezone

import pytest


DRIVE_FILE = {
    "provider": "google_drive",
    "file_id": "drive-file-1",
    "name": "quarterly-report.pdf",
    "mime_type": "application/pdf",
    "size": 2048,
    "modified_at": datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
    "is_folder": False,
    "parent_id": "root",
}


class FakeDriveService:
    """In-memory stand-in for GoogleDriveService."""

    def list_files(self, folder_id="root", search=None, limit=100):
        return [DRIVE_FILE]

    def get_file(self, file_id):
        if file_id != DRIVE_FILE["file_id"]:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="File not found on Google Drive")
        return DRIVE_FILE

    def download_file(self, file_id):
        if file_id != DRIVE_FILE["file_id"]:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="File not found on Google Drive")
        return "quarterly-report.pdf", b"%PDF-1.4 fake content", "application/pdf"

    def upload_file(self, filename, content, mime_type, folder_id=None):
        return {
            "provider": "google_drive",
            "file_id": f"drive-new-{filename}",
            "name": filename,
            "mime_type": mime_type,
            "size": len(content),
            "modified_at": None,
            "is_folder": False,
            "parent_id": folder_id,
        }


@pytest.fixture()
def fake_drive(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.files.get_cloud_service",
        lambda db, user, provider: FakeDriveService(),
    )
    return FakeDriveService()


class TestListFiles:
    def test_list_files(self, client, auth_headers, fake_drive):
        response = client.get(
            "/api/v1/files", params={"provider": "google_drive"}, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["file_id"] == "drive-file-1"
        assert data[0]["name"] == "quarterly-report.pdf"
        assert data[0]["provider"] == "google_drive"

    def test_list_files_requires_auth(self, client):
        response = client.get("/api/v1/files")
        assert response.status_code == 401

    def test_get_file_metadata(self, client, auth_headers, fake_drive):
        response = client.get(
            "/api/v1/files/drive-file-1",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "quarterly-report.pdf"

    def test_get_missing_file_returns_404(self, client, auth_headers, fake_drive):
        response = client.get(
            "/api/v1/files/does-not-exist",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDownloadFiles:
    def test_download(self, client, auth_headers, fake_drive):
        response = client.get(
            "/api/v1/files/drive-file-1/download",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 fake content"
        assert response.headers["content-type"].startswith("application/pdf")
        assert "attachment" in response.headers["content-disposition"]
        assert "quarterly-report.pdf" in response.headers["content-disposition"]

    def test_download_requires_auth(self, client):
        response = client.get(
            "/api/v1/files/x/download", params={"provider": "google_drive"}
        )
        assert response.status_code == 401


class TestUploadFiles:
    def test_upload_stores_metadata_and_hash(self, client, auth_headers, fake_drive):
        content = b"hello world, this is a text file"
        response = client.post(
            "/api/v1/files/upload",
            data={"provider": "google_drive"},
            files={"file": ("notes.txt", content, "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        doc = response.json()
        assert doc["file_name"] == "notes.txt"
        assert doc["file_type"] == "txt"
        assert doc["file_size"] == len(content)
        assert doc["processing_status"] == "pending"
        assert doc["content_hash"] == hashlib.sha256(content).hexdigest()
        assert doc["external_file_id"] == "drive-new-notes.txt"

        # the document shows up in the documents list
        listing = client.get("/api/v1/documents", headers=auth_headers)
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["id"] == doc["id"]

    def test_upload_duplicate_content_rejected(self, client, auth_headers, fake_drive):
        content = b"identical bytes"
        for _ in range(2):
            response = client.post(
                "/api/v1/files/upload",
                data={"provider": "google_drive"},
                files={"file": ("a.txt", content, "text/plain")},
                headers=auth_headers,
            )
        assert response.status_code == 409

    def test_upload_rejects_disallowed_extension(self, client, auth_headers, fake_drive):
        response = client.post(
            "/api/v1/files/upload",
            data={"provider": "google_drive"},
            files={"file": ("evil.exe", b"MZ...", "application/x-msdownload")},
            headers=auth_headers,
        )
        assert response.status_code == 415

    def test_upload_rejects_empty_file(self, client, auth_headers, fake_drive):
        response = client.post(
            "/api/v1/files/upload",
            data={"provider": "google_drive"},
            files={"file": ("empty.txt", b"", "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_upload_requires_auth(self, client, fake_drive):
        response = client.post(
            "/api/v1/files/upload",
            data={"provider": "google_drive"},
            files={"file": ("notes.txt", b"x", "text/plain")},
        )
        assert response.status_code == 401


class TestImportFiles:
    def test_import_stores_metadata(self, client, auth_headers, fake_drive):
        response = client.post(
            "/api/v1/files/drive-file-1/import",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        doc = response.json()
        assert doc["file_name"] == "quarterly-report.pdf"
        assert doc["file_type"] == "pdf"
        assert doc["file_size"] == 2048
        assert doc["mime_type"] == "application/pdf"
        assert doc["external_file_id"] == "drive-file-1"

    def test_import_is_idempotent(self, client, auth_headers, fake_drive):
        first = client.post(
            "/api/v1/files/drive-file-1/import",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        second = client.post(
            "/api/v1/files/drive-file-1/import",
            params={"provider": "google_drive"},
            headers=auth_headers,
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        listing = client.get("/api/v1/documents", headers=auth_headers)
        assert listing.json()["total"] == 1


class TestDocumentsApi:
    def test_documents_start_empty(self, client, auth_headers):
        response = client.get("/api/v1/documents", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"total": 0, "items": []}

    def test_document_status_and_404(self, client, auth_headers, fake_drive):
        created = client.post(
            "/api/v1/files/drive-file-1/import",
            params={"provider": "google_drive"},
            headers=auth_headers,
        ).json()

        status = client.get(f"/api/v1/documents/{created['id']}/status", headers=auth_headers)
        assert status.status_code == 200
        assert status.json()["processing_status"] == "pending"
        assert status.json()["file_name"] == "quarterly-report.pdf"

        detail = client.get(f"/api/v1/documents/{created['id']}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["id"] == created["id"]

        missing = client.get(
            "/api/v1/documents/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert missing.status_code == 404