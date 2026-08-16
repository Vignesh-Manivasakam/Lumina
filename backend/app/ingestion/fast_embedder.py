"""Local embedding service using FastEmbed + BGE-M3.

Runs entirely on CPU; no API keys required. The first call downloads
the model (~1.2 GB) and caches it under ``$HOME/.cache/fastembed``.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

from fastembed import TextEmbedding

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model(model_name: str) -> TextEmbedding:
    """Load and cache the FastEmbed model (one process-wide instance)."""
    logger.info("Loading FastEmbed model %s (first run downloads ~1.2 GB)…", model_name)
    model = TextEmbedding(model_name=model_name)
    logger.info("FastEmbed model %s loaded.", model_name)
    return model


class LocalEmbedder:
    """CPU-only BGE-M3 embedder.

    Attributes
    ----------
    dimension:
        Vector dimensionality (1024 for BGE-M3). Matches ``DENSE_DIM``
        consumed by ``QdrantStore``.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIM
        self._model = _get_model(self.model_name)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns a list of dense vectors."""
        if not texts:
            return []
        vectors = list(self._model.embed(texts))
        return [v.tolist() for v in vectors]

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
        if not query:
            raise ValueError("Query must be a non-empty string.")
        vectors = list(self._model.embed([query]))
        return vectors[0].tolist()
