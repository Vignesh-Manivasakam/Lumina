"""Tests for ParentChildChunker."""
from __future__ import annotations

import pytest

from app.ingestion.chunking import Modality
from app.ingestion.document_analyzer import ChunkingStrategy
from app.ingestion.parent_child_chunker import ParentChildChunker


def _parsed_doc(pages, file_type="pdf", title="Test Doc"):
    return {
        "metadata": {"file_type": file_type, "title": title},
        "pages": pages,
    }


def _page(text: str, page_num: int = 1, tables=None):
    return {"page_num": page_num, "text": text, "tables": tables or []}


class TestParentChildChunker:
    def test_empty_document_returns_empty_list(self):
        chunker = ParentChildChunker()
        result = chunker.chunk_pages(_parsed_doc([]), doc_id="d", dept="HR")
        assert result == []

    def test_short_text_produces_one_parent_with_children(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("This is a short document about HR policy.")])
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        parents = [c for c in result if c.is_parent]
        children = [c for c in result if not c.is_parent]
        assert len(parents) == 1
        # Even short text gets split into multiple children via the 128-token splitter.
        assert len(children) >= 1
        assert parents[0].metadata.get("chunking_strategy") == "fixed"

    def test_parent_lists_all_child_ids(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("A " * 500)])
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        parent = next(c for c in result if c.is_parent)
        # Children in the result must include every ID in parent.child_ids.
        child_ids_in_result = {c.chunk_id for c in result if not c.is_parent}
        assert set(parent.child_ids) == child_ids_in_result
        assert len(parent.child_ids) > 0

    def test_each_child_references_parent_id(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("Long text " * 200)])
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        parents = {c.chunk_id: c for c in result if c.is_parent}
        for child in result:
            if not child.is_parent:
                assert child.parent_id in parents, (
                    f"child {child.chunk_id} → missing parent {child.parent_id}"
                )
                # And the parent's child_ids list must include this child.
                assert child.chunk_id in parents[child.parent_id].child_ids

    def test_long_text_produces_multiple_parents(self):
        chunker = ParentChildChunker(
            parent_chunk_size=128, parent_chunk_overlap=16, child_chunk_size=32, child_chunk_overlap=8
        )
        # Force many parents by using tiny parent size.
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 50
        doc = _parsed_doc([_page(text)])
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        parents = [c for c in result if c.is_parent]
        assert len(parents) >= 2

    def test_metadata_propagated(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc(
            [_page("Some text about HR.")], file_type="pdf", title="HR Manual"
        )
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        for chunk in result:
            assert chunk.metadata["dept"] == "HR"
            assert chunk.metadata["file_type"] == "pdf"
            assert chunk.metadata["title"] == "HR Manual"

    def test_table_becomes_a_parent(self):
        chunker = ParentChildChunker()
        table = {
            "markdown": "| A | B |\n| 1 | 2 |",
            "caption": "Test table",
        }
        doc = _parsed_doc([_page("", tables=[table])])
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        table_parents = [
            c for c in result if c.is_parent and c.modality == Modality.TABLE
        ]
        assert len(table_parents) == 1
        assert "Test table" in table_parents[0].text_repr

    def test_chunk_ids_are_deterministic_for_same_input(self):
        """Same (doc_id, page, idx) → same UUID (deterministic seed)."""
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("Deterministic text.")])
        first = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        second = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        first_ids = sorted([c.chunk_id for c in first])
        second_ids = sorted([c.chunk_id for c in second])
        assert first_ids == second_ids

    def test_page_number_propagated(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc(
            [_page("Page one.", page_num=1), _page("Page two.", page_num=2)]
        )
        result = chunker.chunk_pages(doc, doc_id="d", dept="HR")
        for chunk in result:
            assert chunk.page_num in (1, 2)

    def test_strategy_dispatch_section_aware(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("# Heading 1\nSection 1 text\n## Subheading\nSub text")])
        result = chunker.chunk_pages(doc, doc_id="d", dept="Eng", strategy=ChunkingStrategy.SECTION_AWARE)
        assert any(c.metadata.get("chunking_strategy") == "section_aware" for c in result)

    def test_strategy_dispatch_narrative_and_content(self):
        chunker = ParentChildChunker()
        doc = _parsed_doc([_page("Dialogue or content text here.")])
        narrative_res = chunker.chunk_pages(doc, doc_id="d", dept="Eng", strategy=ChunkingStrategy.NARRATIVE)
        assert narrative_res[0].metadata.get("chunking_strategy") == "narrative"

        content_res = chunker.chunk_pages(doc, doc_id="d", dept="Eng", strategy="content_aware")
        assert content_res[0].metadata.get("chunking_strategy") == "content_aware"
