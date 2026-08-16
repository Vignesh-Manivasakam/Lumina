"""Tests for QdrantStore weighted hybrid search."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from app.retrieval.qdrant_store import QdrantStore


class MockPoint:
    def __init__(self, point_id: str, score: float = 1.0, payload: dict | None = None):
        self.id = point_id
        self.score = score
        self.payload = payload or {"text_repr": f"text for {point_id}"}


class TestQdrantStoreWeights:
    def setup_method(self):
        # Create store bypassing __init__ to avoid connecting to real Qdrant server
        self.store = QdrantStore.__new__(QdrantStore)
        self.store.collection_name = "test_collection"
        self.store.client = MagicMock()
        self.store.sparse_model = MagicMock()
        self.store._bm25_encode = MagicMock(return_value={"indices": [1, 2], "values": [0.5, 0.8]})
        self.store._build_filter = MagicMock(return_value=None)

    def test_equal_weights_uses_fusion_query(self):
        mock_result = MagicMock()
        mock_result.points = [
            MockPoint("p1", score=0.9),
            MockPoint("p2", score=0.8),
        ]
        self.store.client.query_points.return_value = mock_result

        results = self.store.hybrid_search(
            dense_vector=[0.1] * 1024,
            query_text="query",
            bm25_weight=0.5,
            dense_weight=0.5,
        )

        assert len(results) == 2
        assert results[0]["id"] == "p1"
        # Verify query_points was called once with FusionQuery
        assert self.store.client.query_points.call_count == 1
        _, kwargs = self.store.client.query_points.call_args
        assert "query" in kwargs
        assert hasattr(kwargs["query"], "fusion")

    def test_asymmetric_weights_performs_weighted_rrf(self):
        bm25_res = MagicMock()
        bm25_res.points = [MockPoint("bm25_top", payload={"title": "BM25"})]

        dense_res = MagicMock()
        dense_res.points = [MockPoint("dense_top", payload={"title": "Dense"})]

        # First call returns bm25_res, second call returns dense_res
        self.store.client.query_points.side_effect = [bm25_res, dense_res]

        # High BM25 weight (keyword query)
        results = self.store.hybrid_search(
            dense_vector=[0.1] * 1024,
            query_text="exact code",
            bm25_weight=0.9,
            dense_weight=0.1,
        )

        assert len(results) == 2
        # bm25_top should have higher score due to 0.9 weight vs 0.1 weight
        assert results[0]["id"] == "bm25_top"
        assert results[1]["id"] == "dense_top"
        assert results[0]["score"] > results[1]["score"]
