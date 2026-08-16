"""Tests for the unified LLMClient and ProviderRegistry."""
from __future__ import annotations

import pytest

from app.config import settings
from app.services.llm_client import (
    LLMClient,
    _GeminiResponseWrapper,
    _GeminiStreamChunk,
    _GeminiStreamWrapper,
    _lc_messages_to_gemini,
)
from app.services.provider_registry import (
    GeminiProvider,
    LLMProvider,
    NvidiaProvider,
    ProviderRegistry,
    ProviderResponse,
    ProviderStreamChunk,
    ProviderStreamWrapper,
)


class TestLCMessagesToGemini:
    """The message converter must extract system prompts and pass content."""

    def test_extracts_single_system_message(self):
        sys_text, contents = _lc_messages_to_gemini(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
            ]
        )
        assert sys_text == "You are helpful."
        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"] == [{"text": "Hi"}]

    def test_joins_multiple_system_messages(self):
        sys_text, _ = _lc_messages_to_gemini(
            [
                {"role": "system", "content": "First."},
                {"role": "system", "content": "Second."},
                {"role": "user", "content": "Go"},
            ]
        )
        assert sys_text == "First.\n\nSecond."

    def test_maps_assistant_role_to_model(self):
        _, contents = _lc_messages_to_gemini(
            [{"role": "assistant", "content": "Hello"}]
        )
        assert contents[0]["role"] == "model"

    def test_passes_through_text_parts(self):
        _, contents = _lc_messages_to_gemini(
            [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
        )
        assert contents[0]["parts"] == [{"text": "hello"}]

    def test_passes_through_image_url(self):
        _, contents = _lc_messages_to_gemini(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,AAAA"
                            },
                        }
                    ],
                }
            ]
        )
        assert contents[0]["parts"][0]["inline_data"]["mime_type"] == "image/png"
        assert contents[0]["parts"][0]["inline_data"]["data"] == "AAAA"


class TestResponseWrapper:
    def test_content_passes_through(self):
        class _R:
            text = "hello world"

        w = _GeminiResponseWrapper(_R())
        assert w.content == "hello world"
        assert w.text == "hello world"

    def test_content_handles_empty(self):
        class _R:
            text = None

        w = _GeminiResponseWrapper(_R())
        assert w.content == ""


class TestStreamChunk:
    def test_stores_text(self):
        c = _GeminiStreamChunk("tok")
        assert c.content == "tok"
        assert c.text == "tok"

    def test_handles_none(self):
        c = _GeminiStreamChunk(None)
        assert c.content == ""


class TestLLMClientInit:
    def test_raises_without_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        with pytest.raises(RuntimeError, match="No LLM API key is configured"):
            LLMClient()

    def test_initialises_with_gemini_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-gemini-key")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
        ProviderRegistry.reset()
        client = LLMClient()
        assert client.api_key == "fake-gemini-key"
        assert "generator" in client.models
        assert client.provider.provider_name == "gemini"

    def test_initialises_with_nvidia_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "nvidia")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "fake-nvidia-key")
        ProviderRegistry.reset()
        client = LLMClient()
        assert client.api_key == "fake-nvidia-key"
        assert client.provider.provider_name == "nvidia"


class TestDeprecatedMethods:
    """embed() and rerank() must raise NotImplementedError to surface
    stale call sites."""

    def test_embed_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
        client = LLMClient()
        with pytest.raises(NotImplementedError, match="LocalEmbedder"):
            client.embed(["text"])

    def test_rerank_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
        client = LLMClient()
        with pytest.raises(NotImplementedError, match="CPUReranker"):
            client.rerank("q", ["a"])


def test_quote_re_cleans_quotes():
    import re
    pat = re.compile(r"^[\s\"'`]+|[\s\"'`]+$")
    assert pat.sub("", '"hello"') == "hello"
    assert pat.sub("", "`hi`") == "hi"
    assert pat.sub("", "  spaced  ") == "spaced"
