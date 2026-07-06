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
            )

            if not result['success']:
                raise ProviderPortalUploadError(result.get('error', 'Upload failed'))

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

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
    ) -> dict:
        """
        Direct Python Playwright client approach (requires: pip install playwright).

        Falls back to this if Node.js script not available.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ProviderPortalUploadError(
                'Playwright Python not installed. Install with: pip install playwright'
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context()
                page = await context.new_page()

                # Navigate to login
                logger.debug(f'Navigating to {portal_url}/login')
                await page.goto(f'{portal_url}/login')

                # Login
                logger.debug(f'Logging in as {username}')
                await page.fill('input[name="username"]', username)
                await page.fill('input[name="password"]', password)
                await page.click('button[type="submit"]')

                # Wait for dashboard
                await page.wait_for_url(f'{portal_url}/dashboard')
                logger.debug('Login successful')

                # Upload file
                logger.debug(f'Uploading file: {file_path}')
                file_input = page.locator('input[name="notice"]')
                await file_input.set_input_files(file_path)

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

                await context.close()
                await browser.close()

                return {'success': True}

        except Exception as e:
            logger.error(f'Playwright Python upload failed: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
