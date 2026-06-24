"""Public-facing secure letter download flow. No auth required."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, Depends
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.delivery_service import DeliveryService, SecureTokenError
from ..dao.case_dao import CaseDAO

router = APIRouter(prefix="/secure-download", tags=["secure-download"])


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

                try {
                    const response = await fetch('/secure-download/verify', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token, npi })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        // Redirect to download
                        window.location.href = `/secure-download/file?token=${encodeURIComponent(token)}`;
                    } else {
                        const data = await response.json();
                        errorsDiv.innerHTML = `<div class="error">${data.detail || 'Invalid information. Please try again.'}</div>`;
                    }
                } catch (err) {
                    errorsDiv.innerHTML = '<div class="error">An error occurred. Please try again.</div>';
                }
            });
        </script>
    </body>
    </html>
    """
    return html


@router.post("/verify")
async def verify_npi(
    token: str,
    npi: str,
    db: AsyncSession = Depends(get_db),
):
    """Verify NPI against token hash.

    Max 3 attempts per token (basic protection).
    """
    service = DeliveryService(db)

    try:
        is_valid = await service.verify_npi(token, npi)
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
    except Exception as e:
        raise HTTPException(status_code=401, detail="Cannot access file.")

    # Get letter PDF from case/claim
    # For now, return a placeholder; in production, fetch the actual letter PDF
    # from document storage (AWS S3, etc.) based on case_id
    try:
        # Placeholder: would load actual PDF from storage
        pdf_path = f"./letters/{case.case_id}.pdf"
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{case.case_number}.pdf")
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Letter file not found. Please contact your payer.",
        )
