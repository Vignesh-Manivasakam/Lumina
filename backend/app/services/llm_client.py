"""LLM client for Lumina RAG.

Unified facade over ProviderRegistry (NVIDIA NIM primary, Google Gemini fallback).
Exposes the exact same public API: generate(), generate_text(), embed(), rerank().
All agents and ingestion services interact with LLMClient without needing to know
which underlying provider (NVIDIA or Gemini) is active.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

from app.config import settings
from app.services.provider_registry import (
    LLMProvider,
    ProviderRegistry,
    ProviderResponse,
    ProviderStreamChunk,
    ProviderStreamWrapper,
    _GeminiResponseWrapper,
    _GeminiStreamChunk,
    _GeminiStreamWrapper,
    _lc_messages_to_gemini,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client facade delegating to ProviderRegistry.

    Public API
    ----------
    - generate(messages, stream=False, model=None, max_tokens=1500, temperature=0.1)
    - generate_text(messages, model=None, max_tokens=500, temperature=0.1)
    - embed(inputs) -- deprecated placeholder; raises NotImplementedError
    - rerank(query, passages) -- deprecated placeholder; raises NotImplementedError
    """

    def __init__(
        self,
        task: str = "generator",
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.task = task

        # Verify at least one API key is configured unless provider explicitly passed
        if provider is None:
            has_nvidia = bool(getattr(settings, "NVIDIA_API_KEY", ""))
            has_gemini = bool(getattr(settings, "GEMINI_API_KEY", ""))
            if not has_nvidia and not has_gemini:
                raise RuntimeError(
                    "No LLM API key is configured. Set NVIDIA_API_KEY or GEMINI_API_KEY "
                    "in backend/.env (see backend/env.example) before starting."
                )

        self.provider: LLMProvider = provider or ProviderRegistry.get_for_task(self.task)
        self.api_key: str = getattr(self.provider, "api_key", "") or ""

        # Backward compatibility models dict
        provider_type = self.provider.provider_name
        task_models = ProviderRegistry.get_task_model_map(provider_type)
        self.models = {
            "generator": task_models.get("generator", ""),
            "text_llm": task_models.get("router", task_models.get("generator", "")),
        }

        logger.info(
            "LLMClient initialized for task=%s with provider=%s model=%s",
            self.task,
            self.provider.provider_name,
            self.provider.default_model,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: List[dict],
        stream: bool = False,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        """Generate a chat completion (text or multimodal, streaming or non-streaming).

        Returns a ProviderResponse with ``.content`` / ``.text`` (non-streaming)
        or an iterable ProviderStreamWrapper yielding chunks with ``.content`` / ``.text`` (streaming).
        """
        return self.provider.generate(
            messages=messages,
            stream=stream,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_text(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> ProviderResponse:
        """Convenience wrapper for non-streaming text completion."""
        return self.provider.generate_text(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    # ------------------------------------------------------------------
    # Placeholders — real implementations live in dedicated modules
    # ------------------------------------------------------------------

    def embed(self, inputs: List[str]) -> List[List[float]]:
        """Deprecated: embeddings use ``LocalEmbedder`` (FastEmbed BGE-M3).

        Raises so callers fail loudly if they attempt to use legacy embedding calls.
        """
        raise NotImplementedError(
            "LLMClient.embed() is removed. Use app.ingestion.fast_embedder."
            "LocalEmbedder.embed_texts() instead."
        )

    def rerank(self, query: str, passages: List[str]) -> List[float]:
        """Deprecated: reranking uses ``CPUReranker`` (FlashRank).

        Raises so callers fail loudly if they attempt to use legacy reranking calls.
        """
        raise NotImplementedError(
            "LLMClient.rerank() is removed. Use app.retrieval.cpu_reranker."
            "CPUReranker.rerank() instead."
        )


__all__ = [
    "LLMClient",
    "ProviderResponse",
    "ProviderStreamChunk",
    "ProviderStreamWrapper",
    "_GeminiResponseWrapper",
    "_GeminiStreamChunk",
    "_GeminiStreamWrapper",
    "_lc_messages_to_gemini",
]
