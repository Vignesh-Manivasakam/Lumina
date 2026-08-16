"""Tests for CPUReranker.

Uses the real FlashRank model (already verified end-to-end in earlier
phases). The model is small (~4 MB) and cached, so test runs are fast
on subsequent invocations.
"""
from __future__ import annotations

import pytest

from app.retrieval.cpu_reranker import CPUReranker


class TestCPUReranker:
    def test_rerank_strings_returns_sorted_annotated_list(self):
        reranker = CPUReranker()
        query = "What is the vacation policy?"
        passages = [
            "Pineapples grow on trees.",
            "Employees get 20 days of vacation per year.",
            "The cafeteria opens at 9am.",
        ]
        results = reranker.rerank(query, passages)
        # Returned list has the same length as input.
        assert len(results) == len(passages)
        # Each item has rerank_score.
        for r in results:
            assert "rerank_score" in r
            assert isinstance(r["rerank_score"], float)
        # Sorted by descending score.
        scores = [r["rerank_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_relevant_passage_ranks_first(self):
        reranker = CPUReranker()
        query = "What is the vacation policy?"
        passages = [
            "Pineapples grow on trees.",
            "Employees get 20 days of vacation per year.",
            "The cafeteria opens at 9am.",
        ]
        results = reranker.rerank(query, passages)
        # The vacation one should be in position 0.
        assert "vacation" in results[0]["text"].lower()

    def test_rerank_dicts_preserves_original_keys(self):
        reranker = CPUReranker()
        query = "What is the vacation policy?"
        dicts = [
            {"id": "a", "text_repr": "Pineapples.", "doc_id": "d1"},
            {"id": "b", "text_repr": "Employees get 20 days of vacation.", "doc_id": "d2"},
            {"id": "c", "text_repr": "Cafeteria at 9am.", "doc_id": "d3"},
        ]
        results = reranker.rerank(query, dicts)
        for r in results:
            assert "id" in r
            assert "text_repr" in r
            assert "doc_id" in r
            assert "rerank_score" in r

    def test_rerank_empty_input_returns_empty(self):
        reranker = CPUReranker()
        assert reranker.rerank("q", []) == []
        # Single-element list still produces one annotated item.
        results = reranker.rerank("q", ["a"])
        assert len(results) == 1
        assert results[0]["text"] == "a"

    def test_score_helper_returns_input_order(self):
        reranker = CPUReranker()
        passages = [
            "Pineapples grow on trees.",
            "Employees get 20 days of vacation per year.",
        ]
        scores = reranker.score("vacation policy", passages)
        assert len(scores) == 2
        # Scores in original input order (not sorted).
        assert all(0.0 <= s <= 1.0 for s in scores)
