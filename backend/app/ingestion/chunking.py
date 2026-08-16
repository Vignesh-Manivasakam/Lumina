from __future__ import annotations

from enum import Enum
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel

from app.utils import generate_uuid


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    AUDIO_TRANSCRIPT = "audio_transcript"
    VIDEO_FRAME = "video_frame"


class MultimodalChunk(BaseModel):
    """A single embedding unit.

    Phase 3 adds parent-child hierarchy fields and Anthropic-style
    contextual headers. The ``text_repr`` is what gets embedded; the
    ``original_text`` preserves the raw chunk for display, and
    ``contextual_header`` is prepended to ``text_repr`` at embed time
    only (see ``effective_text``).
    """

    chunk_id: str           # unique: {doc_id}_{modality}_{index}
    doc_id: str
    modality: Modality
    text_repr: str          # text used for BM25 + LLM context (may include header)
    base64: Optional[str] = None   # base64 string for image/video modality
    page_num: Optional[int] = None
    timestamp_sec: Optional[int] = None
    metadata: dict = {}
    embedding: Optional[List[float]] = None
    session_id: Optional[str] = None  # Phase 2: multi-tenant isolation payload field

    # ---- Phase 3: parent-child + contextual headers ----
    original_text: Optional[str] = None   # raw text before header prepending
    contextual_header: Optional[str] = None  # one-line summary prepended to text_repr
    parent_id: Optional[str] = None       # for child chunks, id of the parent
    is_parent: bool = False               # True if this is a parent chunk
    child_ids: List[str] = []            # for parent chunks, ids of the children

    @property
    def effective_text(self) -> str:
        """What the embedder should actually vectorise.

        For child chunks (and non-parent text chunks), this is
        ``text_repr`` — which already has the contextual header
        prepended by ``ContextualHeaderGenerator``. This property is
        kept for backward compatibility with code that still calls
        ``chunk.text_repr`` directly.
        """
        return self.text_repr


class ChunkingService:
    """Legacy single-level chunker (kept for back-compat).

    New code should use :class:`ParentChildChunker` instead. This class
    is preserved so existing tests and the ``pipeline`` default still
    work when the optional parent-child path is disabled.
    """

    def __init__(self) -> None:
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " "],
        )

    def chunk_document(self, parsed_doc: dict, doc_id: str, dept: str) -> List[MultimodalChunk]:
        chunks: List[MultimodalChunk] = []

        # 1. Text chunking from pages
        for page in parsed_doc.get("pages", []):
            page_num = page.get("page_num", 1)
            page_text = (page.get("text") or "").strip()
            if not page_text:
                continue

            text_segments = self.text_splitter.split_text(page_text)
            for idx, segment in enumerate(text_segments):
                chunks.append(
                    MultimodalChunk(
                        chunk_id=generate_uuid(f"{doc_id}_text_{page_num}_{idx}"),
                        doc_id=doc_id,
                        modality=Modality.TEXT,
                        text_repr=segment,
                        original_text=segment,
                        page_num=page_num,
                        is_parent=True,  # legacy chunks are their own parents
                        metadata={
                            "title": parsed_doc["metadata"].get("title", ""),
                            "dept": dept,
                            "file_type": parsed_doc["metadata"].get("file_type", "pdf"),
                        },
                    )
                )

        # 2. Table chunking — one chunk per table
        table_idx = 0
        for page in parsed_doc.get("pages", []):
            page_num = page.get("page_num", 1)
            for t in page.get("tables", []):
                t_markdown = (t.get("markdown") or "").strip()
                t_caption = (t.get("caption") or "").strip()
                if not t_markdown:
                    continue

                text_repr = f"Table on page {page_num}: {t_caption}\n\n{t_markdown}"
                chunks.append(
                    MultimodalChunk(
                        chunk_id=generate_uuid(f"{doc_id}_table_{page_num}_{table_idx}"),
                        doc_id=doc_id,
                        modality=Modality.TABLE,
                        text_repr=text_repr,
                        original_text=text_repr,
                        page_num=page_num,
                        is_parent=True,
                        metadata={
                            "title": parsed_doc["metadata"].get("title", ""),
                            "dept": dept,
                            "caption": t_caption,
                            "file_type": parsed_doc["metadata"].get("file_type", "pdf"),
                        },
                    )
                )
                table_idx += 1

        return chunks
