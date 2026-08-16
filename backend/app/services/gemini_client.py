"""Legacy standalone Gemini SDK wrapper.

NOTE: Superseded by ``app.services.llm_client.LLMClient`` (Phase 1 free-stack
migration). Kept here for backward compatibility with code paths that import
``GeminiClient`` directly. The active ingestion / agent paths all use
``LLMClient``.
"""
import logging
import os
import json
from typing import List, Optional, Dict, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.config import settings

logger = logging.getLogger(__name__)

class GeminiClient:
    """
    Standalone Gemini 2.0 Flash wrapper using the official ``google-genai``
    SDK. Provided for callers that don't need the LangChain-shaped
    ``.content``/streaming surface that ``LLMClient`` exposes.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        self.model_name = "gemini-2.0-flash"
        self._client = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiClient] Google GenAI SDK init error: {e}")

    def is_configured(self) -> bool:
        return bool(self.api_key and self._client)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(
            "GeminiClient.generate_text retry %d after %s",
            retry_state.attempt_number,
            retry_state.outcome.exception() if retry_state.outcome else "unknown",
        ),
        reraise=True,
    )
    def _generate_text_with_retry(self, prompt: str, config: dict) -> str:
        """Inner call with tenacity retry for rate-limit / transient errors."""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config if config else None,
        )
        return response.text or ""

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.2) -> str:
        """Generate plain text completion with automatic retry on rate limits."""
        if not self._client:
            return "[GeminiClient] Error: GEMINI_API_KEY not configured."

        try:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction
            config["temperature"] = temperature
            return self._generate_text_with_retry(prompt, config)
        except Exception as e:
            logger.error("GeminiClient.generate_text failed after retries: %s", e)
            return f"Error executing Gemini request: {str(e)}"

    def generate_stream(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.2):
        """Yield text tokens via generator stream."""
        if not self._client:
            yield "[GeminiClient] Error: GEMINI_API_KEY not configured."
            return

        try:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction
            config["temperature"] = temperature

            response = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=config if config else None
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"[Error: {str(e)}]"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(
            "GeminiClient.analyze_vision retry %d after %s",
            retry_state.attempt_number,
            retry_state.outcome.exception() if retry_state.outcome else "unknown",
        ),
        reraise=True,
    )
    def _analyze_vision_with_retry(self, contents: list) -> str:
        """Inner call with tenacity retry for vision requests."""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        return response.text or ""

    def analyze_vision(self, prompt: str, image_b64: str) -> str:
        """Analyze base64-encoded image with Gemini 2.0 Flash multimodal engine."""
        if not self._client:
            return "[GeminiClient] Error: GEMINI_API_KEY not configured."

        try:
            import base64
            image_bytes = base64.b64decode(image_b64)

            from google.genai import types
            image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

            return self._analyze_vision_with_retry([image_part, prompt])
        except Exception as e:
            logger.error("GeminiClient.analyze_vision failed after retries: %s", e)
            return f"Error performing vision analysis: {str(e)}"
