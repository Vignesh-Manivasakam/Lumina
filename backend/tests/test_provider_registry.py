"""Unit and integration tests for ProviderRegistry and LLMProvider abstraction."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.config import settings
from app.services.llm_client import LLMClient
from app.services.provider_registry import (
    GeminiProvider,
    LLMProvider,
    NvidiaProvider,
    ProviderRegistry,
    ProviderResponse,
    ProviderStreamChunk,
    ProviderStreamWrapper,
    _format_openai_messages,
    _lc_messages_to_gemini,
)


class TestProviderWrappers:
    def test_provider_response_string(self):
        resp = ProviderResponse("test content")
        assert resp.content == "test content"
        assert resp.text == "test content"
        assert "test content" in repr(resp)

    def test_provider_response_from_object(self):
        mock_obj = MagicMock()
        mock_obj.text = "generated from text"
        resp = ProviderResponse(mock_obj)
        assert resp.content == "generated from text"
        assert resp.text == "generated from text"

    def test_provider_response_from_content_attr(self):
        mock_obj = MagicMock(spec=[])
        mock_obj.content = "content attr value"
        resp = ProviderResponse(mock_obj)
        assert resp.content == "content attr value"

    def test_provider_stream_chunk_string(self):
        chunk = ProviderStreamChunk("token")
        assert chunk.content == "token"
        assert chunk.text == "token"
        assert "token" in repr(chunk)

    def test_provider_stream_chunk_from_object(self):
        mock_chunk = MagicMock()
        mock_chunk.text = "streamed text"
        chunk = ProviderStreamChunk(mock_chunk)
        assert chunk.content == "streamed text"
        assert chunk.text == "streamed text"

    def test_provider_stream_wrapper_iteration(self):
        raw_items = ["chunk1", ProviderStreamChunk("chunk2"), MagicMock(text="chunk3")]
        wrapper = ProviderStreamWrapper(raw_items)
        results = [c.content for c in wrapper]
        assert results == ["chunk1", "chunk2", "chunk3"]


class TestMessageFormatting:
    def test_format_openai_messages(self):
        msgs = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "model", "content": "I am ready."},
            {"role": "user", "content": "Help me."},
        ]
        formatted = _format_openai_messages(msgs)
        assert formatted[0] == {"role": "system", "content": "You are an assistant."}
        assert formatted[1] == {"role": "assistant", "content": "I am ready."}
        assert formatted[2] == {"role": "user", "content": "Help me."}

    def test_lc_messages_to_gemini(self):
        msgs = [
            {"role": "system", "content": "System directive"},
            {"role": "user", "content": "Hello Gemini"},
            {"role": "assistant", "content": "Hello user"},
        ]
        sys_inst, contents = _lc_messages_to_gemini(msgs)
        assert sys_inst == "System directive"
        assert len(contents) == 2
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"][0]["text"] == "Hello Gemini"
        assert contents[1]["role"] == "model"
        assert contents[1]["parts"][0]["text"] == "Hello user"


class TestNvidiaProvider:
    def test_nvidia_provider_init(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-nv-key")
        monkeypatch.setattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        provider = NvidiaProvider(api_key="test-nv-key", default_model="nvidia/nemotron-test")
        assert provider.provider_name == "nvidia"
        assert provider.default_model == "nvidia/nemotron-test"
        assert provider.api_key == "test-nv-key"

    def test_nvidia_generate_non_streaming(self):
        provider = NvidiaProvider(api_key="fake-key", default_model="test-model")
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "NVIDIA output text"
        mock_response = MagicMock(choices=[mock_choice])
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        resp = provider.generate([{"role": "user", "content": "hello"}], stream=False)
        assert isinstance(resp, ProviderResponse)
        assert resp.content == "NVIDIA output text"
        mock_client.chat.completions.create.assert_called_once()

    def test_nvidia_generate_text(self):
        provider = NvidiaProvider(api_key="fake-key", default_model="test-model")
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "NVIDIA text output"
        mock_response = MagicMock(choices=[mock_choice])
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        resp = provider.generate_text([{"role": "user", "content": "hello"}])
        assert isinstance(resp, ProviderResponse)
        assert resp.content == "NVIDIA text output"

    def test_nvidia_generate_streaming(self):
        provider = NvidiaProvider(api_key="fake-key", default_model="test-model")
        mock_client = MagicMock()
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="NVIDIA!"))]

        mock_client.chat.completions.create.return_value = [chunk1, chunk2]
        provider._client = mock_client

        stream_res = provider.generate([{"role": "user", "content": "hello"}], stream=True)
        assert isinstance(stream_res, ProviderStreamWrapper)
        tokens = [c.content for c in stream_res]
        assert tokens == ["Hello ", "NVIDIA!"]

    def test_nvidia_unconfigured_raises_error(self):
        provider = NvidiaProvider(api_key="")
        provider._client = None
        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY is not configured"):
            provider.generate([{"role": "user", "content": "hi"}])


class TestGeminiProvider:
    def test_gemini_provider_init(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
        provider = GeminiProvider(api_key="test-gemini-key", default_model="gemini-2.0-flash")
        assert provider.provider_name == "gemini"
        assert provider.default_model == "gemini-2.0-flash"
        assert provider.api_key == "test-gemini-key"

    def test_gemini_generate_non_streaming(self):
        provider = GeminiProvider(api_key="fake-key", default_model="gemini-2.0-flash")
        mock_model = MagicMock()
        mock_resp = MagicMock(text="Gemini output response")
        mock_model.generate_content.return_value = mock_resp

        with patch.object(provider, "_build_model", return_value=mock_model):
            resp = provider.generate([{"role": "user", "content": "hello"}], stream=False)
            assert resp.content == "Gemini output response"

    def test_gemini_generate_streaming(self):
        provider = GeminiProvider(api_key="fake-key", default_model="gemini-2.0-flash")
        mock_model = MagicMock()
        chunk1 = MagicMock(text="Gemini ")
        chunk2 = MagicMock(text="stream!")
        mock_model.generate_content.return_value = [chunk1, chunk2]

        with patch.object(provider, "_build_model", return_value=mock_model):
            stream_res = provider.generate([{"role": "user", "content": "hello"}], stream=True)
            tokens = [c.content for c in stream_res]
            assert tokens == ["Gemini ", "stream!"]

    def test_gemini_unconfigured_raises_error(self):
        provider = GeminiProvider(api_key="")
        provider.api_key = ""
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
            provider.generate([{"role": "user", "content": "hi"}])


class TestProviderRegistry:
    def test_task_model_map_nvidia(self):
        mapping = ProviderRegistry.get_task_model_map("nvidia")
        assert mapping["router"] == settings.NVIDIA_ROUTER_MODEL
        assert mapping["generator"] == settings.NVIDIA_GENERATOR_MODEL
        assert mapping["grader"] == settings.NVIDIA_ROUTER_MODEL
        assert mapping["rewriter"] == settings.NVIDIA_ROUTER_MODEL
        assert mapping["image_gen"] == settings.NVIDIA_IMAGE_MODEL
        assert mapping["asr"] == settings.NVIDIA_ASR_MODEL
        assert mapping["tts"] == settings.NVIDIA_TTS_MODEL

    def test_task_model_map_gemini(self):
        mapping = ProviderRegistry.get_task_model_map("gemini")
        assert mapping["generator"] == settings.GEMINI_MODEL
        assert mapping["router"] == (settings.GEMINI_TEXT_MODEL or settings.GEMINI_MODEL)
        assert mapping["grader"] == (settings.GEMINI_TEXT_MODEL or settings.GEMINI_MODEL)

    def test_resolve_provider_nvidia_primary(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "nvidia")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "valid-nv-key")
        assert ProviderRegistry.resolve_provider_type() == "nvidia"

    def test_resolve_provider_gemini_primary(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "valid-gemini-key")
        assert ProviderRegistry.resolve_provider_type() == "gemini"

    def test_resolve_provider_gemini_fallback_when_nv_key_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "nvidia")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "valid-gemini-key")
        assert ProviderRegistry.resolve_provider_type() == "gemini"

    def test_resolve_provider_nvidia_fallback_when_gemini_key_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "valid-nv-key")
        assert ProviderRegistry.resolve_provider_type() == "nvidia"

    def test_get_for_task_routing(self, monkeypatch: pytest.MonkeyPatch):
        ProviderRegistry.reset()
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "nvidia")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-key")

        router_prov = ProviderRegistry.get_for_task("router")
        assert router_prov.provider_name == "nvidia"
        assert router_prov.default_model == settings.NVIDIA_ROUTER_MODEL

        gen_prov = ProviderRegistry.get_for_task("generator")
        assert gen_prov.provider_name == "nvidia"
        assert gen_prov.default_model == settings.NVIDIA_GENERATOR_MODEL

    def test_llm_client_facade_integration(self, monkeypatch: pytest.MonkeyPatch):
        ProviderRegistry.reset()
        monkeypatch.setattr(settings, "PRIMARY_PROVIDER", "nvidia")
        monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-key")
        client = LLMClient(task="generator")
        assert client.task == "generator"
        assert client.provider.provider_name == "nvidia"
        assert client.provider.default_model == settings.NVIDIA_GENERATOR_MODEL
