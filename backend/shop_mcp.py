"""Connects the backend and the agents to the Campus Customs MCP server.

The server is started exactly as configured in the project's .mcp.json (the
same entry Claude Code uses), so agents, the API, and Claude Code share one
source of shop data and tools. Agents get no other way to read or change it.

HUMAN_KEY is created fresh every time the backend starts and is passed only to
this backend's copy of the server. The human approval step (backend/approvals.py) sends it;
agents never see it, so they can't approve their own proposals.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from backend.config import MCP_CONFIG_PATH, MCP_SERVER_NAME

HUMAN_KEY = secrets.token_urlsafe(32)

# Lets tests point the server at scratch copies (see mcp_server/README.md).
PASS_THROUGH_ENV = ("CAMPUS_CUSTOMS_DB", "CAMPUS_CUSTOMS_DRAFTS")


def load_shop_mcp(extra_env: dict[str, str] | None = None) -> MCPToolset:
    """Build the MCP toolset from .mcp.json."""
    servers = json.loads(MCP_CONFIG_PATH.read_text())["mcpServers"]
    if MCP_SERVER_NAME not in servers:
        raise RuntimeError(f"{MCP_CONFIG_PATH} has no {MCP_SERVER_NAME!r} server")
    entry = servers[MCP_SERVER_NAME]
    # .mcp.json uses paths relative to the project root (so a fresh clone works anywhere);
    # resolve them here because the backend itself runs from backend/.
    root = MCP_CONFIG_PATH.parent
    resolve = lambda v: str(root / v) if not Path(v).is_absolute() and (root / v).exists() else v
    env = {
        # Keep the server's startup INFO lines out of the logs; warnings and errors still show.
        "FASTMCP_LOG_LEVEL": "WARNING",
        **{k: os.environ[k] for k in PASS_THROUGH_ENV if k in os.environ},
        **entry.get("env", {}),
        **(extra_env or {}),
        "CAMPUS_CUSTOMS_HUMAN_KEY": HUMAN_KEY,
    }
    transport = StdioTransport(
        command=resolve(entry["command"]),
        args=[resolve(a) for a in entry.get("args", [])],
        env=env,
        cwd=entry.get("cwd") or str(root),
    )
    return MCPToolset(transport, id=MCP_SERVER_NAME)


async def call_shop_tool(shop_mcp: MCPToolset, name: str, args: dict[str, Any] | None = None) -> Any:
    """Call one MCP tool directly (used by the CLI and the human approval step, never by agents)."""
    result = await shop_mcp.direct_call_tool(name, args or {})
    # FastMCP wraps list/None results as {"result": ...}; unwrap them so callers get plain data.
    if isinstance(result, dict) and set(result) == {"result"}:
        return result["result"]
    return result
