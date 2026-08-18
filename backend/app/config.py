import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ---- LLM (Google Gemini - free tier) -----------------------------
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_TEXT_MODEL: str = "gemini-flash-lite-latest"

    # ---- NVIDIA NIM (Primary LLM Provider) ----------------------------
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_ROUTER_MODEL: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    NVIDIA_GENERATOR_MODEL: str = "nvidia/nemotron-3-ultra-550b-a55b"
    NVIDIA_IMAGE_MODEL: str = "stabilityai/sdxl-turbo"
    NVIDIA_ASR_MODEL: str = "nvidia/whisper-large-v3"
    NVIDIA_TTS_MODEL: str = "nvidia/magpie-tts-multilingual"

    # ---- Provider Selection & Additional APIs ------------------------
    PRIMARY_PROVIDER: str = "nvidia"
    TAVILY_API_KEY: str = ""
    AUTO_TITLE_GENERATION: bool = True

    # ---- Embeddings (local, via FastEmbed) ----------------------------
    # BAAI/bge-small-en-v1.5 is lightweight (~67 MB, 384-dim) and runs reliably
    # under restricted container memory environments (e.g. Render free tier 512MB).
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384

    # ---- Reranker (local, FlashRank) ----------------------------------
    RERANK_MODEL: str = "ms-marco-MiniLM-L-12-v2"

    # ---- Vector store -------------------------------------------------
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "multimodal_rag"

    # ---- Metadata DB --------------------------------------------------
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # ---- Audio transcription (Groq Whisper) ---------------------------
    GROQ_API_KEY: str = ""

    # ---- Application settings -----------------------------------------
    CORS_ORIGINS: str = "*"
    MAX_RETRIEVAL_RETRIES: int = 2
    TOP_K_RETRIEVE: int = 20
    TOP_K_RERANK: int = 5
    RELEVANCE_THRESHOLD: float = 0.5

    # ---- Session isolation --------------------------------------------
    SESSION_HEADER: str = "X-Session-ID"
    SESSION_AUTO_ISSUE: bool = True

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
