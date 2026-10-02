"""Unit tests for the Jina AI embedding service.

All HTTP traffic is intercepted with httpx.MockTransport — no real API key,
no network, deterministic vectors.
"""
import httpx
import pytest

from app.config.settings import get_settings
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.jina import (
    TASK_PASSAGE,
    TASK_QUERY,
    JinaEmbeddingService,
)

API_KEY = "jina-test-key-123"
TEST_DIMENSIONS = 4


class JinaAPIRecorder:
    """Configurable fake Jina /v1/embeddings endpoint."""

    def __init__(self, status=200, response=None, shuffle=False, raise_exc=None):
        self.requests: list[httpx.Request] = []
        self.status = status
        self.response = response
        self.shuffle = shuffle
        self.raise_exc = raise_exc

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.response is not None:
            return httpx.Response(self.status, json=self.response)
        body = request.read()
        import json

        payload = json.loads(body)
        dims = payload.get("dimensions", 4)
        data = [
            {"object": "embedding", "index": i, "embedding": [float(len(t))] + [1.0] * (dims - 1)}
            for i, t in enumerate(payload["input"])
        ]
        if self.shuffle:
            data.reverse()
        return httpx.Response(200, json={"model": payload["model"], "data": data})


def make_service(recorder: JinaAPIRecorder, **kwargs) -> JinaEmbeddingService:
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    kwargs.setdefault("api_key", API_KEY)
    kwargs.setdefault("dimensions", TEST_DIMENSIONS)
    kwargs.setdefault("batch_size", 64)
    return JinaEmbeddingService(client=client, **kwargs)


class TestBasicEmbedding:
    def test_empty_input_makes_no_request(self):
        recorder = JinaAPIRecorder()
        service = make_service(recorder)
        assert service.embed_texts([]) == []
        assert service.embed_texts(None) == []
        assert recorder.requests == []

    def test_single_text(self):
        recorder = JinaAPIRecorder()
        vectors = make_service(recorder).embed_texts(["hello"])
        assert len(vectors) == 1
        assert len(vectors[0]) == TEST_DIMENSIONS
        assert len(recorder.requests) == 1

    def test_multiple_texts_preserve_order(self):
        recorder = JinaAPIRecorder()
        texts = ["a", "bb", "ccc", "dddd"]
        vectors = make_service(recorder).embed_texts(texts)
        assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0]

    def test_order_preserved_when_api_shuffles(self):
        recorder = JinaAPIRecorder(shuffle=True)
        texts = ["a", "bb", "ccc"]
        vectors = make_service(recorder).embed_texts(texts)
        # vectors sorted back by index despite reversed response order
        assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]

    def test_empty_string_replaced(self):
        recorder = JinaAPIRecorder()
        make_service(recorder).embed_texts(["", "x"])
        import json

        sent = json.loads(recorder.requests[0].read())
        assert sent["input"][0] == " " and sent["input"][1] == "x"

    def test_long_text_truncated(self):
        recorder = JinaAPIRecorder()
        make_service(recorder).embed_texts(["x" * 50_000])
        import json

        sent = json.loads(recorder.requests[0].read())
        assert len(sent["input"][0]) == 30_000


class TestBatching:
    def test_batches_by_configured_size(self):
        recorder = JinaAPIRecorder()
        service = make_service(recorder, batch_size=2)
        vectors = service.embed_texts(["t1", "t2", "t3", "t4", "t5"])
        assert len(vectors) == 5
        assert len(recorder.requests) == 3
        import json

        sizes = [len(json.loads(r.read())["input"]) for r in recorder.requests]
        assert sizes == [2, 2, 1]

    def test_order_preserved_across_batches(self):
        recorder = JinaAPIRecorder()
        service = make_service(recorder, batch_size=2)
        texts = [f"text-{i}" for i in range(5)]
        vectors = service.embed_texts(texts)
        assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


class TestRequestConstruction:
    def test_request_structure_for_passages(self):
        recorder = JinaAPIRecorder()
        make_service(recorder, model="jina-embeddings-v3").embed_texts(["chunk one", "chunk two"])
        request = recorder.requests[0]
        assert str(request.url) == get_settings().JINA_API_URL
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"

        import json

        body = json.loads(request.read())
        assert body["model"] == "jina-embeddings-v3"
        assert body["task"] == TASK_PASSAGE
        assert body["dimensions"] == TEST_DIMENSIONS
        assert body["input"] == ["chunk one", "chunk two"]

    def test_query_uses_retrieval_query_task(self):
        recorder = JinaAPIRecorder()
        make_service(recorder).embed_query("find documents about machine learning")
        import json

        body = json.loads(recorder.requests[0].read())
        assert body["task"] == TASK_QUERY
        assert body["input"] == ["find documents about machine learning"]

    def test_passage_and_query_tasks_differ(self):
        recorder = JinaAPIRecorder()
        service = make_service(recorder)
        service.embed_texts(["a passage"])
        service.embed_query("a query")
        import json

        tasks = [json.loads(r.read())["task"] for r in recorder.requests]
        assert tasks == [TASK_PASSAGE, TASK_QUERY]

    def test_dimensions_from_settings(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "EMBEDDING_DIMENSIONS", 8)
        recorder = JinaAPIRecorder()
        service = JinaEmbeddingService(
            api_key=API_KEY,
            client=httpx.Client(transport=httpx.MockTransport(recorder.handler)),
        )
        service.embed_texts(["hello"])
        import json

        assert json.loads(recorder.requests[0].read())["dimensions"] == 8


class TestErrors:
    def test_not_configured_raises_without_request(self):
        recorder = JinaAPIRecorder()
        service = JinaEmbeddingService(
            api_key="",
            client=None,  # no injected client → would need a real key
        )
        with pytest.raises(EmbeddingError, match="JINA_API_KEY"):
            service.embed_texts(["hello"])
        assert recorder.requests == []

    def test_http_error_surfaced(self):
        recorder = JinaAPIRecorder(status=401, response={"detail": "invalid api key"})
        with pytest.raises(EmbeddingError, match="401"):
            make_service(recorder).embed_texts(["hello"])

    def test_server_error_surfaced(self):
        recorder = JinaAPIRecorder(status=500, response={"detail": "boom"})
        with pytest.raises(EmbeddingError, match="500"):
            make_service(recorder).embed_texts(["hello"])

    def test_timeout_wrapped(self):
        recorder = JinaAPIRecorder(raise_exc=httpx.ConnectTimeout("timed out"))
        with pytest.raises(EmbeddingError, match="failed"):
            make_service(recorder).embed_texts(["hello"])

    def test_connection_error_wrapped(self):
        recorder = JinaAPIRecorder(raise_exc=httpx.ConnectError("refused"))
        with pytest.raises(EmbeddingError, match="failed"):
            make_service(recorder).embed_texts(["hello"])

    def test_malformed_missing_data(self):
        recorder = JinaAPIRecorder(response={"model": "x"})
        with pytest.raises(EmbeddingError, match="Malformed"):
            make_service(recorder).embed_texts(["hello"])

    def test_malformed_wrong_count(self):
        recorder = JinaAPIRecorder(
            response={"data": [{"object": "embedding", "index": 0, "embedding": [1.0] * TEST_DIMENSIONS}]}
        )
        with pytest.raises(EmbeddingError, match="Malformed"):
            make_service(recorder).embed_texts(["one", "two"])

    def test_malformed_missing_index(self):
        recorder = JinaAPIRecorder(
            response={"data": [{"object": "embedding", "embedding": [1.0] * TEST_DIMENSIONS}]}
        )
        with pytest.raises(EmbeddingError, match="Malformed"):
            make_service(recorder).embed_texts(["hello"])

    def test_malformed_missing_vector(self):
        recorder = JinaAPIRecorder(response={"data": [{"object": "embedding", "index": 0}]})
        with pytest.raises(EmbeddingError, match="Malformed"):
            make_service(recorder).embed_texts(["hello"])

    def test_wrong_dimensions_rejected(self):
        recorder = JinaAPIRecorder(
            response={"data": [{"object": "embedding", "index": 0, "embedding": [1.0, 2.0]}]}
        )
        with pytest.raises(EmbeddingError, match="dimension"):
            make_service(recorder).embed_texts(["hello"])

    def test_non_json_response(self):
        recorder = JinaAPIRecorder(response=None)
        client = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))
        )
        service = JinaEmbeddingService(api_key=API_KEY, dimensions=TEST_DIMENSIONS, client=client)
        with pytest.raises(EmbeddingError, match="non-JSON"):
            service.embed_texts(["hello"])

    def test_api_key_never_leaks_into_errors(self):
        recorder = JinaAPIRecorder(status=500, response={"detail": "internal error"})
        with pytest.raises(EmbeddingError) as excinfo:
            make_service(recorder).embed_texts(["hello"])
        assert API_KEY not in str(excinfo.value)
