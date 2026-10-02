"""Tests for the NVIDIA LLM provider — all HTTP via httpx.MockTransport,
no real API key, no network."""
import json

import httpx
import pytest

from app.config.settings import get_settings
from app.services.llm.base import LLMError
from app.services.llm.manager import llm_configured
from app.services.llm.nvidia import NvidiaProvider

API_KEY = "nvapi-test-key-789"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"


class NvidiaAPIRecorder:
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
        content = self.content if self.content is not None else "Semantic search retrieves by meaning."
        return httpx.Response(200, json={
            "id": "chatcmpl-1",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content},
                 "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        })


def make_provider(recorder: NvidiaAPIRecorder, **kwargs) -> NvidiaProvider:
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    kwargs.setdefault("api_key", API_KEY)
    return NvidiaProvider(client=client, **kwargs)


class TestSuccessfulGeneration:
    def test_returns_final_answer_text(self):
        provider = make_provider(NvidiaAPIRecorder())
        answer = provider.generate_answer("system prompt", "user message")
        assert answer == "Semantic search retrieves by meaning."

    def test_correct_endpoint_and_authorization(self):
        recorder = NvidiaAPIRecorder()
        make_provider(recorder).generate_answer("s", "u")
        request = recorder.requests[0]
        assert str(request.url) == ENDPOINT
        assert request.method == "POST"
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in str(request.url)  # key never in the URL

    def test_request_payload_construction(self):
        recorder = NvidiaAPIRecorder()
        provider = make_provider(recorder, model="nvidia/nemotron-3.5-lightning-30b-a3b")
        provider.generate_answer("SYSTEM-PROMPT", "USER-MESSAGE")

        body = json.loads(recorder.requests[0].read())
        assert body["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
        assert body["messages"][0] == {"role": "system", "content": "SYSTEM-PROMPT"}
        assert body["messages"][1] == {"role": "user", "content": "USER-MESSAGE"}
        assert body["stream"] is False
        assert body["max_tokens"] > 0
        # thinking/reasoning explicitly disabled — final answer only
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert "temperature" in body

    def test_model_from_settings(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "NVIDIA_MODEL", "nvidia/other-model")
        provider = NvidiaProvider(api_key=API_KEY, client=httpx.Client(
            transport=httpx.MockTransport(NvidiaAPIRecorder().handler)
        ))
        assert provider.model == "nvidia/other-model"

    def test_answer_is_stripped(self):
        provider = make_provider(NvidiaAPIRecorder(content="  padded answer  \n"))
        assert provider.generate_answer("s", "u") == "padded answer"


class TestErrors:
    def test_missing_api_key(self):
        provider = NvidiaProvider(api_key="", client=None)  # no injected client
        with pytest.raises(LLMError, match="NVIDIA_API_KEY"):
            provider.generate_answer("s", "u")

    def test_authentication_failure_http_401(self):
        recorder = NvidiaAPIRecorder(status=401, response={"error": "unauthorized"})
        with pytest.raises(LLMError, match="401"):
            make_provider(recorder).generate_answer("s", "u")

    def test_http_4xx_error(self):
        recorder = NvidiaAPIRecorder(status=400, response={"error": "bad request"})
        with pytest.raises(LLMError, match="400"):
            make_provider(recorder).generate_answer("s", "u")

    def test_http_5xx_error(self):
        recorder = NvidiaAPIRecorder(status=503, response={"error": "unavailable"})
        with pytest.raises(LLMError, match="503"):
            make_provider(recorder).generate_answer("s", "u")

    def test_timeout(self):
        recorder = NvidiaAPIRecorder(raise_exc=httpx.ConnectTimeout("timed out"))
        with pytest.raises(LLMError, match="failed"):
            make_provider(recorder).generate_answer("s", "u")

    def test_connection_failure(self):
        recorder = NvidiaAPIRecorder(raise_exc=httpx.ConnectError("refused"))
        with pytest.raises(LLMError, match="failed"):
            make_provider(recorder).generate_answer("s", "u")

    def test_malformed_response_missing_choices(self):
        recorder = NvidiaAPIRecorder(response={"choices": []})
        with pytest.raises(LLMError, match="no choices"):
            make_provider(recorder).generate_answer("s", "u")

    def test_malformed_response_missing_message(self):
        recorder = NvidiaAPIRecorder(response={"choices": [{"index": 0}]})
        with pytest.raises(LLMError, match="no answer content"):
            make_provider(recorder).generate_answer("s", "u")

    def test_missing_answer_content(self):
        recorder = NvidiaAPIRecorder(response={
            "choices": [{"message": {"role": "assistant", "content": ""}}]
        })
        with pytest.raises(LLMError, match="no answer content"):
            make_provider(recorder).generate_answer("s", "u")

    def test_non_json_response(self):
        client = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not json")
        ))
        provider = NvidiaProvider(api_key=API_KEY, client=client)
        with pytest.raises(LLMError, match="non-JSON"):
            provider.generate_answer("s", "u")

    def test_api_key_never_leaks_into_errors(self):
        recorder = NvidiaAPIRecorder(status=500, response={"error": "internal boom"})
        with pytest.raises(LLMError) as excinfo:
            make_provider(recorder).generate_answer("s", "u")
        assert API_KEY not in str(excinfo.value)


class TestConfiguration:
    def test_llm_configured_flag(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "")
        assert llm_configured() is False
        monkeypatch.setattr(get_settings(), "NVIDIA_API_KEY", "nvapi-test")
        assert llm_configured() is True
