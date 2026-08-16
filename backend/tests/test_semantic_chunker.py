"""Tests for SemanticChunker."""
from __future__ import annotations

import pytest

from app.ingestion.chunking import Modality
from app.ingestion.semantic_chunker import SemanticChunker


class MockTopicEmbedder:
    """Returns distinct orthogonal vectors based on topic keywords."""

    def __init__(self, dim: int = 4):
        self.dim = dim

    def embed_texts(self, texts):
        vectors = []
        for t in texts:
            t_lower = t.lower()
            if "biology" in t_lower or "cell" in t_lower or "dna" in t_lower:
                vec = [1.0, 0.0, 0.0, 0.0]
            elif "finance" in t_lower or "stock" in t_lower or "market" in t_lower:
                vec = [0.0, 1.0, 0.0, 0.0]
            elif "astronomy" in t_lower or "star" in t_lower or "planet" in t_lower:
                vec = [0.0, 0.0, 1.0, 0.0]
            else:
                vec = [0.1, 0.1, 0.1, 0.1]
            vectors.append(vec)
        return vectors


def _parsed_doc(pages, file_type="pdf", title="Semantic Test"):
    return {
        "metadata": {"file_type": file_type, "title": title},
        "pages": pages,
    }


def _page(text: str, page_num: int = 1, tables=None):
    return {"page_num": page_num, "text": text, "tables": tables or []}


class TestSemanticChunker:
    def test_empty_document_returns_empty(self):
        chunker = SemanticChunker(embedder=MockTopicEmbedder())
        result = chunker.chunk_pages(_parsed_doc([]), doc_id="d-sem", dept="Research")
        assert result == []

    def test_single_sentence_creates_single_cluster(self):
        chunker = SemanticChunker(embedder=MockTopicEmbedder())
        doc = _parsed_doc([_page("Only one single sentence here.")])
        chunks = chunker.chunk_pages(doc, doc_id="d-sem", dept="Research")
        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if not c.is_parent]
        assert len(parents) == 1
        assert len(children) >= 1
        assert children[0].parent_id == parents[0].chunk_id

    def test_semantic_breakpoint_splits_topics(self):
        text = (
            "Biology studies living organisms and cell structures. "
            "DNA contains the genetic code for cells. "
            "Finance deals with stock markets and investments. "
            "Market valuation dictates investment returns. "
            "Astronomy observes distant stars and galaxies. "
            "Planets orbit stars throughout the cosmos."
        )
        embedder = MockTopicEmbedder()
        chunker = SemanticChunker(embedder=embedder, percentile_threshold=50.0)
        doc = _parsed_doc([_page(text)])
        chunks = chunker.chunk_pages(doc, doc_id="d-sem", dept="Research")

        parents = [c for c in chunks if c.is_parent and c.modality == Modality.TEXT]
        children = [c for c in chunks if not c.is_parent and c.modality == Modality.TEXT]

        # Should produce multiple parents corresponding to topic transitions
        assert len(parents) >= 2
        assert len(children) >= 2

        # Check metadata
        for c in chunks:
            assert c.metadata["chunking_strategy"] == "semantic"
            assert c.metadata["dept"] == "Research"

        # Check that parent child links match
        parent_ids = {p.chunk_id for p in parents}
        for child in children:
            assert child.parent_id in parent_ids

    def test_table_support(self):
        table = {"markdown": "| Gene | Function |\n| BRCA1 | Repair |", "caption": "Genes"}
        doc = _parsed_doc([_page("Biology text here.", tables=[table])])
        chunker = SemanticChunker(embedder=MockTopicEmbedder())
        chunks = chunker.chunk_pages(doc, doc_id="d-sem", dept="Biology")

        tables = [c for c in chunks if c.modality == Modality.TABLE]
        assert len(tables) >= 1
        assert "BRCA1" in tables[0].text_repr
