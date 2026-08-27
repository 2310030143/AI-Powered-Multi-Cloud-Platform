"""OCR via Tesseract (with graceful degradation when not installed).

System requirements (on the machine running the backend):
- OCR:            tesseract          (apt install tesseract-ocr / choco / brew)
- Scanned PDFs:   pdftoppm (poppler) (apt install poppler-utils)
"""
import io
import shutil

from app.config.settings import get_settings
from app.services.document_processing.extractors import PageText
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def is_available() -> bool:
    """True when the tesseract binary is installed."""
    return shutil.which("tesseract") is not None


def rasterizer_available() -> bool:
    """True when scanned-PDF rasterization (poppler's pdftoppm) is available."""
    try:
        import pdf2image  # noqa: F401
    except Exception:
        return False
    return shutil.which("pdftoppm") is not None


class OCRError(Exception):
    """Raised when OCR is requested but cannot run on this machine."""


def image_to_text(content: bytes) -> str:
    """OCR a single image (png/jpg/jpeg/tiff) and return the text."""
    if not is_available():
        raise OCRError(
            "OCR requested but 'tesseract' is not installed on the server. "
            "Install it (e.g. 'sudo apt install tesseract-ocr') and reprocess."
        )
    from PIL import Image
    import pytesseract

    try:
        with Image.open(io.BytesIO(content)) as image:
            # Convert paletted/CMYK images to RGB for tesseract
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            return pytesseract.image_to_string(image).strip()
    except OCRError:
        raise
    except Exception as exc:
        raise OCRError(f"OCR failed on image: {exc}") from exc


def ocr_pdf_pages(
    content: bytes,
    page_numbers: list[int] | None = None,
) -> list[PageText]:
    """Rasterize and OCR selected PDF pages.

    If page_numbers is None, OCR pages 1 through OCR_MAX_PAGES.
    Page numbers are 1-based.
    """
    if not is_available():
        raise OCRError(
            "OCR requested but 'tesseract' is not installed on the server. "
            "Install it (e.g. 'sudo apt install tesseract-ocr') and reprocess."
        )

    if not rasterizer_available():
        raise OCRError(
            "Scanned-PDF OCR requires poppler ('pdftoppm'). "
            "Install it (e.g. 'sudo apt install poppler-utils') and reprocess."
        )

    from pdf2image import convert_from_bytes
    import pytesseract

    if page_numbers is None:
        page_numbers = list(range(1, settings.OCR_MAX_PAGES + 1))

    page_numbers = sorted(set(page_numbers))

    if not page_numbers:
        return []

    if any(page < 1 for page in page_numbers):
        raise OCRError("OCR page numbers must be 1-based positive integers")

    if max(page_numbers) > settings.OCR_MAX_PAGES:
        logger.warning(
            "OCR page selection exceeds cap of %d pages; "
            "ignoring pages beyond the cap",
            settings.OCR_MAX_PAGES,
        )
        page_numbers = [
            page for page in page_numbers
            if page <= settings.OCR_MAX_PAGES
        ]

    if not page_numbers:
        return []

    pages: list[PageText] = []

    try:
        for page_number in page_numbers:
            images = convert_from_bytes(
                content,
                dpi=200,
                first_page=page_number,
                last_page=page_number,
            )

            if not images:
                logger.warning(
                    "PDF produced no renderable image for page %d",
                    page_number,
                )
                continue

            image = images[0]

            try:
                text = pytesseract.image_to_string(image).strip()
            except Exception as exc:
                logger.warning(
                    "OCR failed on page %d: %s",
                    page_number,
                    exc,
                )
                text = ""

            pages.append(
                PageText(
                    page_number=page_number,
                    text=text,
                )
            )

    except Exception as exc:
        raise OCRError(
            f"Could not rasterize PDF for OCR: {exc}"
        ) from exc

    return pages
