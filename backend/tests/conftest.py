"""Shared test fixtures.

CRITICAL — configuration isolation:
Environment variables are set BEFORE any app import. pydantic-settings gives
real environment variables precedence over the developer's ``.env`` file, so
force-setting them here pins the entire test configuration. The suite is
therefore deterministic NO MATTER what the developer's local ``.env``
contains — tests can never see real JINA/NVIDIA/Ollama/S3 credentials and can
never make real external requests. Individual tests that need a service
"configured" monkeypatch the setting explicitly (existing pattern).

All external services default to UNCONFIGURED for the suite:
- JINA_API_KEY / NVIDIA_API_KEY empty  → embedding/LLM report "not configured"
- OLLAMA_MODEL empty                    → the Ollama fallback is disabled
- QDRANT_URL=':memory:'                 → embedded Qdrant, no server needed
- S3_* empty                            → no accidental cloud fallback
- LOCAL_STORAGE_PATH → temp dir         → tests never write into ./storage/
"""
import os
import tempfile

# ── Application configuration (forced, not setdefault — .env must not leak) ──
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["LOCAL_STORAGE_PATH"] = tempfile.mkdtemp(prefix="ai-platform-tests-")

# ── External AI services: always unconfigured unless a test opts in ──────────
os.environ["JINA_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""
os.environ["OLLAMA_MODEL"] = ""

# ── Vector DB: embedded in-memory mode — never a real Qdrant server ──────────
os.environ["QDRANT_URL"] = ":memory:"
os.environ["QDRANT_API_KEY"] = ""

# ── Cloud providers: no accidental fallback to real .env credentials ─────────
os.environ["S3_ACCESS_KEY_ID"] = ""
os.environ["S3_SECRET_ACCESS_KEY"] = ""
os.environ["S3_BUCKET_NAME"] = ""
os.environ["S3_ENDPOINT_URL"] = ""
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

import pytest
from fastapi.testclient import TestClient

from app.database.session import Base, SessionLocal, engine, get_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def clean_tables(setup_database):
    """Clear every table after each test (reversed dependency order)."""
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def user_payload() -> dict:
    return {"name": "Test User", "email": "test@example.com", "password": "supersecret123"}


@pytest.fixture()
def auth_headers(client: TestClient, user_payload: dict) -> dict:
    """Register a user and return an 'Authorization: Bearer ...' header."""
    response = client.post("/api/v1/auth/register", json=user_payload)
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
