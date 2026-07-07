"""HTML → PDF rendering with full CSS fidelity via headless Chromium.

The provider notice letters are stored as fully styled HTML documents
(see utils/letter_renderer.py — letterhead band, serif body, section
headers). fpdf2's write_html cannot honour that CSS, so rendering through
it produces a bland, unstyled letter. Playwright's Chromium is already a
runtime dependency (provider portal automation; installed on Railway via
`playwright install --with-deps chromium`), so print the HTML with a real
browser engine instead.

Callers should catch HtmlPdfError and fall back to a simpler renderer if
Chromium is unavailable in their environment.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Screen CSS in the letter HTML is tuned for the in-app preview (grey page
# background, drop shadow, capped width). Neutralize those for print so the
# PDF is a clean full-width page; everything else renders as authored.
_PRINT_OVERRIDES = """
<style>
  body { background: #fff !important; }
  .letter-page {
    box-shadow: none !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 0 !important;
  }
</style>
"""


class HtmlPdfError(Exception):
    """Raised when Chromium HTML→PDF rendering is unavailable or fails."""


async def html_to_pdf(html: str) -> bytes:
    """Render an HTML document to PDF bytes using headless Chromium."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise HtmlPdfError("playwright not installed") from e

    if "</head>" in html:
        html = html.replace("</head>", f"{_PRINT_OVERRIDES}</head>", 1)
    else:
        html = _PRINT_OVERRIDES + html

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content(html, wait_until="load")
                pdf_bytes = await page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={
                        "top": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.9in",
                        "right": "0.9in",
                    },
                )
            finally:
                await browser.close()
    except HtmlPdfError:
        raise
    except Exception as e:
        raise HtmlPdfError(f"Chromium PDF render failed: {e}") from e

    return bytes(pdf_bytes)
