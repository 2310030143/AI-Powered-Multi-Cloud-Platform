"""Tests for the OCR service (mocked when tesseract is unavailable on this machine)."""
import pytest

from app.services.ocr import ocr


@pytest.mark.skipif(not ocr.is_available(), reason="tesseract not installed on this machine")
class TestRealOcr:
    def test_image_to_text(self):
        import io

        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (600, 160), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=48)
        except TypeError:  # older Pillow without sized default font
            font = ImageFont.load_default()
        draw.text((20, 40), "Hello OCR World", fill="black", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        text = ocr.image_to_text(buffer.getvalue())
        assert "Hello" in text and "OCR" in text

    def test_scanned_pdf_ocr(self):
        from tests.helpers import make_pdf

        # A text-less PDF page renders blank → OCR returns empty, not an error
        pages = ocr.ocr_pdf_pages(make_pdf([""]))
        assert len(pages) == 1
        assert pages[0].page_number == 1


class TestOcrDegradation:
    def test_image_to_text_raises_clean_error_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(ocr, "is_available", lambda: False)
        with pytest.raises(ocr.OCRError, match="tesseract"):
            ocr.image_to_text(b"png-bytes")

    def test_pdf_ocr_requires_rasterizer(self, monkeypatch):
        monkeypatch.setattr(ocr, "is_available", lambda: True)
        monkeypatch.setattr(ocr, "rasterizer_available", lambda: False)
        with pytest.raises(ocr.OCRError, match="poppler"):
            ocr.ocr_pdf_pages(b"pdf-bytes")

    def test_pdf_ocr_requires_tesseract(self, monkeypatch):
        monkeypatch.setattr(ocr, "is_available", lambda: False)
        with pytest.raises(ocr.OCRError, match="tesseract"):
            ocr.ocr_pdf_pages(b"pdf-bytes")
