"""Shared pytest configuration for Lumina backend tests.

Goals
-----
- No external services (Qdrant, Supabase, Gemini) are required.
- The ``supabase`` Python SDK isn't installed in this env, so we inject
  a stub via ``sys.modules`` so import-time references resolve cleanly.
- Provide lightweight fixtures for mocked stores and embedders.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any, Iterator, List

import pytest

# ---------------------------------------------------------------------------
# Path setup: ensure ``backend/`` is importable as ``app.*``
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Inject a stub ``supabase`` package before any app module tries to import it.
# Only used at import-time of ``app.services.supabase_client`` which lazily
# resolves the client on first call.
# ---------------------------------------------------------------------------
def _install_supabase_stub() -> None:
    if "supabase" in sys.modules:
        return

    supabase_mod = types.ModuleType("supabase")

    class _StubClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._init_args = args
            self._init_kwargs = kwargs

        # Stubbed methods — return empty structures for any common call.
        def table(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def select(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def insert(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def delete(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def update(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def eq(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def order(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def limit(self, *args: Any, **kwargs: Any) -> _StubClient:
            return self

        def execute(self) -> types.SimpleNamespace:
            return types.SimpleNamespace(data=[], count=0)

    def _create_client(*args: Any, **kwargs: Any) -> _StubClient:
        return _StubClient(*args, **kwargs)

    supabase_mod.create_client = _create_client  # type: ignore[attr-defined]
    supabase_mod.Client = _StubClient  # type: ignore[attr-defined]
    sys.modules["supabase"] = supabase_mod


_install_supabase_stub()


# ---------------------------------------------------------------------------
# Environment defaults for tests
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "")
os.environ.setdefault("EMBEDDING_DIM", "1024")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StubResponse:
    """Mimics ``LLMClient.generate_text`` return — a wrapper with ``.content``."""

    def __init__(self, content: str) -> None:
        self.content = content


class StubLLMClient:
    """Stub LLMClient that returns scripted text responses.

    Tests register a queue of strings via ``set_responses([...])``; each
    call to ``generate_text`` / ``generate`` pops the next value. When the
    queue is empty, falls back to a deterministic default so tests don't
    crash mid-run.
    """

    def __init__(self) -> None:
        self._responses: List[str] = []
        self.calls: List[List[dict]] = []

    def set_responses(self, responses: List[str]) -> None:
        self._responses = list(responses)

    def _next(self) -> str:
        if self._responses:
            return self._responses.pop(0)
        return ""

    def generate_text(self, messages: List[dict], **kwargs: Any) -> _StubResponse:
        self.calls.append(messages)
        return _StubResponse(self._next())

    def generate(self, messages: List[dict], stream: bool = False, **kwargs: Any):
        self.calls.append(messages)
        return _StubResponse(self._next())

    # Back-compat aliases
    @property
    def nvidia(self) -> "StubLLMClient":
        return self


class StubEmbedder:
    """Returns zero vectors of the configured dim. Avoids loading FastEmbed."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.calls: List[List[str]] = []

    def embed_texts(self, texts: List[str]):
        self.calls.append(texts)
        return [[0.0] * self.dim for _ in texts]

    def embed_query(self, query: str, image_b64: Any = None):
        self.calls.append([query])
        return [0.0] * self.dim


class StubQdrantStore:
    """In-memory stub of QdrantStore for retriever tests.

    Mimics the dict-shaped hits returned by the real ``hybrid_search``:
    each hit is ``{"id": chunk_id, "score": float, "parent_id": ...,
    "session_id": ..., "is_parent": bool, "text_repr": ..., ...}``.
    """

    def __init__(self) -> None:
        # points are dicts in real-hybrid_search shape.
        self.points: List[dict] = []

    def upsert(self, chunks, session_id: Any = None) -> None:
        for c in chunks:
            # Chunk is a MultimodalChunk — pull payload fields from it.
            self.points.append(
                {
                    "id": getattr(c, "chunk_id", ""),
                    "score": 0.0,
                    "parent_id": getattr(c, "parent_id", None),
                    "is_parent": bool(getattr(c, "is_parent", False)),
                    "session_id": session_id,
                    "text_repr": getattr(c, "text_repr", ""),
                    "chunk": c,
                }
            )

    def hybrid_search(
        self,
        dense_vector,
        query_text: str,
        top_k: int = 10,
        filters: Any = None,
        session_id: Any = None,
        only_children: bool = True,
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
    ):
        results: List[dict] = []
        for p in self.points:
            if session_id is not None and p["session_id"] != session_id:
                continue
            if only_children and p["is_parent"]:
                continue
            results.append(
                {
                    "id": p["id"],
                    "score": p["score"],
                    "parent_id": p["parent_id"],
                    "is_parent": p["is_parent"],
                    "session_id": p["session_id"],
                    "text_repr": p["text_repr"],
                }
            )
        return results[:top_k]

    def get_by_ids(self, ids):
        """Return full payloads (id + chunk) for a set of IDs."""
        id_set = set(ids)
        return [
            {"id": p["id"], **self._payload_of(p)}
            for p in self.points
            if p["id"] in id_set
        ]

    def get_parents_for_children(self, child_hits, session_id=None, max_parents: int = 5):
        parent_scores: dict = {}
        for hit in child_hits:
            pid = hit.get("parent_id")
            if not pid:
                continue
            score = float(hit.get("score", 0.0) or 0.0)
            prev = parent_scores.get(pid)
            if prev is None or score > prev:
                parent_scores[pid] = score

        if not parent_scores:
            return []
        ordered_ids = sorted(
            parent_scores.keys(), key=lambda k: parent_scores[k], reverse=True
        )[:max_parents]
        parents = self.get_by_ids(ordered_ids)
        index_map = {pid: i for i, pid in enumerate(ordered_ids)}
        parents.sort(key=lambda p: index_map.get(p.get("id"), 10**6))
        if session_id:
            parents = [p for p in parents if p.get("session_id") == session_id]
        return parents

    def delete_by_session(self, session_id: str) -> int:
        before = len(self.points)
        self.points = [p for p in self.points if p["session_id"] != session_id]
        return before - len(self.points)

    @staticmethod
    def _payload_of(point: dict) -> dict:
        return {
            "parent_id": point["parent_id"],
            "is_parent": point["is_parent"],
            "session_id": point["session_id"],
            "text_repr": point["text_repr"],
        }


@pytest.fixture
def stub_llm() -> StubLLMClient:
    return StubLLMClient()


@pytest.fixture
def stub_embedder() -> StubEmbedder:
    return StubEmbedder()


@pytest.fixture
def stub_qdrant() -> StubQdrantStore:
    return StubQdrantStore()


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin a known config baseline so tests aren't affected by env drift."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_DIM", "1024")
    yield
