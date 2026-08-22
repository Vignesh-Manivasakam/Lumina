"""MCP client connections endpoints with live testing, tool discovery, and SSRF protection."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.mcp_client import MCPClientService, is_safe_mcp_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP"])
mcp_client_service = MCPClientService()

MAX_CONNECTIONS_PER_SESSION = 10


class MCPConnectionCreate(BaseModel):
    name: str
    endpoint_url: str
    transport: str = "sse"
    scope: str = "workspace"
    session_id: Optional[str] = None


class MCPTestRequest(BaseModel):
    endpoint_url: str
    transport: str = "sse"


@router.post("/test")
async def test_mcp_endpoint(data: MCPTestRequest):
    """Test live connectivity and tool discovery for an MCP endpoint without registering."""
    try:
        result = await mcp_client_service.test_connection_async(
            endpoint_url=data.endpoint_url, transport=data.transport
        )
        return result
    except Exception as exc:
        logger.exception("Failed to test MCP endpoint: %s", exc)
        return {
            "success": False,
            "status": "error",
            "message": str(exc),
            "tools_count": 0,
            "tools": [],
        }


@router.post("/connections")
async def register_mcp_connection(data: MCPConnectionCreate, http_request: Request):
    """Register an external MCP server connection and discover its tools."""
    try:
        # SSRF validation
        is_safe, reason = is_safe_mcp_url(data.endpoint_url)
        if not is_safe:
            raise HTTPException(status_code=400, detail=f"Invalid endpoint URL: {reason}")

        trusted_session = getattr(http_request.state, "session_id", None)
        effective_session = data.session_id or trusted_session

        # Check existing connection count
        existing = mcp_client_service.list_connections(session_id=effective_session)
        if len(existing) >= MAX_CONNECTIONS_PER_SESSION:
            raise HTTPException(
                status_code=400,
                detail=f"Connection limit reached ({MAX_CONNECTIONS_PER_SESSION} max connections per session).",
            )

        record = await mcp_client_service.register_server_async(
            name=data.name,
            endpoint_url=data.endpoint_url,
            transport=data.transport,
            scope=data.scope,
            session_id=effective_session,
        )
        return record
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to register MCP server: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/connections")
async def list_mcp_connections(
    http_request: Request,
    scope: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """List active MCP server connections."""
    try:
        connections = mcp_client_service.list_connections(
            scope=scope, session_id=session_id
        )
        return connections
    except Exception as exc:
        logger.exception("Failed to list MCP connections: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/connections/{connection_id}/tools")
async def discover_connection_tools(connection_id: str):
    """Re-discover exposed tools for a registered MCP connection."""
    try:
        conn = mcp_client_service.get_connection(connection_id)
        if not conn:
            raise HTTPException(status_code=404, detail="MCP connection not found")
        tools = await mcp_client_service.discover_tools_async(
            conn.get("endpoint_url"), transport=conn.get("transport", "sse")
        )
        return {"connection_id": connection_id, "tools": tools, "count": len(tools)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to discover tools for connection: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/connections/{connection_id}")
async def remove_mcp_connection(connection_id: str):
    """Remove a registered MCP server connection."""
    try:
        success = mcp_client_service.remove_connection(connection_id)
        return {"status": "deleted", "connection_id": connection_id, "success": success}
    except Exception as exc:
        logger.exception("Failed to delete MCP connection: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
