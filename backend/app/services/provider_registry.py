"""LLM Provider Abstraction Layer for Lumina RAG.

Provides a unified interface for multiple LLM providers (NVIDIA NIM, Google Gemini)
with automatic fallback, task-to-model routing, and uniform response wrapping
(guaranteeing ``.content`` and ``.text`` properties across streaming and non-streaming).
"""
from __future__ import annotations

import abc
import logging
import os
from typing import Any, Dict, Iterator, List, Optional, Union

from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Universal Response & Stream Wrappers
# ---------------------------------------------------------------------------

class ProviderResponse:
    """Wraps a non-streaming response so callers can use ``.content`` or ``.text``."""

    def __init__(self, content: Any = "", raw_response: Any = None) -> None:
        if raw_response is None and not isinstance(content, str):
            self._raw_response = content
            text_val = ""
            try:
                text_val = getattr(content, "text", None)
                if text_val is None:
                    text_val = getattr(content, "content", "")
            except (ValueError, AttributeError):
                text_val = ""
            self._content = str(text_val) if text_val is not None else ""
        else:
            self._content = str(content) if content is not None else ""
            self._raw_response = raw_response

    @property
    def content(self) -> str:
        return self._content

    @property
    def text(self) -> str:
        return self._content

    def __repr__(self) -> str:
        preview = (self._content[:40] + "...") if len(self._content) > 40 else self._content
        return f"<ProviderResponse content={preview!r}>"


class ProviderStreamChunk:
    """Single streaming chunk with ``.content`` and ``.text`` (mirrors LangChain/OpenAI)."""

    def __init__(self, content: Any = "", raw_chunk: Any = None) -> None:
        if raw_chunk is None and not isinstance(content, str) and content is not None:
            self._raw_chunk = content
            text_val = ""
            try:
                text_val = getattr(content, "text", None)
                if text_val is None:
                    text_val = getattr(content, "content", "")
            except (ValueError, AttributeError):
                text_val = ""
            self.content = str(text_val) if text_val is not None else ""
        else:
            self.content = str(content) if content is not None else ""
            self._raw_chunk = raw_chunk
        self.text = self.content

    def __repr__(self) -> str:
        return f"<ProviderStreamChunk content={self.content!r}>"


class ProviderStreamWrapper:
    """Iterates over a streaming response yielding chunks with ``.content`` and ``.text``."""

    def __init__(self, stream_iterator: Any) -> None:
        self._stream = stream_iterator

    def __iter__(self) -> Iterator[ProviderStreamChunk]:
        for item in self._stream:
            if isinstance(item, ProviderStreamChunk):
                yield item
            elif isinstance(item, str):
                yield ProviderStreamChunk(item)
            else:
                text = ""
                try:
                    text = getattr(item, "text", None)
                    if text is None:
                        text = getattr(item, "content", "")
                except (ValueError, AttributeError):
                    text = ""
                yield ProviderStreamChunk(str(text) if text is not None else "", raw_chunk=item)


# Backwards compatibility aliases for existing tests / callers
_GeminiResponseWrapper = ProviderResponse
_GeminiStreamChunk = ProviderStreamChunk
_GeminiStreamWrapper = ProviderStreamWrapper


# ---------------------------------------------------------------------------
# Message formatting helpers
# ---------------------------------------------------------------------------

def _lc_messages_to_gemini(messages: List[dict]) -> tuple[list, list]:
    """Convert OpenAI/LangChain-style message dicts to Gemini contents.

    Gemini splits messages by role into ``system_instruction`` (single string)
    and ``contents`` (list of {role, parts}). Any non-text part (e.g. inline
    image data) is passed through.
    """
    system_parts: list[str] = []
    contents: list[dict] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        system_parts.append(part.get("text", ""))
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts: list[dict] = []

        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    parts.append({"text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    # Expect data URL: data:<mime>;base64,<b64>
                    if url.startswith("data:") and ";base64," in url:
                        mime, b64 = url.split(";base64,", 1)
                        mime = mime.replace("data:", "")
                        parts.append(
                            {
                                "inline_data": {
                                    "mime_type": mime,
                                    "data": b64,
                                }
                            }
                        )
                    else:
                        parts.append({"text": url})
        else:
            parts.append({"text": str(content)})

        contents.append({"role": gemini_role, "parts": parts})

    return "\n\n".join(p for p in system_parts if p), contents


def _format_openai_messages(messages: List[dict]) -> List[dict]:
    """Ensure message list is strictly compatible with OpenAI / NVIDIA NIM / Groq."""
    formatted: List[dict] = []
    for msg in messages:
        role = msg.get("role", "user") or "user"
        content = msg.get("content")

        if content is None:
            content = ""

        # Normalise role names if necessary
        if role == "model":
            role = "assistant"

        # If content is a list, check if it contains image_url
        if isinstance(content, list):
            has_image = any(isinstance(p, dict) and p.get("type") == "image_url" for p in content)
            if not has_image:
                # Text-only list: flatten into a single clean string
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        text_parts.append(part.get("text", "") or "")
                    elif isinstance(part, str):
                        text_parts.append(part)
                    else:
                        text_parts.append(str(part))
                content = "\n".join(tp for tp in text_parts if tp)
            else:
                # Ensure all parts in multimodal list are well-formed
                cleaned_parts = []
                for p in content:
                    if isinstance(p, dict):
                        cleaned_parts.append(p)
                    elif isinstance(p, str):
                        cleaned_parts.append({"type": "text", "text": p})
                content = cleaned_parts

        elif not isinstance(content, str):
            content = str(content)

        formatted.append({"role": role, "content": content})
    return formatted


# ---------------------------------------------------------------------------
# Abstract Base Provider
# ---------------------------------------------------------------------------

class LLMProvider(abc.ABC):
    """Abstract base class for all LLM providers in Lumina."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'nvidia', 'gemini')."""
        pass

    @property
    @abc.abstractmethod
    def default_model(self) -> str:
        """Default model for this provider instance."""
        pass

    @abc.abstractmethod
    def generate(
        self,
        messages: List[dict],
        stream: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        """Generate chat completion (streaming or non-streaming)."""
        pass

    @abc.abstractmethod
    def generate_text(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> ProviderResponse:
        """Convenience method for text-only non-streaming completion."""
        pass


# ---------------------------------------------------------------------------
# NVIDIA NIM Provider (Primary)
# ---------------------------------------------------------------------------

class NvidiaProvider(LLMProvider):
    """NVIDIA NIM provider using the official OpenAI-compatible SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.NVIDIA_API_KEY
        self.base_url = base_url or settings.NVIDIA_BASE_URL
        self._default_model = default_model or settings.NVIDIA_GENERATOR_MODEL
        self._client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                logger.info(
                    "NvidiaProvider initialized with base_url=%s, default_model=%s",
                    self.base_url,
                    self._default_model,
                )
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client for NvidiaProvider: %s", exc)
                self._client = None

    @property
    def provider_name(self) -> str:
        return "nvidia"

    @property
    def default_model(self) -> str:
        return self._default_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _invoke_nvidia(
        self,
        messages: List[dict],
        model_name: str,
        stream: bool,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        if not self._client:
            raise RuntimeError(
                "NVIDIA_API_KEY is not configured or OpenAI client failed to initialize."
            )

        formatted_messages = _format_openai_messages(messages)
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "stream": stream,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        if stream:
            response = self._client.chat.completions.create(**kwargs)

            def _stream_gen() -> Iterator[ProviderStreamChunk]:
                for chunk in response:
                    choices = getattr(chunk, "choices", [])
                    if choices:
                        delta = choices[0].delta
                        content = getattr(delta, "content", "") or ""
                        if content:
                            yield ProviderStreamChunk(content, raw_chunk=chunk)

            return ProviderStreamWrapper(_stream_gen())

        response = self._client.chat.completions.create(**kwargs)
        choices = getattr(response, "choices", [])
        content = choices[0].message.content if choices else ""
        return ProviderResponse(content or "", raw_response=response)

    def generate(
        self,
        messages: List[dict],
        stream: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = 1500,
        temperature: Optional[float] = 0.1,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        model_name = model or self._default_model
        return self._invoke_nvidia(
            messages=messages,
            model_name=model_name,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_text(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: Optional[int] = 500,
        temperature: Optional[float] = 0.1,
    ) -> ProviderResponse:
        model_name = model or self._default_model
        res = self._invoke_nvidia(
            messages=messages,
            model_name=model_name,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if isinstance(res, ProviderResponse):
            return res
        return ProviderResponse(str(res))


# ---------------------------------------------------------------------------
# Google Gemini Provider (Fallback / Alternative)
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini provider using google.generativeai."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._default_model = default_model or settings.GEMINI_MODEL
        self._is_configured = False

        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                os.environ.setdefault("GOOGLE_API_KEY", self.api_key)
                self._is_configured = True
                logger.info(
                    "GeminiProvider initialized with default_model=%s",
                    self._default_model,
                )
            except Exception as exc:
                logger.warning("Failed to configure GeminiProvider: %s", exc)
                self._is_configured = False

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self._default_model

    def _get_safety_settings(self) -> list[dict]:
        try:
            from google.generativeai.types import HarmBlockThreshold, HarmCategory
            return [
                {
                    "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                    "threshold": HarmBlockThreshold.BLOCK_NONE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    "threshold": HarmBlockThreshold.BLOCK_NONE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    "threshold": HarmBlockThreshold.BLOCK_NONE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    "threshold": HarmBlockThreshold.BLOCK_NONE,
                },
            ]
        except Exception:
            return []

    def _build_model(self, model_name: str, system_instruction: Optional[str] = None):
        import google.generativeai as genai
        kwargs = {
            "model_name": model_name,
            "safety_settings": self._get_safety_settings(),
        }
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        return genai.GenerativeModel(**kwargs)

    def _invoke_gemini(
        self,
        messages: List[dict],
        model_name: str,
        stream: bool,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Add it to backend/.env before starting."
            )

        # Normalize aliases to stable production endpoints
        if model_name in ("gemini-flash-latest", "gemini-flash", "gemini-2.0-flash", "gemini-2.5-flash"):
            model_name = "gemini-3.6-flash"
        elif model_name in ("gemini-flash-lite-latest", "gemini-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite"):
            model_name = "gemini-flash-lite-latest"

        system_instruction, contents = _lc_messages_to_gemini(messages)
        if not contents:
            raise ValueError("No user/model messages provided to GeminiProvider.")

        gen_config: Dict[str, Any] = {}
        if max_tokens is not None:
            gen_config["max_output_tokens"] = max_tokens
        if temperature is not None:
            gen_config["temperature"] = temperature

        candidate_models = [model_name]
        for fallback_m in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.5-flash-lite"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        last_error = None
        for candidate_m in candidate_models:
            try:
                model = self._build_model(candidate_m, system_instruction=system_instruction)

                if stream:
                    raw_stream = model.generate_content(
                        contents,
                        stream=True,
                        generation_config=gen_config or None,
                    )

                    def _stream_gen() -> Iterator[ProviderStreamChunk]:
                        try:
                            for chunk in raw_stream:
                                text = ""
                                try:
                                    text = getattr(chunk, "text", "") or ""
                                except (ValueError, AttributeError):
                                    try:
                                        if hasattr(chunk, "candidates") and chunk.candidates:
                                            parts = chunk.candidates[0].content.parts
                                            text = "".join(getattr(p, "text", "") for p in parts)
                                    except Exception:
                                        text = ""
                                if text:
                                    yield ProviderStreamChunk(text, raw_chunk=chunk)
                        except Exception as iter_exc:
                            logger.warning("Gemini stream iteration encountered exception: %s", iter_exc)

                    return ProviderStreamWrapper(_stream_gen())

                response = model.generate_content(
                    contents,
                    generation_config=gen_config or None,
                )
                content = ""
                try:
                    content = getattr(response, "text", "") or ""
                except (ValueError, AttributeError):
                    try:
                        if hasattr(response, "candidates") and response.candidates:
                            parts = response.candidates[0].content.parts
                            content = "".join(getattr(p, "text", "") for p in parts)
                    except Exception:
                        content = ""
                return ProviderResponse(content, raw_response=response)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Gemini candidate model %s failed (%s), trying next candidate...",
                    candidate_m,
                    exc,
                )

        raise last_error or RuntimeError(f"All Gemini candidates failed for {model_name}")

    def generate(
        self,
        messages: List[dict],
        stream: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = 1500,
        temperature: Optional[float] = 0.1,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        model_name = model or self._default_model
        return self._invoke_gemini(
            messages=messages,
            model_name=model_name,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_text(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: Optional[int] = 500,
        temperature: Optional[float] = 0.1,
    ) -> ProviderResponse:
        model_name = model or self._default_model
        res = self._invoke_gemini(
            messages=messages,
            model_name=model_name,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if isinstance(res, ProviderResponse):
            return res
        return ProviderResponse(str(res))


class GroqProvider(LLMProvider):
    """Groq Cloud provider using the OpenAI-compatible SDK for ultra-fast inference."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://api.groq.com/openai/v1",
        default_model: Optional[str] = "openai/gpt-oss-120b",
    ) -> None:
        self.api_key = api_key if api_key is not None else getattr(settings, "GROQ_API_KEY", "")
        self.base_url = base_url
        self._default_model = default_model or "openai/gpt-oss-120b"
        self._client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                logger.info(
                    "GroqProvider initialized with default_model=%s",
                    self._default_model,
                )
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client for GroqProvider: %s", exc)
                self._client = None

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def default_model(self) -> str:
        return self._default_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _invoke_groq(
        self,
        messages: List[dict],
        model_name: str,
        stream: bool,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        if not self._client:
            raise RuntimeError(
                "GROQ_API_KEY is not configured or client failed to initialize."
            )

        formatted_messages = _format_openai_messages(messages)
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "stream": stream,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        candidate_models = [model_name]
        for fallback_m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "llama-3.3-70b-versatile"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        last_err = None
        for candidate in candidate_models:
            kwargs["model"] = candidate
            try:
                if stream:
                    response = self._client.chat.completions.create(**kwargs)

                    def _stream_gen(resp_obj) -> Iterator[ProviderStreamChunk]:
                        for chunk in resp_obj:
                            choices = getattr(chunk, "choices", [])
                            if choices:
                                delta = choices[0].delta
                                content = getattr(delta, "content", "") or ""
                                if content:
                                    yield ProviderStreamChunk(content, raw_chunk=chunk)

                    return ProviderStreamWrapper(_stream_gen(response))

                response = self._client.chat.completions.create(**kwargs)
                choices = getattr(response, "choices", [])
                content = choices[0].message.content if choices else ""
                return ProviderResponse(content or "", raw_response=response)
            except Exception as exc:
                last_err = exc
                err_str = str(exc).lower()
                if "model_not_found" in err_str or "does not exist" in err_str or "404" in err_str:
                    logger.warning("Groq model %s unavailable, trying next candidate: %s", candidate, exc)
                    continue
                raise exc

        if last_err:
            raise last_err

    def generate(
        self,
        messages: List[dict],
        stream: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = 1500,
        temperature: Optional[float] = 0.1,
    ) -> Union[ProviderResponse, ProviderStreamWrapper]:
        model_name = model or self._default_model
        return self._invoke_groq(
            messages=messages,
            model_name=model_name,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_text(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: Optional[int] = 500,
        temperature: Optional[float] = 0.1,
    ) -> ProviderResponse:
        model_name = model or self._default_model
        res = self._invoke_groq(
            messages=messages,
            model_name=model_name,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if isinstance(res, ProviderResponse):
            return res
        return ProviderResponse(str(res))


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Central registry resolving LLM providers and models per task.

    Supports dynamic multi-model routing across Google Gemini, NVIDIA NIM, and Groq.
    """

    _instances: Dict[str, LLMProvider] = {}

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {
            "nvidia": NvidiaProvider(),
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
        }

    @property
    def providers(self) -> Dict[str, LLMProvider]:
        return self._providers

    def get(self, provider_name: str) -> Optional[LLMProvider]:
        return self._providers.get(provider_name.lower())

    @classmethod
    def get_task_model_map(cls, provider_type: str) -> Dict[str, str]:
        """Return task-to-model mapping for a given provider type."""
        if provider_type == "nvidia":
            return {
                "router": settings.NVIDIA_ROUTER_MODEL,
                "generator": settings.NVIDIA_GENERATOR_MODEL,
                "grader": settings.NVIDIA_ROUTER_MODEL,
                "rewriter": settings.NVIDIA_ROUTER_MODEL,
                "contextual_headers": settings.NVIDIA_ROUTER_MODEL,
                "header": settings.NVIDIA_ROUTER_MODEL,
                "safety": settings.NVIDIA_ROUTER_MODEL,
                "image_gen": settings.NVIDIA_IMAGE_MODEL,
                "image": settings.NVIDIA_IMAGE_MODEL,
                "asr": settings.NVIDIA_ASR_MODEL,
                "tts": settings.NVIDIA_TTS_MODEL,
            }
        elif provider_type == "groq":
            return {
                "router": "openai/gpt-oss-120b",
                "generator": "openai/gpt-oss-120b",
                "grader": "openai/gpt-oss-120b",
                "rewriter": "openai/gpt-oss-120b",
                "contextual_headers": "openai/gpt-oss-120b",
                "header": "openai/gpt-oss-120b",
                "safety": "openai/gpt-oss-120b",
                "image_gen": settings.GEMINI_MODEL,
                "image": settings.GEMINI_MODEL,
                "asr": "whisper-large-v3",
                "tts": "whisper-large-v3",
            }
        else:  # Gemini mapping
            text_model = settings.GEMINI_TEXT_MODEL or settings.GEMINI_MODEL
            gen_model = settings.GEMINI_MODEL
            return {
                "router": text_model,
                "generator": gen_model,
                "grader": text_model,
                "rewriter": text_model,
                "contextual_headers": text_model,
                "header": text_model,
                "safety": text_model,
                "image_gen": gen_model,
                "image": gen_model,
                "asr": text_model,
                "tts": text_model,
            }

    @classmethod
    def resolve_provider_type(cls) -> str:
        """Determine which provider to use based on configuration and available keys."""
        primary = (getattr(settings, "PRIMARY_PROVIDER", "gemini") or "gemini").lower()

        if primary == "gemini" and getattr(settings, "GEMINI_API_KEY", ""):
            return "gemini"
        if primary == "nvidia" and getattr(settings, "NVIDIA_API_KEY", ""):
            return "nvidia"
        if primary == "groq" and getattr(settings, "GROQ_API_KEY", ""):
            return "groq"

        if getattr(settings, "NVIDIA_API_KEY", ""):
            return "nvidia"
        if getattr(settings, "GEMINI_API_KEY", ""):
            return "gemini"
        if getattr(settings, "GROQ_API_KEY", ""):
            return "groq"

        return primary

    @classmethod
    def get_for_task(cls, task_name: str = "generator", model_override: Optional[str] = None) -> LLMProvider:
        """Get an LLMProvider configured with the appropriate model for the specified task."""
        if model_override:
            m_lower = model_override.lower()
            if "groq" in m_lower or "llama" in m_lower or "mixtral" in m_lower:
                clean_model = model_override.replace("groq/", "")
                return GroqProvider(default_model=clean_model)
            elif "nvidia" in m_lower or "nemotron" in m_lower:
                return NvidiaProvider(default_model=model_override)
            elif "gemini" in m_lower:
                return GeminiProvider(default_model=model_override)

        provider_type = cls.resolve_provider_type()
        task_models = cls.get_task_model_map(provider_type)
        model = task_models.get(task_name, task_models.get("generator"))

        cache_key = f"{provider_type}:{task_name}:{model}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        if provider_type == "nvidia":
            provider = NvidiaProvider(default_model=model)
        elif provider_type == "groq":
            provider = GroqProvider(default_model=model)
        else:
            provider = GeminiProvider(default_model=model)

        cls._instances[cache_key] = provider
        return provider

    @classmethod
    def reset(cls) -> None:
        """Clear cached provider instances (useful for testing)."""
        cls._instances.clear()

