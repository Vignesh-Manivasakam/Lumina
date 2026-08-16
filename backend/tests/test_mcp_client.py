"""Unit tests for MCPClientService."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.mcp_client import MCPClientService


@pytest.mark.asyncio
async def test_mcp_client_register_and_list():
    mock_supabase = MagicMock()
    mock_supabase.create_mcp_connection.return_value = {
        "id": "mcp-conn-123",
        "name": "test_server",
        "endpoint_url": "http://localhost:8000/mcp/sse",
        "transport": "sse",
        "scope": "workspace",
        "session_id": "sess-1",
        "tools": [{"name": "test_tool", "description": "A test tool", "input_schema": {}}],
    }
    mock_supabase.list_mcp_connections.return_value = [
        {
            "id": "mcp-conn-123",
            "name": "test_server",
            "endpoint_url": "http://localhost:8000/mcp/sse",
            "transport": "sse",
            "scope": "workspace",
            "session_id": "sess-1",
            "tools": [{"name": "test_tool", "description": "A test tool", "input_schema": {}}],
        }
    ]
    mock_supabase.get_mcp_connection.return_value = {
        "id": "mcp-conn-123",
        "name": "test_server",
        "endpoint_url": "http://localhost:8000/mcp/sse",
        "transport": "sse",
        "scope": "workspace",
        "session_id": "sess-1",
        "tools": [{"name": "test_tool", "description": "A test tool", "input_schema": {}}],
    }
    mock_supabase.delete_mcp_connection.return_value = True

    service = MCPClientService(supabase=mock_supabase)

    # Patch discover_tools_async
    with patch.object(service, "discover_tools_async", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = [{"name": "test_tool", "description": "A test tool", "input_schema": {}}]

        reg = await service.register_server_async(
            name="test_server",
            endpoint_url="http://localhost:8000/mcp/sse",
            transport="sse",
            scope="workspace",
            session_id="sess-1",
        )

        assert reg["name"] == "test_server"
        assert len(reg["tools"]) == 1

        conns = service.list_connections(scope="workspace")
        assert len(conns) == 1
        assert conns[0]["name"] == "test_server"

        conn = service.get_connection("test_server")
        assert conn is not None
        assert conn["id"] == "mcp-conn-123"

        deleted = service.remove_connection("mcp-conn-123")
        assert deleted is True


@pytest.mark.asyncio
async def test_mcp_client_invoke_tool_mock():
    service = MCPClientService()
    service._local_connections["test_server"] = {
        "id": "mcp-1",
        "name": "test_server",
        "endpoint_url": "http://localhost:8000/mcp/sse",
        "transport": "sse",
        "scope": "workspace",
        "tools": [{"name": "echo", "description": "Echo back", "input_schema": {}}],
    }

    # Test invoking unknown server raises ValueError
    with pytest.raises(ValueError):
        await service.invoke_tool_async("unknown_server", "echo")
