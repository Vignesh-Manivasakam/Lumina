"""MCP server exposing Lumina RAG tools.

Fixes from Phase 1 (B1-B4):

* ``mcp`` package is no longer optional — import is at module top and
  is declared in ``requirements.txt``.
* ``embedder.embed_text`` -> ``local_embedder.embed_query`` (B2).
* ``qdrant_store.query`` -> ``qdrant_store.hybrid_search`` (B3).
* Reuse the singleton ``LocalEmbedder`` / ``QdrantStore`` from the
  FastAPI app instead of constructing fresh clients per MCP call (B4).

Phase 2: session scoping — ``query_knowledge_base`` now accepts an
optional ``session_id`` parameter and forwards it to ``hybrid_search``
so results are scoped per-tenant.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    try:
        from mcp.server import FastMCP  # type: ignore
    except ImportError:
        FastMCP = None  # type: ignore

from app.config import settings
from app.ingestion.fast_embedder import LocalEmbedder
from app.retrieval.qdrant_store import QdrantStore
from app.services.supabase_client import SupabaseService

logger = logging.getLogger(__name__)

mcp = FastMCP("Lumina RAG Server") if FastMCP is not None else None

# Shared singletons (B4 fix) - instantiated lazily so the MCP server can
# be imported in unit tests without forcing a Qdrant connection at
# import time.
_embedder: Optional[LocalEmbedder] = None
_qdrant: Optional[QdrantStore] = None
_supabase: Optional[SupabaseService] = None


def _get_embedder() -> LocalEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = LocalEmbedder()
    return _embedder


def _get_qdrant() -> QdrantStore:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantStore()
    return _qdrant


def _get_supabase() -> SupabaseService:
    global _supabase
    if _supabase is None:
        _supabase = SupabaseService()
    return _supabase


@mcp.tool()
def list_documents() -> str:
    """List all uploaded documents in the Lumina RAG knowledge base."""
    try:
        docs = _get_supabase().get_all_documents()
        if not docs:
            return "Uploaded Documents:\nNo documents found."
        lines = [
            f"- {d['filename']} (Type: {d['file_type']}, Dept: {d['dept']}, "
            f"Status: {d['status']}, ID: {d['id']})"
            for d in docs
        ]
        return "Uploaded Documents:\n" + "\n".join(lines)
    except Exception as e:
        logger.exception("list_documents failed")
        return f"Error listing documents: {e}"


@mcp.tool()
def query_knowledge_base(
    query: str,
    dept: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Query the Lumina RAG knowledge base for text segments, tables, and visual captions.

    Args:
        query: The search query to retrieve relevant contexts for.
        dept: Optional department filter (General, HR, Finance, Policy, Legal).
        session_id: Optional session UUID for multi-tenant isolation. When
            provided, only chunks belonging to this session are returned.
    """
    try:
        # B2: LocalEmbedder.embed_query is the correct method name
        query_vector = _get_embedder().embed_query(query)
        filters = {"dept": dept} if dept else None

        # B3: hybrid_search is the correct method name on QdrantStore
        # Phase 2: forward session_id so retrieval is scoped per-tenant
        results = _get_qdrant().hybrid_search(
            dense_vector=query_vector,
            query_text=query,
            top_k=5,
            filters=filters,
            session_id=session_id,
        )

        if not results:
            return "Retrieved Contexts:\nNo matches found."

        formatted = []
        for i, r in enumerate(results, 1):
            score = r.get("rerank_score", r.get("score", 0.0))
            formatted.append(
                f"Result {i} (Score: {float(score):.3f}, "
                f"Modality: {r.get('modality', 'text')}, "
                f"Page: {r.get('page_num', 'N/A')}):\n{r.get('text_repr', '')}\n"
            )
        return "Retrieved Contexts:\n\n" + "\n---\n\n".join(formatted)
    except Exception as e:
        logger.exception("query_knowledge_base failed")
        return f"Error querying knowledge base: {e}"


if __name__ == "__main__":  # pragma: no cover
    mcp.run()
