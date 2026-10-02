"""Tests for the Qdrant vector store (in-memory Qdrant — real search behavior,
no server required)."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.services.vector_store.qdrant_store import QdrantVectorStore, VectorStoreError

TEST_DIMENSIONS = 4


@pytest.fixture()
def store():
    return QdrantVectorStore(QdrantClient(":memory:"), "test_chunks")


def make_document(doc_id=None, file_name="notes.txt", mime_type="text/plain", source="s3"):
    return SimpleNamespace(
        id=doc_id or uuid4(),
        file_name=file_name,
        mime_type=mime_type,
        provider=SimpleNamespace(value=source),
    )


def make_user(user_id=None):
    return SimpleNamespace(id=user_id or uuid4())


def make_chunks(document_id, contents, page_numbers=None):
    return [
        SimpleNamespace(
            id=uuid4(),
            chunk_index=i,
            page_number=(page_numbers[i] if page_numbers else i + 1),
            content=content,
            token_count=len(content) // 4,
        )
        for i, content in enumerate(contents)
    ]


class TestCollection:
    def test_creates_once(self, store):
        assert store.ensure_collection(TEST_DIMENSIONS) is True
        assert store.ensure_collection(TEST_DIMENSIONS) is False  # already exists

    def test_cosine_distance_and_dimensions(self, store):
        from qdrant_client import models

        store.ensure_collection(TEST_DIMENSIONS)
        info = store.client.get_collection(store.collection_name)
        vectors = info.config.params.vectors
        assert vectors.size == TEST_DIMENSIONS
        assert vectors.distance == models.Distance.COSINE


class TestPayload:
    def test_payload_is_metadata_only(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user, document = make_user(), make_document()
        chunks = make_chunks(document.id, ["python chunk text"])
        store.upsert_document_chunks(document, user, chunks, [[1.0, 0, 0, 0]])

        # stored payload carries all required metadata (incl. user_id)
        stored = store.client.retrieve(store.collection_name, ids=[str(chunks[0].id)], with_payload=True)
        payload = stored[0].payload
        for field in ("user_id", "document_id", "chunk_id", "chunk_index",
                      "page_number", "source", "file_name", "mime_type"):
            assert field in payload
        assert payload["user_id"] == str(user.id)
        assert payload["document_id"] == str(document.id)
        assert payload["source"] == "s3"
        assert payload["mime_type"] == "text/plain"
        assert "content" not in payload  # chunk text stays in PostgreSQL

        results = store.search([1.0, 0, 0, 0], user_id=user.id)
        hit = results[0]
        assert hit["document_id"] == str(document.id)
        assert hit["chunk_id"] == str(chunks[0].id)
        assert "content" not in hit


class TestUpsertAndSearch:
    def test_roundtrip(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user, document = make_user(), make_document()
        chunks = make_chunks(document.id, ["python chunk text"])
        stored = store.upsert_document_chunks(document, user, chunks, [[1.0, 0.0, 0.0, 0.0]])
        assert stored == 1

        results = store.search([1.0, 0.0, 0.0, 0.0], user_id=user.id)
        assert len(results) == 1
        assert results[0]["chunk_id"] == str(chunks[0].id)
        assert results[0]["score"] == pytest.approx(1.0, abs=1e-6)

    def test_count_mismatch_raises(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        document, user = make_document(), make_user()
        chunks = make_chunks(document.id, ["a", "b"])
        with pytest.raises(VectorStoreError, match="mismatch"):
            store.upsert_document_chunks(document, user, chunks, [[0.0] * TEST_DIMENSIONS])

    def test_ranking_by_similarity(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user, document = make_user(), make_document()
        chunks = make_chunks(document.id, ["near", "far"])
        store.upsert_document_chunks(document, user, chunks, [[1.0, 0, 0, 0], [0.0, 1.0, 0, 0]])
        results = store.search([0.9, 0.1, 0, 0], user_id=user.id)
        assert results[0]["chunk_id"] == str(chunks[0].id)
        assert results[0]["score"] > results[1]["score"]

    def test_limit(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user, document = make_user(), make_document()
        chunks = make_chunks(document.id, [f"chunk {i}" for i in range(10)])
        store.upsert_document_chunks(document, user, chunks, [[1.0, 0, 0, 0]] * 10)
        assert len(store.search([1.0, 0, 0, 0], user_id=user.id, limit=3)) == 3

    def test_empty_results_for_unknown_user(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user, document = make_user(), make_document()
        store.upsert_document_chunks(document, user, make_chunks(document.id, ["x"]), [[1.0, 0, 0, 0]])
        assert store.search([1.0, 0, 0, 0], user_id=uuid4()) == []


class TestUserIsolation:
    def test_users_only_see_own_vectors(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user1, user2 = make_user(), make_user()
        doc1, doc2 = make_document(), make_document()
        store.upsert_document_chunks(doc1, user1, make_chunks(doc1.id, ["user one"]), [[1.0, 0, 0, 0]])
        store.upsert_document_chunks(doc2, user2, make_chunks(doc2.id, ["user two"]), [[1.0, 0, 0, 0]])

        assert len(store.search([1.0, 0, 0, 0], user_id=user1.id)) == 1
        assert len(store.search([1.0, 0, 0, 0], user_id=user2.id)) == 1
        assert store.search([1.0, 0, 0, 0], user_id=uuid4()) == []


class TestMetadataFiltering:
    @pytest.fixture()
    def filtered_store(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user = make_user()
        docs = [
            make_document(file_name="a.pdf", mime_type="application/pdf", source="s3"),
            make_document(file_name="b.txt", mime_type="text/plain", source="google_drive"),
            make_document(file_name="c.pdf", mime_type="application/pdf", source="google_drive"),
        ]
        for doc in docs:
            store.upsert_document_chunks(doc, user, make_chunks(doc.id, [f"chunk {doc.file_name}"]),
                                         [[1.0, 0, 0, 0]])
        return store, user, docs

    def test_filter_by_document_id(self, filtered_store):
        store, user, docs = filtered_store
        results = store.search([1.0, 0, 0, 0], user_id=user.id, document_id=docs[1].id)
        assert {r["document_id"] for r in results} == {str(docs[1].id)}

    def test_filter_by_mime_type(self, filtered_store):
        store, user, _ = filtered_store
        results = store.search([1.0, 0, 0, 0], user_id=user.id, mime_type="application/pdf")
        assert len(results) == 2
        assert all(r["mime_type"] == "application/pdf" for r in results)

    def test_filter_by_source(self, filtered_store):
        store, user, _ = filtered_store
        results = store.search([1.0, 0, 0, 0], user_id=user.id, source="google_drive")
        assert len(results) == 2
        assert all(r["source"] == "google_drive" for r in results)

    def test_filters_combine(self, filtered_store):
        store, user, _ = filtered_store
        results = store.search(
            [1.0, 0, 0, 0], user_id=user.id, source="google_drive", mime_type="application/pdf"
        )
        assert len(results) == 1
        assert results[0]["file_name"] == "c.pdf"

    def test_filter_excluding_everything(self, filtered_store):
        store, user, _ = filtered_store
        assert store.search([1.0, 0, 0, 0], user_id=user.id, mime_type="video/mp4") == []


class TestDeleteAndRetry:
    def test_delete_document_points(self, store):
        store.ensure_collection(TEST_DIMENSIONS)
        user = make_user()
        doc1, doc2 = make_document(), make_document()
        store.upsert_document_chunks(doc1, user, make_chunks(doc1.id, ["one"]), [[1.0, 0, 0, 0]])
        store.upsert_document_chunks(doc2, user, make_chunks(doc2.id, ["two"]), [[1.0, 0, 0, 0]])

        store.delete_document_points(doc1.id)
        results = store.search([1.0, 0, 0, 0], user_id=user.id)
        assert len(results) == 1
        assert results[0]["file_name"] in ("two",) or results[0]["document_id"] == str(doc2.id)

    def test_delete_then_reupsert_replaces_no_duplicates(self, store):
        # the embedding manager deletes a document's points before re-upserting
        store.ensure_collection(TEST_DIMENSIONS)
        user, doc = make_user(), make_document()
        store.upsert_document_chunks(doc, user, make_chunks(doc.id, ["old one", "old two"]),
                                     [[1.0, 0, 0, 0], [1.0, 0, 0, 0]])
        store.delete_document_points(doc.id)
        store.upsert_document_chunks(doc, user, make_chunks(doc.id, ["new one"]),
                                     [[1.0, 0, 0, 0]])
        assert len(store.search([1.0, 0, 0, 0], user_id=user.id)) == 1
