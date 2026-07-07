"""Service for automating recoup notice uploads to provider portals via Playwright."""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProviderPortalUploadError(Exception):
    """Raised when provider portal upload fails."""
    pass


class ProviderPortalService:
    """Handles automated uploads to provider portals using Playwright."""

    # Portal configurations — can be expanded to support multiple providers
    PORTAL_CONFIGS = {
        'default': {
            'url': os.getenv('PROVIDER_PORTAL_URL', 'http://localhost:3002'),
            'username': os.getenv('PROVIDER_PORTAL_USER', 'provider'),
            'password': os.getenv('PROVIDER_PORTAL_PASS', 'password'),
        }
    }

    @staticmethod
    def _video_dir() -> Path:
        """Directory where portal-session recordings are stored."""
        from .prepay_intake_service import UPLOAD_DIR
        d = UPLOAD_DIR / 'portal_videos'
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    async def upload_recoup_notice(
        provider_id: str,
        notice_file_path: str,
        case_id: str,
        portal_key: str = 'default',
        headless: bool = True,
        member_first: Optional[str] = None,
        member_last: Optional[str] = None,
        member_number: Optional[str] = None,
        claim_icn: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> dict:
        """Upload a recoup notice PDF to a provider portal via Playwright."""
        if portal_key not in ProviderPortalService.PORTAL_CONFIGS:
            raise ProviderPortalUploadError(f'Unknown portal: {portal_key}')

        if not os.path.exists(notice_file_path):
            raise ProviderPortalUploadError(f'Notice file not found: {notice_file_path}')

        config = ProviderPortalService.PORTAL_CONFIGS[portal_key]
        start_time = datetime.utcnow()

        logger.info(
            f'[PORTAL] Starting upload for case {case_id}, provider {provider_id}, '
            f'file: {notice_file_path}'
        )

        try:
            result = await ProviderPortalService._run_playwright_upload(
                portal_url=config['url'],
                file_path=notice_file_path,
                username=config['username'],
                password=config['password'],
                provider_id=provider_id,
                headless=headless,
                member_first=member_first,
                member_last=member_last,
                member_number=member_number,
                claim_icn=claim_icn,
                provider_name=provider_name,
                video_dir=ProviderPortalService._video_dir(),
            )

            if not result['success']:
                raise ProviderPortalUploadError(result.get('error', 'Upload failed'))

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Give the session recording a stable, case-scoped name so the UI
            # can link to it (Playwright names videos with a random hash).
            video_file = None
            if result.get('video_path'):
                try:
                    src = Path(result['video_path'])
                    video_file = f"portal_upload_{case_id}_{int(end_time.timestamp())}.webm"
                    src.rename(ProviderPortalService._video_dir() / video_file)
                except OSError as e:
                    logger.warning(f'[PORTAL] Could not persist session video: {e}')
                    video_file = None

            audit_entry = {
                'case_id': case_id,
                'provider_id': provider_id,
                'status': 'success',
                'file_path': notice_file_path,
                'file_name': os.path.basename(notice_file_path),
                'portal': portal_key,
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'video_file': video_file,
                'message': 'Recoup notice uploaded successfully',
            }

            logger.info(f'[PORTAL] Upload successful for case {case_id}: {audit_entry}')
            return audit_entry

        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            audit_entry = {
                'case_id': case_id,
                'provider_id': provider_id,
                'status': 'failed',
                'file_path': notice_file_path,
                'file_name': os.path.basename(notice_file_path),
                'portal': portal_key,
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'error': str(e),
            }

            logger.error(f'[PORTAL] Upload failed for case {case_id}: {e}', exc_info=True)
            return audit_entry

    @staticmethod
    async def _run_playwright_upload(
        portal_url: str,
        file_path: str,
        username: str,
        password: str,
        provider_id: str,
        headless: bool = True,
        member_first: Optional[str] = None,
        member_last: Optional[str] = None,
        member_number: Optional[str] = None,
        claim_icn: Optional[str] = None,
        provider_name: Optional[str] = None,
        video_dir: Optional[Path] = None,
    ) -> dict:
        """Execute the Playwright upload script, passing real case member/claim data."""
        script_path = Path(__file__).parent.parent.parent.parent.parent / \
                      'mock-provider-portal/playwright-upload.js'

        if not script_path.exists():
            logger.warning(f'Playwright script not found at {script_path}, using Python client')
            return await ProviderPortalService._run_python_playwright_upload(
                portal_url=portal_url,
                file_path=file_path,
                username=username,
                password=password,
                headless=headless,
                member_first=member_first,
                member_last=member_last,
                member_number=member_number,
                claim_icn=claim_icn,
                provider_name=provider_name,
                video_dir=video_dir,
            )

        cmd = [
            'node',
            str(script_path),
            f'--portal-url={portal_url}',
            f'--file={file_path}',
            f'--username={username}',
            f'--password={password}',
            f'--provider-id={provider_id}',
            f'--headless={"true" if headless else "false"}',
        ]
        if member_first:
            cmd.append(f'--member-first={member_first}')
        if member_last:
            cmd.append(f'--member-last={member_last}')
        if member_number:
            cmd.append(f'--member-id={member_number}')
        if claim_icn:
            cmd.append(f'--claim-id={claim_icn}')
        if provider_name:
            cmd.append(f'--provider={provider_name}')

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()
            output = stdout.decode()

            if result.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f'Playwright script failed: {error_msg}')
                return {'success': False, 'error': error_msg}

            logger.debug(f'Playwright output: {output}')
            return {'success': True, 'output': output}

        except FileNotFoundError:
            logger.error('Node.js not found — install Node.js to use Playwright automation')
            raise ProviderPortalUploadError(
                'Playwright automation not available (Node.js not found). '
                'Install Node.js or use direct browser automation.'
            )
        except Exception as e:
            logger.error(f'Error running Playwright script: {e}', exc_info=True)
            raise ProviderPortalUploadError(f'Failed to run upload script: {e}')

    @staticmethod
    async def _run_python_playwright_upload(
        portal_url: str,
        file_path: str,
        username: str,
        password: str,
        headless: bool = True,
        member_first: Optional[str] = None,
        member_last: Optional[str] = None,
        member_number: Optional[str] = None,
        claim_icn: Optional[str] = None,
        provider_name: Optional[str] = None,
        video_dir: Optional[Path] = None,
    ) -> dict:
        """
        Direct Python Playwright client approach (requires: pip install playwright).

        Falls back to this if Node.js script not available. Mirrors the Node
        script's flow (login → member info → upload → confirmation) and, when
        `video_dir` is given, records the whole session so the UI can replay
        the automation — headless runs are otherwise invisible to the user.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ProviderPortalUploadError(
                'Playwright Python not installed. Install with: pip install playwright'
            )

        video_path: Optional[str] = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context_opts: dict = {'viewport': {'width': 1280, 'height': 800}}
                if video_dir is not None:
                    context_opts['record_video_dir'] = str(video_dir)
                    context_opts['record_video_size'] = {'width': 1280, 'height': 800}
                context = await browser.new_context(**context_opts)
                page = await context.new_page()

                # The pauses below are deliberate: they make the session
                # recording readable (and pace the typed input) — drop them and
                # the replay is a blur.
                async def pause(ms: int) -> None:
                    await page.wait_for_timeout(ms)

                try:
                    # Navigate to login
                    logger.debug(f'Navigating to {portal_url}/login')
                    await page.goto(f'{portal_url}/login')
                    await pause(600)

                    # Login
                    logger.debug(f'Logging in as {username}')
                    await page.type('input[name="username"]', username, delay=40)
                    await page.type('input[name="password"]', password, delay=40)
                    await pause(300)
                    await page.click('button[type="submit"]')

                    # Wait for dashboard
                    await page.wait_for_url(f'{portal_url}/dashboard')
                    logger.debug('Login successful')
                    await pause(600)

                    # Fill the member info panel when we have case data (same
                    # flow as the Node script: fill → save → dismiss modal).
                    member_fields = [
                        ('#memberFirstName', member_first),
                        ('#memberLastName', member_last),
                        ('#memberNumber', member_number),
                        ('#memberClaimId', claim_icn),
                        ('#memberProvider', provider_name),
                    ]
                    if any(v for _, v in member_fields):
                        for selector, value in member_fields:
                            if value:
                                await page.type(selector, str(value), delay=25)
                        await pause(300)
                        await page.click('#btnSaveMember')
                        await page.wait_for_selector('#memberModal.active', timeout=5000)
                        await pause(800)
                        await page.click('button.member-modal-close')
                        await page.wait_for_selector(
                            '#memberModal.active', state='hidden', timeout=5000
                        )
                        await pause(400)

                    # Upload file
                    logger.debug(f'Uploading file: {file_path}')
                    file_input = page.locator('input[name="notice"]')
                    await file_input.scroll_into_view_if_needed()
                    await file_input.set_input_files(file_path)
                    await pause(700)

                    # Submit the upload form (not the first submit button on the
                    # page) and wait out the navigation — POST /upload renders a
                    # full new confirmation page.
                    async with page.expect_navigation(
                        wait_until='domcontentloaded', timeout=15000
                    ):
                        await page.click('form[action="/upload"] button[type="submit"]')

                    # The portal's confirmation page renders .modal-confirmation
                    # (same selector the Node script waits on); there is no
                    # .success element anywhere in the portal.
                    await page.wait_for_selector('.modal-confirmation', timeout=15000)
                    logger.debug('Upload successful')
                    await pause(1500)  # linger on the confirmation in the replay
                finally:
                    # The video file is finalized on context close; grab its
                    # path first (valid to query before close, ready after).
                    video = page.video if video_dir is not None else None
                    await context.close()
                    if video is not None:
                        try:
                            video_path = await video.path()
                        except Exception:
                            video_path = None
                    await browser.close()

                return {'success': True, 'video_path': video_path}

        except Exception as e:
            logger.error(f'Playwright Python upload failed: {e}', exc_info=True)
            return {'success': False, 'error': str(e), 'video_path': video_path}
