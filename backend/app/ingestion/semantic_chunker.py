"""Semantic breakpoint hierarchical chunker.

Splits text at topic boundaries detected by cosine distance spikes between
consecutive sentence embeddings.
- CPU-only local embeddings (BGE-M3 / FastEmbed) with 0 API / LLM calls.
- Semantic clusters become parent chunks (broad context).
- Granular sub-splits / sentences become child chunks (precise retrieval).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.chunking import Modality, MultimodalChunk
from app.ingestion.fast_embedder import LocalEmbedder
from app.utils import generate_uuid

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class SemanticChunker:
    """Embedding distance breakpoint chunker."""

    def __init__(
        self,
        embedder: Optional[Any] = None,
        percentile_threshold: float = 90.0,
        parent_chunk_size: int = 1536,
        child_chunk_size: int = 256,
        child_chunk_overlap: int = 32,
    ) -> None:
        self._embedder = embedder
        self.percentile_threshold = percentile_threshold
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
            separators=["\n\n", "\n", " "],
        )

    @property
    def embedder(self) -> Any:
        if self._embedder is None:
            self._embedder = LocalEmbedder()
        return self._embedder

    def chunk_pages(
        self,
        parsed_doc: dict,
        doc_id: str,
        dept: str,
    ) -> List[MultimodalChunk]:
        """Chunk document pages using semantic breakpoint detection."""
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
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return self._create_single_cluster(
                text=text,
                doc_id=doc_id,
                dept=dept,
                page_num=page_num,
                title=title,
                file_type=file_type,
                parent_idx=0,
            )

        # 1. Embed sentences using LocalEmbedder (no API calls)
        try:
            embeddings = self.embedder.embed_texts(sentences)
        except Exception as exc:
            logger.warning("LocalEmbedder failed in SemanticChunker: %s; falling back to text split", exc)
            return self._create_single_cluster(
                text=text,
                doc_id=doc_id,
                dept=dept,
                page_num=page_num,
                title=title,
                file_type=file_type,
                parent_idx=0,
            )

        if not embeddings or len(embeddings) != len(sentences):
            return self._create_single_cluster(
                text=text,
                doc_id=doc_id,
                dept=dept,
                page_num=page_num,
                title=title,
                file_type=file_type,
                parent_idx=0,
            )

        # 2. Compute cosine distances between consecutive sentences
        distances = []
        for i in range(len(embeddings) - 1):
            dist = self._cosine_distance(embeddings[i], embeddings[i + 1])
            distances.append(dist)

        # 3. Identify breakpoints exceeding percentile threshold
        breakpoints = set()
        if distances and max(distances) > 0.0:
            threshold = float(np.percentile(distances, self.percentile_threshold))
            for idx, d in enumerate(distances):
                if d >= threshold:
                    breakpoints.add(idx)

        # 4. Group sentences into semantic clusters
        clusters: List[List[str]] = []
        current_cluster: List[str] = []

        for idx, sentence in enumerate(sentences):
            current_cluster.append(sentence)
            if idx in breakpoints or idx == len(sentences) - 1:
                clusters.append(current_cluster)
                current_cluster = []

        if current_cluster:
            clusters.append(current_cluster)

        # 5. Build parent-child chunks from clusters
        out: List[MultimodalChunk] = []
        for parent_idx, cluster in enumerate(clusters):
            cluster_text = " ".join(cluster).strip()
            if not cluster_text:
                continue

            parent_id = generate_uuid(f"{doc_id}_sem_p_{page_num}_{parent_idx}")
            child_chunks: List[MultimodalChunk] = []

            # If cluster is small, individual sentences can be children; otherwise use child_splitter
            if len(cluster_text.split()) <= (self.child_chunk_size // 4):
                cid = generate_uuid(f"{doc_id}_sem_c_{page_num}_{parent_idx}_0")
                child_chunks.append(
                    MultimodalChunk(
                        chunk_id=cid,
                        doc_id=doc_id,
                        modality=Modality.TEXT,
                        text_repr=cluster_text,
                        original_text=cluster_text,
                        parent_id=parent_id,
                        is_parent=False,
                        page_num=page_num,
                        metadata={
                            "title": title,
                            "dept": dept,
                            "file_type": file_type,
                            "chunking_strategy": "semantic",
                            "parent_idx": parent_idx,
                            "child_idx": 0,
                        },
                    )
                )
            else:
                child_texts = self.child_splitter.split_text(cluster_text)
                for c_idx, c_text in enumerate(child_texts):
                    cid = generate_uuid(f"{doc_id}_sem_c_{page_num}_{parent_idx}_{c_idx}")
                    child_chunks.append(
                        MultimodalChunk(
                            chunk_id=cid,
                            doc_id=doc_id,
                            modality=Modality.TEXT,
                            text_repr=c_text,
                            original_text=c_text,
                            parent_id=parent_id,
                            is_parent=False,
                            page_num=page_num,
                            metadata={
                                "title": title,
                                "dept": dept,
                                "file_type": file_type,
                                "chunking_strategy": "semantic",
                                "parent_idx": parent_idx,
                                "child_idx": c_idx,
                            },
                        )
                    )

            child_ids = [c.chunk_id for c in child_chunks]
            parent_chunk = MultimodalChunk(
                chunk_id=parent_id,
                doc_id=doc_id,
                modality=Modality.TEXT,
                text_repr=cluster_text,
                original_text=cluster_text,
                is_parent=True,
                child_ids=child_ids,
                page_num=page_num,
                metadata={
                    "title": title,
                    "dept": dept,
                    "file_type": file_type,
                    "chunking_strategy": "semantic",
                    "parent_idx": parent_idx,
                    "num_children": len(child_ids),
                },
            )

            out.extend(child_chunks)
            out.append(parent_chunk)

        return out

    def _split_sentences(self, text: str) -> List[str]:
        raw_parts = _SENTENCE_SPLIT_RE.split(text)
        cleaned = []
        for part in raw_parts:
            s = part.strip()
            if s:
                cleaned.append(s)
        return cleaned

    def _cosine_distance(self, vec_a: List[float], vec_b: List[float]) -> float:
        a = np.array(vec_a, dtype=float)
        b = np.array(vec_b, dtype=float)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        similarity = float(np.dot(a, b) / (norm_a * norm_b))
        # Clamp to [-1.0, 1.0] for numerical stability
        similarity = max(min(similarity, 1.0), -1.0)
        return 1.0 - similarity

    def _create_single_cluster(
        self,
        text: str,
        doc_id: str,
        dept: str,
        page_num: int,
        title: str,
        file_type: str,
        parent_idx: int,
    ) -> List[MultimodalChunk]:
        parent_id = generate_uuid(f"{doc_id}_sem_p_{page_num}_{parent_idx}")
        child_texts = self.child_splitter.split_text(text)
        if not child_texts:
            child_texts = [text]

        child_chunks: List[MultimodalChunk] = []
        for c_idx, c_text in enumerate(child_texts):
            cid = generate_uuid(f"{doc_id}_sem_c_{page_num}_{parent_idx}_{c_idx}")
            child_chunks.append(
                MultimodalChunk(
                    chunk_id=cid,
                    doc_id=doc_id,
                    modality=Modality.TEXT,
                    text_repr=c_text,
                    original_text=c_text,
                    parent_id=parent_id,
                    is_parent=False,
                    page_num=page_num,
                    metadata={
                        "title": title,
                        "dept": dept,
                        "file_type": file_type,
                        "chunking_strategy": "semantic",
                        "parent_idx": parent_idx,
                        "child_idx": c_idx,
                    },
                )
            )

        child_ids = [c.chunk_id for c in child_chunks]
        parent_chunk = MultimodalChunk(
            chunk_id=parent_id,
            doc_id=doc_id,
            modality=Modality.TEXT,
            text_repr=text,
            original_text=text,
            is_parent=True,
            child_ids=child_ids,
            page_num=page_num,
            metadata={
                "title": title,
                "dept": dept,
                "file_type": file_type,
                "chunking_strategy": "semantic",
                "parent_idx": parent_idx,
                "num_children": len(child_ids),
            },
        )
        return child_chunks + [parent_chunk]

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
        parent_id = generate_uuid(f"{doc_id}_sem_p_table_{page_num}_{table_idx}")
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
                    "chunking_strategy": "semantic",
                    "caption": caption,
                },
            )
        )

        if len(table_markdown.split()) > self.child_splitter._chunk_size:
            row_chunks = self.child_splitter.split_text(table_markdown)
            child_ids: List[str] = []
            for ci, row_text in enumerate(row_chunks):
                cid = generate_uuid(f"{doc_id}_sem_c_table_{page_num}_{table_idx}_{ci}")
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
                            "chunking_strategy": "semantic",
                            "caption": caption,
                            "child_idx": ci,
                        },
                    )
                )
            out[0].child_ids = child_ids

        return out


__all__ = ("SemanticChunker",)
