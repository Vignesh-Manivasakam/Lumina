"""Tests for RetrieverAgent.

We mock QdrantStore + LocalEmbedder + CPUReranker via the fixtures
in conftest. The RetrieverAgent is reconstructed bypassing ``__init__``
so we never load a real model.
"""
from __future__ import annotations

import pytest

from app.agents.retriever import RetrieverAgent
from app.ingestion.chunking import Modality, MultimodalChunk


def _make_retriever(stub_llm, stub_embedder, stub_qdrant) -> RetrieverAgent:
    """Bypass RetrieverAgent.__init__ to avoid real LLMClient + FlashRank."""
    agent = RetrieverAgent.__new__(RetrieverAgent)
    agent.llm = stub_llm
    agent.nvidia = stub_llm
    agent.embedder = stub_embedder
    agent.store = stub_qdrant
    agent.reranker = StubReranker()
    return agent


class StubReranker:
    """Returns children unchanged (no real model load)."""

    def rerank(self, query, passages):
        # Annotate and return sorted by input order — mirrors FlashRank.
        annotated = []
        for i, p in enumerate(passages):
            if isinstance(p, dict):
                new = {**p, "rerank_score": 1.0 - (i * 0.01)}
                annotated.append(new)
            else:
                annotated.append(p)
        return annotated


def _make_chunk(chunk_id, parent_id=None, is_parent=False, text="hello"):
    return MultimodalChunk(
        chunk_id=chunk_id,
        doc_id="doc-1",
        modality=Modality.TEXT,
        text_repr=text,
        original_text=text,
        parent_id=parent_id,
        is_parent=is_parent,
    )


def _seed_qdrant(stub_qdrant, session_id="sess-A"):
    """Add one parent + two children sharing the parent."""
    parent = _make_chunk("p1", is_parent=True, text="PARENT TEXT")
    c1 = _make_chunk("c1", parent_id="p1", text="child 1")
    c2 = _make_chunk("c2", parent_id="p1", text="child 2")
    stub_qdrant.upsert([parent, c1, c2], session_id=session_id)


class TestRetrieverAgent:
    def test_retrieve_returns_parents(self, stub_llm, stub_embedder, stub_qdrant):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {"query": "test query", "session_id": "sess-A"}
        result = agent.retrieve(state)
        # Default use_parent_resolution=True → parents.
        assert len(result["retrieved_docs"]) == 1
        assert result["retrieved_docs"][0]["id"] == "p1"
        # Children are still surfaced.
        assert len(result["retrieved_children"]) == 2

    def test_session_id_plumbed_through(self, stub_llm, stub_embedder, stub_qdrant):
        _seed_qdrant(stub_qdrant, session_id="sess-X")
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        # Different session — should see nothing.
        state = {"query": "test", "session_id": "sess-Y"}
        result = agent.retrieve(state)
        assert result["retrieved_docs"] == []
        assert result["retrieved_children"] == []

    def test_use_parents_false_returns_children(self, stub_llm, stub_embedder, stub_qdrant):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {
            "query": "test",
            "session_id": "sess-A",
            "use_parent_resolution": False,
        }
        result = agent.retrieve(state)
        # Children (not parents).
        assert all(c["is_parent"] is False for c in result["retrieved_docs"])
        assert len(result["retrieved_docs"]) == 2

    def test_uses_rewritten_query_when_available(
        self, stub_llm, stub_embedder, stub_qdrant
    ):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {
            "query": "original",
            "rewritten_query": "better reformulation",
            "session_id": "sess-A",
        }
        agent.retrieve(state)
        # Embedder saw the rewritten query, not the original.
        assert stub_embedder.calls[-1] == ["better reformulation"]

    def test_falls_back_to_children_when_no_parents(
        self, stub_llm, stub_embedder, stub_qdrant
    ):
        """If parents can't be resolved (shouldn't happen but defensive),
        retriever still returns children."""
        # Seed only children, no parent.
        c1 = _make_chunk("c1", parent_id="ghost", text="c1")
        stub_qdrant.upsert([c1], session_id="sess-A")
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {"query": "q", "session_id": "sess-A"}
        result = agent.retrieve(state)
        # No parents resolved → fallback to children.
        assert len(result["retrieved_docs"]) == 1
        assert result["retrieved_docs"][0]["id"] == "c1"

    def test_thinking_note_reports_counts(
        self, stub_llm, stub_embedder, stub_qdrant
    ):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {"query": "q", "session_id": "sess-A"}
        result = agent.retrieve(state)
        assert "2 child hits" in result["thinking_note"]
        assert "1 parent" in result["thinking_note"]

    def test_retrieval_count_increments(
        self, stub_llm, stub_embedder, stub_qdrant
    ):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {"query": "q", "session_id": "sess-A"}
        result = agent.retrieve(state)
        assert result["retrieval_count"] == 1

    def test_image_query_uses_image_path(self, stub_llm, stub_embedder, stub_qdrant):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {
            "query": "describe this",
            "user_image_b64": "AAAA",
            "session_id": "sess-A",
        }
        # Should not raise; embedder gets a single call (query + image fused).
        result = agent.retrieve(state)
        assert "retrieved_docs" in result

    def test_query_type_weights_applied(self, stub_llm, stub_embedder, monkeypatch):
        class RecordingQdrant:
            def __init__(self):
                self.last_weights = None
            def hybrid_search(self, dense_vector, query_text, top_k=20, filters=None, session_id=None, only_children=True, bm25_weight=0.5, dense_weight=0.5):
                self.last_weights = (bm25_weight, dense_weight)
                return []
            def get_parents_for_children(self, hits, session_id=None, max_parents=5):
                return []

        rec_store = RecordingQdrant()
        agent = _make_retriever(stub_llm, stub_embedder, rec_store)

        # Keyword
        agent.retrieve({"query": "q", "query_type": "keyword"})
        assert rec_store.last_weights == (0.8, 0.2)

        # Numerical
        agent.retrieve({"query": "q", "query_type": "numerical"})
        assert rec_store.last_weights == (0.9, 0.1)

        # Semantic
        agent.retrieve({"query": "q", "query_type": "semantic"})
        assert rec_store.last_weights == (0.2, 0.8)

        # Multi-hop
        agent.retrieve({"query": "q", "query_type": "multi_hop"})
        assert rec_store.last_weights == (0.5, 0.5)

        # Default / unknown
        agent.retrieve({"query": "q", "query_type": "unknown"})
        assert rec_store.last_weights == (0.5, 0.5)

    def test_thinking_note_includes_query_type_and_weights(self, stub_llm, stub_embedder, stub_qdrant):
        _seed_qdrant(stub_qdrant)
        agent = _make_retriever(stub_llm, stub_embedder, stub_qdrant)
        state = {"query": "q", "session_id": "sess-A", "query_type": "keyword"}
        result = agent.retrieve(state)
        assert "keyword: bm25=0.8, dense=0.2" in result["thinking_note"]


class TestStubQdrantStore:
    """Sanity checks for the conftest stub itself."""

    def test_delete_by_session_only_removes_matching(self):
        from tests.conftest import StubQdrantStore

        s = StubQdrantStore()
        s.upsert([_make_chunk("a")], session_id="x")
        s.upsert([_make_chunk("b")], session_id="y")
        deleted = s.delete_by_session("x")
        assert deleted == 1
        assert len(s.points) == 1
        assert s.points[0]["id"] == "b"

    def test_hybrid_search_filters_by_session(self):
        from tests.conftest import StubQdrantStore

        s = StubQdrantStore()
        parent = _make_chunk("p1", is_parent=True)
        c1 = _make_chunk("c1", parent_id="p1")
        s.upsert([parent, c1], session_id="sess-A")
        results = s.hybrid_search([0.0] * 1024, "q", session_id="sess-A")
        assert len(results) == 1
        assert results[0]["id"] == "c1"
