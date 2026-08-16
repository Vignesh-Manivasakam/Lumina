"""Tests for SectionChunker."""
from __future__ import annotations

import pytest

from app.ingestion.chunking import Modality
from app.ingestion.section_chunker import SectionChunker


def _parsed_doc(pages, file_type="md", title="Section Test Doc"):
    return {
        "metadata": {"file_type": file_type, "title": title},
        "pages": pages,
    }


def _page(text: str, page_num: int = 1, tables=None):
    return {"page_num": page_num, "text": text, "tables": tables or []}


class TestSectionChunker:
    def test_empty_doc_returns_empty_list(self):
        chunker = SectionChunker()
        result = chunker.chunk_pages(_parsed_doc([]), doc_id="d1", dept="Engineering")
        assert result == []

    def test_heading_hierarchy_creates_parents_and_children(self):
        text = """
# Architecture Overview
This section outlines the high-level architecture of Lumina.

## Ingestion Engine
The ingestion engine processes PDFs, DOCX, and audio files.
It extracts text, generates embeddings, and indexes content.

## Retrieval Engine
The retrieval engine runs hybrid search across dense vectors and BM25.
It leverages parent-child resolution.

# Security Standards
This section details security protocols.

## Authentication
Authentication is handled via OAuth and JWT tokens.
"""
        chunker = SectionChunker()
        doc = _parsed_doc([_page(text)])
        chunks = chunker.chunk_pages(doc, doc_id="sec-doc", dept="Engineering")

        parents = [c for c in chunks if c.is_parent and c.modality == Modality.TEXT]
        children = [c for c in chunks if not c.is_parent and c.modality == Modality.TEXT]

        assert len(parents) == 2  # "Architecture Overview" and "Security Standards"
        assert len(children) >= 3

        # Verify child links to parents
        parent_ids = {p.chunk_id for p in parents}
        for child in children:
            assert child.parent_id in parent_ids
            # Child chunk text_repr should preserve heading context
            assert ("Architecture Overview" in child.text_repr) or ("Security Standards" in child.text_repr)

        # Check metadata
        for chunk in chunks:
            assert chunk.metadata["chunking_strategy"] == "section_aware"
            assert chunk.metadata["dept"] == "Engineering"

    def test_fallback_when_no_headings(self):
        text = "This is plain text without any markdown headings at all. " * 30
        chunker = SectionChunker()
        doc = _parsed_doc([_page(text)])
        chunks = chunker.chunk_pages(doc, doc_id="plain-doc", dept="HR")

        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if not c.is_parent]

        assert len(parents) >= 1
        assert len(children) >= 1
        for c in children:
            assert c.parent_id in {p.chunk_id for p in parents}

    def test_table_handling(self):
        table = {"markdown": "| Col1 | Col2 |\n| Val1 | Val2 |", "caption": "Summary"}
        doc = _parsed_doc([_page("# Title\nBody text", tables=[table])])
        chunker = SectionChunker()
        chunks = chunker.chunk_pages(doc, doc_id="tbl-doc", dept="Finance")

        tables = [c for c in chunks if c.modality == Modality.TABLE]
        assert len(tables) >= 1
        assert "Summary" in tables[0].text_repr
