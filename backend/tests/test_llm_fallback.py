"""Tests for the centralized LLM fallback layer and the Ollama provider.

Every test uses fake providers or httpx.MockTransport — the suite never
contacts real NVIDIA/Ollama endpoints, regardless of the developer's .env.
"""
import httpx
import pytest

from app.config.settings import get_settings
from app.services.llm.base import LLMError, LLMProvider
from app.services.llm.manager import FallbackLLMProvider, llm_configured
from app.services.llm.ollama import OllamaProvider


class FakeProvider(LLMProvider):
    """Deterministic fake — the ONLY provider used in fallback-matrix tests."""

    def __init__(self, answer="OK", error=None):
        self.answer = answer
        self.error = error
        self.calls = 0

    @property
    def model(self):
        return "fake-model"

    def generate_answer(self, system_prompt, user_message):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.answer


# ─────────────────────────────────────────────────────────────────────────────
# Fallback matrix (fake providers only — never real NVIDIA availability)
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackProvider:
    def test_nvidia_success_returns_immediately(self):
        nvidia = FakeProvider(answer="from nvidia")
        ollama = FakeProvider(answer="from ollama")
        provider = FallbackLLMProvider(primary=nvidia, fallback=ollama)
        assert provider.generate_answer("s", "u") == "from nvidia"
        assert nvidia.calls == 1
        assert ollama.calls == 0  # fallback not touched on success
        assert provider.last_provider == "nvidia"

    def test_nvidia_failure_falls_back_to_ollama(self):
        nvidia = FakeProvider(error=LLMError("NVIDIA API returned HTTP 500: internal details"))
        ollama = FakeProvider(answer="from ollama")
        provider = FallbackLLMProvider(primary=nvidia, fallback=ollama)
        assert provider.generate_answer("s", "u") == "from ollama"
        assert ollama.calls == 1
        assert provider.last_provider == "ollama"

    def test_nvidia_unconfigured_falls_back_to_ollama(self):
        nvidia = FakeProvider(error=LLMError("NVIDIA_API_KEY is not configured on this server"))
        ollama = FakeProvider(answer="local answer")
        provider = FallbackLLMProvider(primary=nvidia, fallback=ollama)
        assert provider.generate_answer("s", "u") == "local answer"
        assert provider.last_provider == "ollama"

    def test_ollama_unavailable_reports_sanitized_error(self):
        nvidia = FakeProvider(error=LLMError("NVIDIA API request failed: connection reset"))
        ollama = FakeProvider(error=LLMError("Ollama API request failed: [Errno 111] refused"))
        provider = FallbackLLMProvider(primary=nvidia, fallback=ollama)
        with pytest.raises(LLMError) as excinfo:
            provider.generate_answer("s", "u")
        message = str(excinfo.value)
        assert "nvidia" in message and "ollama" in message
        # sanitized: response bodies / transport details stripped
        assert "connection reset" not in message
        assert "[Errno 111]" not in message
        assert "internal details" not in message

    def test_both_providers_fail(self):
        provider = FallbackLLMProvider(
            primary=FakeProvider(error=LLMError("NVIDIA_API_KEY is not configured on this server")),
            fallback=FakeProvider(error=LLMError("OLLAMA_MODEL is not configured on this server")),
        )
        with pytest.raises(LLMError, match="LLM generation failed"):
            provider.generate_answer("s", "u")

    def test_api_key_never_in_error(self):
        provider = FallbackLLMProvider(
            primary=FakeProvider(error=LLMError("NVIDIA API returned HTTP 401: key nvapi-SECRET")),
            fallback=FakeProvider(error=LLMError("Ollama API returned HTTP 404: model missing")),
        )
        with pytest.raises(LLMError) as excinfo:
            provider.generate_answer("s", "u")
        assert "nvapi-SECRET" not in str(excinfo.value)

    def test_non_llm_errors_are_not_swallowed(self):
        # fallback is for provider failures only — never bad input/bugs
        class Exploding(FakeProvider):
            def generate_answer(self, system_prompt, user_message):
                raise RuntimeError("unexpected bug")

        provider = FallbackLLMProvider(primary=Exploding(), fallback=FakeProvider())
        with pytest.raises(RuntimeError):
            provider.generate_answer("s", "u")

    def test_construction_is_side_effect_free_without_any_provider(self):
        # Real provider classes with the (isolated) test configuration:
        # no key and no model → LLMError from BOTH without any network I/O.
        provider = FallbackLLMProvider()
        with pytest.raises(LLMError) as excinfo:
            provider.generate_answer("s", "u")
        message = str(excinfo.value)
        assert "NVIDIA_API_KEY is not configured" in message
        assert "OLLAMA_MODEL is not configured" in message
        assert provider.last_provider is None


class TestLLMConfigured:
    def test_neither_configured(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "")
        monkeypatch.setattr(get_settings(), "OLLAMA_MODEL", "")
        assert llm_configured() is False

    def test_only_nvidia(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "nvapi-x")
        monkeypatch.setattr(get_settings(), "OLLAMA_MODEL", "")
        assert llm_configured() is True

    def test_only_ollama(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "")
        monkeypatch.setattr(get_settings(), "OLLAMA_MODEL", "llama3.1")
        assert llm_configured() is True


# ─────────────────────────────────────────────────────────────────────────────
# Ollama provider (HTTP via httpx.MockTransport — zero real requests)
# ─────────────────────────────────────────────────────────────────────────────

class OllamaRecorder:
    def __init__(self, status=200, response=None, raise_exc=None, content=None):
        self.requests: list[httpx.Request] = []
        self.status = status
        self.response = response
        self.raise_exc = raise_exc
        self.content = content

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.response is not None:
            return httpx.Response(self.status, json=self.response)
        content = self.content if self.content is not None else "Local answer."
        return httpx.Response(200, json={
            "model": "llama3.1", "done": True,
            "message": {"role": "assistant", "content": content},
        })


def make_ollama(recorder: OllamaRecorder, **kwargs) -> OllamaProvider:
    kwargs.setdefault("model", "llama3.1")
    kwargs.setdefault("base_url", "http://localhost:11434")
    return OllamaProvider(client=httpx.Client(transport=httpx.MockTransport(recorder.handler)), **kwargs)


class TestOllamaProvider:
    def test_success(self):
        provider = make_ollama(OllamaRecorder(content="  trimmed answer  "))
        assert provider.generate_answer("s", "u") == "trimmed answer"

    def test_request_construction(self):
        recorder = OllamaRecorder()
        make_ollama(recorder).generate_answer("SYSTEM", "USER")
        request = recorder.requests[0]
        assert str(request.url) == "http://localhost:11434/api/chat"
        import json

        payload = json.loads(request.read())
        assert payload["model"] == "llama3.1"
        assert payload["messages"][0] == {"role": "system", "content": "SYSTEM"}
        assert payload["messages"][1] == {"role": "user", "content": "USER"}
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0.2

    def test_never_downloads_models(self):
        recorder = OllamaRecorder()
        make_ollama(recorder).generate_answer("s", "u")
        # only the chat endpoint is ever called — no /api/pull, no downloads
        assert all(str(r.url).endswith("/api/chat") for r in recorder.requests)
        assert not any("pull" in str(r.url) for r in recorder.requests)

    def test_unconfigured_model_makes_zero_requests(self):
        recorder = OllamaRecorder()
        provider = OllamaProvider(model="", client=httpx.Client(
            transport=httpx.MockTransport(recorder.handler)
        ))
        with pytest.raises(LLMError, match="OLLAMA_MODEL"):
            provider.generate_answer("s", "u")
        assert recorder.requests == []

    def test_construction_makes_zero_requests(self):
        recorder = OllamaRecorder()
        OllamaProvider(model="llama3.1", client=httpx.Client(
            transport=httpx.MockTransport(recorder.handler)
        ))  # construct only
        assert recorder.requests == []

    def test_connection_refused(self):
        recorder = OllamaRecorder(raise_exc=httpx.ConnectError("[Errno 111] Connection refused"))
        with pytest.raises(LLMError, match="Ollama API request failed"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_timeout(self):
        recorder = OllamaRecorder(raise_exc=httpx.ConnectTimeout("timed out"))
        with pytest.raises(LLMError, match="Ollama API request failed"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_model_not_found_http_404(self):
        recorder = OllamaRecorder(status=404, response={"error": "model 'x' not found"})
        with pytest.raises(LLMError, match="404"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_http_5xx(self):
        recorder = OllamaRecorder(status=500, response={"error": "boom"})
        with pytest.raises(LLMError, match="500"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_malformed_response(self):
        recorder = OllamaRecorder(response={"done": True})  # no message
        with pytest.raises(LLMError, match="no answer content"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_empty_content(self):
        recorder = OllamaRecorder(response={"message": {"content": "   "}})
        with pytest.raises(LLMError, match="no answer content"):
            make_ollama(recorder).generate_answer("s", "u")

    def test_non_json_response(self):
        client = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not json")
        ))
        provider = OllamaProvider(model="llama3.1", client=client)
        with pytest.raises(LLMError, match="non-JSON"):
            provider.generate_answer("s", "u")

    def test_base_url_from_settings(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "OLLAMA_BASE_URL", "http://ollama-host:1234/")
        provider = OllamaProvider(model="llama3.1", client=httpx.Client(
            transport=httpx.MockTransport(OllamaRecorder().handler)
        ))
        provider.generate_answer("s", "u")
        assert provider.base_url == "http://ollama-host:1234"
