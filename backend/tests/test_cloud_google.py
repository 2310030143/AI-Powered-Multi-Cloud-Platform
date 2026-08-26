"""Tests for the Google Drive OAuth connector endpoints."""
from datetime import datetime, timedelta, timezone

from app.utils.security import create_state_token


class FakeCredentials:
    def __init__(self):
        self.token = "fake-access-token"
        self.refresh_token = "fake-refresh-token"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)


def test_connect_returns_authorization_url(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.build_authorization_url",
        lambda state: f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
    )
    response = client.get("/api/v1/cloud/google/connect", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["authorization_url"].startswith("https://accounts.google.com")
    assert "message" in data


def test_full_oauth_callback_flow(client, auth_headers, monkeypatch):
    # 1. start the flow to obtain a valid signed state for this user
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.build_authorization_url",
        lambda state: f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
    )
    connect = client.get("/api/v1/cloud/google/connect", headers=auth_headers)
    assert connect.status_code == 200

    # 2. simulate Google's redirect with code + state
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.exchange_code_for_credentials",
        lambda code: FakeCredentials(),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.fetch_user_email",
        lambda token: "tester@gmail.com",
    )
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    state = create_state_token(me["id"], "google_connect")
    callback = client.get("/api/v1/cloud/google/callback", params={"code": "auth-code", "state": state})
    assert callback.status_code == 200, callback.text
    assert callback.json() == {"status": "connected", "provider": "google_drive", "account": "tester@gmail.com"}

    # 3. status shows the connection
    status = client.get("/api/v1/cloud/google/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["is_connected"] is True
    assert status.json()["account_identifier"] == "tester@gmail.com"

    # 4. disconnect removes it
    disconnect = client.delete("/api/v1/cloud/google/disconnect", headers=auth_headers)
    assert disconnect.status_code == 200
    status = client.get("/api/v1/cloud/google/status", headers=auth_headers)
    assert status.json()["is_connected"] is False


def test_callback_rejects_invalid_state(client):
    response = client.get(
        "/api/v1/cloud/google/callback", params={"code": "x", "state": "garbage"}
    )
    assert response.status_code == 400


def test_callback_rejects_missing_params(client):
    response = client.get("/api/v1/cloud/google/callback")
    assert response.status_code == 400


def test_callback_rejects_provider_error(client):
    response = client.get(
        "/api/v1/cloud/google/callback", params={"error": "access_denied"}
    )
    assert response.status_code == 400


def test_tokens_are_stored_encrypted(client, auth_headers, monkeypatch):
    from app.database.session import SessionLocal
    from app.models.models import CloudProvider, ConnectedCloudAccount

    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.exchange_code_for_credentials",
        lambda code: FakeCredentials(),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.cloud_google.fetch_user_email",
        lambda token: "tester@gmail.com",
    )
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    state = create_state_token(me["id"], "google_connect")
    response = client.get("/api/v1/cloud/google/callback", params={"code": "c", "state": state})
    assert response.status_code == 200

    db = SessionLocal()
    try:
        account = (
            db.query(ConnectedCloudAccount)
            .filter(ConnectedCloudAccount.provider == CloudProvider.google_drive)
            .first()
        )
        assert account is not None
        assert account.access_token_ref.startswith("enc:v1:")
        assert account.refresh_token_ref.startswith("enc:v1:")
        assert "fake-access-token" not in account.access_token_ref
    finally:
        db.close()