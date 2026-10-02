"""Configuration-isolation guarantees for the test suite.

These tests encode the Phase 6 regression contract: the suite must be
deterministic NO MATTER what the developer's real .env contains. conftest.py
force-sets environment variables (which pydantic-settings prefers over .env),
so every external service is unconfigured for the suite unless a test
explicitly monkeypatches a setting back on. If one of these tests fails, some
change has reintroduced .env leakage into the test run.
"""
from app.config.settings import get_settings
from app.services.embeddings.manager import embedding_available
from app.services.llm.manager import llm_configured


class TestExternalServicesDefaultToUnconfigured:
    def test_jina_not_configured(self):
        assert get_settings().JINA_API_KEY == ""
        assert embedding_available() is False

    def test_nvidia_not_configured(self):
        assert get_settings().NVIDIA_API_KEY == ""

    def test_ollama_not_configured(self):
        assert get_settings().OLLAMA_MODEL == ""
        assert llm_configured() is False

    def test_qdrant_is_embedded_not_a_server(self):
        # in-memory mode — the suite can never reach a real Qdrant server
        assert get_settings().QDRANT_URL == ":memory:"
        assert get_settings().QDRANT_API_KEY == ""

    def test_s3_env_credentials_isolated(self):
        settings = get_settings()
        assert settings.S3_ACCESS_KEY_ID == ""
        assert settings.S3_SECRET_ACCESS_KEY == ""
        assert settings.S3_BUCKET_NAME == ""

    def test_database_is_in_memory_sqlite(self):
        assert get_settings().DATABASE_URL == "sqlite:///:memory:"

    def test_local_storage_is_not_the_repo_storage_dir(self):
        assert not get_settings().LOCAL_STORAGE_PATH.startswith("./storage")
        assert "ai-platform-tests-" in get_settings().LOCAL_STORAGE_PATH

    def test_opt_in_pattern_works_via_monkeypatch(self, monkeypatch):
        # tests that need a configured service monkeypatch the setting —
        # ambient .env values are never the source
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "explicit-test-key")
        assert llm_configured() is True
        monkeypatch.undo()
        assert llm_configured() is False
