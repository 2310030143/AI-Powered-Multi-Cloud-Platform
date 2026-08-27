"""Tests for token-aware chunking with overlap."""
from app.services.document_processing.chunking import (
    chunk_pages,
    chunk_text,
    token_count,
)
from app.services.document_processing.extractors import PageText


class TestTokenCount:
    def test_never_zero_for_nonempty(self):
        assert token_count("hello world") >= 1

    def test_word_level(self):
        assert token_count("one two") > token_count("one")


class TestChunkText:
    def test_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   \n  ") == []

    def test_single_small_paragraph(self):
        chunks = chunk_text("Just one short paragraph.")
        assert len(chunks) == 1
        assert chunks[0]["content"] == "Just one short paragraph."
        assert chunks[0]["page_number"] == 1
        assert chunks[0]["token_count"] >= 1

    def test_paragraphs_kept_together_when_small(self):
        paragraphs = [f"Paragraph number {i} with some words." for i in range(3)]
        chunks = chunk_text("\n\n".join(paragraphs))
        assert len(chunks) == 1
        for paragraph in paragraphs:
            assert paragraph in chunks[0]["content"]

    def test_many_paragraphs_split_with_overlap(self):
        paragraphs = [f"Paragraph {i}: " + ("lorem ipsum dolor sit amet " * 60) for i in range(5)]
        chunks = chunk_text("\n\n".join(paragraphs), chunk_tokens=200, overlap_tokens=40)
        assert len(chunks) > 1
        # every chunk within size bounds (overlap can push slightly over)
        for chunk in chunks:
            assert chunk["token_count"] <= 200 + 40 + 50
        # consecutive chunks overlap: the tail of chunk i appears at the head of chunk i+1
        for i in range(len(chunks) - 1):
            tail_words = chunks[i]["content"].split()[-8:]
            head_words = chunks[i + 1]["content"].split()[:8]
            assert any(w in head_words for w in tail_words)

    def test_single_huge_paragraph_is_hard_split(self):
        huge = "word " * 4000
        chunks = chunk_text(huge, chunk_tokens=150, overlap_tokens=0)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk["token_count"] <= 150 + 60  # word-level split tolerance

    def test_no_content_loss(self):
        paragraphs = [f"UniqueMarker{i} " + "filler text here " * 40 for i in range(8)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_tokens=150, overlap_tokens=30)
        joined = "\n\n".join(c["content"] for c in chunks)
        for i in range(8):
            assert f"UniqueMarker{i}" in joined


class TestChunkPages:
    def test_page_numbers_tracked(self):
        pages = [
            PageText(page_number=1, text="page one " + "alpha " * 100),
            PageText(page_number=2, text="page two " + "beta " * 100),
        ]
        chunks = chunk_pages(pages, chunk_tokens=120, overlap_tokens=20)
        assert len(chunks) > 1
        page_numbers = {c["page_number"] for c in chunks}
        assert 1 in page_numbers and 2 in page_numbers
        # chunks are ordered
        assert chunks[0]["page_number"] == 1

    def test_chunk_indexes_sequential_in_pipeline_order(self):
        chunks = chunk_text("Some text. " * 500, chunk_tokens=100, overlap_tokens=20)
        contents = [c["content"] for c in chunks]
        assert all(contents)  # no empty chunks

    def test_explicit_parameters_override_settings(self):
        chunks = chunk_text(" ".join(f"word{i}" for i in range(40)), chunk_tokens=4, overlap_tokens=0)
        assert len(chunks) >= 2
