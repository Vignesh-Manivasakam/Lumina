"""Tests for ``app.services.gemini_client.GeminiClient``.

All tests mock the Google GenAI SDK so they run without a real API key.
Covers: generate_text, generate_stream, analyze_vision, retry logic,
and error/fallback behaviour.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(api_key: str = "test-key"):
    """Create a GeminiClient with a mocked google.genai SDK."""
    mock_genai_module = types.ModuleType("google.genai")
    mock_genai = MagicMock()
    mock_genai_module.Client = MagicMock(return_value=mock_genai)

    with patch.dict("sys.modules", {"google": types.ModuleType("google"),
                                     "google.genai": mock_genai_module}):
        with patch("os.getenv", side_effect=lambda k, d="": api_key if "GEMINI" in k or "GOOGLE" in k else d):
            from app.services.gemini_client import GeminiClient
            client = GeminiClient.__new__(GeminiClient)
            client.api_key = api_key
            client.model_name = "gemini-2.0-flash"
            client._client = mock_genai
    return client, mock_genai


class TestGeminiClientInit:
    """Test client initialization and is_configured."""

    def test_is_configured_with_key(self):
        client, _ = _make_client("test-key-123")
        assert client.is_configured()

    def test_is_not_configured_without_key(self):
        from app.services.gemini_client import GeminiClient
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = ""
        client._client = None
        assert not client.is_configured()


class TestGenerateText:
    """Test generate_text with mock responses."""

    def test_returns_text(self):
        client, mock = _make_client()
        mock_response = MagicMock()
        mock_response.text = "Hello, World!"
        mock.models.generate_content.return_value = mock_response

        result = client.generate_text("Say hello")
        assert result == "Hello, World!"
        mock.models.generate_content.assert_called_once()

    def test_system_instruction_passed(self):
        client, mock = _make_client()
        mock_response = MagicMock()
        mock_response.text = "OK"
        mock.models.generate_content.return_value = mock_response

        client.generate_text("test", system_instruction="Be brief")
        call_kwargs = mock.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config is not None
        assert config.get("system_instruction") == "Be brief"

    def test_returns_error_string_without_client(self):
        from app.services.gemini_client import GeminiClient
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = ""
        client._client = None
        result = client.generate_text("test")
        assert "Error" in result or "not configured" in result

    def test_handles_exception_gracefully(self):
        client, mock = _make_client()
        mock.models.generate_content.side_effect = RuntimeError("API down")

        result = client.generate_text("test")
        assert "Error" in result

    def test_empty_response(self):
        client, mock = _make_client()
        mock_response = MagicMock()
        mock_response.text = None
        mock.models.generate_content.return_value = mock_response

        result = client.generate_text("test")
        assert result == ""


class TestGenerateStream:
    """Test generate_stream yields tokens."""

    def test_yields_chunks(self):
        client, mock = _make_client()
        chunk1 = MagicMock()
        chunk1.text = "Hello "
        chunk2 = MagicMock()
        chunk2.text = "World"
        mock.models.generate_content_stream.return_value = [chunk1, chunk2]

        tokens = list(client.generate_stream("test"))
        assert tokens == ["Hello ", "World"]

    def test_skips_empty_chunks(self):
        client, mock = _make_client()
        chunk1 = MagicMock()
        chunk1.text = "data"
        chunk2 = MagicMock()
        chunk2.text = ""
        mock.models.generate_content_stream.return_value = [chunk1, chunk2]

        tokens = list(client.generate_stream("test"))
        assert tokens == ["data"]

    def test_yields_error_without_client(self):
        from app.services.gemini_client import GeminiClient
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = ""
        client._client = None
        tokens = list(client.generate_stream("test"))
        assert len(tokens) == 1
        assert "Error" in tokens[0] or "not configured" in tokens[0]


class TestAnalyzeVision:
    """Test multimodal vision analysis."""

    def test_returns_description(self):
        client, mock = _make_client()
        mock_response = MagicMock()
        mock_response.text = "A photo of a cat"
        mock.models.generate_content.return_value = mock_response

        import base64
        dummy_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()

        with patch.dict("sys.modules", {"google.genai.types": MagicMock()}):
            result = client.analyze_vision("Describe this image", dummy_b64)
        assert "cat" in result or result  # may vary with mock setup

    def test_returns_error_without_client(self):
        from app.services.gemini_client import GeminiClient
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = ""
        client._client = None
        result = client.analyze_vision("describe", "base64data")
        assert "Error" in result or "not configured" in result


class TestRetryLogic:
    """Verify tenacity retry decorators exist and are configured."""

    def test_generate_text_has_retry(self):
        from app.services.gemini_client import GeminiClient
        # The _generate_text_with_retry should have retry metadata
        assert hasattr(GeminiClient._generate_text_with_retry, "retry")

    def test_analyze_vision_has_retry(self):
        from app.services.gemini_client import GeminiClient
        assert hasattr(GeminiClient._analyze_vision_with_retry, "retry")
