"""Tests for RouterAgent."""
from __future__ import annotations

import pytest

from app.agents.router import RouterAgent
from app.services.llm_client import LLMClient


def _make_router(stub_llm) -> RouterAgent:
    # Inject the stub directly — bypass the LLMClient() default.
    return RouterAgent.__new__(RouterAgent)._init(stub_llm) if hasattr(RouterAgent, "_init") else _patch_init(stub_llm)


def _patch_init(stub_llm):
    """Bypass __init__ to avoid hitting the real LLMClient()."""
    agent = RouterAgent.__new__(RouterAgent)
    agent.llm = stub_llm
    agent.nvidia = stub_llm
    return agent


class TestRouterAgent:
    def test_image_bypass_routes_to_multimodal(self, stub_llm):
        agent = _patch_init(stub_llm)
        state = {"query": "What's in this image?", "user_image_b64": "AAAA"}
        result = agent.route(state)
        assert result["route"] == "multimodal"
        assert result["query_type"] == "multimodal"
        assert "Image attached" in result["thinking_note"]
        assert len(stub_llm.calls) == 0

    def test_heuristic_greeting_prefilter(self, stub_llm):
        agent = _patch_init(stub_llm)
        state = {"query": "Hello, how are you?"}
        result = agent.route(state)
        assert result["route"] == "direct"
        assert result["query_type"] == "greeting"
        assert len(stub_llm.calls) == 0

    def test_heuristic_image_gen_prefilter(self, stub_llm):
        agent = _patch_init(stub_llm)
        state = {"query": "Please generate an image of our new office layout"}
        result = agent.route(state)
        assert result["route"] == "image_gen"
        assert result["query_type"] == "image_gen"
        assert len(stub_llm.calls) == 0

    def test_heuristic_web_search_prefilter(self, stub_llm):
        agent = _patch_init(stub_llm)
        state = {"query": "Search the web for Q3 financial industry benchmarks"}
        result = agent.route(state)
        assert result["route"] == "web_search"
        assert result["query_type"] == "web_search"
        assert len(stub_llm.calls) == 0

    def test_classifies_as_simple_with_json(self, stub_llm):
        stub_llm.set_responses(['{"route": "simple", "query_type": "semantic"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "What is the policy on PTO?"}
        result = agent.route(state)
        assert result["route"] == "simple"
        assert result["query_type"] == "semantic"
        assert len(stub_llm.calls) == 1

    def test_classifies_as_complex_multi_hop(self, stub_llm):
        stub_llm.set_responses(['{"route": "complex", "query_type": "multi_hop"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "Compare HR and Finance policies on travel reimbursement"}
        result = agent.route(state)
        assert result["route"] == "complex"
        assert result["query_type"] == "multi_hop"

    def test_unknown_classification_defaults_to_simple(self, stub_llm):
        stub_llm.set_responses(["totally-bogus-category"])
        agent = _patch_init(stub_llm)
        state = {"query": "Explain the quantum fluctuations in employee handbook"}
        result = agent.route(state)
        # Out-of-vocab responses fall back to "simple" (safe default).
        assert result["route"] == "simple"
        assert result["query_type"] == "semantic"

    def test_filters_extract_hr_department(self, stub_llm):
        stub_llm.set_responses(['{"route": "simple", "query_type": "semantic"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "What does the HR team say about vacations?"}
        result = agent.route(state)
        assert result["filters"]["dept"] == "HR"

    def test_filters_extract_legal_department(self, stub_llm):
        stub_llm.set_responses(['{"route": "simple", "query_type": "semantic"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "Show me the legal policies"}
        result = agent.route(state)
        assert result["filters"]["dept"] == "Legal"

    def test_no_filter_for_unrelated_query(self, stub_llm):
        stub_llm.set_responses(['{"route": "simple", "query_type": "semantic"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "Explain standard operating procedures"}
        result = agent.route(state)
        assert result["filters"] == {}

    def test_thinking_note_records_classification(self, stub_llm):
        stub_llm.set_responses(['{"route": "complex", "query_type": "multi_hop"}'])
        agent = _patch_init(stub_llm)
        state = {"query": "Compare across finance and legal documents"}
        result = agent.route(state)
        assert "Classified as 'complex'" in result["thinking_note"]
        assert "dept filter:" in result["thinking_note"]
