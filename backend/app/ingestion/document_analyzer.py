"""Document analyzer for adaptive chunking strategy selection.

Applies lightweight, deterministic heuristics (0 LLM tokens, pure CPU)
to categorize documents into the optimal chunking strategy:
- SECTION_AWARE: structured manuals, policies, markdown with frequent headings
- TABULAR: reports with dense tables and spreadsheets
- CONTENT_AWARE: code files, technical docs with code fences
- SEMANTIC: long-form essays, research papers, legal opinions with deep paragraphs
- NARRATIVE: dialog, fiction, rapid short-paragraph text
- FIXED: default fallback (1024 / 128 parent-child)
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List


class ChunkingStrategy(str, Enum):
    SECTION_AWARE = "section_aware"
    SEMANTIC = "semantic"
    TABULAR = "tabular"
    NARRATIVE = "narrative"
    CONTENT_AWARE = "content_aware"
    FIXED = "fixed"


class DocumentAnalyzer:
    """Deterministic document heuristic analyzer."""

    def extract_full_text(self, parsed_doc: Dict[str, Any]) -> str:
        """Extract full document text from parsed_doc."""
        if not parsed_doc:
            return ""

        # If full markdown text is already provided
        text_markdown = parsed_doc.get("text_markdown")
        if text_markdown and isinstance(text_markdown, str) and text_markdown.strip():
            return text_markdown

        # Otherwise aggregate from pages and tables
        parts: List[str] = []
        for page in parsed_doc.get("pages", []):
            p_text = (page.get("text") or "").strip()
            if p_text:
                parts.append(p_text)
            for t in page.get("tables", []):
                t_md = (t.get("markdown") or "").strip()
                if t_md:
                    parts.append(t_md)
        return "\n\n".join(parts)

    def analyze(self, parsed_doc: Dict[str, Any]) -> ChunkingStrategy:
        """Analyze parsed document and return the recommended ChunkingStrategy."""
        text = self.extract_full_text(parsed_doc)
        if not text or not text.strip():
            return ChunkingStrategy.FIXED

        total_chars = len(text)
        words = text.split()
        total_words = len(words)

        if total_words == 0:
            return ChunkingStrategy.FIXED

        # 1. Code blocks count (``` occurrences or fenced blocks > 3)
        code_fence_matches = re.findall(r"```", text)
        code_blocks_count = len(code_fence_matches) // 2
        if code_blocks_count > 3 or len(code_fence_matches) > 3:
            return ChunkingStrategy.CONTENT_AWARE

        # 2. Table ratio (pipe chars / total chars > 0.05)
        pipe_count = text.count("|")
        table_ratio = pipe_count / max(total_chars, 1)
        if table_ratio > 0.05:
            return ChunkingStrategy.TABULAR

        # 3. Headings count (>5 per 2000 words)
        headings = re.findall(r"^#{1,3}\s", text, flags=re.MULTILINE)
        heading_count = len(headings)
        headings_per_2000_words = (heading_count / total_words) * 2000.0
        if headings_per_2000_words > 5.0 and heading_count >= 2:
            return ChunkingStrategy.SECTION_AWARE

        # 4. Paragraph length heuristics
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if paragraphs:
            para_word_counts = [len(p.split()) for p in paragraphs]
            avg_para_length = sum(para_word_counts) / len(paragraphs)

            # Avg paragraph length > 200 words -> SEMANTIC
            if avg_para_length > 200:
                return ChunkingStrategy.SEMANTIC

            # Avg paragraph length < 50 words -> NARRATIVE
            if avg_para_length < 50:
                return ChunkingStrategy.NARRATIVE

        return ChunkingStrategy.FIXED


__all__ = ("ChunkingStrategy", "DocumentAnalyzer")
