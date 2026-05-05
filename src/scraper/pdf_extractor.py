import re
from pathlib import Path

import pymupdf as fitz

from src.config.settings import PDF_CACHE_DIR, MAX_PDF_PAGES, MAX_TEXT_PER_PDF


def extract_text(pdf_path: Path) -> str | None:
    """Extract text content from a PDF file."""
    try:
        doc = fitz.open(str(pdf_path))
        pages = min(len(doc), MAX_PDF_PAGES)
        parts = [doc[i].get_text().strip() for i in range(pages)]
        doc.close()

        text = "\n\n".join(p for p in parts if p)
        if len(text) > MAX_TEXT_PER_PDF:
            text = text[:MAX_TEXT_PER_PDF] + "\n[... truncated]"

        return text if text.strip() else None
    except Exception as e:
        print(f"  ⚠️  PDF extraction error: {e}")
        return None


def get_cached_text(course_code: str, filename: str) -> str | None:
    """Try to load previously extracted text from cache."""
    text_path = _text_cache_path(course_code, filename)
    if text_path.exists():
        return text_path.read_text(encoding="utf-8")
    return None


def save_cached_text(course_code: str, filename: str, text: str):
    """Save extracted text to cache."""
    text_path = _text_cache_path(course_code, filename)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")


def pdf_cache_path(course_code: str, filename: str) -> Path:
    """Get the cache path for a downloaded PDF."""
    safe_name = re.sub(r"[^\w\s.-]", "", filename)
    safe_name = re.sub(r"\s+", "_", safe_name)[:100]
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    return PDF_CACHE_DIR / course_code / safe_name


def _text_cache_path(course_code: str, filename: str) -> Path:
    return pdf_cache_path(course_code, filename).with_suffix(".txt")