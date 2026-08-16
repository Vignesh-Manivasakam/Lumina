"""Parent-child hierarchical chunker with adaptive strategy dispatch.

Two-level hierarchy:
- **Parent chunks** (broad context): returned to the LLM at generation time.
- **Child chunks** (granular matches): used for dense + BM25 search.

Adaptive strategies:
- FIXED: default 1024 / 128 tokens
- SECTION_AWARE: markdown heading hierarchy (# / ## / ###)
- SEMANTIC: embedding distance breakpoint clustering
- TABULAR: table-optimized 2048 / 256 tokens
- NARRATIVE: story/dialog-optimized 1536 / 256 tokens
- CONTENT_AWARE: code/content-optimized 1024 / 256 tokens
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.chunking import Modality, MultimodalChunk
from app.ingestion.document_analyzer import ChunkingStrategy
from app.ingestion.section_chunker import SectionChunker
from app.ingestion.semantic_chunker import SemanticChunker
from app.utils import generate_uuid

logger = logging.getLogger(__name__)


class ParentChildChunker:
    """Adaptive two-level chunker supporting multiple chunking strategies."""

    def __init__(
        self,
        parent_chunk_size: int = 1024,
        parent_chunk_overlap: int = 128,
        child_chunk_size: int = 128,
        child_chunk_overlap: int = 32,
        section_chunker: Optional[SectionChunker] = None,
        semantic_chunker: Optional[SemanticChunker] = None,
    ) -> None:
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
            separators=["\n\n", "\n", " "],
        )

        # Strategy-specific splitters
        self.tabular_parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2048, chunk_overlap=128, separators=["\n\n", "\n", " "]
        )
        self.tabular_child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=256, chunk_overlap=32, separators=["\n\n", "\n", " "]
        )

        self.narrative_parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1536, chunk_overlap=128, separators=["\n\n", "\n", ". ", " "]
        )
        self.narrative_child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=256, chunk_overlap=32, separators=["\n\n", "\n", " "]
        )

        self.content_parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024, chunk_overlap=128, separators=["\n\n", "\n", " "]
        )
        self.content_child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=256, chunk_overlap=32, separators=["\n\n", "\n", " "]
        )

        self._section_chunker = section_chunker
        self._semantic_chunker = semantic_chunker

    @property
    def section_chunker(self) -> SectionChunker:
        if self._section_chunker is None:
            self._section_chunker = SectionChunker()
        return self._section_chunker

    @property
    def semantic_chunker(self) -> SemanticChunker:
        if self._semantic_chunker is None:
            self._semantic_chunker = SemanticChunker()
        return self._semantic_chunker

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def chunk_pages(
        self,
        parsed_doc: dict,
        doc_id: str,
        dept: str,
        strategy: Optional[Union[ChunkingStrategy, str]] = None,
    ) -> List[MultimodalChunk]:
        """Chunk every page into parents + children based on strategy.

        Returns a flat list containing both parents and children, with
        cross-references (parent.child_ids, child.parent_id).
        """
        # Resolve strategy enum
        resolved_strategy = self._resolve_strategy(strategy)

        # Dispatch specialized chunkers
        if resolved_strategy == ChunkingStrategy.SECTION_AWARE:
            return self.section_chunker.chunk_pages(parsed_doc, doc_id=doc_id, dept=dept)

        if resolved_strategy == ChunkingStrategy.SEMANTIC:
            return self.semantic_chunker.chunk_pages(parsed_doc, doc_id=doc_id, dept=dept)

        # Select splitters for size-varied strategies
        if resolved_strategy == ChunkingStrategy.TABULAR:
            p_splitter = self.tabular_parent_splitter
            c_splitter = self.tabular_child_splitter
        elif resolved_strategy == ChunkingStrategy.NARRATIVE:
            p_splitter = self.narrative_parent_splitter
            c_splitter = self.narrative_child_splitter
        elif resolved_strategy == ChunkingStrategy.CONTENT_AWARE:
            p_splitter = self.content_parent_splitter
            c_splitter = self.content_child_splitter
        else:
            p_splitter = self.parent_splitter
            c_splitter = self.child_splitter

        chunks: List[MultimodalChunk] = []
        file_type = parsed_doc.get("metadata", {}).get("file_type", "pdf")
        title = parsed_doc.get("metadata", {}).get("title", "")

        for page in parsed_doc.get("pages", []):
            page_num = page.get("page_num", 1)
            page_text = (page.get("text") or "").strip()
            if page_text:
                chunks.extend(
                    self._chunk_page_text(
                        text=page_text,
                        doc_id=doc_id,
                        dept=dept,
                        page_num=page_num,
                        title=title,
                        file_type=file_type,
                        strategy_name=resolved_strategy.value,
                        p_splitter=p_splitter,
                        c_splitter=c_splitter,
                    )
                )

            for table_idx, table in enumerate(page.get("tables", [])):
                t_markdown = (table.get("markdown") or "").strip()
                if not t_markdown:
                    continue
                t_caption = (table.get("caption") or "").strip()
                chunks.extend(
                    self._chunk_table(
                        table_markdown=t_markdown,
                        caption=t_caption,
                        doc_id=doc_id,
                        dept=dept,
                        page_num=page_num,
                        table_idx=table_idx,
                        title=title,
                        file_type=file_type,
                        strategy_name=resolved_strategy.value,
                        c_splitter=c_splitter,
                    )
                )

        return chunks

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_strategy(self, strategy: Optional[Union[ChunkingStrategy, str]]) -> ChunkingStrategy:
        if strategy is None:
            return ChunkingStrategy.FIXED
        if isinstance(strategy, ChunkingStrategy):
            return strategy
        if isinstance(strategy, str):
            s_clean = strategy.strip().lower()
            for s in ChunkingStrategy:
                if s.value == s_clean or s.name.lower() == s_clean:
                    return s
        return ChunkingStrategy.FIXED

    def _chunk_page_text(
        self,
        text: str,
        doc_id: str,
        dept: str,
        page_num: int,
        title: str,
        file_type: str,
        strategy_name: str,
        p_splitter: RecursiveCharacterTextSplitter,
        c_splitter: RecursiveCharacterTextSplitter,
    ) -> List[MultimodalChunk]:
        out: List[MultimodalChunk] = []
        parent_texts = p_splitter.split_text(text)

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = generate_uuid(f"{doc_id}_p_{page_num}_{parent_idx}")
            child_ids: List[str] = []

            child_texts = c_splitter.split_text(parent_text)
            for child_idx, child_text in enumerate(child_texts):
                child_id = generate_uuid(f"{doc_id}_c_{page_num}_{parent_idx}_{child_idx}")
                child_ids.append(child_id)
                out.append(
                    MultimodalChunk(
                        chunk_id=child_id,
                        doc_id=doc_id,
                        modality=Modality.TEXT,
                        text_repr=child_text,
                        original_text=child_text,
                        parent_id=parent_id,
                        is_parent=False,
                        page_num=page_num,
                        metadata={
                            "title": title,
                            "dept": dept,
                            "file_type": file_type,
                            "chunking_strategy": strategy_name,
                            "parent_idx": parent_idx,
                            "child_idx": child_idx,
                        },
                    )
                )

            out.append(
                MultimodalChunk(
                    chunk_id=parent_id,
                    doc_id=doc_id,
                    modality=Modality.TEXT,
                    text_repr=parent_text,
                    original_text=parent_text,
                    is_parent=True,
                    child_ids=child_ids,
                    page_num=page_num,
                    metadata={
                        "title": title,
                        "dept": dept,
                        "file_type": file_type,
                        "chunking_strategy": strategy_name,
                        "parent_idx": parent_idx,
                        "num_children": len(child_ids),
                    },
                )
            )
        return out

    def _chunk_table(
        self,
        table_markdown: str,
        caption: str,
        doc_id: str,
        dept: str,
        page_num: int,
        table_idx: int,
        title: str,
        file_type: str,
        strategy_name: str,
        c_splitter: RecursiveCharacterTextSplitter,
    ) -> List[MultimodalChunk]:
        """A table is a single parent + (optionally) child chunks if very large."""
        out: List[MultimodalChunk] = []
        parent_id = generate_uuid(f"{doc_id}_p_table_{page_num}_{table_idx}")
        table_text = f"Table on page {page_num}: {caption}\n\n{table_markdown}"

        out.append(
            MultimodalChunk(
                chunk_id=parent_id,
                doc_id=doc_id,
                modality=Modality.TABLE,
                text_repr=table_text,
                original_text=table_text,
                is_parent=True,
                page_num=page_num,
                metadata={
                    "title": title,
                    "dept": dept,
                    "file_type": file_type,
                    "chunking_strategy": strategy_name,
                    "caption": caption,
                },
            )
        )

        if len(table_markdown.split()) > c_splitter._chunk_size:
            row_chunks = c_splitter.split_text(table_markdown)
            child_ids: List[str] = []
            for ci, row_text in enumerate(row_chunks):
                cid = generate_uuid(f"{doc_id}_c_table_{page_num}_{table_idx}_{ci}")
                child_ids.append(cid)
                out.append(
                    MultimodalChunk(
                        chunk_id=cid,
                        doc_id=doc_id,
                        modality=Modality.TABLE,
                        text_repr=f"Table excerpt: {caption}\n\n{row_text}",
                        original_text=row_text,
                        parent_id=parent_id,
                        is_parent=False,
                        page_num=page_num,
                        metadata={
                            "title": title,
                            "dept": dept,
                            "file_type": file_type,
                            "chunking_strategy": strategy_name,
                            "caption": caption,
                            "child_idx": ci,
                        },
                    )
                )
            out[0].child_ids = child_ids

        return out


__all__ = ("ParentChildChunker",)
