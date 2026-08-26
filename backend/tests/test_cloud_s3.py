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