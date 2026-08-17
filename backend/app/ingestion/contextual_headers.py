"""Anthropic-style contextual retrieval headers with batch optimization.

For each chunk, generate a one-sentence header that situates the chunk
within the document. Prepend the header to ``text_repr`` before
embedding so dense retrieval has the contextual signal.

Batches up to 10 chunks per LLM call to dramatically reduce API overhead,
with robust per-chunk fallback if batch parsing fails.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.ingestion.chunking import MultimodalChunk
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# System prompt for single-chunk generation (fallback).
_HEADER_PROMPT = (
    "You write one-sentence context headers for enterprise document "
    "chunks to improve retrieval. Given the document title, a section "
    "context, and the chunk, output exactly one sentence (10-25 words) "
    "that situates the chunk in the document. No quotes, no preamble, "
    "no explanation. If the chunk already includes the section heading, "
    "still rewrite it for retrieval. Return ONLY the sentence."
)

# System prompt for batch header generation.
_BATCH_HEADER_PROMPT = (
    "You write one-sentence context headers for enterprise document chunks to improve retrieval.\n"
    "Given the document title, document context, and a list of numbered chunks, output a JSON array "
    "where each element is an object with 'index' (the integer chunk index) and 'header' "
    "(a concise 10-25 word sentence situating the chunk within the overall document).\n"
    "Example format:\n"
    "[\n"
    '  {"index": 0, "header": "This section explains the employee vacation policy."},\n'
    '  {"index": 1, "header": "This section outlines medical leave requirements."}\n'
    "]\n"
    "Return ONLY the JSON array. Do not include markdown preamble or explanations."
)

# Compile once. Catches stray quotes / markdown around the output.
_QUOTE_RE = re.compile(r'^[\s"\'`]+|[\s"\'`]+$')
_LINEBREAK_RE = re.compile(r"\s+")


def _clean_header(raw: str) -> str:
    text = raw.strip()
    text = _QUOTE_RE.sub("", text)
    # Take only the first line if the model returned multiple.
    text = text.split("\n", 1)[0]
    text = _LINEBREAK_RE.sub(" ", text).strip()
    # Drop leading dashes / bullets
    text = re.sub(r"^[-*•\d.\s]+", "", text)
    return text


class ContextualHeaderGenerator:
    """Generate one-sentence context headers for chunks with batch LLM calls.

    Usage::

        gen = ContextualHeaderGenerator()
        gen.enrich_chunks(chunks, full_document_text, doc_metadata)

    After ``enrich_chunks`` each chunk has:
    - ``original_text``: raw chunk text (set if not already)
    - ``contextual_header``: one-line header
    - ``text_repr``: ``"<header>\n\n<original>"`` (used for embedding)
    """

    def __init__(self, llm_client: Optional[Any] = None, batch_size: int = 10) -> None:
        self.llm = llm_client or LLMClient(task="contextual_headers")
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    # Public & Internal Generation
    # ------------------------------------------------------------------

    def _batch_generate_headers(
        self,
        chunks: List[MultimodalChunk],
        full_document_context: str,
        doc_metadata: dict,
    ) -> Dict[int, str]:
        """Generate contextual headers for up to 10 chunks in a single LLM call."""
        if not chunks:
            return {}

        title = (doc_metadata or {}).get("title", "Unknown")
        context_excerpt = (full_document_context or "")[:600]

        chunk_sections: List[str] = []
        for idx, c in enumerate(chunks):
            raw_text = c.original_text or c.text_repr or ""
            chunk_excerpt = raw_text[:300]
            chunk_sections.append(f"[Chunk {idx}]:\n{chunk_excerpt}")

        chunks_text = "\n\n".join(chunk_sections)
        prompt = (
            f"Document Title: {title}\n"
            f"Document Context Excerpt: {context_excerpt}\n\n"
            f"Chunks to annotate:\n{chunks_text}\n\n"
            "JSON Array:"
        )

        resp = self.llm.generate_text(
            [
                {"role": "system", "content": _BATCH_HEADER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=64 * len(chunks) + 128,
            temperature=0.0,
        )
        content = resp.content.strip()

        # Robust markdown code block cleaning
        if "```" in content:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()

        headers_map: Dict[int, str] = {}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        idx = item.get("index")
                        hdr = item.get("header", "")
                        if idx is not None and isinstance(idx, int) and hdr:
                            headers_map[idx] = _clean_header(str(hdr))
        except Exception:
            # Secondary regex fallback for loose JSON items
            matches = re.findall(
                r'\{\s*"index"\s*:\s*(\d+)\s*,\s*"header"\s*:\s*"([^"]+)"\s*\}',
                content,
            )
            for idx_str, hdr in matches:
                headers_map[int(idx_str)] = _clean_header(hdr)

        return headers_map

    def generate_header(
        self,
        chunk_text: str,
        full_document_context: str,
        doc_metadata: dict,
    ) -> str:
        """Generate a one-line contextual header for a single chunk."""
        title = (doc_metadata or {}).get("title", "Unknown")
        context_excerpt = (full_document_context or "")[:500]
        chunk_excerpt = (chunk_text or "")[:300]

        prompt = (
            f"Document title: {title}\n"
            f"Document context (excerpt): {context_excerpt}\n\n"
            f"Chunk:\n{chunk_excerpt}\n\n"
            "Header:"
        )

        try:
            response = self.llm.generate_text(
                [
                    {"role": "system", "content": _HEADER_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=64,
                temperature=0.0,
            )
            return _clean_header(response.content)
        except Exception as exc:
            logger.warning("Contextual header generation failed: %s", exc)
            return ""

    def enrich_chunks(
        self,
        chunks: List[MultimodalChunk],
        full_document_text: str,
        doc_metadata: dict,
    ) -> List[MultimodalChunk]:
        """Annotate each chunk with a contextual header in-place using batch LLM calls.

        Skips chunks whose modality is not ``TEXT`` or ``TABLE`` (image,
        audio, video already carry their own caption context).
        """
        text_chunks = [c for c in chunks if c.modality.value in ("text", "table")]

        for i in range(0, len(text_chunks), self.batch_size):
            batch = text_chunks[i : i + self.batch_size]

            headers_map: Dict[int, str] = {}
            try:
                headers_map = self._batch_generate_headers(
                    chunks=batch,
                    full_document_context=full_document_text,
                    doc_metadata=doc_metadata,
                )
            except Exception as exc:
                logger.warning(
                    "Batch contextual header generation skipped (%s); using original text",
                    exc,
                )
                headers_map = {}

            for idx, chunk in enumerate(batch):
                # Always preserve the original text
                if chunk.original_text is None:
                    chunk.original_text = chunk.text_repr

                header = headers_map.get(idx)
                if not header and len(text_chunks) <= 5:
                    try:
                        header = self.generate_header(
                            chunk_text=chunk.original_text,
                            full_document_context=full_document_text,
                            doc_metadata=doc_metadata,
                        )
                    except Exception:
                        header = ""

                chunk.contextual_header = header or ""
                if header:
                    chunk.text_repr = f"{header}\n\n{chunk.original_text}"

        return chunks
