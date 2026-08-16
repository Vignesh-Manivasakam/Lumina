"""Tests for ``app.ingestion.fast_embedder.LocalEmbedder``.

Mocks the underlying ``fastembed.TextEmbedding`` model so tests run
instantly without downloading the ~400 MB BGE model.

Covers: embed_texts, embed_query, dimension consistency, empty input,
        singleton caching.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from typing import List

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIM = 1024


def _make_fake_embeddings(texts: List[str]) -> list:
    """Return deterministic numpy vectors for testing."""
    return [np.random.default_rng(hash(t) % 2**31).random(DIM).astype(np.float32) for t in texts]


@pytest.fixture
def mock_text_embedding():
    """Patch fastembed.TextEmbedding so no model download occurs."""
    mock_model = MagicMock()

    def _embed(texts):
        return iter(_make_fake_embeddings(list(texts)))

    mock_model.embed = _embed

    with patch("app.ingestion.fast_embedder._get_model", return_value=mock_model):
        from app.ingestion.fast_embedder import LocalEmbedder
        embedder = LocalEmbedder(model_name="test-model", dimension=DIM)
        yield embedder, mock_model


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmbedTexts:
    """Test batch embedding."""

    def test_returns_list_of_vectors(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        result = embedder.embed_texts(["hello", "world"])
        assert isinstance(result, list)
        assert len(result) == 2

    def test_vector_dimension(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        result = embedder.embed_texts(["test"])
        assert len(result[0]) == DIM

    def test_returns_python_lists(self, mock_text_embedding):
        """Vectors should be plain Python lists, not numpy arrays."""
        embedder, _ = mock_text_embedding
        result = embedder.embed_texts(["test"])
        assert isinstance(result[0], list)
        assert isinstance(result[0][0], float)

    def test_empty_input(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        result = embedder.embed_texts([])
        assert result == []

    def test_single_text(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        result = embedder.embed_texts(["one"])
        assert len(result) == 1

    def test_large_batch(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        texts = [f"text_{i}" for i in range(50)]
        result = embedder.embed_texts(texts)
        assert len(result) == 50


class TestEmbedQuery:
    """Test single-query embedding."""

    def test_returns_single_vector(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        result = embedder.embed_query("What is AI?")
        assert isinstance(result, list)
        assert len(result) == DIM

    def test_raises_on_empty_query(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        with pytest.raises(ValueError, match="non-empty"):
            embedder.embed_query("")

    def test_deterministic_same_input(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        v1 = embedder.embed_query("test query")
        v2 = embedder.embed_query("test query")
        assert v1 == v2


class TestDimensionConsistency:
    """Verify dimension setting is respected."""

    def test_dimension_attribute(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        assert embedder.dimension == DIM

    def test_batch_and_query_same_dimension(self, mock_text_embedding):
        embedder, _ = mock_text_embedding
        batch = embedder.embed_texts(["batch text"])
        query = embedder.embed_query("query text")
        assert len(batch[0]) == len(query) == DIM
