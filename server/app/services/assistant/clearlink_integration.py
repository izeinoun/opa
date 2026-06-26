"""Integration with ClearLink MCP server.

Fetches member data tools from ClearLink's MCP server and exposes them as
Claude tools for the Assistant. Allows cross-referencing PayGuard cases with
ClearLink member clinical data.

Environment variables:
  CLEARLINK_MCP_URL      — ClearLink MCP server URL (e.g., http://localhost:8010/mcp)
  CLEARLINK_MCP_API_KEY  — API key for MCP authentication
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("opa.clearlink")

CLEARLINK_MCP_URL = os.getenv("CLEARLINK_MCP_URL", "http://localhost:8010/mcp")
CLEARLINK_MCP_API_KEY = os.getenv("CLEARLINK_MCP_API_KEY", "")


async def fetch_clearlink_tools() -> list[dict[str, Any]]:
    """Fetch available tools from ClearLink MCP server.

    Returns a list of tool definitions in Claude API tool format.
    Returns empty list if ClearLink is not configured or unavailable.
    """
    if not CLEARLINK_MCP_API_KEY:
        logger.debug("CLEARLINK_MCP_API_KEY not set, skipping ClearLink tools")
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{CLEARLINK_MCP_URL}/tools",
                headers={"X-API-Key": CLEARLINK_MCP_API_KEY},
            )
            response.raise_for_status()
            data = response.json()
            tools = data.get("tools", [])

            # Convert to Claude API format: inputSchema → input_schema
            normalized_tools = []
            for tool in tools:
                normalized = {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
                normalized_tools.append(normalized)

            logger.info(f"Loaded {len(normalized_tools)} tools from ClearLink MCP")
            return normalized_tools
    except Exception as e:
        logger.warning(f"Failed to load ClearLink tools: {e}")
        return []


async def call_clearlink_tool(tool_name: str, input_data: dict[str, Any]) -> tuple[bool, str]:
    """Execute a tool on the ClearLink MCP server with automatic retry.

    Retries up to 3 times with exponential backoff (500ms, 1s, 2s) for transient failures.
    Only returns success or final error after all retries are exhausted.
    Returns (ok: bool, content: str) where ok=True on success.
    The content is the JSON response body (as a string).
    """
    if not CLEARLINK_MCP_API_KEY:
        return False, "ClearLink MCP not configured"

    import asyncio

    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]  # exponential backoff in seconds
    last_error = None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{CLEARLINK_MCP_URL}/tools/{tool_name}/call",
                    json=input_data,
                    headers={"X-API-Key": CLEARLINK_MCP_API_KEY},
                )
                ok = response.status_code < 400
                body = response.text

                # Success on any attempt
                if ok:
                    if attempt > 0:
                        logger.info(f"ClearLink tool '{tool_name}' succeeded after {attempt} retries")
                    return True, body

                # Transient error — retry if we have attempts left
                if attempt < max_retries - 1:
                    last_error = f"HTTP {response.status_code}: {body}"
                    logger.debug(f"ClearLink tool '{tool_name}' attempt {attempt + 1} failed ({response.status_code}), retrying...")
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                # Final attempt failed
                return False, f"HTTP {response.status_code}: {body}"

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                logger.debug(f"ClearLink tool '{tool_name}' attempt {attempt + 1} error: {e}, retrying...")
                await asyncio.sleep(retry_delays[attempt])
                continue

            # Final attempt failed
            logger.exception(f"ClearLink tool '{tool_name}' failed after {max_retries} attempts")
            return False, f"Tool execution error: {e}"

    # Shouldn't reach here, but just in case
    return False, last_error or "ClearLink tool execution failed"
