"""Unit and integration tests for VoiceService and Voice API endpoints."""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.voice_service import VoiceService


client = TestClient(app)


class TestVoiceServiceTranscription:
    def test_transcribe_unconfigured_key_returns_graceful_notice(self):
        service = VoiceService(api_key="")
        text = service.transcribe(b"dummy audio data", format="wav")
        assert "not configured" in text.lower()

    def test_transcribe_empty_bytes_returns_empty_string(self):
        service = VoiceService(api_key="mock-key")
        text = service.transcribe(b"", format="wav")
        assert text == ""

    def test_transcribe_with_openai_client_success(self):
        service = VoiceService(api_key="mock-key")
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Lumina enterprise intelligence system"
        mock_client.audio.transcriptions.create.return_value = mock_transcript
        service._asr_client = mock_client
        service._client = mock_client

        result = service.transcribe(b"fake audio data", format="wav")
        assert result == "Lumina enterprise intelligence system"
        mock_client.audio.transcriptions.create.assert_called_once()

    def test_transcribe_openai_failure_falls_back_to_httpx(self):
        service = VoiceService(api_key="mock-key")
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = Exception("SDK error")
        service._asr_client = mock_client
        service._client = mock_client

        mock_http_resp = MagicMock()
        mock_http_resp.is_success = True
        mock_http_resp.json.return_value = {"text": "Transcribed via HTTP fallback"}

        with patch("httpx.Client") as mock_httpx:
            mock_httpx.return_value.__enter__.return_value.post.return_value = mock_http_resp
            result = service.transcribe(b"audio binary payload", format="mp3")
            assert result == "Transcribed via HTTP fallback"


class TestVoiceServiceSynthesis:
    def test_synthesize_unconfigured_key_returns_empty_bytes(self):
        service = VoiceService(api_key="")
        audio = service.synthesize("Hello Lumina")
        assert audio == b""

    def test_synthesize_empty_text_returns_empty_bytes(self):
        service = VoiceService(api_key="mock-key")
        audio = service.synthesize("   ")
        assert audio == b""

    def test_synthesize_with_openai_client_success(self):
        service = VoiceService(api_key="mock-key")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = b"RIFF_MOCK_WAVE_HEADER_AUDIO_STREAM"
        mock_client.audio.speech.create.return_value = mock_resp
        service._client = mock_client

        audio = service.synthesize("Synthesize this sentence into speech.")
        assert audio == b"RIFF_MOCK_WAVE_HEADER_AUDIO_STREAM"
        mock_client.audio.speech.create.assert_called_once()

    def test_synthesize_openai_failure_falls_back_to_httpx(self):
        service = VoiceService(api_key="mock-key")
        mock_client = MagicMock()
        mock_client.audio.speech.create.side_effect = Exception("SDK speech error")
        service._client = mock_client

        mock_http_resp = MagicMock()
        mock_http_resp.is_success = True
        mock_http_resp.content = b"RIFF_HTTP_SYNTHESIZED_WAVE"

        with patch("httpx.Client") as mock_httpx:
            mock_httpx.return_value.__enter__.return_value.post.return_value = mock_http_resp
            audio = service.synthesize("Fallback speech text", voice="en-US")
            assert audio == b"RIFF_HTTP_SYNTHESIZED_WAVE"


class TestVoiceAPIEndpoints:
    def test_transcribe_endpoint_success(self):
        with patch("app.routers.voice.voice_service.transcribe", return_value="Test audio transcription"):
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.wav", b"fake audio content", "audio/wav")},
            )
            assert response.status_code == 200
            assert response.json() == {"text": "Test audio transcription"}

    def test_transcribe_endpoint_with_audio_field(self):
        with patch("app.routers.voice.voice_service.transcribe", return_value="Audio field transcription"):
            response = client.post(
                "/api/voice/transcribe",
                files={"audio": ("sample.mp3", b"fake mp3 bytes", "audio/mpeg")},
                data={"format": "mp3"},
            )
            assert response.status_code == 200
            assert response.json() == {"text": "Audio field transcription"}

    def test_transcribe_endpoint_missing_file_raises_400(self):
        response = client.post("/api/voice/transcribe")
        assert response.status_code == 400
        assert "No audio file provided" in response.json()["detail"]

    def test_transcribe_endpoint_empty_file_raises_400(self):
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert response.status_code == 400
        assert "Empty audio file provided" in response.json()["detail"]

    def test_synthesize_endpoint_success(self):
        fake_wav = b"RIFF_SYNTHESIZED_AUDIO"
        with patch("app.routers.voice.voice_service.synthesize", return_value=fake_wav):
            response = client.post(
                "/api/voice/synthesize",
                json={"text": "Welcome to Lumina Enterprise", "voice": "en-US"},
            )
            assert response.status_code == 200
            assert response.content == fake_wav
            assert response.headers["content-type"] == "audio/wav"

    def test_synthesize_endpoint_empty_text_raises_400(self):
        response = client.post(
            "/api/voice/synthesize",
            json={"text": "   ", "voice": "en-US"},
        )
        assert response.status_code == 400
        assert "Text cannot be empty" in response.json()["detail"]

    def test_synthesize_endpoint_unconfigured_returns_empty_wav(self):
        with patch("app.routers.voice.voice_service.synthesize", return_value=b""):
            response = client.post(
                "/api/voice/synthesize",
                json={"text": "Hello world", "voice": "en-US"},
            )
            assert response.status_code == 200
            assert response.content == b""
            assert response.headers["content-type"] == "audio/wav"
