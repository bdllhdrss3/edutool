import logging
from contextlib import ExitStack
from functools import lru_cache
from io import BytesIO
from math import isfinite, sqrt
from threading import Lock

from fastapi import HTTPException
from pypdf import PdfReader

from app.core.config import get_settings

logger = logging.getLogger(__name__)
# PDFium and the cached OCR runtime are serialized within each worker.
_ocr_lock = Lock()


def normalize_text(text: str) -> str:
    lines = []
    seen = set()
    for line in text.splitlines():
        line = " ".join(line.split())
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def _table_text(page) -> str:
    tables = page.extract_tables() or []
    rows: list[str] = []
    for table in tables:
        for row in table or []:
            cells = [" ".join((cell or "").split()) for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
    return normalize_text("\n".join(rows))


def _layout_text(page) -> str:
    words = page.extract_words() or []
    midpoint = page.width / 2
    left = [word for word in words if word["x1"] < midpoint - 8]
    right = [word for word in words if word["x0"] > midpoint + 8]
    # Only split an unambiguous central gutter. Other layouts retain pdfplumber's ordering.
    if len(left) >= 8 and len(right) >= 8 and len(left) + len(right) == len(words):
        left_text = page.crop((0, 0, midpoint, page.height)).extract_text() or ""
        right_text = page.crop((midpoint, 0, page.width, page.height)).extract_text() or ""
        return normalize_text(f"{left_text}\n{right_text}")
    return normalize_text(page.extract_text(layout=True) or "")


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _ocr_page(content: bytes, page_number: int) -> str:
    settings = get_settings()
    try:
        import pypdfium2 as pdfium

        with _ocr_lock, ExitStack() as resources:
            document = pdfium.PdfDocument(content)
            resources.callback(document.close)
            page = document[page_number]
            resources.callback(page.close)
            width, height = page.get_size()
            if not all(isfinite(value) and value > 0 for value in (width, height)):
                raise ValueError("Invalid page dimensions")
            scale = min(2.0, settings.pdf_ocr_max_dimension / max(width, height),
                        sqrt(settings.pdf_ocr_max_pixels / (width * height))) * 0.99
            bitmap = page.render(scale=scale)
            resources.callback(bitmap.close)
            image = bitmap.to_pil()
            resources.callback(image.close)
            result, _ = _ocr_engine()(image)
            return normalize_text("\n".join(item[1] for item in result or [] if len(item) > 1))
    except ImportError as exc:
        raise HTTPException(503, "OCR dependencies are unavailable. Install the backend dependencies and retry this scanned PDF.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"OCR could not process page {page_number + 1}. Try a smaller, clearer PDF.") from exc


def extract_pdf_pages(content: bytes, minimum_text_length: int = 40) -> list[str]:
    settings = get_settings()
    if not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(422, "The file does not have a valid PDF signature")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise HTTPException(422, "Encrypted PDFs cannot be processed; upload an unencrypted copy")
        page_count = len(reader.pages)
        if not 1 <= page_count <= settings.pdf_max_pages:
            raise HTTPException(422, f"PDF must contain 1 to {settings.pdf_max_pages} pages")
        texts = []
        for page in reader.pages:
            try:
                texts.append(normalize_text(page.extract_text() or ""))
            except Exception as exc:  # noqa: BLE001 -- third-party parser recovery boundary
                logger.warning("Text extraction failed (%s); trying layout/OCR", type(exc).__name__)
                texts.append("")  # Layout extraction or selective OCR can still recover this page.
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "The PDF could not be read; it may be corrupt") from exc

    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(content)) as document:
            for index, page in enumerate(document.pages):
                try:
                    layout = _layout_text(page)
                    tables = _table_text(page)
                    # Skip table rows already represented by an equivalent flattened layout line.
                    flattened = {" ".join(line.replace("|", " ").split()) for line in layout.splitlines()}
                    tables = "\n".join(line for line in tables.splitlines()
                                       if " ".join(line.replace("|", " ").split()) not in flattened)
                    combined = normalize_text("\n".join(part for part in (layout, tables) if part))
                    if len(combined) >= minimum_text_length or len(combined) > len(texts[index]):
                        texts[index] = combined
                except Exception as exc:  # noqa: BLE001 -- preserve fallback for a malformed page
                    logger.warning("Layout extraction failed on page %s (%s)", index + 1, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 -- retain pypdf output if layout analysis is unavailable
        logger.warning("Layout analysis unavailable (%s); using text/OCR", type(exc).__name__)

    ocr_pages = [index for index, text in enumerate(texts) if len(text) < minimum_text_length]
    if len(ocr_pages) > settings.pdf_max_ocr_pages:
        raise HTTPException(422, f"PDF needs OCR on more than {settings.pdf_max_ocr_pages} pages; split it into smaller PDFs")
    for index in ocr_pages:
        texts[index] = _ocr_page(content, index) or texts[index]
    if not any(text.strip() for text in texts):
        raise HTTPException(422, "No readable text was found, even after OCR. Upload a clearer PDF.")
    return texts