"""Section-aware hierarchical chunker.

Splits structured documents at Markdown heading boundaries (`#`, `##`, `###`).
- Top-level sections become parent chunks (broad context).
- Sub-sections or bounded splits become child chunks (precise search targets).
- Preserves heading breadcrumbs across child chunks so semantic context is retained.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.chunking import Modality, MultimodalChunk
from app.utils import generate_uuid

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


class SectionChunker:
    """Markdown section-aware hierarchical chunker."""

    def __init__(
        self,
        parent_chunk_size: int = 1536,
        parent_chunk_overlap: int = 128,
        child_chunk_size: int = 256,
        child_chunk_overlap: int = 32,
    ) -> None:
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
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

    def chunk_pages(
        self,
        parsed_doc: dict,
        doc_id: str,
        dept: str,
    ) -> List[MultimodalChunk]:
        """Chunk document pages into section-aware parents and children."""
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
                    )
                )

        return chunks

    def _chunk_page_text(
        self,
        text: str,
        doc_id: str,
        dept: str,
        page_num: int,
        title: str,
        file_type: str,
    ) -> List[MultimodalChunk]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return self._fallback_chunk_text(
                text=text,
                doc_id=doc_id,
                dept=dept,
                page_num=page_num,
                title=title,
                file_type=file_type,
            )

        # Parse sections based on heading levels
        sections = self._split_into_sections(text, matches)
        out: List[MultimodalChunk] = []

        for parent_idx, sec in enumerate(sections):
            parent_heading = sec["heading"]
            parent_text = sec["full_text"]
            parent_id = generate_uuid(f"{doc_id}_sec_p_{page_num}_{parent_idx}")
            child_chunks: List[MultimodalChunk] = []

            # Process subsections or split content
            subsections = sec["subsections"]
            if subsections:
                for sub_idx, sub in enumerate(subsections):
                    sub_heading = sub["heading"]
                    sub_content = sub["content"]
                    header_prefix = f"{parent_heading} > {sub_heading}\n\n" if parent_heading != sub_heading else f"{sub_heading}\n\n"
                    
                    if len(sub_content.split()) <= (self.child_chunk_size // 4):
                        cid = generate_uuid(f"{doc_id}_sec_c_{page_num}_{parent_idx}_{len(child_chunks)}")
                        child_text = f"{header_prefix}{sub_content}".strip()
                        child_chunks.append(
                            MultimodalChunk(
                                chunk_id=cid,
                                doc_id=doc_id,
                                modality=Modality.TEXT,
                                text_repr=child_text,
                                original_text=sub_content,
                                parent_id=parent_id,
                                is_parent=False,
                                page_num=page_num,
                                metadata={
                                    "title": title,
                                    "dept": dept,
                                    "file_type": file_type,
                                    "chunking_strategy": "section_aware",
                                    "parent_idx": parent_idx,
                                    "heading": sub_heading,
                                },
                            )
                        )
                    else:
                        sub_splits = self.child_splitter.split_text(sub_content)
                        for sp_idx, sp in enumerate(sub_splits):
                            cid = generate_uuid(f"{doc_id}_sec_c_{page_num}_{parent_idx}_{len(child_chunks)}")
                            child_text = f"{header_prefix}{sp}".strip()
                            child_chunks.append(
                                MultimodalChunk(
                                    chunk_id=cid,
                                    doc_id=doc_id,
                                    modality=Modality.TEXT,
                                    text_repr=child_text,
                                    original_text=sp,
                                    parent_id=parent_id,
                                    is_parent=False,
                                    page_num=page_num,
                                    metadata={
                                        "title": title,
                                        "dept": dept,
                                        "file_type": file_type,
                                        "chunking_strategy": "section_aware",
                                        "parent_idx": parent_idx,
                                        "heading": sub_heading,
                                    },
                                )
                            )
            else:
                # No subheadings; split parent content directly
                body_content = sec["content"]
                header_prefix = f"{parent_heading}\n\n" if parent_heading else ""
                child_texts = self.child_splitter.split_text(body_content) if body_content else [parent_text]
                for c_idx, c_text in enumerate(child_texts):
                    cid = generate_uuid(f"{doc_id}_sec_c_{page_num}_{parent_idx}_{c_idx}")
                    full_child_repr = f"{header_prefix}{c_text}".strip() if header_prefix and not c_text.startswith("#") else c_text
                    child_chunks.append(
                        MultimodalChunk(
                            chunk_id=cid,
                            doc_id=doc_id,
                            modality=Modality.TEXT,
                            text_repr=full_child_repr,
                            original_text=c_text,
                            parent_id=parent_id,
                            is_parent=False,
                            page_num=page_num,
                            metadata={
                                "title": title,
                                "dept": dept,
                                "file_type": file_type,
                                "chunking_strategy": "section_aware",
                                "parent_idx": parent_idx,
                                "heading": parent_heading,
                            },
                        )
                    )

            child_ids = [c.chunk_id for c in child_chunks]
            parent_chunk = MultimodalChunk(
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
                    "chunking_strategy": "section_aware",
                    "parent_idx": parent_idx,
                    "heading": parent_heading,
                    "num_children": len(child_ids),
                },
            )

            out.extend(child_chunks)
            out.append(parent_chunk)

        return out

    def _split_into_sections(self, text: str, matches: List[re.Match]) -> List[Dict[str, Any]]:
        """Group markdown text into top-level sections with sub-sections."""
        min_level = min(len(m.group(1)) for m in matches)
        sections: List[Dict[str, Any]] = []

        # Handle preamble text before first heading
        first_start = matches[0].start()
        if first_start > 0 and text[:first_start].strip():
            preamble = text[:first_start].strip()
            sections.append({
                "heading": "Introduction",
                "content": preamble,
                "full_text": preamble,
                "subsections": [],
            })

        current_parent: Optional[Dict[str, Any]] = None
        current_sub: Optional[Dict[str, Any]] = None

        for i, match in enumerate(matches):
            level = len(match.group(1))
            heading_title = match.group(0).strip()
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start_pos:end_pos].strip()
            body_only = text[match.end():end_pos].strip()

            if level == min_level:
                # Flush previous parent
                if current_parent is not None:
                    if current_sub is not None:
                        current_parent["subsections"].append(current_sub)
                        current_sub = None
                    sections.append(current_parent)

                current_parent = {
                    "heading": heading_title,
                    "content": body_only,
                    "full_text": block,
                    "subsections": [],
                }
            else:
                # Sub-heading
                if current_parent is None:
                    current_parent = {
                        "heading": heading_title,
                        "content": body_only,
                        "full_text": block,
                        "subsections": [],
                    }
                else:
                    if current_sub is not None:
                        current_parent["subsections"].append(current_sub)
                    current_sub = {
                        "heading": heading_title,
                        "content": body_only,
                        "full_text": block,
                    }
                    current_parent["full_text"] += f"\n\n{block}"

        if current_sub is not None and current_parent is not None:
            current_parent["subsections"].append(current_sub)
        if current_parent is not None:
            sections.append(current_parent)

        return sections

    def _fallback_chunk_text(
        self,
        text: str,
        doc_id: str,
        dept: str,
        page_num: int,
        title: str,
        file_type: str,
    ) -> List[MultimodalChunk]:
        out: List[MultimodalChunk] = []
        parent_texts = self.parent_splitter.split_text(text)

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = generate_uuid(f"{doc_id}_sec_p_{page_num}_{parent_idx}")
            child_ids: List[str] = []

            child_texts = self.child_splitter.split_text(parent_text)
            for child_idx, child_text in enumerate(child_texts):
                child_id = generate_uuid(f"{doc_id}_sec_c_{page_num}_{parent_idx}_{child_idx}")
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
                            "chunking_strategy": "section_aware",
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
                        "chunking_strategy": "section_aware",
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
    ) -> List[MultimodalChunk]:
        out: List[MultimodalChunk] = []
        parent_id = generate_uuid(f"{doc_id}_sec_p_table_{page_num}_{table_idx}")
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
                    "chunking_strategy": "section_aware",
                    "caption": caption,
                },
            )
        )

        if len(table_markdown.split()) > self.child_splitter._chunk_size:
            row_chunks = self.child_splitter.split_text(table_markdown)
            child_ids: List[str] = []
            for ci, row_text in enumerate(row_chunks):
                cid = generate_uuid(f"{doc_id}_sec_c_table_{page_num}_{table_idx}_{ci}")
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
                            "chunking_strategy": "section_aware",
                            "caption": caption,
                            "child_idx": ci,
                        },
                    )
                )
            out[0].child_ids = child_ids

        return out


__all__ = ("SectionChunker",)
