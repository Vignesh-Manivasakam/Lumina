"""MCP client connections endpoints."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.mcp_client import MCPClientService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP"])
mcp_client_service = MCPClientService()


class MCPConnectionCreate(BaseModel):
    name: str
    endpoint_url: str
    transport: str = "sse"
    scope: str = "workspace"
    session_id: Optional[str] = None


@router.post("/connections")
async def register_mcp_connection(data: MCPConnectionCreate, http_request: Request):
    """Register an external MCP server connection and discover its tools."""
    try:
        trusted_session = getattr(http_request.state, "session_id", None)
        effective_session = data.session_id or trusted_session

        record = await mcp_client_service.register_server_async(
            name=data.name,
            endpoint_url=data.endpoint_url,
            transport=data.transport,
            scope=data.scope,
            session_id=effective_session,
        )
        return record
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


@router.delete("/connections/{connection_id}")
async def remove_mcp_connection(connection_id: str):
    """Remove a registered MCP server connection."""
    try:
        success = mcp_client_service.remove_connection(connection_id)
        return {"status": "deleted", "connection_id": connection_id, "success": success}
    except Exception as exc:
        logger.exception("Failed to delete MCP connection: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


class MCPToolInvokeRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Optional[dict] = None


@router.post("/invoke")
async def invoke_mcp_tool(req: MCPToolInvokeRequest):
    """Directly invoke a tool on a connected MCP server."""
    try:
        result = await mcp_client_service.invoke_tool_async(
            server_name=req.server_name,
            tool_name=req.tool_name,
            arguments=req.arguments,
        )
        return result
    except Exception as exc:
        logger.exception("Failed to invoke MCP tool: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/rag/tools")
def get_rag_tools():
    """List native Lumina RAG tools exposed via MCP."""
    return [
        {
            "name": "query_knowledge_base",
            "description": "Runs hybrid dense+BM25 search & reranking across all indexed passages in Lumina.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "dept": {"type": "string", "description": "Optional department filter"},
                    "session_id": {"type": "string", "description": "Optional session UUID for multi-tenant isolation"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "list_documents",
            "description": "Returns titles, chunk counts, and metadata for all holdings in the Lumina library.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


class RAGQueryRequest(BaseModel):
    query: str
    dept: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/rag/query")
def run_rag_query(req: RAGQueryRequest):
    """Execute the query_knowledge_base MCP tool directly."""
    from app.mcp_server import query_knowledge_base
    result = query_knowledge_base(query=req.query, dept=req.dept, session_id=req.session_id)
    return {"tool": "query_knowledge_base", "result": result}


@router.get("/rag/documents")
def run_list_documents():
    """Execute the list_documents MCP tool directly."""
    from app.mcp_server import list_documents
    result = list_documents()
    return {"tool": "list_documents", "result": result}

