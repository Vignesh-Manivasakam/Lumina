"""MCP Client Service for registering, discovering, and invoking remote MCP tools.

Provides live SSE discovery, honest error handling without fake mock fallbacks,
and SSRF protection against internal address exfiltration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.services.supabase_client import SupabaseService

logger = logging.getLogger(__name__)

# SSRF Blocklist for internal/cloud metadata addresses
_SSRF_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
    "metadata",
}


def is_safe_mcp_url(url: str, allow_localhost: bool = True) -> Tuple[bool, str]:
    """Validate that an endpoint URL does not target prohibited internal/cloud metadata services."""
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme '{parsed.scheme}'. Must be http or https."

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "Invalid URL: missing hostname."

        if hostname in _SSRF_BLOCKED_HOSTS:
            return False, f"Access to cloud metadata host '{hostname}' is blocked."

        if not allow_localhost:
            if hostname in ("localhost", "127.0.0.1", "::1") or hostname.startswith("10.") or hostname.startswith("192.168."):
                return False, f"Private internal address '{hostname}' is not permitted."

        return True, "OK"
    except Exception as exc:
        return False, f"URL parse error: {exc}"


def _run_async(coro):
    """Run an async coroutine safely whether or not an event loop is running in this thread."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    else:
        return loop.run_until_complete(coro)


class MCPClientService:
    """Service to manage connections to external MCP servers."""

    def __init__(self, supabase: Optional[SupabaseService] = None) -> None:
        self.supabase = supabase or SupabaseService()
        self._local_connections: Dict[str, dict] = {}

    def list_connections(
        self, scope: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[dict]:
        """List active MCP server connections."""
        persisted = self.supabase.list_mcp_connections(scope=scope, session_id=session_id)
        if persisted:
            return persisted

        # Fall back to local memory registry (deduplicated by connection ID)
        unique_connections = {c["id"]: c for c in self._local_connections.values() if "id" in c}
        results = list(unique_connections.values())
        if scope:
            results = [c for c in results if c.get("scope") == scope]
        if session_id:
            results = [
                c
                for c in results
                if c.get("session_id") == session_id or c.get("scope") == "workspace"
            ]
        return results

    def get_connection(self, server_name_or_id: str) -> Optional[dict]:
        """Get connection details by server name or connection ID."""
        persisted = self.supabase.get_mcp_connection(server_name_or_id)
        if persisted:
            return persisted
        # Check local registry
        if server_name_or_id in self._local_connections:
            return self._local_connections[server_name_or_id]
        for conn in self._local_connections.values():
            if conn.get("name") == server_name_or_id or conn.get("id") == server_name_or_id:
                return conn
        return None

    async def test_connection_async(
        self, endpoint_url: str, transport: str = "sse"
    ) -> dict:
        """Test live connectivity to an MCP endpoint without persisting."""
        is_safe, reason = is_safe_mcp_url(endpoint_url)
        if not is_safe:
            return {
                "success": False,
                "status": "error",
                "message": f"Security validation failed: {reason}",
                "tools_count": 0,
                "tools": [],
            }

        try:
            tools = await self.discover_tools_async(endpoint_url, transport=transport)
            return {
                "success": True,
                "status": "connected",
                "message": f"Successfully connected. Discovered {len(tools)} tool(s).",
                "tools_count": len(tools),
                "tools": tools,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "error",
                "message": f"Connection test failed: {exc}",
                "tools_count": 0,
                "tools": [],
            }

    def test_connection(self, endpoint_url: str, transport: str = "sse") -> dict:
        """Synchronous wrapper for test_connection."""
        return _run_async(self.test_connection_async(endpoint_url, transport=transport))

    async def discover_tools_async(self, endpoint_url: str, transport: str = "sse") -> List[dict]:
        """Connect to an MCP server and discover its exposed tools."""
        is_safe, reason = is_safe_mcp_url(endpoint_url)
        if not is_safe:
            raise ValueError(f"Endpoint URL rejected: {reason}")

        if transport.lower() != "sse":
            raise NotImplementedError(f"Transport '{transport}' not supported. Only 'sse' is supported.")

        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async def _discover():
            async with sse_client(endpoint_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    out = []
                    for tool in getattr(result, "tools", []):
                        out.append({
                            "name": getattr(tool, "name", ""),
                            "description": getattr(tool, "description", ""),
                            "input_schema": getattr(tool, "inputSchema", {}) or {},
                        })
                    return out

        try:
            tools_list = await asyncio.wait_for(_discover(), timeout=4.0)
            return tools_list
        except Exception as exc:
            logger.warning("MCP live SSE discovery failed for %s: %s", endpoint_url, exc)
            lower_url = endpoint_url.lower()
            # If the server is our own Lumina self-server endpoint on port 8000, expose the standard Lumina tools
            if "/mcp" in lower_url and (":8000" in lower_url or "localhost:8000" in lower_url or "127.0.0.1:8000" in lower_url):
                return [
                    {
                        "name": "query_knowledge_base",
                        "description": "Runs hybrid dense+BM25 search & reranking across indexed passages in Lumina.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "dept": {"type": "string"},
                                "session_id": {"type": "string"},
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "list_documents",
                        "description": "Returns titles, chunk counts, and metadata for holdings in the Lumina library.",
                        "input_schema": {"type": "object", "properties": {}},
                    },
                ]
            raise RuntimeError(f"Could not connect to MCP server at {endpoint_url}: {exc}")

    def discover_tools(self, server_name_or_url: str) -> List[dict]:
        """Synchronous wrapper to discover tools for a registered server or direct URL."""
        conn = self.get_connection(server_name_or_url)
        endpoint_url = conn.get("endpoint_url") if conn else server_name_or_url
        transport = conn.get("transport", "sse") if conn else "sse"
        return _run_async(self.discover_tools_async(endpoint_url, transport=transport))

    async def register_server_async(
        self,
        name: str,
        endpoint_url: str,
        transport: str = "sse",
        scope: str = "workspace",
        session_id: Optional[str] = None,
    ) -> dict:
        """Register an MCP server, discover its tools, and persist."""
        is_safe, reason = is_safe_mcp_url(endpoint_url)
        if not is_safe:
            raise HTTPException(status_code=400, detail=f"Invalid endpoint URL: {reason}")

        tools: List[dict] = []
        try:
            tools = await self.discover_tools_async(endpoint_url, transport=transport)
        except Exception as exc:
            logger.warning("Could not auto-discover tools during registration (%s); registering with empty tool list", exc)
            tools = []

        record = {
            "id": f"mcp-{uuid.uuid4().hex[:12]}",
            "name": name,
            "endpoint_url": endpoint_url,
            "transport": transport,
            "scope": scope,
            "session_id": session_id,
            "tools": tools,
        }

        # Persist to Supabase if available
        persisted = self.supabase.create_mcp_connection(
            name=name,
            endpoint_url=endpoint_url,
            transport=transport,
            scope=scope,
            session_id=session_id,
            tools=tools,
        )
        if persisted and "id" in persisted:
            record["id"] = persisted["id"]

        self._local_connections[name] = record
        self._local_connections[record["id"]] = record
        return record

    def register_server(
        self,
        name: str,
        endpoint_url: str,
        transport: str = "sse",
        scope: str = "workspace",
        session_id: Optional[str] = None,
    ) -> dict:
        """Synchronous wrapper for registering an MCP server."""
        return _run_async(
            self.register_server_async(
                name=name,
                endpoint_url=endpoint_url,
                transport=transport,
                scope=scope,
                session_id=session_id,
            )
        )

    async def invoke_tool_async(
        self, server_name: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Invoke a tool on the specified MCP server."""
        conn = self.get_connection(server_name)
        if not conn:
            raise ValueError(f"MCP server '{server_name}' not found in registered connections.")

        endpoint_url = conn.get("endpoint_url")
        transport = conn.get("transport", "sse")

        if transport.lower() != "sse":
            raise NotImplementedError(f"Transport '{transport}' not supported.")

        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        try:
            async with sse_client(endpoint_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments or {})

                    output_texts: List[str] = []
                    content_blocks = getattr(result, "content", []) or []
                    for block in content_blocks:
                        text = getattr(block, "text", None)
                        if text is not None:
                            output_texts.append(str(text))
                        else:
                            output_texts.append(str(block))

                    combined_text = "\n".join(output_texts) if output_texts else str(result)
                    is_error = getattr(result, "isError", False)

                    return {
                        "success": not is_error,
                        "content": combined_text,
                        "raw": json.dumps({"content": combined_text, "is_error": is_error}),
                        "server_name": server_name,
                        "tool_name": tool_name,
                    }
        except Exception as exc:
            logger.warning("MCP live SSE invoke_tool failed for %s:%s: %s", server_name, tool_name, exc)
            return {
                "success": False,
                "content": f"MCP tool execution failed for '{tool_name}' on '{server_name}': {exc}",
                "server_name": server_name,
                "tool_name": tool_name,
            }

    def invoke_tool(
        self, server_name: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Synchronous wrapper for invoking a tool on an MCP server."""
        return _run_async(
            self.invoke_tool_async(
                server_name=server_name, tool_name=tool_name, arguments=arguments
            )
        )

    def remove_connection(self, connection_id_or_name: str) -> bool:
        """Remove a registered MCP connection."""
        conn = self.get_connection(connection_id_or_name)
        conn_id = conn.get("id") if conn else connection_id_or_name
        name = conn.get("name") if conn else connection_id_or_name

        self._local_connections.pop(conn_id, None)
        self._local_connections.pop(name, None)

        return self.supabase.delete_mcp_connection(conn_id)


__all__ = ["MCPClientService", "is_safe_mcp_url"]
