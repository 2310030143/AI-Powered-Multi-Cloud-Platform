"""Table extraction: pdfplumber for PDFs, native parsing for CSVs."""
import io

from app.utils.logger import get_logger

logger = get_logger(__name__)


class TableExtractionError(Exception):
    pass


def _clean_rows(raw_table) -> list[list[str]]:
    rows = []
    for row in raw_table:
        cells = [("" if cell is None else str(cell)).strip() for cell in row]
        rows.append(cells)
    # drop completely empty rows / tables
    rows = [row for row in rows if any(cell for cell in row)]
    return rows


def _to_table(page_number: int | None, table_index: int, rows: list[list[str]]) -> dict | None:
    if not rows:
        return None
    return {
        "page_number": page_number,
        "table_index": table_index,
        "rows": rows,
        "row_count": len(rows),
        "col_count": max(len(row) for row in rows),
    }


def extract_tables_from_pdf(content: bytes) -> list[dict]:
    """Extract tables from every page of a PDF via pdfplumber.

    Returns a list of ``{"page_number", "table_index", "rows", "row_count", "col_count"}``.
    """
    import pdfplumber

    tables: list[dict] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    raw_tables = page.extract_tables()
                except Exception as exc:
                    logger.warning("Table extraction failed on page %d: %s", page_number, exc)
                    continue
                for table_index, raw_table in enumerate(raw_tables or []):
                    table = _to_table(page_number, table_index, _clean_rows(raw_table))
                    if table:
                        tables.append(table)
    except Exception as exc:
        raise TableExtractionError(f"Could not read PDF for table extraction: {exc}") from exc
    return tables


def table_from_csv_rows(csv_rows: list[list[str]] | None) -> list[dict]:
    """Wrap already-parsed CSV rows (header first) as a single table record."""
    if not csv_rows:
        return []
    table = _to_table(None, 0, _clean_rows(csv_rows))
    return [table] if table else []
