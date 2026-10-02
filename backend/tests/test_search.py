"""End-to-end Phase 4 tests: pipeline embedding stage, semantic search API and
the document embed endpoint.

Uses deterministic fake embeddings (keyword → basis vector) and the real
in-memory Qdrant engine. No Jina API key, no Qdrant server, no network.
"""
import io
from uuid import UUID

import pytest
from qdrant_client import QdrantClient

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models.models import Document, DocumentChunk, JobType, ProcessingJob, ProcessingStatus
from app.services.embeddings.base import EmbeddingError
from app.services.vector_store.qdrant_store import QdrantVectorStore

TEST_DIMENSIONS = 3
KEYWORDS = ("python", "finance")


class FakeEmbeddingProvider:
    """Deterministic embeddings: 'python' → e0, 'finance' → e1, else → e2."""

    model = "fake-embedding-model"

    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def _vec(text: str) -> list[float]:
        text = (text or "").lower()
        vector = [0.0] * TEST_DIMENSIONS
        if "python" in text:
            vector[0] = 1.0
        if "finance" in text:
            vector[1] = 1.0
        if not any(vector):
            vector[2] = 1.0
        return vector

    def embed_texts(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeCloudService:
    """Cloud provider stand-in serving files from an in-memory dict."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def get_file(self, file_id):
        import mimetypes

        from fastapi import HTTPException

        if file_id not in self.files:
            raise HTTPException(status_code=404, detail="File not found")
        name = file_id.rsplit("/", 1)[-1]
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return {
            "provider": "s3", "file_id": file_id, "name": name,
            "mime_type": mime_type, "size": len(self.files[file_id]),
            "modified_at": None, "is_folder": False, "parent_id": None,
        }

    def download_file(self, file_id):
        from fastapi import HTTPException

        if file_id not in self.files:
            raise HTTPException(status_code=404, detail="File not found")
        name = file_id.rsplit("/", 1)[-1]
        return name, io.BytesIO(self.files[file_id]), "text/plain"


@pytest.fixture()
def fake_cloud(monkeypatch):
    files: dict[str, bytes] = {}
    service = FakeCloudService(files)
    monkeypatch.setattr(
        "app.api.v1.endpoints.files.get_cloud_service", lambda db, user, provider: service
    )
    monkeypatch.setattr(
        "app.services.document_processing.pipeline.get_cloud_service",
        lambda db, user, provider: service,
    )
    return files


@pytest.fixture()
def fake_embedding(monkeypatch):
    """Fake Jina provider + in-memory Qdrant wired into manager and endpoints."""
    monkeypatch.setattr(
        "app.services.embeddings.manager.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.ai.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )
    monkeypatch.setattr(get_settings(), "EMBEDDING_DIMENSIONS", TEST_DIMENSIONS)
    store = QdrantVectorStore(QdrantClient(":memory:"), "test_chunks")
    monkeypatch.setattr(QdrantVectorStore, "from_settings", classmethod(lambda cls: store))
    return store


@pytest.fixture()
def jina_enabled(monkeypatch):
    """Make the pipeline/endpoints believe embeddings are configured."""
    monkeypatch.setattr(get_settings(), "JINA_API_KEY", "test-jina-key")


def _import_and_process(client, auth_headers, provider: str, file_id: str) -> str:
    response = client.post(
        f"/api/v1/files/{file_id}/import", params={"provider": provider}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    doc_id = response.json()["id"]
    response = client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)
    assert response.status_code == 202, response.text
    return doc_id


def _get_doc(doc_id):
    db = SessionLocal()
    try:
        return db.get(Document, UUID(str(doc_id)))
    finally:
        db.close()


def _chunks_of(doc_id):
    db = SessionLocal()
    try:
        return (
            db.query(DocumentChunk)
            .filter_by(document_id=UUID(str(doc_id)))
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
    finally:
        db.close()


# ── Pipeline integration ─────────────────────────────────────────────────────

class TestPipelineEmbeddingStage:
    def test_processing_embeds_automatically(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled):
        fake_cloud["code.txt"] = b"python programming tutorial\n\npython data science basics"
        doc_id = _import_and_process(client, auth_headers, "s3", "code.txt")

        document = _get_doc(doc_id)
        assert document.processing_status == ProcessingStatus.completed
        assert document.embedding_completed is True
        chunks = _chunks_of(doc_id)
        assert chunks and all(c.embedding_id for c in chunks)

        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        embed_jobs = [j for j in status["jobs"] if j["job_type"] == "embedding"]
        assert embed_jobs and embed_jobs[0]["status"] == "completed"

    def test_embedding_failure_fails_document_not_silent(
        self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled, monkeypatch
    ):
        def exploding_embed(db, document):
            raise EmbeddingError("Jina API returned HTTP 500: boom")

        monkeypatch.setattr(
            "app.services.document_processing.pipeline.embedding_available", lambda: True
        )
        monkeypatch.setattr(
            "app.services.document_processing.pipeline.embed_document_chunks", exploding_embed
        )
        fake_cloud["notes.txt"] = b"some text that chunks fine"
        doc_id = _import_and_process(client, auth_headers, "s3", "notes.txt")

        document = _get_doc(doc_id)
        assert document.processing_status == ProcessingStatus.failed
        assert document.embedding_completed is False

        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        assert status["processing_status"] == "failed"
        embed_jobs = [j for j in status["jobs"] if j["job_type"] == "embedding"]
        assert embed_jobs and embed_jobs[0]["status"] == "failed"
        assert "500" in (embed_jobs[0]["error_message"] or "")

    def test_phase3_processing_unchanged_without_jina_key(
        self, client, auth_headers, fake_cloud, fake_embedding
    ):
        # no JINA_API_KEY configured in the test environment
        fake_cloud["notes.txt"] = b"plain phase 3 document processing"
        doc_id = _import_and_process(client, auth_headers, "s3", "notes.txt")

        document = _get_doc(doc_id)
        assert document.processing_status == ProcessingStatus.completed
        assert document.embedding_completed is False
        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        assert all(j["job_type"] != "embedding" for j in status["jobs"])  # stage skipped


# ── Search API ───────────────────────────────────────────────────────────────

class TestSearchApi:
    @pytest.fixture()
    def indexed(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled):
        fake_cloud["code.txt"] = b"python programming tutorial for beginners\n\npython data science"
        fake_cloud["money.txt"] = b"finance budget planning next year\n\nfinance investment notes"
        fake_cloud["readme.csv"] = b"topic,note\nmisc,general observations about weather"
        self.code_doc = _import_and_process(client, auth_headers, "s3", "code.txt")
        self.money_doc = _import_and_process(client, auth_headers, "google_drive", "money.txt")
        self.misc_doc = _import_and_process(client, auth_headers, "s3", "readme.csv")
        return self

    def test_semantic_search_returns_relevant_chunk(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "python programming"}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] >= 1
        assert "python" in data["results"][0]["content"].lower()
        assert data["results"][0]["document_id"] == self.code_doc
        # ranked: top score >= every other score
        scores = [r["score"] for r in data["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_result_shape_and_hydration(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "python", "limit": 3}, headers=auth_headers
        )
        hit = response.json()["results"][0]
        for field in ("score", "chunk_id", "chunk_index", "page_number", "content",
                      "token_count", "document_id", "file_name", "mime_type", "source"):
            assert field in hit
        assert hit["content"]  # hydrated from PostgreSQL, not Qdrant
        assert hit["mime_type"] == "text/plain"
        assert hit["source"] == "s3"
        assert hit["file_name"] == "code.txt"

    def test_filter_by_document_id(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search",
            json={"query": "python", "document_id": self.money_doc},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert all(r["document_id"] == self.money_doc for r in response.json()["results"])

    def test_filter_by_source(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "python", "source": "google_drive"}, headers=auth_headers
        )
        assert all(r["source"] == "google_drive" for r in response.json()["results"])

    def test_filter_by_mime_type(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "observations", "mime_type": "text/csv"}, headers=auth_headers
        )
        assert response.json()["total"] >= 1
        assert all(r["file_name"] == "readme.csv" for r in response.json()["results"])

    def test_filter_excluding_everything_gives_empty(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "python", "mime_type": "video/mp4"}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_min_score_filters_weak_matches(self, client, auth_headers, indexed):
        response = client.post(
            "/api/v1/search", json={"query": "python", "min_score": 0.5}, headers=auth_headers
        )
        assert all(r["score"] >= 0.5 for r in response.json()["results"])

    def test_user_isolation(self, client, auth_headers, indexed):
        other = {"name": "Second", "email": "second@example.com", "password": "secondpass123"}
        client.post("/api/v1/auth/register", json=other)
        token = client.post(
            "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
        ).json()["access_token"]
        response = client.post(
            "/api/v1/search", json={"query": "python"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0  # other user has no vectors

    def test_requires_authentication(self, client):
        response = client.post("/api/v1/search", json={"query": "python"})
        assert response.status_code == 401

    def test_not_configured_returns_503(self, client, auth_headers, fake_cloud):
        response = client.post("/api/v1/search", json={"query": "python"}, headers=auth_headers)
        assert response.status_code == 503

    def test_invalid_request_rejected(self, client, auth_headers, fake_embedding, jina_enabled):
        for bad in ({"query": ""}, {"query": "x", "limit": 0}, {"query": "x", "limit": 999},
                    {"query": "x", "min_score": 1.5}, {}, {"query": "x", "source": "dropbox"}):
            response = client.post("/api/v1/search", json=bad, headers=auth_headers)
            assert response.status_code == 422, bad

    def test_jina_failure_returns_502(self, client, auth_headers, fake_embedding, jina_enabled, monkeypatch):
        class ExplodingProvider:
            model = "fake"

            def embed_texts(self, texts):
                raise EmbeddingError("Jina API request failed: timeout")

            def embed_query(self, text):
                raise EmbeddingError("Jina API request failed: timeout")

        monkeypatch.setattr(
            "app.api.v1.endpoints.ai.get_embedding_provider", lambda: ExplodingProvider()
        )
        response = client.post("/api/v1/search", json={"query": "python"}, headers=auth_headers)
        assert response.status_code == 502
        assert "Jina" in response.json()["detail"]

    def test_qdrant_failure_returns_502(self, client, auth_headers, fake_embedding, jina_enabled, monkeypatch):
        from app.services.vector_store.qdrant_store import VectorStoreError

        def exploding_from_settings(cls):
            raise VectorStoreError("Qdrant unreachable")

        monkeypatch.setattr(QdrantVectorStore, "from_settings", classmethod(exploding_from_settings))
        response = client.post("/api/v1/search", json={"query": "python"}, headers=auth_headers)
        assert response.status_code == 502
        assert "Qdrant" in response.json()["detail"]


# ── Embed endpoint ───────────────────────────────────────────────────────────

class TestEmbedEndpoint:
    def test_embed_processed_document(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled):
        fake_cloud["code.txt"] = b"python content that will be embedded"
        response = client.post(
            "/api/v1/files/code.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)

        response = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "completed"
        assert data["chunks_embedded"] >= 1
        assert data["model"] == "fake-embedding-model"

        assert _get_doc(doc_id).embedding_completed is True
        # now searchable
        search = client.post("/api/v1/search", json={"query": "python"}, headers=auth_headers)
        assert search.status_code == 200
        assert search.json()["total"] >= 1

    def test_reembedding_is_retry_safe_no_duplicates(
        self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled
    ):
        fake_cloud["code.txt"] = b"python content embedded twice"
        response = client.post(
            "/api/v1/files/code.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)

        first = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers).json()
        second = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers).json()
        assert first["chunks_embedded"] == second["chunks_embedded"]

        # vector count unchanged after re-embed (no duplicates)
        all_results = fake_embedding.search(
            [1.0, 0.0, 0.0], user_id=_get_doc(doc_id).user_id, limit=100
        )
        doc_results = [r for r in all_results if r["document_id"] == str(doc_id)]
        assert len(doc_results) == second["chunks_embedded"]

    def test_embed_without_chunks_returns_409(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled):
        fake_cloud["notes.txt"] = b"imported but never processed"
        response = client.post(
            "/api/v1/files/notes.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        response = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers)
        assert response.status_code == 409

    def test_embed_unauthorized_document_404(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled):
        fake_cloud["code.txt"] = b"someone else's python document"
        response = client.post(
            "/api/v1/files/code.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]

        other = {"name": "Second", "email": "second@example.com", "password": "secondpass123"}
        client.post("/api/v1/auth/register", json=other)
        token = client.post(
            "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
        ).json()["access_token"]
        response = client.post(
            f"/api/v1/documents/{doc_id}/embed", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_embed_not_configured_503(self, client, auth_headers, fake_cloud):
        fake_cloud["notes.txt"] = b"plain notes"
        response = client.post(
            "/api/v1/files/notes.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        response = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers)
        assert response.status_code == 503

    def test_embed_jina_failure_502(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled, monkeypatch):
        fake_cloud["code.txt"] = b"python document"
        response = client.post(
            "/api/v1/files/code.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)

        def exploding_embed(db, document):
            raise EmbeddingError("Jina API returned HTTP 429: rate limited")

        monkeypatch.setattr("app.api.v1.endpoints.documents.embed_document_chunks", exploding_embed)
        response = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers)
        assert response.status_code == 502
        assert "429" in response.json()["detail"]

        # failure recorded in the job history
        status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers).json()
        embed_jobs = [j for j in status["jobs"] if j["job_type"] == "embedding"]
        assert embed_jobs and embed_jobs[-1]["status"] == "failed"

    def test_embed_qdrant_failure_502(self, client, auth_headers, fake_cloud, fake_embedding, jina_enabled, monkeypatch):
        from app.services.vector_store.qdrant_store import VectorStoreError

        fake_cloud["code.txt"] = b"python document"
        response = client.post(
            "/api/v1/files/code.txt/import", params={"provider": "s3"}, headers=auth_headers
        )
        doc_id = response.json()["id"]
        client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)

        def exploding_embed(db, document):
            raise VectorStoreError("Qdrant upsert failed: connection refused")

        monkeypatch.setattr("app.api.v1.endpoints.documents.embed_document_chunks", exploding_embed)
        response = client.post(f"/api/v1/documents/{doc_id}/embed", headers=auth_headers)
        assert response.status_code == 502
        assert "Qdrant" in response.json()["detail"]
