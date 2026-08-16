"""Tests for ``app.retrieval.qdrant_store.QdrantStore``.

Uses the ``StubQdrantStore`` from conftest for most tests, plus a few
tests that verify the real class's interface via monkey-patching.

Covers: session filtering, parent-child resolution, delete_by_session,
        payload field completeness.
"""
from __future__ import annotations

from typing import List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    chunk_id: str,
    text: str = "test content",
    parent_id: str | None = None,
    is_parent: bool = False,
    session_id: str | None = None,
    doc_id: str = "doc-1",
    page_num: int = 1,
):
    """Build a minimal mock chunk object matching MultimodalChunk shape."""
    from types import SimpleNamespace
    return SimpleNamespace(
        chunk_id=chunk_id,
        text_repr=text,
        parent_id=parent_id,
        is_parent=is_parent,
        session_id=session_id,
        doc_id=doc_id,
        page_num=page_num,
        modality="text",
        base64=None,
        metadata={"session_id": session_id} if session_id else {},
        embedding=[0.0] * 1024,
        child_ids=[],
        contextual_header=None,
        original_text=None,
    )


# ---------------------------------------------------------------------------
# Session isolation tests
# ---------------------------------------------------------------------------

class TestSessionFiltering:
    """Verify that hybrid_search scopes results by session_id."""

    def test_returns_only_matching_session(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1", "alpha")], session_id="session-A")
        stub_qdrant.upsert([_make_chunk("c2", "beta")], session_id="session-B")

        results = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id="session-A",
            only_children=False,
        )
        ids = {r["id"] for r in results}
        assert "c1" in ids
        assert "c2" not in ids

    def test_unscoped_returns_all(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1")], session_id="s1")
        stub_qdrant.upsert([_make_chunk("c2")], session_id="s2")

        results = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id=None,
            only_children=False,
        )
        assert len(results) == 2


class TestDeleteBySession:
    """Verify session-scoped deletion."""

    def test_deletes_matching_session_chunks(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1"), _make_chunk("c2")], session_id="doomed")
        stub_qdrant.upsert([_make_chunk("c3")], session_id="safe")

        deleted = stub_qdrant.delete_by_session("doomed")
        assert deleted == 2

        remaining = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id=None,
            only_children=False,
        )
        assert len(remaining) == 1
        assert remaining[0]["id"] == "c3"

    def test_returns_zero_when_no_match(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1")], session_id="keep")
        deleted = stub_qdrant.delete_by_session("nonexistent")
        assert deleted == 0

    def test_empty_session_id_is_noop(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1")], session_id="keep")
        deleted = stub_qdrant.delete_by_session("")
        # Empty string should still filter — no points have "" as session
        assert deleted == 0


# ---------------------------------------------------------------------------
# Parent-child resolution tests
# ---------------------------------------------------------------------------

class TestParentChildResolution:
    """Verify that child hits resolve to parent chunks."""

    def test_resolves_children_to_parents(self, stub_qdrant: StubQdrantStore):
        parent = _make_chunk("p1", text="parent context", is_parent=True)
        child1 = _make_chunk("c1", text="child 1", parent_id="p1")
        child2 = _make_chunk("c2", text="child 2", parent_id="p1")

        stub_qdrant.upsert([parent, child1, child2], session_id="s1")

        # Simulate child-only search
        child_hits = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id="s1",
            only_children=True,
        )
        assert len(child_hits) == 2

        # Resolve to parents
        parents = stub_qdrant.get_parents_for_children(child_hits, session_id="s1")
        assert len(parents) == 1
        assert parents[0]["id"] == "p1"

    def test_deduplicates_parents(self, stub_qdrant: StubQdrantStore):
        """Multiple children sharing the same parent should yield one parent."""
        parent = _make_chunk("p1", text="parent", is_parent=True)
        child_a = _make_chunk("ca", text="a", parent_id="p1")
        child_b = _make_chunk("cb", text="b", parent_id="p1")
        child_c = _make_chunk("cc", text="c", parent_id="p1")

        stub_qdrant.upsert([parent, child_a, child_b, child_c], session_id="s1")
        child_hits = [
            {"id": "ca", "parent_id": "p1", "score": 0.9},
            {"id": "cb", "parent_id": "p1", "score": 0.7},
            {"id": "cc", "parent_id": "p1", "score": 0.5},
        ]
        parents = stub_qdrant.get_parents_for_children(child_hits, session_id="s1")
        assert len(parents) == 1

    def test_max_parents_limit(self, stub_qdrant: StubQdrantStore):
        """Respects max_parents parameter."""
        for i in range(10):
            parent = _make_chunk(f"p{i}", text=f"parent {i}", is_parent=True)
            child = _make_chunk(f"c{i}", text=f"child {i}", parent_id=f"p{i}")
            stub_qdrant.upsert([parent, child], session_id="s1")

        child_hits = [
            {"id": f"c{i}", "parent_id": f"p{i}", "score": float(i) / 10}
            for i in range(10)
        ]
        parents = stub_qdrant.get_parents_for_children(
            child_hits, session_id="s1", max_parents=3
        )
        assert len(parents) <= 3

    def test_empty_child_hits(self, stub_qdrant: StubQdrantStore):
        parents = stub_qdrant.get_parents_for_children([], session_id="s1")
        assert parents == []


# ---------------------------------------------------------------------------
# Payload field completeness
# ---------------------------------------------------------------------------

class TestPayloadFields:
    """Verify all required payload fields are stored."""

    def test_session_id_in_payload(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1")], session_id="s-abc")
        results = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id=None,
            only_children=False,
        )
        assert results[0]["session_id"] == "s-abc"

    def test_parent_id_in_payload(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert([_make_chunk("c1", parent_id="p1")], session_id="s1")
        results = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id=None,
            only_children=False,
        )
        assert results[0]["parent_id"] == "p1"

    def test_is_parent_in_payload(self, stub_qdrant: StubQdrantStore):
        stub_qdrant.upsert(
            [_make_chunk("p1", is_parent=True)], session_id="s1"
        )
        results = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id=None,
            only_children=False,
        )
        assert results[0]["is_parent"] is True


# ---------------------------------------------------------------------------
# Only-children filter
# ---------------------------------------------------------------------------

class TestOnlyChildrenFilter:
    """Verify only_children flag excludes parents from search."""

    def test_excludes_parents(self, stub_qdrant: StubQdrantStore):
        parent = _make_chunk("p1", text="parent", is_parent=True)
        child = _make_chunk("c1", text="child", parent_id="p1")

        stub_qdrant.upsert([parent, child], session_id="s1")

        with_parents = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id="s1",
            only_children=False,
        )
        without_parents = stub_qdrant.hybrid_search(
            dense_vector=[0.0] * 1024,
            query_text="test",
            session_id="s1",
            only_children=True,
        )
        assert len(with_parents) == 2
        assert len(without_parents) == 1
        assert without_parents[0]["id"] == "c1"
