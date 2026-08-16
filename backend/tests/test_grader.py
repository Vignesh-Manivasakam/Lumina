"""Tests for GraderAgent."""
from __future__ import annotations

import pytest

from app.agents.grader import GraderAgent
from app.services.llm_client import LLMClient


def _make_grader(stub_llm) -> GraderAgent:
    """Bypass LLMClient() — inject the stub directly."""
    agent = GraderAgent.__new__(GraderAgent)
    agent.llm = stub_llm
    agent.nvidia = stub_llm
    return agent


class TestGraderAgent:
    def test_scores_each_doc_batch_json(self, stub_llm):
        # Two docs, both relevant, returned in a single batch JSON array.
        stub_llm.set_responses([
            '[{"doc_index": 0, "score": 0.9, "reason": "direct"}, {"doc_index": 1, "score": 0.8, "reason": "partial"}]'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "What is the policy?",
            "retrieved_docs": [
                {"text_repr": "doc1", "chunk_id": "a"},
                {"text_repr": "doc2", "chunk_id": "b"},
            ],
        }
        result = agent.grade(state)
        assert len(stub_llm.calls) == 1
        assert len(result["relevant_docs"]) == 2
        assert result["is_sufficient"] is True

    def test_filters_irrelevant_docs(self, stub_llm):
        # Doc 0 irrelevant, doc 1 relevant in batch JSON array.
        stub_llm.set_responses([
            '[{"doc_index": 0, "score": 0.1, "reason": "no"}, {"doc_index": 1, "score": 0.85, "reason": "yes"}]'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "What is the policy?",
            "retrieved_docs": [
                {"text_repr": "doc1", "chunk_id": "a"},
                {"text_repr": "doc2", "chunk_id": "b"},
            ],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["chunk_id"] == "b"
        assert result["is_sufficient"] is False  # Need ≥ 2

    def test_fallback_to_individual_grading(self, stub_llm):
        """When batch grading fails or returns non-JSON, falls back to individual doc grading."""
        stub_llm.set_responses([
            "batch grading failed",  # Batch call fails
            '{"score": 0.9, "reason": "doc1 ok"}',  # Doc 1 individual
            '{"score": 0.2, "reason": "doc2 irrelevant"}',  # Doc 2 individual
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "What is the policy?",
            "retrieved_docs": [
                {"text_repr": "doc1", "chunk_id": "a"},
                {"text_repr": "doc2", "chunk_id": "b"},
            ],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["chunk_id"] == "a"

    def test_parses_markdown_fenced_json(self, stub_llm):
        stub_llm.set_responses(['```json\n[{"doc_index": 0, "score": 0.9, "reason": "ok"}]\n```'])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Q",
            "retrieved_docs": [{"text_repr": "doc", "chunk_id": "a"}],
        }
        result = agent.grade(state)
        assert result["relevant_docs"][0]["relevance_score"] == 0.9

    def test_parses_loose_json(self, stub_llm):
        stub_llm.set_responses(['[{"doc_index": 0, "score": 0.7, "reason": "partial"'])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Q",
            "retrieved_docs": [{"text_repr": "doc", "chunk_id": "a"}],
        }
        result = agent.grade(state)
        assert result["relevant_docs"][0]["relevance_score"] == 0.7

    def test_default_score_on_complete_failure(self, stub_llm):
        # LLM returns garbage for both batch and individual; fallback gives 0.7.
        stub_llm.set_responses(["garbage", "not a number at all"])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Q",
            "retrieved_docs": [{"text_repr": "doc", "chunk_id": "a"}],
        }
        result = agent.grade(state)
        # 0.7 passes threshold (default 0.5), so doc is included.
        assert result["relevant_docs"][0]["relevance_score"] == 0.7

    def test_thinking_note_records_decision(self, stub_llm):
        stub_llm.set_responses([
            '[{"doc_index": 0, "score": 0.9}, {"doc_index": 1, "score": 0.8}]'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Q",
            "retrieved_docs": [
                {"text_repr": "a", "chunk_id": "x"},
                {"text_repr": "b", "chunk_id": "y"},
            ],
        }
        result = agent.grade(state)
        assert "Graded 2 of 2" in result["thinking_note"]
        assert "Sufficient context" in result["thinking_note"]

    def test_thinking_note_records_insufficient(self, stub_llm):
        stub_llm.set_responses(['[{"doc_index": 0, "score": 0.1}]'])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Q",
            "retrieved_docs": [{"text_repr": "a", "chunk_id": "x"}],
        }
        result = agent.grade(state)
        assert "Context insufficient" in result["thinking_note"]


class TestShouldRewrite:
    def test_multimodal_skips_rewrite(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "multimodal", "is_sufficient": False}
        assert agent.should_rewrite(state) == "generate"

    def test_sufficient_goes_to_generate(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "simple", "is_sufficient": True}
        assert agent.should_rewrite(state) == "generate"

    def test_insufficient_rewrites(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "simple", "is_sufficient": False, "retrieval_count": 1}
        assert agent.should_rewrite(state) == "rewrite"

    def test_max_retrievals_force_generate(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {
            "route": "simple",
            "is_sufficient": False,
            "retrieval_count": 10,
            "retrieved_docs": [{"text_repr": "a"}, {"text_repr": "b"}],
        }
        assert agent.should_rewrite(state) == "generate"
        # And the fallback seeds relevant_docs with top retrieved_docs.
        assert len(state["relevant_docs"]) == 2
