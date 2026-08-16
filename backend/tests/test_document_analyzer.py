"""Unit tests for DocumentAnalyzer strategy selection and text extraction."""
from __future__ import annotations

import pytest

from app.ingestion.document_analyzer import ChunkingStrategy, DocumentAnalyzer


class TestDocumentAnalyzer:
    def setup_method(self):
        self.analyzer = DocumentAnalyzer()

    def test_empty_document_defaults_to_fixed(self):
        doc = {"pages": [], "text_markdown": ""}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.FIXED

    def test_none_document_defaults_to_fixed(self):
        assert self.analyzer.analyze({}) == ChunkingStrategy.FIXED
        assert self.analyzer.extract_full_text({}) == ""

    def test_code_heavy_doc_returns_content_aware(self):
        text = """# Developer Guide
Here is some python code:
```python
def foo():
    return 1
```
And another block:
```python
def bar():
    return 2
```
And shell command:
```bash
pytest backend/tests
```
And json configuration:
```json
{"status": "ok"}
```
"""
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.CONTENT_AWARE

    def test_table_heavy_doc_returns_tabular(self):
        text = """| ID | Product | Q1 Sales | Q2 Sales | Q3 Sales | Q4 Sales | Total |
|---|---|---|---|---|---|---|
| 1 | Lumina Enterprise | 1000 | 1200 | 1400 | 1600 | 5200 |
| 2 | Lumina Cloud | 2000 | 2200 | 2500 | 3000 | 9700 |
| 3 | Lumina Pro | 500 | 600 | 700 | 800 | 2600 |
| 4 | Lumina Starter | 100 | 150 | 200 | 250 | 700 |
| 5 | Lumina Edge | 300 | 400 | 500 | 600 | 1800 |
"""
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.TABULAR

    def test_heading_heavy_returns_section_aware(self):
        text = """
# Section 1: Executive Summary
Overview of enterprise architecture and compliance policies.

## Subsection 1.1: Background and Scope
Details on project initiation and boundaries.

### Subsubsection 1.1.1: Constraints
Hardware and bandwidth limitations.

## Subsection 1.2: System Architecture
Diagrams and interface specifications for all modules.

# Section 2: Security & RLS
Multi-tenant isolation policies and cryptographic keys.

## Subsection 2.1: Key Rotation
Quarterly key rotation schedule and protocols.
"""
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.SECTION_AWARE

    def test_long_paragraphs_returns_semantic(self):
        # Paragraphs with > 200 words each
        p1 = " ".join(["enterprise"] * 250)
        p2 = " ".join(["retrieval"] * 220)
        text = f"{p1}\n\n{p2}"
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.SEMANTIC

    def test_short_dialog_paragraphs_returns_narrative(self):
        text = """
"Are we ready for the production migration?" asked the lead architect.

"Yes, all database migrations and tests have passed," confirmed the engineer.

"Excellent. Let's trigger the deployment pipeline now."

"Deployment initiated and monitoring telemetry."

"All services are healthy and responding."
"""
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.NARRATIVE

    def test_medium_paragraphs_returns_fixed(self):
        # Paragraph with ~100 words (not semantic >200 and not narrative <50)
        p1 = " ".join(["lumina"] * 100)
        p2 = " ".join(["platform"] * 100)
        text = f"{p1}\n\n{p2}"
        doc = {"text_markdown": text, "pages": []}
        assert self.analyzer.analyze(doc) == ChunkingStrategy.FIXED

    def test_extract_text_from_pages_and_tables(self):
        doc = {
            "pages": [
                {"text": "Page 1 intro text", "tables": [{"markdown": "| col1 | col2 |\n|---|---|\n| a | b |"}]},
                {"text": "Page 2 detailed text", "tables": []},
            ]
        }
        extracted = self.analyzer.extract_full_text(doc)
        assert "Page 1 intro text" in extracted
        assert "| col1 | col2 |" in extracted
        assert "Page 2 detailed text" in extracted
