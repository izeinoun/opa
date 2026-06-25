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

    Returns a list of tool definitions in OPA Tool format.
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
            logger.info(f"Loaded {len(tools)} tools from ClearLink MCP")
            return tools
    except Exception as e:
        logger.warning(f"Failed to load ClearLink tools: {e}")
        return []


async def call_clearlink_tool(tool_name: str, input_data: dict[str, Any]) -> tuple[bool, str]:
    """Execute a tool on the ClearLink MCP server.

    Returns (ok: bool, content: str) where ok=True on success.
    The content is the JSON response body (as a string).
    """
    if not CLEARLINK_MCP_API_KEY:
        return False, "ClearLink MCP not configured"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CLEARLINK_MCP_URL}/tools/{tool_name}/call",
                json=input_data,
                headers={"X-API-Key": CLEARLINK_MCP_API_KEY},
            )
            ok = response.status_code < 400
            body = response.text
            return ok, body
    except Exception as e:
        logger.exception(f"ClearLink tool execution failed: {tool_name}")
        return False, f"Tool execution error: {e}"
