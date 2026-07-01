"""Public-facing secure letter download flow. No auth required."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, Depends
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.delivery_service import DeliveryService, SecureTokenError
from ..dao.case_dao import CaseDAO


class VerifyNPIRequest(BaseModel):
    token: str
    npi: str

router = APIRouter(prefix="/api/secure-download", tags=["secure-download"])


@router.get("", response_class=HTMLResponse)
async def secure_download_page():
    """Serve the public-facing secure download page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Download Claim Recovery Letter</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f5f5f5; }
            .container { max-width: 400px; margin: 100px auto; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            h1 { font-size: 24px; margin: 0 0 20px 0; }
            .error { color: #d32f2f; margin: 10px 0; padding: 10px; background: #ffebee; border-radius: 4px; }
            .form-group { margin: 15px 0; }
            label { display: block; margin-bottom: 5px; font-weight: 500; }
            input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #1976d2; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
            button:hover { background: #1565c0; }
            .info { font-size: 12px; color: #666; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Download Letter</h1>
            <p>Please enter your billing NPI to access your letter.</p>
            <form id="npiForm">
                <div class="form-group">
                    <label for="npi">Billing NPI:</label>
                    <input type="text" id="npi" name="npi" placeholder="10-digit NPI" maxlength="10" required>
                </div>
                <div id="errors"></div>
                <button type="submit">Continue</button>
            </form>
            <div class="info">
                This link will expire in 24 hours. If you have questions, contact your payer.
            </div>
        </div>

        <script>
            const params = new URLSearchParams(window.location.search);
            const token = params.get('token');
            if (!token) {
                document.getElementById('errors').innerHTML = '<div class="error">Missing or expired access token. Please request a new link from your payer.</div>';
                document.getElementById('npiForm').style.display = 'none';
            }

            document.getElementById('npiForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const npi = document.getElementById('npi').value;
                const errorsDiv = document.getElementById('errors');
                errorsDiv.innerHTML = '';

                console.log('[DEBUG] Form submission:');
                console.log('  Token:', token);
                console.log('  NPI:', npi);
                console.log('  NPI length:', npi.length);
                console.log('  Payload:', JSON.stringify({ token, npi }));

                try {
                    const response = await fetch('/api/secure-download/verify', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token, npi })
                    });

                    console.log('[DEBUG] Response status:', response.status);

                    if (response.ok) {
                        const data = await response.json();
                        console.log('[DEBUG] Verification succeeded:', data);
                        // Redirect to download
                        window.location.href = `/api/secure-download/file?token=${encodeURIComponent(token)}`;
                    } else {
                        try {
                            const data = await response.json();
                            console.log('[DEBUG] Verification failed:', data);
                            errorsDiv.innerHTML = `<div class="error">${data.detail || 'Invalid information. Please try again.'}</div>`;
                        } catch (parseErr) {
                            // Response is not JSON (e.g., 405 Method Not Allowed)
                            console.log('[DEBUG] Server unreachable - response not JSON:', response.status, response.statusText);
                            errorsDiv.innerHTML = '<div class="error">The server is unreachable. Please try again later or contact your payer.</div>';
                        }
                    }
                } catch (err) {
                    console.log('[DEBUG] Network error:', err);
                    errorsDiv.innerHTML = '<div class="error">The server is unreachable. Please check your connection and try again.</div>';
                }
            });
        </script>
    </body>
    </html>
    """
    return html


@router.post("/verify")
async def verify_npi(
    req: VerifyNPIRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify NPI against token hash.

    Max 3 attempts per token (basic protection).
    """
    service = DeliveryService(db)

    try:
        is_valid = await service.verify_npi(req.token, req.npi)
        if not is_valid:
            raise HTTPException(
                status_code=403,
                detail="The information you entered does not match. Please try again.",
            )
    except SecureTokenError as e:
        raise HTTPException(status_code=401, detail="This link has expired or is invalid.")

    return {"message": "NPI verified. Download link is ready."}


@router.get("/file")
async def download_file(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Stream the PDF letter file.

    Requires a valid token. Updates case status to letter_accessed.
    """
    service = DeliveryService(db)
    case_dao = CaseDAO(db)

    try:
        case = await service.record_letter_access(token, acting_user_id=None)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=401, detail="Cannot access file.")

    # Fetch the provider notice that was created for this case
    from ..dao.letter_dao import LetterDAO
    letter_dao = LetterDAO(db)
    notices = await letter_dao.get_notices_by_case_id(case.case_id)

    if not notices:
        # The secure link can be sent before a recoupment letter is composed, so
        # the case may have no notice when the provider arrives here. Generate one
        # now from the case's default LOB template so there's always a letter to
        # download (idempotent — auto_generate is a no-op if a notice exists).
        try:
            from ..services.letter_service import LetterService
            await LetterService(db).auto_generate_for_case(case.case_sequence)
            await db.commit()
            notices = await letter_dao.get_notices_by_case_id(case.case_id)
        except Exception:
            await db.rollback()

    if not notices:
        raise HTTPException(
            status_code=404,
            detail="Letter not found for this case. Please contact your payer.",
        )

    notice = notices[0]  # Latest notice

    # Parse notice content and extract HTML
    import json
    from io import BytesIO

    try:
        content = json.loads(notice.letter_content or "{}")
        html_content = content.get("html", "")
    except json.JSONDecodeError:
        html_content = notice.letter_content or ""

    if not html_content:
        raise HTTPException(
            status_code=404,
            detail="Letter content not found.",
        )

    # Generate PDF from HTML using fpdf2
    from fpdf import FPDF

    try:
        pdf = FPDF()
        pdf.add_page()

        # Use DejaVuSans font which supports Unicode characters like em-dashes
        try:
            pdf.set_font("DejaVuSans", size=10)
        except:
            # Fallback to Helvetica if DejaVuSans is not available
            pdf.set_font("Helvetica", size=10)

        # Remove <style> tags since fpdf2 has limited CSS support and will render them as text
        import re
        cleaned_html = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

        # Replace special characters that might cause issues
        cleaned_html = cleaned_html.replace("—", "-").replace("–", "-")
        cleaned_html = cleaned_html.replace(""", '"').replace(""", '"')
        cleaned_html = cleaned_html.replace("'", "'").replace("'", "'")

        # Add custom color styling for headers using inline styles that fpdf2 understands
        # Replace section headers with colored version
        cleaned_html = re.sub(
            r'<div class="section-header">([^<]+)</div>',
            r'<b style="color: #1e3a5f; font-size: 12px; border-bottom: 1px solid #dde3ec; padding: 6px 0; margin: 12px 0;">\1</b><br>',
            cleaned_html,
            flags=re.IGNORECASE
        )

        # Replace letterhead with dark blue
        cleaned_html = re.sub(
            r'<div class="letterhead">([^<]+)</div>',
            r'<b style="color: #1e3a5f; font-size: 13px; border-bottom: 3px solid #1e3a5f; padding-bottom: 6px; margin-bottom: 14px;">\1</b><br><br>',
            cleaned_html,
            flags=re.IGNORECASE
        )

        # Normalize any remaining non-Latin-1 characters (bullets, accents, math
        # symbols, …) so fpdf2's core Helvetica font never crashes mid-render.
        # The manual replacements above only cover a few punctuation marks.
        from ..utils.markdown_pdf import _pdf_safe
        cleaned_html = _pdf_safe(cleaned_html)

        # Use write_html to render the HTML content
        pdf.write_html(cleaned_html)

        # Generate PDF bytes
        pdf_bytes = pdf.output(dest='S')

        # pdf.output() returns bytes already, no need to encode
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin-1')
        elif not isinstance(pdf_bytes, bytes):
            # If it's a bytearray, convert to bytes
            pdf_bytes = bytes(pdf_bytes)

        # Return as file response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={case.case_number}.pdf"}
        )
    except Exception as e:
        import traceback
        print(f"PDF Error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {str(e)}",
        )
