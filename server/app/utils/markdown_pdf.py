"""Markdown → PDF rendering.

Pure-Python pipeline with no system dependencies (Railway-safe):
    Markdown text → HTML (markdown lib) → PDF bytes (fpdf2.write_html).

fpdf2 supports a useful subset of HTML/CSS (headings, paragraphs, bold/italic,
lists, tables, links, blockquotes). It is intentionally simpler than a full
browser engine; that trade-off keeps deploys dependency-light. If richer
layout is ever required, swap this module's body for WeasyPrint without
touching callers.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Minimal styling wrapper applied around the rendered HTML so output isn't
# wall-to-wall text. fpdf2 honours a subset of inline/style attributes.
_HTML_SHELL = (
    "<style>"
    "h1 {{ font-size: 18pt; }} h2 {{ font-size: 14pt; }} h3 {{ font-size: 12pt; }}"
    "</style>"
    "{body}"
)

# fpdf2's core fonts (Helvetica/Courier) are Latin-1 only and RAISE on any
# character outside that range. AI-generated content routinely contains em
# dashes, smart quotes, ≥/≤, etc., so normalize the common ones to ASCII and
# replace anything else still unsupported rather than crash. (markdown escapes
# any '<' we introduce, so '<='/'->' are safe.)
_UNICODE_TO_ASCII = str.maketrans({
    "—": "-", "–": "-", "‐": "-", "‑": "-", "−": "-",
    "•": "-", "·": "-", "‚": ",",
    "‘": "'", "’": "'", "“": '"', "”": '"', "＂": '"',
    "…": "...", "°": " deg", "≥": ">=", "≤": "<=", "≠": "!=",
    "×": "x", "÷": "/", "→": "->", "←": "<-", "✓": "[x]", "✗": "[ ]",
    " ": " ", " ": " ", " ": " ",
})


def _pdf_safe(text: str) -> str:
    """Make text renderable by fpdf2's Latin-1 core fonts."""
    t = (text or "").translate(_UNICODE_TO_ASCII)
    # Drop-replace any remaining out-of-range character with '?'.
    return t.encode("latin-1", "replace").decode("latin-1")


def markdown_to_html(md: str) -> str:
    """Convert Markdown to HTML. Raises RuntimeError if the lib is missing."""
    try:
        import markdown as md_lib
    except ImportError as e:  # pragma: no cover - exercised only without dep
        raise RuntimeError("markdown package not installed") from e
    return md_lib.markdown(
        md or "",
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )


def markdown_to_pdf(md: str, title: str | None = None) -> bytes:
    """Render Markdown to PDF bytes.

    `title` is set as the PDF document title metadata; it is not printed as a
    heading (put that in the Markdown itself if you want it visible).
    """
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("fpdf2 package not installed") from e

    html = _HTML_SHELL.format(body=markdown_to_html(_pdf_safe(md)))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    if title:
        pdf.set_title(_pdf_safe(title))
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.write_html(html)
    # fpdf2 >=2.7 returns a bytearray from output(); normalize to bytes.
    return bytes(pdf.output())
