"""Local FastEmbed wrapper — alternate BGE-M3 model.

NOTE: Vestigial duplicate of ``app.ingestion.fast_embedder.LocalEmbedder``
(which uses ``BAAI/bge-large-en-v1.5``, the model fastembed currently
ships with). Kept here so callers who explicitly want BGE-M3 (568M params,
multilingual) can opt in. The active ingestion path uses
``LocalEmbedder``.
"""
from typing import List, Union
import numpy as np

class FastEmbedService:
    """
    Local FastEmbed BGE-M3 (1024-dim) embedding service.
    Pure CPU via ONNX Runtime. No API keys, no network calls per request.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
                print(f"[FastEmbedService] Loading local embedding model '{self.model_name}'...")
                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                print(f"[FastEmbedService] Failed to load FastEmbed model: {e}")
                raise RuntimeError(f"FastEmbed initialization error: {e}")
        return self._model

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        if not documents:
            return []
        model = self._get_model()
        embeddings_generator = model.embed(documents)
        return [np.array(emb).tolist() for emb in embeddings_generator]

    def embed_query(self, query: str) -> List[float]:
        if not query:
            return [0.0] * 1024
        embeddings = self.embed_documents([query])
        return embeddings[0] if embeddings else [0.0] * 1024
