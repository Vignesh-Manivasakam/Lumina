"""Unit tests for Observability and Usage Tracker services."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import uuid
from app.main import app
from app.services.observability import ObservabilityService, TraceContext
from app.services.usage_tracker import UsageTracker


class TestObservabilityService:
    def test_trace_lifecycle_without_crashing(self):
        obs = ObservabilityService.get_instance()
        session_id = str(uuid.uuid4())
        trace = obs.create_trace(query="Test query", session_id=session_id, model="gemini-3.6-flash")
        assert isinstance(trace, TraceContext)
        assert trace.query == "Test query"

        span = trace.start_span("router", inputs={"query": "Test query"})
        span.finish(outputs={"route": "llm_direct"})
        assert span.duration_ms >= 0

        trace.finish(final_response="Answer", route="llm_direct", total_tokens=150)


class TestUsageTracker:
    def test_record_and_get_session_usage(self):
        tracker = UsageTracker()
        session_id = f"test-tracker-{uuid.uuid4()}"

        # Record 2 queries
        tracker.record_query(
            session_id=session_id,
            query="Query 1",
            model="gemini-3.6-flash",
            route="simple",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=350,
        )
        tracker.record_query(
            session_id=session_id,
            query="Query 2",
            model="gemini-3.6-flash",
            route="llm_direct",
            prompt_tokens=80,
            completion_tokens=40,
            latency_ms=200,
        )

        stats = tracker.get_session_usage(session_id)
        assert stats["session_id"] == session_id
        assert stats["total_queries"] == 2
        assert stats["total_prompt_tokens"] == 180
        assert stats["total_completion_tokens"] == 90
        assert stats["total_tokens"] == 270
        assert stats["tokens_by_model"]["gemini-3.6-flash"] == 270
        assert stats["queries_by_route"]["simple"] == 1
        assert stats["queries_by_route"]["llm_direct"] == 1


class TestUsageAPIEndpoint:
    def test_get_session_usage_endpoint(self):
        client = TestClient(app)
        session_id = str(uuid.uuid4())
        res = client.get(f"/api/sessions/{session_id}/usage", headers={"X-Session-ID": session_id})
        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == session_id
        assert "total_tokens" in data
        assert "total_queries" in data
