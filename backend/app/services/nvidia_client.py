"""DEPRECATED shim for the old NVIDIA NIM client.

The Lumina backend migrated to Google Gemini 2.0 Flash (``LLMClient``)
plus local FastEmbed + FlashRank models. Importing from this module
emits a deprecation warning and instantiating the class raises so any
forgotten reference fails loudly during startup rather than silently
hitting the old NVIDIA endpoint.

Migration map:
    NVIDIAClient.embed   -> app.ingestion.fast_embedder.LocalEmbedder
    NVIDIAClient.rerank  -> app.retrieval.cpu_reranker.CPUReranker
    NVIDIAClient.generate / generate_text -> app.services.llm_client.LLMClient
"""
from __future__ import annotations

import warnings


class NVIDIAClient:
    """Removed in Phase 1 of the free-stack migration."""

    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "NVIDIAClient has been removed. Use app.services.llm_client.LLMClient "
            "for text generation, app.ingestion.fast_embedder.LocalEmbedder for "
            "embeddings, and app.retrieval.cpu_reranker.CPUReranker for reranking.",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError(
            "NVIDIAClient has been removed. Migrate to LLMClient / LocalEmbedder / "
            "CPUReranker. See backend/app/services/llm_client.py."
        )
