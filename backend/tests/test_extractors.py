"""Tests for text extraction (PDF / DOCX / TXT / CSV)."""
import pytest

from app.services.document_processing import extractors
from tests.helpers import make_docx, make_pdf


class TestPdfExtraction:
    def test_single_page(self):
        result = extractors.extract_pdf(make_pdf(["Hello Phase 3 world with a proper text layer and plenty of characters"]))
        assert "Hello Phase 3 world" in result.text
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert result.ocr_recommended is False

    def test_multi_page(self):
        result = extractors.extract_pdf(make_pdf(["Page one text", "Page two text", "Page three text"]))
        assert len(result.pages) == 3
        assert [p.page_number for p in result.pages] == [1, 2, 3]
        assert "Page one text" in result.text and "Page three text" in result.text

    def test_scanned_pdf_flagged_for_ocr(self):
        # a PDF whose pages carry (almost) no extractable text
        result = extractors.extract_pdf(make_pdf(["", ""]))
        assert result.ocr_recommended is True
        assert result.text == ""


class TestDocxExtraction:
    def test_paragraphs_and_tables(self):
        content = make_docx(
            paragraphs=["First paragraph.", "Second paragraph."],
            table_rows=[["Name", "Score"], ["Alice", "10"]],
        )
        result = extractors.extract_docx(content)
        assert "First paragraph." in result.text
        assert "Second paragraph." in result.text
        assert "Name | Score" in result.text
        assert "Alice | 10" in result.text

    def test_invalid_docx_raises(self):
        with pytest.raises(extractors.ExtractionFailed):
            extractors.extract_docx(b"this is not a docx file")


class TestTxtExtraction:
    def test_utf8(self):
        result = extractors.extract_txt("héllo wörld".encode("utf-8"))
        assert "héllo wörld" in result.text

    def test_latin1_fallback(self):
        result = extractors.extract_txt("café au lait".encode("latin-1"))
        assert "café" in result.text


class TestCsvExtraction:
    def test_rows_and_text(self):
        csv_bytes = b"name,city,age\nAlice,Hyderabad,30\nBob,Chennai,25\n"
        result = extractors.extract_csv(csv_bytes)
        assert result.csv_rows == [
            ["name", "city", "age"],
            ["Alice", "Hyderabad", "30"],
            ["Bob", "Chennai", "25"],
        ]
        assert "name: Alice" in result.text
        assert "city: Hyderabad" in result.text
        assert "age: 25" in result.text

    def test_empty_csv_raises(self):
        with pytest.raises(extractors.ExtractionFailed):
            extractors.extract_csv(b"   \n")


class TestDispatch:
    def test_dispatch_by_type(self):
        assert extractors.extract(b"hello", "txt").text == "hello"
        assert extractors.extract(b"hello", ".txt").text == "hello"

    def test_image_always_recommends_ocr(self):
        result = extractors.extract(b"\x89PNG fake", "png")
        assert result.ocr_recommended is True
        assert result.text == ""

    def test_unsupported_type_raises(self):
        with pytest.raises(extractors.UnsupportedFileType):
            extractors.extract(b"data", "mp4")

    def test_uppercase_type(self):
        assert extractors.extract(b"hello", "TXT").text == "hello"
