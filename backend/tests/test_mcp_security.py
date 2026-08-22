"""Unit tests for MCP security, SSRF validation, and honest error handling."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.mcp_client import MCPClientService, is_safe_mcp_url


class TestMCPSecurity:
    def test_ssrf_blocks_cloud_metadata(self):
        is_safe, reason = is_safe_mcp_url("http://169.254.169.254/latest/meta-data")
        assert is_safe is False
        assert "blocked" in reason

        is_safe2, reason2 = is_safe_mcp_url("http://metadata.google.internal/computeMetadata/v1/")
        assert is_safe2 is False

    def test_valid_http_and_https_urls_allowed(self):
        is_safe, _ = is_safe_mcp_url("https://api.github.com/mcp")
        assert is_safe is True

        is_safe_local, _ = is_safe_mcp_url("http://localhost:8000/mcp")
        assert is_safe_local is True

    def test_invalid_schemes_rejected(self):
        is_safe, reason = is_safe_mcp_url("file:///etc/passwd")
        assert is_safe is False
        assert "scheme" in reason


class TestMCPClientHonestErrors:
    def test_unreachable_endpoint_raises_or_returns_honest_error(self):
        service = MCPClientService()
        # Test connection should report failure cleanly without raising unhandled crash
        res = service.test_connection("http://localhost:59999/mcp")
        assert res["success"] is False
        assert res["tools_count"] == 0
        assert "failed" in res["message"].lower() or "error" in res["status"].lower()


class TestMCPEndpoints:
    def test_test_endpoint_rejects_ssrf(self):
        client = TestClient(app)
        res = client.post("/api/mcp/test", json={"endpoint_url": "http://169.254.169.254/mcp"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "security" in data["message"].lower() or "blocked" in data["message"].lower()

    def test_test_endpoint_checks_url(self):
        client = TestClient(app)
        res = client.post("/api/mcp/test", json={"endpoint_url": "http://localhost:8000/mcp"})
        assert res.status_code == 200
        data = res.json()
        # Should return structured status object
        assert "success" in data
        assert "tools" in data
