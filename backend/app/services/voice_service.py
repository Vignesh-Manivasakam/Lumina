"""Voice transcription and synthesis service using NVIDIA NIM (Whisper & Magpie TTS)."""
from __future__ import annotations

import io
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class VoiceService:
    """Voice transcription (STT) and speech synthesis (TTS) service."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        asr_model: Optional[str] = None,
        tts_model: Optional[str] = None,
    ) -> None:
        if api_key is not None:
            self.asr_api_key = api_key
            self.asr_base_url = base_url or getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            self.asr_model = asr_model or getattr(settings, "NVIDIA_ASR_MODEL", "nvidia/whisper-large-v3")
            self.api_key = api_key
            self.base_url = base_url or getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        else:
            groq_key = getattr(settings, "GROQ_API_KEY", "")
            if groq_key:
                self.asr_api_key = groq_key
                self.asr_base_url = "https://api.groq.com/openai/v1"
                self.asr_model = asr_model or "whisper-large-v3-turbo"
            else:
                self.asr_api_key = getattr(settings, "NVIDIA_API_KEY", "")
                self.asr_base_url = base_url or getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
                self.asr_model = asr_model or getattr(settings, "NVIDIA_ASR_MODEL", "nvidia/whisper-large-v3")
            self.api_key = getattr(settings, "NVIDIA_API_KEY", "")
            self.base_url = base_url or getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

        self.tts_model = tts_model or getattr(settings, "NVIDIA_TTS_MODEL", "nvidia/magpie-tts-multilingual")
        self._client = None
        self._asr_client = None

        if self.asr_api_key:
            try:
                from openai import OpenAI
                self._asr_client = OpenAI(
                    api_key=self.asr_api_key,
                    base_url=self.asr_base_url,
                )
                logger.info("VoiceService ASR initialized with base_url=%s model=%s", self.asr_base_url, self.asr_model)
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client for ASR: %s", exc)

        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                logger.info("VoiceService initialized with base_url=%s", self.base_url)
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client for VoiceService: %s", exc)
                self._client = None

    def transcribe(self, audio_bytes: bytes, format: str = "wav") -> str:
        """Transcribe audio bytes to text using Whisper-large-v3."""
        if not self.asr_api_key:
            logger.warning("Transcribe called without ASR API key configured.")
            return "Transcription unavailable: API key is not configured."

        if not audio_bytes:
            return ""

        filename = f"audio.{format}"

        # Method 1: OpenAI SDK audio transcriptions
        client = self._asr_client or self._client
        if client:
            try:
                buffer = io.BytesIO(audio_bytes)
                buffer.name = filename
                transcription = client.audio.transcriptions.create(
                    model=self.asr_model,
                    file=buffer,
                )
                text = getattr(transcription, "text", "") or str(transcription)
                return text.strip()
            except Exception as exc:
                logger.warning("OpenAI client transcription failed: %s; trying HTTP fallback", exc)

        # Method 2: HTTP multipart fallback via httpx
        try:
            import httpx
            url = f"{self.asr_base_url.rstrip('/')}/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.asr_api_key}"}
            files = {"file": (filename, audio_bytes, f"audio/{format}")}
            data = {"model": self.asr_model}

            with httpx.Client(timeout=30.0) as http_client:
                resp = http_client.post(url, headers=headers, files=files, data=data)
                if resp.is_success:
                    result = resp.json()
                    return (result.get("text") or "").strip()
                logger.error("HTTP transcription failed (%d): %s", resp.status_code, resp.text)
                return f"Transcription error ({resp.status_code}): {resp.text}"
        except Exception as exc:
            logger.exception("HTTP transcription exception: %s", exc)
            return f"Transcription error: {exc}"

    def synthesize(self, text: str, voice: str = "en-US") -> bytes:
        """Synthesize text to speech audio bytes using NVIDIA Magpie TTS."""
        if not self.api_key:
            logger.warning("Synthesize called without NVIDIA_API_KEY configured.")
            return b""

        if not text.strip():
            return b""

        # Method 1: OpenAI SDK speech generation
        if self._client:
            try:
                response = self._client.audio.speech.create(
                    model=self.tts_model,
                    voice=voice,
                    input=text,
                    response_format="wav",
                )
                if hasattr(response, "content"):
                    return response.content
                if hasattr(response, "read"):
                    return response.read()
            except Exception as exc:
                logger.warning("OpenAI client synthesis failed: %s; trying HTTP fallback", exc)

        # Method 2: HTTP POST fallback via httpx
        try:
            import httpx
            url = f"{self.base_url.rstrip('/')}/audio/speech"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.tts_model,
                "input": text,
                "voice": voice,
                "response_format": "wav",
            }
            with httpx.Client(timeout=30.0) as http_client:
                resp = http_client.post(url, headers=headers, json=payload)
                if resp.is_success:
                    return resp.content
                logger.error("HTTP synthesis failed (%d): %s", resp.status_code, resp.text)
                return b""
        except Exception as exc:
            logger.exception("HTTP synthesis exception: %s", exc)
            return b""


__all__ = ["VoiceService"]
