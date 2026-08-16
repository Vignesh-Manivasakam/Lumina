"""Tests for ContextualHeaderGenerator."""
from __future__ import annotations

import pytest

from app.ingestion.chunking import Modality, MultimodalChunk
from app.ingestion.contextual_headers import (
    ContextualHeaderGenerator,
    _clean_header,
)


def _make_chunk(text="raw text", modality=Modality.TEXT, original=None):
    chunk = MultimodalChunk(
        chunk_id="c1",
        doc_id="d",
        modality=modality,
        text_repr=text,
        original_text=original,
    )
    return chunk


class TestCleanHeader:
    def test_strips_outer_quotes(self):
        assert _clean_header('"a quoted header"') == "a quoted header"

    def test_strips_outer_backticks(self):
        assert _clean_header("`code style`") == "code style"

    def test_takes_first_line_only(self):
        assert _clean_header("first line\nsecond line") == "first line"

    def test_collapses_whitespace(self):
        assert _clean_header("too    much    space") == "too much space"

    def test_drops_leading_dashes(self):
        assert _clean_header("- leading dash") == "leading dash"

    def test_drops_leading_numbers(self):
        assert _clean_header("1. numbered header") == "numbered header"


def _make_generator(stub_llm) -> ContextualHeaderGenerator:
    """Bypass LLMClient default — inject stub."""
    gen = ContextualHeaderGenerator.__new__(ContextualHeaderGenerator)
    gen.llm = stub_llm
    gen.batch_size = 8
    return gen


class TestContextualHeaderGenerator:
    def test_generate_header_calls_llm(self, stub_llm):
        stub_llm.set_responses(["This chunk explains the vacation policy."])
        gen = _make_generator(stub_llm)
        header = gen.generate_header(
            chunk_text="vacation is 20 days",
            full_document_context="HR policies include vacations",
            doc_metadata={"title": "HR Manual"},
        )
        assert header == "This chunk explains the vacation policy."
        assert len(stub_llm.calls) == 1

    def test_generate_header_falls_back_on_error(self, stub_llm):
        """LLM raises → empty header (graceful)."""
        gen = _make_generator(stub_llm)

        class _Boom:
            def __getattr__(self, name):
                raise RuntimeError("boom")

        gen.llm = _Boom()
        header = gen.generate_header(
            chunk_text="text", full_document_context="ctx", doc_metadata={}
        )
        assert header == ""

    def test_enrich_chunks_batch_json(self, stub_llm):
        """Batch generation outputs a JSON array containing headers for all chunks in 1 call."""
        stub_llm.set_responses([
            '[{"index": 0, "header": "header for chunk 1"}, {"index": 1, "header": "header for chunk 2"}]'
        ])
        gen = _make_generator(stub_llm)
        c1 = _make_chunk("original text 1", original="ORIGINAL 1")
        c2 = _make_chunk("original text 2", original="ORIGINAL 2")
        result = gen.enrich_chunks([c1, c2], "FULL DOC", {"title": "T"})

        # Verify only 1 batch LLM call was made
        assert len(stub_llm.calls) == 1
        assert c1.original_text == "ORIGINAL 1"
        assert c2.original_text == "ORIGINAL 2"
        assert c1.contextual_header == "header for chunk 1"
        assert c2.contextual_header == "header for chunk 2"
        assert c1.text_repr == "header for chunk 1\n\nORIGINAL 1"
        assert c2.text_repr == "header for chunk 2\n\nORIGINAL 2"
        assert result is not None

    def test_enrich_chunks_fallback_on_invalid_batch_json(self, stub_llm):
        """If batch returns non-JSON, falls back to individual calls per chunk."""
        stub_llm.set_responses([
            "not a json array",  # batch call fails parsing
            "header fallback 1",  # chunk 1 individual call
            "header fallback 2",  # chunk 2 individual call
        ])
        gen = _make_generator(stub_llm)
        c1 = _make_chunk("chunk 1 text")
        c2 = _make_chunk("chunk 2 text")
        gen.enrich_chunks([c1, c2], "FULL DOC", {"title": "T"})

        assert c1.contextual_header == "header fallback 1"
        assert c2.contextual_header == "header fallback 2"

    def test_enrich_chunks_skips_image_modality(self, stub_llm):
        """Images carry their own caption; don't generate headers."""
        stub_llm.set_responses([])
        gen = _make_generator(stub_llm)
        img = MultimodalChunk(
            chunk_id="img",
            doc_id="d",
            modality=Modality.IMAGE,
            text_repr="an image",
        )
        gen.enrich_chunks([img], "FULL DOC", {})
        # No LLM call should have happened.
        assert len(stub_llm.calls) == 0
        assert img.contextual_header is None
