"""Unit tests for VoiceService."""
from unittest.mock import MagicMock, patch
import pytest

from app.services.voice_service import VoiceService


def test_voice_service_transcribe_no_key():
    service = VoiceService(api_key="")
    text = service.transcribe(b"fake audio data", format="wav")
    assert "not configured" in text.lower()


def test_voice_service_transcribe_empty_bytes():
    service = VoiceService(api_key="mock-key")
    text = service.transcribe(b"", format="wav")
    assert text == ""


def test_voice_service_transcribe_with_client():
    service = VoiceService(api_key="mock-key")
    mock_client = MagicMock()
    mock_transcript = MagicMock()
    mock_transcript.text = "Hello, Lumina RAG!"
    mock_client.audio.transcriptions.create.return_value = mock_transcript
    service._asr_client = mock_client
    service._client = mock_client

    text = service.transcribe(b"fake audio content", format="wav")
    assert text == "Hello, Lumina RAG!"


def test_voice_service_synthesize_no_key():
    service = VoiceService(api_key="")
    audio = service.synthesize("Hello world")
    assert audio == b""


def test_voice_service_synthesize_empty_text():
    service = VoiceService(api_key="mock-key")
    audio = service.synthesize("")
    assert audio == b""


def test_voice_service_synthesize_with_client():
    service = VoiceService(api_key="mock-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = b"RIFF....WAVEfmt"
    mock_client.audio.speech.create.return_value = mock_response
    service._client = mock_client

    audio = service.synthesize("This is Lumina voice synthesis.")
    assert audio == b"RIFF....WAVEfmt"
