"""Input content-safety guard for Lumina RAG.

Uses provider-agnostic LLM classification (NVIDIA / Gemini) along with fast
blocklist regex checks before invoking the graph.

The guard is intentionally permissive: if no LLM provider is configured
or an error occurs during classification, it defaults to safe (graceful fallback).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Conservative patterns that bypass the LLM safety call entirely. Used
# only to short-circuit obvious prompt-injection / PII requests.
_BLOCKLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (?:all )?previous instructions", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"reveal your (?:api ?key|instructions)", re.IGNORECASE),
)


class SafetyGuard:
    """Best-effort safety check used by ``/api/chat`` before invoking the graph."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self._llm = llm_client
        self._client = None  # Back-compat attribute for tests

        if self._llm is None:
            try:
                from app.services.llm_client import LLMClient
                self._llm = LLMClient(task="safety")
            except Exception as exc:
                logger.warning("SafetyGuard could not initialize LLMClient: %s", exc)
                self._llm = None

    @staticmethod
    def _has_blocklist_match(text: str) -> bool:
        return any(p.search(text) for p in _BLOCKLIST_PATTERNS)

    def is_safe(self, text: str) -> bool:
        """Return True if ``text`` passes the safety filter.

        Implements graceful fallback: any exception or unavailable
        client returns True so the pipeline keeps flowing.
        """
        if not text or not text.strip():
            return True

        if self._has_blocklist_match(text):
            logger.info("SafetyGuard: blocklist match for input.")
            return False

        # Support tests setting _client = None or instance created via __new__
        llm = getattr(self, "_llm", None)
        if llm is None and getattr(self, "_client", None) is None:
            return True

        try:
            if llm is not None:
                resp = llm.generate_text(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are a content safety classifier for an AI research assistant.\n"
                                "Classify a query as 'unsafe' ONLY if it explicitly requests:\n"
                                "- Self-harm, suicide, or severe bodily harm\n"
                                "- Cyberattacks, exploits, or malware generation\n"
                                "- CSAM or severe sexual violence\n"
                                "- Direct hate speech or terroristic threats\n\n"
                                "All other requests (art generation, Ghibli/anime styles, image creation, "
                                "coding, document analysis, creative writing, everyday conversation) are 100% SAFE.\n"
                                "Reply with ONLY 'safe' or 'unsafe'."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Classify this input as 'safe' or 'unsafe':\n{text[:512]}",
                        },
                    ],
                    max_tokens=8,
                    temperature=0.0,
                )
                content = resp.content.strip().lower()
                # Check for explicit unsafe verdict
                if content.startswith("unsafe") or content == "unsafe":
                    return False
                return True
            return True
        except Exception as exc:
            logger.warning("SafetyGuard LLM check failed; defaulting to safe: %s", exc)
            return True


__all__: Iterable[str] = ("SafetyGuard",)
