"""Routes for provider portal automation (recoup notice uploads)."""

import json
import logging
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, Response

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaCase, AuditLog, OpaUser
from ..services.provider_portal_service import ProviderPortalService, ProviderPortalUploadError
from ..dao.case_dao import CaseDAO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provider-portal", tags=["provider_portal"])


class UploadRecoupNoticeRequest:
    """Request to upload recoup notice to provider portal."""
    case_id: str
    portal_key: str = 'default'
    headless: bool = True


class UploadRecoupNoticeResponse:
    """Response from recoup notice upload."""
    success: bool
    case_id: str
    message: str
    upload_audit_id: str


@router.post("/upload-recoup-notice")
async def upload_recoup_notice(
    case_id: str,
    portal_key: str = 'default',
    headless: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    """
    Upload a recoup notice for a case to the provider portal.

    Workflow:
    1. Fetch the case and its generated recoup notice document
    2. Call ProviderPortalService to automate the upload
    3. Log the upload attempt in audit trail
    4. Return success/failure status

    Args:
        case_id: PayGuard case ID
        portal_key: Portal configuration key (e.g., 'default', 'provider-abc')
        headless: Run browser in headless mode (True for production)

    Returns:
        Upload result with audit trail ID
    """
    logger.info(f'[PORTAL] Upload request for case {case_id} by user {current_user.username}')

    try:
        # Fetch case — accept the UUID (UI) or the sequence number (assistant).
        if case_id.isdigit():
            result = await db.execute(select(OpaCase).where(OpaCase.case_sequence == int(case_id)))
        else:
            result = await db.execute(select(OpaCase).where(OpaCase.case_id == case_id))
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail=f'Case {case_id} not found')
        case_id = case.case_id

        # Upload is allowed in ANY state (production + demo flexibility). If a
        # notice was already delivered, we still allow the upload but surface a
        # non-blocking warning so the operator knows they may be sending a
        # duplicate to the provider portal.
        already_delivered = {
            'notice_sent', 'letter_accessed', 'provider_responded', 'reconciling',
            'recovered', 'closed_recovered', 'closed_written_off',
            'closed_unrecoverable', 'closed_overturned',
        }
        upload_warning = (
            f'A recoupment notice was already delivered for this case '
            f'(status "{case.status}"). This upload sends an additional copy to '
            f'the provider portal.'
            if case.status in already_delivered else None
        )

        # Fetch generated recoup notice file from documents table.
        # Document model uses `kind` (not document_type) and `uploaded_at` (not created_at).
        from ..models.workflow import Document

        doc_result = await db.execute(
            select(Document)
            .where(Document.case_id == case.case_id)
            .where(Document.kind == 'recoupment_letter')
            .order_by(Document.uploaded_at.desc())
        )
        notice_doc = doc_result.scalars().first()

        if notice_doc and notice_doc.file_path and os.path.exists(notice_doc.file_path):
            notice_file_path = notice_doc.file_path
            logger.info(f'[PORTAL] Using recoupment letter: {notice_file_path}')
        else:
            logger.warning(f'[PORTAL] No recoupment letter on disk for case {case_id}')
            return {
                'success': False,
                'case_id': case_id,
                'message': 'No recoupment letter found for this case. Go to the Output page to generate one first.',
            }

        # Fetch member and claim for the portal form fields
        from ..models.reference import Member, ProviderOrg
        from ..models.claims import Claim

        member = None
        if case.member_id:
            member = (await db.execute(
                select(Member).where(Member.member_id == case.member_id)
            )).scalar_one_or_none()

        claim = None
        if case.claim_id:
            claim = (await db.execute(
                select(Claim).where(Claim.claim_id == case.claim_id)
            )).scalar_one_or_none()

        provider_org = None
        if case.provider_org_id:
            provider_org = (await db.execute(
                select(ProviderOrg).where(ProviderOrg.provider_org_id == case.provider_org_id)
            )).scalar_one_or_none()

        provider_id = case.provider_org_id or 'PROV-001'
        upload_result = await ProviderPortalService.upload_recoup_notice(
            provider_id=provider_id,
            notice_file_path=notice_file_path,
            case_id=case_id,
            portal_key=portal_key,
            headless=headless,
            member_first=member.first_name if member else None,
            member_last=member.last_name if member else None,
            member_number=member.member_number if member else None,
            claim_icn=claim.icn if claim else None,
            provider_name=provider_org.name if provider_org else None,
        )

        # A successful upload from a pre-delivery state IS the notice delivery:
        # advance the case to notice_sent. Cases already delivered/closed keep
        # their status (this upload is just an additional copy).
        pre_delivery = {'new', 'assigned', 'in_review', 'ready_for_notice', 'ready_to_send'}
        upload_succeeded = upload_result.get('status') == 'success'
        from_state = case.status
        to_state = case.status
        if upload_succeeded and case.status in pre_delivery:
            case.status = 'notice_sent'
            to_state = 'notice_sent'
            db.add(case)

        # Create audit log entry
        audit_log = AuditLog(
            case_id=case_id,
            actor_user_id=current_user.user_id,
            action='PORTAL_UPLOAD_RECOUP_NOTICE',
            from_state=from_state,
            to_state=to_state,
            reason=f'Automated upload to {portal_key} portal',
            meta_json=json.dumps({
                'provider_id': case.provider_org_id,
                'portal': portal_key,
                'file': notice_file_path,
                'upload_result': upload_result,
                'user': current_user.username,
            }),
        )
        db.add(audit_log)
        await db.commit()

        logger.info(
            f'[PORTAL] Upload complete for case {case_id}, audit_id {audit_log.audit_id}, '
            f'status {upload_result.get("status")}'
        )

        message = upload_result.get('message') or upload_result.get('error') or (
            'Recoup notice uploaded successfully' if upload_succeeded else 'Upload failed'
        )
        video_file = upload_result.get('video_file')
        return {
            'success': upload_succeeded,
            'case_id': case_id,
            'case_status': to_state,
            'message': message,
            'warning': upload_warning,
            'upload_audit_id': audit_log.audit_id,
            'video_url': f'/api/provider-portal/session-video/{video_file}' if video_file else None,
            'details': upload_result,
        }

    except ProviderPortalUploadError as e:
        logger.error(f'[PORTAL] Upload error for case {case_id}: {e}')

        # Log failure in audit trail
        audit_log = AuditLog(
            case_id=case_id,
            actor_user_id=current_user.user_id,
            action='PORTAL_UPLOAD_RECOUP_NOTICE_FAILED',
            reason=str(e),
            meta_json=json.dumps({
                'error': str(e),
                'portal': portal_key,
                'user': current_user.username,
            }),
        )
        db.add(audit_log)
        await db.commit()

        raise HTTPException(status_code=400, detail=f'Upload failed: {e}')

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'[PORTAL] Unexpected error for case {case_id}: {e}', exc_info=True)
        error_msg = f'Upload service error: {str(e)}'
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/session-video/{filename}")
async def get_session_video(
    filename: str,
    current_user: OpaUser = Depends(get_current_user),
) -> Response:
    """Stream the recorded browser session for a portal upload.

    The recording is produced by the headless Playwright run so users can
    watch what the automation did on the provider portal.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    # Serve only flat .webm names out of the videos directory — reject any
    # path-shaped input outright.
    if Path(filename).name != filename or not filename.endswith('.webm'):
        raise HTTPException(status_code=400, detail='Invalid video name')

    video_path = ProviderPortalService._video_dir() / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail='Session video not found')

    return FileResponse(path=video_path, media_type='video/webm', filename=filename)


@router.get("/upload-status/{case_id}")
async def get_upload_status(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    """
    Get the upload status history for a case.

    Returns all audit entries related to portal uploads for this case.
    """
    try:
        # Fetch audit logs for this case related to portal uploads
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .where(AuditLog.action.like('%PORTAL_UPLOAD%'))
            .order_by(AuditLog.created_at.desc())
        )
        logs = result.scalars().all()

        return {
            'case_id': case_id,
            'upload_count': len(logs),
            'uploads': [
                {
                    'audit_id': log.audit_id,
                    'action': log.action,
                    'status': 'success' if 'FAILED' not in log.action else 'failed',
                    'timestamp': log.created_at,
                    'user': log.actor.username if log.actor else 'unknown',
                    'details': json.loads(log.meta_json) if log.meta_json else {},
                }
                for log in logs
            ]
        }

    except Exception as e:
        logger.error(f'Error fetching upload status for case {case_id}: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Error fetching upload history')
