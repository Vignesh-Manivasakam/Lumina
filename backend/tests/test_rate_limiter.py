"""Unit tests for RateLimiterMiddleware."""
from __future__ import annotations

import time
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.middleware.rate_limiter import RateLimiterMiddleware


def create_test_app(max_per_min: int = 3, max_per_hour: int = 10) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(
        RateLimiterMiddleware,
        max_requests_per_minute=max_per_min,
        max_requests_per_hour=max_per_hour,
    )

    @test_app.get("/api/test")
    def api_test():
        return {"status": "ok"}

    @test_app.get("/health")
    def health_test():
        return {"status": "healthy"}

    return test_app


class TestRateLimiterMiddleware:
    def test_requests_within_limit_pass(self):
        app = create_test_app(max_per_min=5)
        client = TestClient(app)
        for _ in range(5):
            res = client.get("/api/test", headers={"X-Session-ID": "test-session-1"})
            assert res.status_code == 200

    def test_exceeding_limit_returns_429(self):
        app = create_test_app(max_per_min=3)
        client = TestClient(app)
        # 3 requests pass
        for _ in range(3):
            res = client.get("/api/test", headers={"X-Session-ID": "test-session-rate"})
            assert res.status_code == 200

        # 4th request exceeds limit
        res4 = client.get("/api/test", headers={"X-Session-ID": "test-session-rate"})
        assert res4.status_code == 429
        assert "Too many requests" in res4.json()["detail"]
        assert "Retry-After" in res4.headers

    def test_exempt_prefixes_bypass_limit(self):
        app = create_test_app(max_per_min=2)
        client = TestClient(app)
        for _ in range(10):
            res = client.get("/health")
            assert res.status_code == 200

    def test_different_sessions_have_independent_limits(self):
        app = create_test_app(max_per_min=2)
        client = TestClient(app)
        # Session A hits limit
        client.get("/api/test", headers={"X-Session-ID": "session-a"})
        client.get("/api/test", headers={"X-Session-ID": "session-a"})
        res_a = client.get("/api/test", headers={"X-Session-ID": "session-a"})
        assert res_a.status_code == 429

        # Session B is unaffected
        res_b = client.get("/api/test", headers={"X-Session-ID": "session-b"})
        assert res_b.status_code == 200
