"""Tests for the S3-compatible storage connector endpoints (Backblaze B2 / AWS S3)."""


class FakeS3Service:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def validate(self):
        return {"bucket": self.kwargs.get("bucket_name")}


def test_connect_with_request_body(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
    "app.api.v1.endpoints.cloud_s3.settings.S3_ACCESS_KEY_ID",
    "",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.settings.S3_SECRET_ACCESS_KEY",
        "",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.settings.S3_BUCKET_NAME",
        "",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.S3StorageService",
        FakeS3Service,
    )
    response = client.post(
        "/api/v1/cloud/s3/connect",
        json={
            "access_key_id": "key-id-123",
            "secret_access_key": "secret-456",
            "region": "us-west-004",
            "endpoint_url": "https://s3.us-west-004.backblazeb2.com",
            "bucket_name": "my-free-bucket",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "connected"
    assert data["provider"] == "s3"
    assert data["bucket"] == "my-free-bucket"

    # status reflects the stored connection
    status = client.get("/api/v1/cloud/s3/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["is_connected"] is True
    assert status.json()["account_identifier"] == "my-free-bucket"

    # credentials are stored encrypted, never raw
    from app.database.session import SessionLocal
    from app.models.models import CloudProvider, ConnectedCloudAccount

    db = SessionLocal()
    try:
        account = (
            db.query(ConnectedCloudAccount)
            .filter(ConnectedCloudAccount.provider == CloudProvider.s3)
            .first()
        )
        assert account is not None
        assert account.access_token_ref.startswith("enc:v1:")
        assert "key-id-123" not in account.access_token_ref
        assert account.extra_data["endpoint_url"] == "https://s3.us-west-004.backblazeb2.com"
    finally:
        db.close()

    # disconnect removes it
    response = client.delete("/api/v1/cloud/s3/disconnect", headers=auth_headers)
    assert response.status_code == 200
    status = client.get("/api/v1/cloud/s3/status", headers=auth_headers)
    assert status.json()["is_connected"] is False


def test_connect_without_credentials_returns_400(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.settings.S3_ACCESS_KEY_ID",
        "",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.settings.S3_SECRET_ACCESS_KEY",
        "",
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_s3.settings.S3_BUCKET_NAME",
        "",
    )

    response = client.post(
        "/api/v1/cloud/s3/connect",
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_connect_with_invalid_credentials_surfaces_error(client, auth_headers, monkeypatch):
    class ExplodingService:
        def __init__(self, **kwargs):
            pass

        def validate(self):
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Credentials are not valid")

    monkeypatch.setattr("app.api.v1.endpoints.cloud_s3.S3StorageService", ExplodingService)
    response = client.post(
        "/api/v1/cloud/s3/connect",
        json={"access_key_id": "bad", "secret_access_key": "bad", "bucket_name": "nope"},
        headers=auth_headers,
    )
    assert response.status_code == 400

class ListableFakeS3:
    """Fake S3 service for resolution-level tests (no network)."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def validate(self):
        return {"bucket": self.kwargs.get("bucket_name")}

    def list_files(self, folder_id="", search=None, limit=1000):
        return [{
            "provider": "s3",
            "file_id": "env-bucket-file.txt",
            "name": "env-bucket-file.txt",
            "mime_type": "text/plain",
            "size": 12,
            "modified_at": None,
            "is_folder": False,
            "parent_id": None,
        }]


def _set_env_credentials(monkeypatch):
    from app.config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "S3_ACCESS_KEY_ID", "env-key-id")
    monkeypatch.setattr(settings, "S3_SECRET_ACCESS_KEY", "env-secret")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "env-bucket")


class TestS3DisconnectSemantics:
    """Disconnect must fully block S3 access — even when the server has
    S3_* environment credentials configured (the fallback only applies to
    users who never connected)."""

    def test_env_fallback_when_never_connected(self, client, auth_headers, monkeypatch):
        _set_env_credentials(monkeypatch)
        monkeypatch.setattr("app.services.s3_storage.service.S3StorageService", ListableFakeS3)
        response = client.get("/api/v1/files", params={"provider": "s3"}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()[0]["file_id"] == "env-bucket-file.txt"

    def test_disconnect_blocks_listing_even_with_env_credentials(self, client, auth_headers, monkeypatch):
        _set_env_credentials(monkeypatch)
        monkeypatch.setattr("app.services.s3_storage.service.S3StorageService", ListableFakeS3)
        monkeypatch.setattr("app.api.v1.endpoints.cloud_s3.S3StorageService", ListableFakeS3)

        # connect → disconnect
        connect = client.post("/api/v1/cloud/s3/connect", json={
            "access_key_id": "personal-key", "secret_access_key": "personal-secret",
            "bucket_name": "personal-bucket",
        }, headers=auth_headers)
        assert connect.status_code == 200
        assert client.delete("/api/v1/cloud/s3/disconnect", headers=auth_headers).status_code == 200

        # listing is now blocked — env fallback must NOT kick in
        response = client.get("/api/v1/files", params={"provider": "s3"}, headers=auth_headers)
        assert response.status_code == 400
        assert "disconnected" in response.json()["detail"].lower()

        # status reports the disconnected state explicitly
        status = client.get("/api/v1/cloud/s3/status", headers=auth_headers).json()
        assert status["is_connected"] is False
        assert "reconnect" in (status["detail"] or "").lower()

    def test_reconnect_restores_access(self, client, auth_headers, monkeypatch):
        _set_env_credentials(monkeypatch)
        monkeypatch.setattr("app.services.s3_storage.service.S3StorageService", ListableFakeS3)
        monkeypatch.setattr("app.api.v1.endpoints.cloud_s3.S3StorageService", ListableFakeS3)

        client.post("/api/v1/cloud/s3/connect", json={
            "access_key_id": "k", "secret_access_key": "s", "bucket_name": "b",
        }, headers=auth_headers)
        client.delete("/api/v1/cloud/s3/disconnect", headers=auth_headers)

        # blocked while disconnected
        assert client.get("/api/v1/files", params={"provider": "s3"}, headers=auth_headers).status_code == 400

        # reconnect → access restored
        reconnect = client.post("/api/v1/cloud/s3/connect", json={
            "access_key_id": "k", "secret_access_key": "s", "bucket_name": "b",
        }, headers=auth_headers)
        assert reconnect.status_code == 200
        response = client.get("/api/v1/files", params={"provider": "s3"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()[0]["file_id"] == "env-bucket-file.txt"
        assert client.get("/api/v1/cloud/s3/status", headers=auth_headers).json()["is_connected"] is True

    def test_disconnect_without_connection_is_noop(self, client, auth_headers, monkeypatch):
        _set_env_credentials(monkeypatch)
        monkeypatch.setattr("app.services.s3_storage.service.S3StorageService", ListableFakeS3)
        # never connected → disconnect is a no-op and env access continues
        response = client.delete("/api/v1/cloud/s3/disconnect", headers=auth_headers)
        assert response.status_code == 200
        listing = client.get("/api/v1/files", params={"provider": "s3"}, headers=auth_headers)
        assert listing.status_code == 200
