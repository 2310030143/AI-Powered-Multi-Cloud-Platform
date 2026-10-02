"""Tests for RAG query processing."""
import pytest

from app.services.rag.query_processing import (
    MAX_QUERY_CHARS,
    InvalidQueryError,
    prepare_query,
)


class TestPrepareQuery:
    def test_normal_query_trimmed(self):
        assert prepare_query("  What is semantic search?  ") == "What is semantic search?"

    def test_internal_whitespace_collapsed(self):
        assert prepare_query("what   is\n\nsemantic\tsearch?") == "what is semantic search?"

    def test_question_meaning_preserved(self):
        query = "How does the Qdrant cosine similarity ranking work?"
        assert prepare_query(query) == query

    def test_empty_query_rejected(self):
        with pytest.raises(InvalidQueryError):
            prepare_query("")

    def test_whitespace_only_query_rejected(self):
        with pytest.raises(InvalidQueryError):
            prepare_query("   \n\t  ")

    def test_none_rejected(self):
        with pytest.raises(InvalidQueryError):
            prepare_query(None)

    def test_maximum_length_enforced(self):
        with pytest.raises(InvalidQueryError, match="maximum length"):
            prepare_query("x" * (MAX_QUERY_CHARS + 1))

    def test_exactly_maximum_length_accepted(self):
        assert len(prepare_query("x" * MAX_QUERY_CHARS)) == MAX_QUERY_CHARS

    def test_unicode_preserved(self):
        assert prepare_query("  What is naïve Bayes? 🤖 ") == "What is naïve Bayes? 🤖"


class TestChatRequestValidation:
    """Request-model level validation (limit / min_score bounds)."""

    def test_defaults(self):
        from app.schemas.chat import ChatRequest

        payload = ChatRequest(message="hello")
        assert payload.limit == 5
        assert payload.min_score == 0.2

    def test_whitespace_only_message_rejected(self):
        import pydantic

        from app.schemas.chat import ChatRequest

        with pytest.raises(pydantic.ValidationError):
            ChatRequest(message="   \n\t  ")

    def test_invalid_limit_rejected(self):
        import pydantic

        from app.schemas.chat import ChatRequest

        for bad in (0, -1, 21, 100):
            with pytest.raises(pydantic.ValidationError):
                ChatRequest(message="hello", limit=bad)

    def test_invalid_min_score_rejected(self):
        import pydantic

        from app.schemas.chat import ChatRequest

        for bad in (-0.1, 1.5, 99):
            with pytest.raises(pydantic.ValidationError):
                ChatRequest(message="hello", min_score=bad)

    def test_message_too_long_rejected(self):
        import pydantic

        from app.schemas.chat import ChatRequest

        with pytest.raises(pydantic.ValidationError):
            ChatRequest(message="x" * 2001)
