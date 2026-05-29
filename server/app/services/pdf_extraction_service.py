"""PDF text extraction via pdfplumber.

Ported from ClaimGuard's inline pdfplumber usage. Wrapped in a small helper
so callers don't all have to remember the import-guard + page-iteration pattern.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def extract_text(path: Path) -> Tuple[str, int]:
    """Extract concatenated text + page count from a PDF.

    Returns (text, page_count). Returns ('', 0) on import failure or
    unreadable PDF — callers should treat empty text as a 422.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed; cannot extract PDF text")
        return "", 0

    try:
        with pdfplumber.open(str(path)) as pdf:
            parts = [(p.extract_text() or "") for p in pdf.pages]
            return "\n".join(parts), len(pdf.pages)
    except Exception as e:
        logger.exception("pdfplumber failed on %s: %s", path, e)
        return "", 0
