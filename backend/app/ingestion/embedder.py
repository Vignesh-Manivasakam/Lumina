"""Multimodal chunk embedder.

Thin wrapper over :class:`LocalEmbedder` (FastEmbed BGE-M3). Kept under
the historical ``MultimodalEmbedder`` name so existing call sites in
``ingestion.pipeline`` and ``mcp_server`` keep working after the
NVIDIA → local migration.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.ingestion.chunking import MultimodalChunk
from app.ingestion.fast_embedder import LocalEmbedder

logger = logging.getLogger(__name__)


class MultimodalEmbedder:
    """Embed chunks using local BGE-M3 (CPU).

    For text/table/audio chunks, only ``text_repr`` is embedded. For
    image/video-frame chunks the same path is used (caption + context
    string); the raw image bytes are stored in ``base64`` separately
    and consumed by the generator node when the user query actually
    references the image.
    """

    def __init__(self, embedder: Optional[LocalEmbedder] = None) -> None:
        self._embedder = embedder or LocalEmbedder()

    def embed_chunks(self, chunks: List[MultimodalChunk]) -> List[MultimodalChunk]:
        """Embed ``chunks`` in-place. Empty input is a no-op."""
        if not chunks:
            return chunks
        texts = [c.text_repr for c in chunks]
        embeddings = self._embedder.embed_texts(texts)
        for chunk, vec in zip(chunks, embeddings):
            chunk.embedding = vec
        return chunks

    def embed_query(self, query: str, image_b64: Optional[str] = None) -> List[float]:
        """Embed a user query.

        ``image_b64`` is accepted for API back-compat; with BGE-M3 the
        image is not embedded as a vector. When an image is attached
        we prepend a short marker so the semantic space still
        distinguishes multimodal queries.
        """
        if image_b64 and not query:
            query = "[image attached]"
        elif image_b64:
            query = f"[image attached] {query}"
        return self._embedder.embed_query(query)

    # Historical shims (no longer used but kept for type-checkers) ----
    @property
    def dimension(self) -> int:
        return self._embedder.dimension
