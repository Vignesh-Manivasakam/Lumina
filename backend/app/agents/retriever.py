"""Retriever agent (Phase 3).

Two-step retrieval:
1. **Child search** — Qdrant returns top-K child chunks (128 tokens,
   high precision). Session + parent-child filters applied.
2. **Parent resolution** — children map to parents (1024 tokens, broad
   context). The retriever returns the *parents* to downstream agents
   so the LLM sees rich context.

When ``state["use_parent_resolution"]`` is False (set by tests / admin
tools) the retriever returns the raw child hits instead.
"""
from __future__ import annotations

from typing import List

from app.config import settings
from app.ingestion.embedder import MultimodalEmbedder
from app.ingestion.fast_embedder import LocalEmbedder
from app.retrieval.cpu_reranker import CPUReranker
from app.retrieval.qdrant_store import QdrantStore
from app.services.llm_client import LLMClient


QUERY_TYPE_WEIGHTS = {
    "keyword": (0.8, 0.2),
    "numerical": (0.9, 0.1),
    "semantic": (0.2, 0.8),
    "multi_hop": (0.5, 0.5),
}


class RetrieverAgent:
    def __init__(
        self,
        qdrant_store: QdrantStore,
        embedder: MultimodalEmbedder | LocalEmbedder,
        llm_client: LLMClient | None = None,
        reranker: CPUReranker | None = None,
    ) -> None:
        self.store = qdrant_store
        self.embedder = embedder
        self.llm = llm_client or LLMClient()
        self.reranker = reranker or CPUReranker()
        # Back-compat alias for code paths still reading .nvidia
        self.nvidia = self.llm

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def retrieve(self, state: dict) -> dict:
        query = state.get("rewritten_query") or state["query"]
        image_b64 = state.get("user_image_b64")
        filters = state.get("filters") or {}
        session_id = state.get("session_id")
        use_parents = state.get("use_parent_resolution", True)
        query_type = (state.get("query_type") or "").strip().lower()

        # Step 1: determine query-aware retrieval weights
        bm25_weight, dense_weight = QUERY_TYPE_WEIGHTS.get(query_type, (0.5, 0.5))

        # Step 2: embed the query (BGE-M3)
        dense_vec = self._embed_query(query, image_b64)

        # Step 3: hybrid search restricted to child chunks (Phase 3)
        child_hits = self.store.hybrid_search(
            dense_vector=dense_vec,
            query_text=query,
            top_k=settings.TOP_K_RETRIEVE,
            filters=filters,
            session_id=session_id,
            only_children=True,
            bm25_weight=bm25_weight,
            dense_weight=dense_weight,
        )

        # Step 4: rerank child hits via FlashRank
        if len(child_hits) > settings.TOP_K_RERANK:
            child_hits = self.reranker.rerank(query, child_hits)[:settings.TOP_K_RERANK]

        # Step 5: resolve to parents for context-rich retrieval
        if use_parents:
            retrieved_docs = self.store.get_parents_for_children(
                child_hits,
                session_id=session_id,
                max_parents=settings.TOP_K_RERANK,
            )
            # Fallback: if no parents found (shouldn't happen, but be
            # defensive), keep child hits so downstream never sees empty.
            if not retrieved_docs:
                retrieved_docs = child_hits
        else:
            retrieved_docs = child_hits

        # Surface the child hits too so the grader / generator can
        # decide what to do with them (e.g. show chunk-level citations).
        state["retrieved_docs"] = retrieved_docs
        state["retrieved_children"] = child_hits
        state["retrieval_count"] = state.get("retrieval_count", 0) + 1
        child_count = len(child_hits)
        parent_count = len(retrieved_docs)
        type_str = f" ({query_type}: bm25={bm25_weight}, dense={dense_weight})" if query_type else ""
        state["thinking_note"] = (
            f"Hybrid search{type_str} returned {child_count} child hits; "
            f"resolved {parent_count} parent contexts after rerank."
        )
        return state

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _embed_query(self, query: str, image_b64):
        if image_b64 and hasattr(self.embedder, "embed_query"):
            return self.embedder.embed_query(query, image_b64)
        return self.embedder.embed_query(query)


__all__: List[str] = ["RetrieverAgent"]
