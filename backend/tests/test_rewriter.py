"""Tests for RewriterAgent."""
from __future__ import annotations

import json
import pytest

from app.agents.rewriter import RewriterAgent
from app.services.llm_client import LLMClient


def _make_rewriter(stub_llm) -> RewriterAgent:
    agent = RewriterAgent.__new__(RewriterAgent)
    agent.llm = stub_llm
    agent.nvidia = stub_llm
    return agent


class TestRewriterAgent:
    def test_first_attempt_uses_hyde(self, stub_llm):
        stub_llm.set_responses(["A hypothetical answer about vacations."])
        agent = _make_rewriter(stub_llm)
        state = {"query": "vacation policy", "retrieval_count": 1}
        result = agent.rewrite(state)
        assert result["rewritten_query"] == "A hypothetical answer about vacations."
        assert "hyde" in result["thinking_note"]

    def test_second_attempt_uses_stepback(self, stub_llm):
        stub_llm.set_responses(["General policy framework"])
        agent = _make_rewriter(stub_llm)
        state = {"query": "vacation policy", "retrieval_count": 2}
        result = agent.rewrite(state)
        assert "stepback" in result["thinking_note"]

    def test_third_attempt_uses_decompose(self, stub_llm):
        stub_llm.set_responses([json.dumps(["subq 1", "subq 2"])])
        agent = _make_rewriter(stub_llm)
        state = {"query": "Compare X and Y", "retrieval_count": 3}
        result = agent.rewrite(state)
        assert "decompose" in result["thinking_note"]
        assert result["rewritten_query"] == "subq 1"
        assert result["sub_queries"] == ["subq 1", "subq 2"]

    def test_decompose_strips_markdown_fences(self, stub_llm):
        stub_llm.set_responses(["```json\n[\"q1\", \"q2\"]\n```"])
        agent = _make_rewriter(stub_llm)
        state = {"query": "complex question", "retrieval_count": 3}
        result = agent.rewrite(state)
        assert result["sub_queries"] == ["q1", "q2"]

    def test_decompose_falls_back_to_single_query(self, stub_llm):
        stub_llm.set_responses(["not json at all"])
        agent = _make_rewriter(stub_llm)
        state = {"query": "complex question", "retrieval_count": 3}
        result = agent.rewrite(state)
        # Falls back to wrapping the original query.
        assert result["rewritten_query"] == "complex question"
        assert result["sub_queries"] == ["complex question"]

    def test_strategy_cycles_through_retries(self, stub_llm):
        # Three calls — one per strategy — then it cycles back.
        responses = [
            "h1",  # hyde on attempt 1
            "s1",  # stepback on attempt 2
            json.dumps(["d1", "d2"]),  # decompose on attempt 3
            "h2",  # hyde on attempt 4 (cycles)
            "s2",  # stepback on attempt 5
        ]
        stub_llm.set_responses(responses)
        agent = _make_rewriter(stub_llm)
        strategies = []
        for attempt in range(1, 6):
            state = {"query": "Q", "retrieval_count": attempt}
            result = agent.rewrite(state)
            if "hyde" in result["thinking_note"]:
                strategies.append("hyde")
            elif "stepback" in result["thinking_note"]:
                strategies.append("stepback")
            elif "decompose" in result["thinking_note"]:
                strategies.append("decompose")
        assert strategies == ["hyde", "stepback", "decompose", "hyde", "stepback"]
