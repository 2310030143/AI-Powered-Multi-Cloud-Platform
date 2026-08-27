"""Tests for table extraction (pdfplumber mocked; CSV real)."""
from app.services.table_extraction import extractor


class FakePage:
    def __init__(self, tables):
        self._tables = tables

    def extract_tables(self):
        return self._tables


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_pdf_tables_extracted(monkeypatch):
    fake_pdf = FakePdf(
        pages=[
            FakePage([[["Name", "Age"], ["Alice", "30"]], [["x"]]]),  # 2 tables on page 1
            FakePage([[["City", "Pop"], [None, "999"]]]),             # messy table on page 2
        ]
    )
    monkeypatch.setattr("pdfplumber.open", lambda *_a, **_k: fake_pdf)

    tables = extractor.extract_tables_from_pdf(b"fake-pdf-bytes")
    assert len(tables) == 3

    first = tables[0]
    assert first["page_number"] == 1
    assert first["table_index"] == 0
    assert first["rows"] == [["Name", "Age"], ["Alice", "30"]]
    assert first["row_count"] == 2
    assert first["col_count"] == 2

    second = tables[1]
    assert second["table_index"] == 1

    third = tables[2]
    assert third["page_number"] == 2
    assert third["rows"] == [["City", "Pop"], ["", "999"]]  # None cell → ""; non-empty row kept


def test_empty_tables_filtered(monkeypatch):
    fake_pdf = FakePdf(pages=[FakePage([[["", ""], [" ", None]]])])
    monkeypatch.setattr("pdfplumber.open", lambda *_a, **_k: fake_pdf)
    assert extractor.extract_tables_from_pdf(b"x") == []


def test_no_tables(monkeypatch):
    fake_pdf = FakePdf(pages=[FakePage([])])
    monkeypatch.setattr("pdfplumber.open", lambda *_a, **_k: fake_pdf)
    assert extractor.extract_tables_from_pdf(b"x") == []


def test_broken_pdf_raises():
    import pytest

    with pytest.raises(extractor.TableExtractionError):
        extractor.extract_tables_from_pdf(b"not a pdf at all")


def test_csv_rows_wrapped_as_table():
    tables = extractor.table_from_csv_rows([["a", "b"], ["1", "2"], ["3", "4"]])
    assert len(tables) == 1
    assert tables[0]["rows"] == [["a", "b"], ["1", "2"], ["3", "4"]]
    assert tables[0]["row_count"] == 3
    assert tables[0]["col_count"] == 2
    assert tables[0]["page_number"] is None

    assert extractor.table_from_csv_rows(None) == []
    assert extractor.table_from_csv_rows([["", ""], [" "]]) == []
