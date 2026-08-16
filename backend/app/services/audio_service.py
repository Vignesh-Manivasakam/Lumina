import os
from typing import Optional
from app.config import settings

class GroqAudioService:
    """
    100% Free Speech-to-Text service using Groq Whisper Large V3.
    Free tier limit: 7,000 tokens / min.

    NOTE: Vestigial duplicate of the inline Groq call in
    ``app.ingestion.audio_pipeline.AudioPipeline``. Kept for backward
    compatibility with code paths that import ``GroqAudioService``
    directly. The active ingestion path uses ``AudioPipeline``.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY") or settings.GROQ_API_KEY
        self._client = None

        if self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"[GroqAudioService] Groq client init failed: {e}")

    def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio file (WAV, MP3, M4A, OGG) to text using Whisper Large V3."""
        if not self._client:
            return "[GroqAudioService] Error: GROQ_API_KEY is not set."

        if not os.path.exists(file_path):
            return f"[GroqAudioService] Error: File '{file_path}' not found."

        try:
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as file:
                transcription = self._client.audio.transcriptions.create(
                    file=(filename, file.read()),
                    model="whisper-large-v3",
                    response_format="text"
                )
            return str(transcription).strip()
        except Exception as e:
            print(f"[GroqAudioService] Transcription error: {e}")
            return f"Error transcribing audio: {str(e)}"
