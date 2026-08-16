"""Unit tests for GraderAgent batch evaluation and parse fallback."""
from __future__ import annotations

import pytest

from app.agents.grader import GraderAgent
from app.config import settings


def _make_grader(stub_llm) -> GraderAgent:
    """Instantiate GraderAgent with an injected stub LLM."""
    agent = GraderAgent.__new__(GraderAgent)
    agent.llm = stub_llm
    agent.nvidia = stub_llm
    return agent


class TestBatchGrader:
    def test_scores_each_doc_batch_json(self, stub_llm):
        # Batch of 2 docs returning valid JSON array
        stub_llm.set_responses([
            '[{"doc_index": 0, "score": 0.95, "reason": "exact match"}, {"doc_index": 1, "score": 0.85, "reason": "highly relevant"}]'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "What is the data retention policy?",
            "retrieved_docs": [
                {"text_repr": "Retention policy: data is kept for 90 days.", "chunk_id": "c1"},
                {"text_repr": "Compliance audit rules require 90 days retention.", "chunk_id": "c2"},
            ],
        }
        result = agent.grade(state)
        assert len(stub_llm.calls) == 1
        assert len(result["relevant_docs"]) == 2
        assert result["is_sufficient"] is True
        assert result["relevant_docs"][0]["relevance_score"] == 0.95
        assert result["relevant_docs"][1]["relevance_score"] == 0.85

    def test_filters_irrelevant_docs_below_threshold(self, stub_llm):
        # Doc 0 is below threshold, Doc 1 is above
        stub_llm.set_responses([
            '[{"doc_index": 0, "score": 0.2, "reason": "irrelevant"}, {"doc_index": 1, "score": 0.9, "reason": "relevant"}]'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Where is the API key configured?",
            "retrieved_docs": [
                {"text_repr": "Unrelated chapter on marketing.", "chunk_id": "c1"},
                {"text_repr": "API keys are defined in backend/.env.", "chunk_id": "c2"},
            ],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["chunk_id"] == "c2"
        # Need at least 2 relevant docs to be sufficient
        assert result["is_sufficient"] is False

    def test_fallback_to_individual_grading_on_batch_failure(self, stub_llm):
        # 1st call (batch) fails with non-JSON text; next 2 calls are individual doc evaluations
        stub_llm.set_responses([
            "Sorry, I cannot grade these documents as a JSON list.",
            '{"score": 0.88, "reason": "Doc 1 is directly relevant"}',
            '{"score": 0.15, "reason": "Doc 2 is not related"}',
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "How to deploy Supabase migrations?",
            "retrieved_docs": [
                {"text_repr": "Apply migrations using supabase db push.", "chunk_id": "c1"},
                {"text_repr": "Frontend layout components.", "chunk_id": "c2"},
            ],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["chunk_id"] == "c1"
        assert result["relevant_docs"][0]["relevance_score"] == 0.88

    def test_parses_markdown_fenced_batch_json(self, stub_llm):
        stub_llm.set_responses([
            '```json\n[{"doc_index": 0, "score": 0.92, "reason": "Fenced markdown output"}]\n```'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Search query",
            "retrieved_docs": [{"text_repr": "Document text", "chunk_id": "c1"}],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["relevance_score"] == 0.92

    def test_regex_fallback_for_malformed_batch_json(self, stub_llm):
        # Missing closing brackets but includes regex-extractable index and score
        stub_llm.set_responses([
            'Evaluation: [{"doc_index": 0, "score": 0.75, "reason": "partially matching"'
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Search query",
            "retrieved_docs": [{"text_repr": "Document text", "chunk_id": "c1"}],
        }
        result = agent.grade(state)
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["relevance_score"] == 0.75

    def test_default_score_when_all_parsing_fails(self, stub_llm):
        # Both batch and individual grading return complete garbage
        stub_llm.set_responses([
            "total garbage batch",
            "total garbage single",
        ])
        agent = _make_grader(stub_llm)
        state = {
            "query": "Search query",
            "retrieved_docs": [{"text_repr": "Document text", "chunk_id": "c1"}],
        }
        result = agent.grade(state)
        # Default fallback score is 0.7 which passes the default threshold 0.5
        assert len(result["relevant_docs"]) == 1
        assert result["relevant_docs"][0]["relevance_score"] == 0.7

    def test_empty_retrieved_docs_handled(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"query": "Empty test", "retrieved_docs": []}
        result = agent.grade(state)
        assert result["relevant_docs"] == []
        assert result["is_sufficient"] is False
        assert "No documents retrieved" in result["thinking_note"]


class TestGraderConditionalRouting:
    def test_multimodal_route_bypasses_rewrite(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "multimodal", "is_sufficient": False}
        assert agent.should_rewrite(state) == "generate"

    def test_sufficient_docs_proceeds_to_generate(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "rag", "is_sufficient": True}
        assert agent.should_rewrite(state) == "generate"

    def test_insufficient_docs_triggers_rewrite(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {"route": "rag", "is_sufficient": False, "retrieval_count": 0}
        assert agent.should_rewrite(state) == "rewrite"

    def test_max_retrievals_reached_forces_generate(self, stub_llm):
        agent = _make_grader(stub_llm)
        state = {
            "route": "rag",
            "is_sufficient": False,
            "retrieval_count": settings.MAX_RETRIEVAL_RETRIES,
            "retrieved_docs": [
                {"text_repr": "Fallback doc 1", "chunk_id": "c1"},
                {"text_repr": "Fallback doc 2", "chunk_id": "c2"},
            ],
        }
        decision = agent.should_rewrite(state)
        assert decision == "generate"
        assert len(state["relevant_docs"]) == 2
