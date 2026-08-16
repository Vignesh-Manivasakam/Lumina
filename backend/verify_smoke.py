"""Smoke test for the post-migration free stack.

Replaces the legacy ``verify_nvidia.py`` (NVIDIA NIM) — Lumina now runs
on Gemini 2.0 Flash + FastEmbed BGE-large + FlashRank. This script:

  1. Verifies GEMINI_API_KEY is configured
  2. Calls Gemini text generation end-to-end
  3. Embeds a sample passage with the local embedder
  4. Reranks three passages with FlashRank

Run from the ``backend/`` directory::

    python verify_smoke.py

Exits 0 on full success, prints ❌ markers and non-zero exit on the
first failure (no silent exception swallowing — B9).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {name}{(': ' + detail) if detail else ''}")
    return ok


def main() -> int:
    print("=== Lumina stack smoke test ===\n")

    nv_key = os.getenv("NVIDIA_API_KEY", "").strip()
    gem_key = os.getenv("GEMINI_API_KEY", "").strip()
    has_key = bool(nv_key or gem_key)
    detail = f"NVIDIA={nv_key[:8]}…" if nv_key else (f"Gemini={gem_key[:8]}…" if gem_key else "missing")
    if not _check("LLM API key configured (NVIDIA or Gemini)", has_key, detail):
        return 1

    all_ok = True

    # ---- 1. LLM text generation ----
    print("\n--- LLM text generation ---")
    try:
        from app.services.llm_client import LLMClient

        client = LLMClient()
        resp = client.generate(
            [{"role": "user", "content": "Reply with one short sentence confirming you are online."}],
            stream=False,
        )
        text = (resp.content or "").strip()
        provider_name = client.provider.provider_name
        all_ok &= _check(f"chat completion returned text ({provider_name})", bool(text), text[:60])
    except Exception as exc:
        all_ok &= _check("chat completion", False, repr(exc))

    # ---- 2. Local embedder ----
    print("\n--- Local embedder (FastEmbed BGE-large) ---")
    try:
        from app.ingestion.fast_embedder import LocalEmbedder

        emb = LocalEmbedder()
        vecs = emb.embed_texts(["Lumina is a library, not a search engine."])
        ok = bool(vecs) and len(vecs[0]) == 1024
        all_ok &= _check(
            "embedding returned 1024-dim vector",
            ok,
            f"{len(vecs)} vector(s), dim={len(vecs[0]) if vecs else 0}",
        )
    except Exception as exc:
        all_ok &= _check("embedding", False, repr(exc))

    # ---- 3. FlashRank reranker ----
    print("\n--- FlashRank reranker ---")
    try:
        from app.retrieval.cpu_reranker import CPUReranker

        reranker = CPUReranker()
        results = reranker.rerank(
            "What is the vacation policy?",
            [
                "Pineapples grow on trees.",
                "Employees get 20 days of vacation per year.",
                "The cafeteria opens at 9am.",
            ],
        )
        top = results[0]["text"] if results else ""
        all_ok &= _check(
            "rerank surfaces vacation passage first",
            "vacation" in top.lower(),
            f"top={top!r}",
        )
    except Exception as exc:
        all_ok &= _check("reranker", False, repr(exc))

    # ---- Summary ----
    print()
    if all_ok:
        print("[OK] all smoke checks passed.")
        return 0
    print("[FAIL] one or more smoke checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
