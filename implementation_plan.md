# Lumina RAG -- Enterprise-Grade Multimodal RAG Implementation Plan

> **Goal:** Transform Lumina from a proof-of-concept relying on paid NVIDIA NIM endpoints into a production-grade, 100% FREE enterprise Multimodal RAG application with multi-tenant session isolation, advanced contextual chunking, and a polished agent-streaming UI.

---

## Table of Contents

1. [Executive Summary & Free Tech Stack Matrix](#1-executive-summary--free-tech-stack-matrix)
2. [Privacy & Multi-tenant Session Isolation Architecture](#2-privacy--multi-tenant-session-isolation-architecture)
3. [Advanced 5-Stage Ingestion & Retrieval Pipeline](#3-advanced-5-stage-ingestion--retrieval-pipeline)
4. [Step-by-Step 5-Phase Implementation Plan](#4-step-by-step-5-phase-implementation-plan)
5. [Working with This Plan in Claude Code](#5-working-with-this-plan-in-claude-code)
6. [Setup Instructions for All Free APIs](#6-setup-instructions-for-all-free-apis)

---

## 1. Executive Summary & Free Tech Stack Matrix

### Executive Summary

Lumina currently depends on **NVIDIA NIM Cloud Endpoints** for every AI capability: LLM inference, embeddings, reranking, and content safety. This creates a single-vendor dependency, introduces per-request costs at scale, and provides no user session privacy guarantees. This plan replaces every paid dependency with a **100% free** alternative while simultaneously upgrading the architecture from a public POC to an enterprise-grade multi-tenant platform.

The transformation covers five pillars:

| Pillar | Current State | Target State |
|--------|--------------|--------------|
| **LLM Inference** | NVIDIA NIM (paid after trial) | Google Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/day) |
| **Embeddings** | NVIDIA NIM (paid) | Local FastEmbed BGE-M3 (free, runs on CPU) |
| **Reranking** | NVIDIA NIM (paid) | Local FlashRank CPU reranker (free, runs on CPU) |
| **Audio Transcription** | Not implemented | Groq Whisper Large V3 (free tier: 7K tokens/min) |
| **Vector Store** | Qdrant Cloud (paid beyond 1GB) | Qdrant Free Tier / Local Docker (1GB free, or unlimited local) |
| **Metadata DB** | Supabase (paid beyond limits) | Supabase Free Tier (500MB DB, 1GB file storage) |
| **Privacy** | No session isolation | Client UUID + X-Session-ID headers + Supabase RLS + Qdrant payload filters |
| **Chunking** | RecursiveCharacterTextSplitter (512 tokens) | Contextual Headers (Anthropic pattern) + Parent-Child split (128 child / 1024 parent) |
| **UI** | Basic SSE streaming | Agent streaming badges, progress indicators, polished design |

### Complete Free Tech Stack Matrix

| Layer | Component | Tool/Library | Free Tier / Limits | Why This Choice |
|-------|-----------|-------------|-------------------|-----------------|
| **LLM** | Text generation | `google-generativeai` (Gemini 2.0 Flash) | 15 RPM, 1M tokens/day free | Multimodal native, fast, generous free tier |
| **LLM** | Code generation | `google-generativeai` (Gemini 2.0 Flash Lite) | Same free tier | Lightweight variant for simple tasks |
| **Embeddings** | Dense vectors | `fastembed` (BAAI/bge-m3, 1024-dim) | Unlimited, runs locally on CPU | Multilingual, supports dense+sparse, no API needed |
| **Sparse** | BM25 keywords | `fastembed` (Qdrant/bm25) | Unlimited, runs locally | Already in use, keep it |
| **Reranking** | Precision filter | `flashrank` (ms-marco-MiniLM-L-12-v2) | Unlimited, runs locally on CPU | Sub-50ms inference, no API |
| **ASR** | Audio transcription | `groq` (Whisper Large V3) | 7,000 tokens/min free | Best free speech-to-text |
| **Vision** | Image description | Gemini 2.0 Flash (multimodal) | Included in free tier | Natively handles images |
| **Video** | Frame extraction | `ffmpeg` (local) | Unlimited | Industry standard, no API |
| **PDF Parsing** | Document parsing | `PyMuPDF` (fitz) + `docling` | Unlimited, runs locally | Best combination for PDF + structured docs |
| **Vector DB** | Vector search | Qdrant (free tier or Docker) | 1GB cloud free, or unlimited local | Hybrid dense+sparse, RRF fusion |
| **Metadata DB** | Session/doc storage | Supabase (PostgreSQL) | 500MB DB, 1GB storage, 50K MAU | RLS policies for multi-tenant isolation |
| **Safety** | Content filtering | NemoGuard 8B (local) or Gemini safety settings | Free (local) or included in Gemini | Graceful fallback chain |
| **API Gateway** | HTTP server | FastAPI | Unlimited | Already in use |
| **Frontend** | UI framework | Next.js 15 + React 19 | Unlimited | Already in use |
| **Embeddings Model** | Multimodal embed | BGE-M3 via FastEmbed | CPU-only, unlimited | 1024-dim, good quality/cost ratio |

---

## 2. Privacy & Multi-tenant Session Isolation Architecture

### 2.1 Architecture Overview

```
Client (Browser)                    Backend (FastAPI)                 Storage
    |                                    |                              |
    |-- POST /api/chat ----------------->|                              |
    |   Header: X-Session-ID: <UUID>     |                              |
    |                                    |-- Verify UUID format ------->|
    |                                    |                              |
    |                                    |-- Query Qdrant ------------->|
    |                                    |   filter: payload["session_id"] = <UUID>
    |                                    |                              |
    |                                    |-- Supabase query ----------->|
    |                                    |   WHERE session_id = <UUID>
    |                                    |   (enforced by RLS policy)  |
    |                                    |                              |
    |<-- SSE Stream ---------------------|                              |
    |   Events scoped to session         |                              |
```

### 2.2 Client-side UUID Generation

Each browser tab/window generates a unique `sessionUUID` on first visit. This UUID is:
- Generated via `crypto.randomUUID()` on the client
- Stored in `localStorage` as `lumina_session_uuid`
- Sent with every API request as `X-Session-ID` header
- Never re-used across tabs; cleared on explicit logout

**Frontend implementation (`frontend/lib/api.ts`):**

```typescript
function getOrCreateSessionUUID(): string {
  const existing = localStorage.getItem('lumina_session_uuid');
  if (existing) return existing;
  const uuid = crypto.randomUUID();
  localStorage.setItem('lumina_session_uuid', uuid);
  return uuid;
}

// Add to every fetch call:
headers: {
  "Content-Type": "application/json",
  "X-Session-ID": getOrCreateSessionUUID(),
}
```

### 2.3 X-Session-ID Header Validation (Backend Middleware)

A FastAPI dependency validates the UUID format on every request. Invalid or missing UUIDs receive a 401 Unauthorized response with a new UUID issued in the response header.

**Backend implementation (`backend/app/middleware/session.py`):**

```python
import uuid
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

SESSION_HEADER = "X-Session-ID"

class SessionIsolationMiddleware(BaseHTTPMiddleware):
    """Validates and injects session UUID on every request."""

    # Paths that do not require a session
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/mcp/sse"}

    async def dispatch(self, request: Request, call_next):
        # Skip validation for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        session_id = request.headers.get(SESSION_HEADER)

        if session_id:
            try:
                uuid.UUID(session_id, version=4)
            except ValueError:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid session UUID format. Please refresh."
                )
            # Pass validated session_id downstream
            request.state.session_id = session_id
        else:
            # Issue a new UUID for anonymous access
            new_uuid = str(uuid.uuid4())
            request.state.session_id = new_uuid

        response = await call_next(request)

        # If we issued a new UUID, include it in response headers
        if not session_id:
            response.headers["X-Session-ID"] = request.state.session_id

        return response
```

### 2.4 Supabase RLS Policies

Row-Level Security ensures that even if a session bypasses the application layer, database queries are scoped by `session_id`.

**Migration SQL (`backend/supabase_migrations/002_session_rls.sql`):**

```sql
-- Enable RLS on all tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Sessions table: each session sees only its own records
CREATE POLICY "session_isolation_messages" ON messages
    FOR ALL
    USING (session_id = current_setting('request.headers')::json->>'x-session-id');

-- Documents are shared across all sessions (read-only for everyone)
CREATE POLICY "documents_read_all" ON documents
    FOR SELECT USING (true);

-- Documents can only be ingested by authenticated service role
CREATE POLICY "documents_insert_service" ON documents
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- Chunks inherit document visibility
CREATE POLICY "chunks_read_all" ON chunks
    FOR SELECT USING (true);

-- Chunks inserted via service role only (ingestion pipeline)
CREATE POLICY "chunks_insert_service" ON chunks
    FOR INSERT WITH CHECK (auth.role() = 'service_role');
```

**Note:** The `request.headers` approach requires setting the header as a PostgreSQL setting. The more practical approach is to use a Supabase RPC function or set the session context in the Supabase client call:

```python
# In supabase_client.py, set the session context:
self.client.postgrest.auth(None)  # service role
# Then pass session_id as a parameter to queries:
result = self.client.table("messages").select("*").eq("session_id", session_id).execute()
```

### 2.5 Qdrant Payload Filters

Every chunk stored in Qdrant includes a `session_id` in its payload. During retrieval, a filter ensures only chunks belonging to the requesting session are returned.

**Storage change (`backend/app/retrieval/qdrant_store.py`):**

```python
# In the upsert method, add session_id to payload:
payload={
    "text_repr": c.text_repr,
    "modality": c.modality,
    "doc_id": c.doc_id,
    "session_id": c.session_id,  # NEW: session isolation field
    "page_num": c.page_num,
    "base64": c.base64,
    "metadata": c.metadata,
}
```

**Query change:**

```python
def hybrid_search(self, dense_vector, query_text, top_k=20, filters=None, session_id=None):
    """Add session_id filter for multi-tenant isolation."""
    if session_id:
        filters = filters or {}
        filters["session_id"] = session_id  # Always scope to session

    qdrant_filter = self._build_filter(filters)
    # ... rest of query
```

### 2.6 Session Cleanup API

A scheduled endpoint and a user-initiated endpoint handle session data lifecycle.

**New endpoints (`backend/app/main.py`):**

```python
@app.post("/api/sessions/{session_id}/cleanup")
async def cleanup_session(session_id: str):
    """Delete all messages and session data for a given session."""
    try:
        # Delete from Supabase
        pipeline.supabase.cleanup_session(session_id)

        # Delete from Qdrant (all chunks with this session_id)
        pipeline.qdrant.delete_by_session(session_id)

        return {"status": "cleaned", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Permanent deletion of session data."""
    try:
        pipeline.supabase.delete_session(session_id)
        pipeline.qdrant.delete_by_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.7 Updated Supabase Schema

```sql
-- Add session_id to sessions table (already exists but add RLS)
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add session_id index for fast lookups
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chunks_session_id ON chunks(session_id);

-- Auto-expire sessions older than 24 hours (run via pg_cron or cron job)
-- SELECT cron.schedule('cleanup-old-sessions', '0 2 * * *',
--   $$DELETE FROM sessions WHERE created_at < NOW() - INTERVAL '24 hours'$$);
```

---

## 3. Advanced 5-Stage Ingestion & Retrieval Pipeline

### 3.1 Stage 1: Adaptive Document Parsing

Replace the current `DocumentParser` with an adaptive parser that selects the optimal extraction strategy based on document type.

**Stage 1 Strategy:**

| Document Type | Parser | Why |
|---------------|--------|-----|
| PDF (text-heavy) | `PyMuPDF` (fitz) | Fastest text extraction, native table detection |
| PDF (scanned/image) | `PyMuPDF` OCR + Gemini Vision fallback | Handles OCR edge cases |
| DOCX | `python-docx` + custom table extractor | Preserves structure |
| PPTX | `python-pptx` | Slide-aware extraction |
| Images | `Gemini 2.0 Flash` multimodal | VLM captioning |
| Audio | `Groq Whisper Large V3` | Best free ASR |
| Video | `ffmpeg` keyframes + Gemini Vision | Frame-by-frame captioning |

**Implementation (`backend/app/ingestion/adaptive_parser.py`):**

```python
import pymupdf  # PyMuPDF
from pathlib import Path
from typing import Dict, List, Any

class AdaptiveDocumentParser:
    """Selects the best parser for each document type."""

    def parse(self, file_path: str) -> Dict[str, Any]:
        ext = Path(file_path).suffix.lower()

        if ext == ".pdf":
            return self._parse_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return self._parse_docx(file_path)
        elif ext in [".pptx", ".ppt"]:
            return self._parse_pptx(file_path)
        else:
            raise ValueError(f"Unsupported: {ext}")

    def _parse_pdf(self, file_path: str) -> Dict[str, Any]:
        """PyMuPDF-based PDF parsing with table extraction."""
        doc = pymupdf.open(file_path)
        pages = []
        metadata = {"title": "", "total_pages": len(doc)}

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            tables = self._extract_tables_pymupdf(page)
            images = self._extract_images_pymupdf(page)

            pages.append({
                "page_num": page_num + 1,
                "text": text,
                "tables": tables,
                "images": images,
            })

        metadata["title"] = doc.metadata.get("title", "")
        doc.close()
        return {"pages": pages, "metadata": metadata}
```

### 3.2 Stage 2: Contextual Chunk Headers (Anthropic Pattern)

Instead of bare text chunks, prepend each chunk with a **contextual header** that summarizes what the chunk is about and its position within the source document. This pattern comes from Anthropic's Contextual Retrieval research and dramatically improves retrieval relevance.

**How it works:**

1. For each chunk, use Gemini Flash to generate a one-sentence contextual header based on the full document and chunk position
2. Prepend the header to the chunk before embedding
3. Store the chunk with both the header (for embedding) and the raw text (for display)

**Implementation (`backend/app/ingestion/contextual_headers.py`):**

```python
import google.generativeai as genai
from app.config import settings

class ContextualHeaderGenerator:
    """Generates contextual headers for chunks (Anthropic Contextual Retrieval pattern)."""

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def generate_header(self, chunk_text: str, full_document_context: str, doc_metadata: dict) -> str:
        """Generate a one-line contextual header for a chunk.

        The header answers: "What is this chunk about, and where does it fit in the document?"
        """
        prompt = f"""Given the following document context and chunk, generate a one-sentence contextual header.
This header will be prepended to the chunk to improve search retrieval.

Document title: {doc_metadata.get('title', 'Unknown')}
Document section context: {full_document_context[:500]}

Chunk:
{chunk_text[:300]}

Output ONLY the header sentence. No quotes, no explanation. Example:
"This document describes the Q4 2024 financial results for Acme Corp, specifically covering revenue growth."""

        response = self.model.generate_content(prompt)
        return response.text.strip().strip('"')

    def enrich_chunks(self, chunks: list, full_document_text: str, doc_metadata: dict) -> list:
        """Add contextual headers to all chunks."""
        enriched = []
        for chunk in chunks:
            header = self.generate_header(
                chunk.text_repr,
                full_document_text,
                doc_metadata
            )
            # Store original and enriched
            chunk.original_text = chunk.text_repr
            chunk.contextual_header = header
            # Prepend header to text for embedding
            chunk.text_repr = f"{header}\n\n{chunk.text_repr}"
            enriched.append(chunk)
        return enriched
```

### 3.3 Stage 3: Parent-Child Chunk Split Strategy

Instead of a single chunk size, implement a **two-level hierarchy**:

- **Parent chunks** (1024 tokens): Broad context, used for retrieval
- **Child chunks** (128 tokens): Granular matches, used for precise relevance

During retrieval, we search on child chunks (smaller, more precise) but return parent chunks (broader context) to the LLM.

**Implementation (`backend/app/ingestion/parent_child_chunker.py`):**

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Dict

class ParentChildChunker:
    """Two-level chunk hierarchy: parent (1024 tokens) + children (128 tokens).

    Search hits on child chunks; retrieval returns parent chunks for context.
    """

    def __init__(self):
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=128,
            separators=["\n\n", "\n", ". ", " "],
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=128,
            chunk_overlap=32,
            separators=["\n\n", "\n", " "],
        )

    def create_hierarchical_chunks(
        self,
        text: str,
        doc_id: str,
        page_num: int,
        metadata: dict
    ) -> Dict[str, List]:
        """Create parent-child chunk pairs.

        Returns:
            {
                "parents": [{"id": ..., "text": ..., "children_ids": [...]}],
                "children": [{"id": ..., "text": ..., "parent_id": ...}],
            }
        """
        # Step 1: Split into parent chunks
        parent_texts = self.parent_splitter.split_text(text)
        parents = []
        children = []

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = f"{doc_id}_p_{page_num}_{parent_idx}"

            # Step 2: Split each parent into child chunks
            child_texts = self.child_splitter.split_text(parent_text)
            child_ids = []

            for child_idx, child_text in enumerate(child_texts):
                child_id = f"{doc_id}_c_{page_num}_{parent_idx}_{child_idx}"
                child_ids.append(child_id)
                children.append({
                    "id": child_id,
                    "text": child_text,
                    "parent_id": parent_id,
                    "doc_id": doc_id,
                    "page_num": page_num,
                    "metadata": metadata,
                })

            parents.append({
                "id": parent_id,
                "text": parent_text,
                "children_ids": child_ids,
                "doc_id": doc_id,
                "page_num": page_num,
                "metadata": metadata,
            })

        return {"parents": parents, "children": children}
```

### 3.4 Stage 4: Local BGE-M3 Embeddings (FastEmbed)

Replace NVIDIA NIM embeddings with **local FastEmbed BGE-M3** running on CPU. This produces 1024-dimensional dense vectors and supports multilingual text.

**Implementation (`backend/app/ingestion/fast_embedder.py`):**

```python
from fastembed import TextEmbedding
from typing import List
import numpy as np

class LocalEmbedder:
    """CPU-based embedding using FastEmbed BGE-M3.

    First run downloads the model (~1.2GB). Subsequent runs use the cache.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = TextEmbedding(model_name=model_name)
        self.dimension = 1024  # BGE-M3 default

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts into dense vectors."""
        embeddings = list(self.model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        embeddings = list(self.model.embed([query]))
        return embeddings[0].tolist()
```

**Qdrant collection update:** Change `DENSE_DIM` from 2048 to 1024 in `qdrant_store.py`.

### 3.5 Stage 5: Local FlashRank CPU Reranking

Replace NVIDIA NIM reranker with **FlashRank**, a local CPU reranker that runs in under 50ms per batch.

**Implementation (`backend/app/retrieval/cpu_reranker.py`):**

```python
from flashrank import Rerank, RankRequest

class CPUReranker:
    """Local CPU reranker using FlashRank.

    Downloads the model on first use. No API key needed.
    """

    def __init__(self):
        self.reranker = Rerank(
            model="ms-marco-MiniLM-L-12-v2"
        )

    def rerank(self, query: str, passages: list[dict]) -> list[dict]:
        """Rerank passages by relevance to query.

        Args:
            query: The search query
            passages: List of dicts with 'id' and 'text' keys

        Returns:
            List of passages sorted by relevance score (descending)
        """
        rank_input = [
            {"id": p["id"], "text": p["text"]}
            for p in passages
        ]
        rank_request = RankRequest(
            query=query,
            passages=rank_input
        )
        results = self.reranker.rerank(rank_request)

        # Map scores back to original passages
        score_map = {r.id: r.score for r in results}
        for p in passages:
            p["rerank_score"] = score_map.get(p["id"], 0.0)

        return sorted(passages, key=lambda x: x["rerank_score"], reverse=True)
```

### 3.6 Retrieval Pipeline Flow (Updated)

```
User Query
    |
    v
[1] Embed Query (FastEmbed BGE-M3, local CPU)
    |
    v
[2] Hybrid Search (Qdrant: dense + BM25 sparse, RRF fusion)
    |   Filter: session_id = user's UUID
    |   Returns: top-K child chunks
    |
    v
[3] Map Children -> Parents (resolve parent chunk IDs)
    |
    v
[4] Rerank Parents (FlashRank CPU, <50ms)
    |   Returns: top-5 parent chunks by relevance
    |
    v
[5] Send to Gemini 2.0 Flash with parent chunk context
    |
    v
SSE Stream with citations
```

---

## 4. Step-by-Step 5-Phase Implementation Plan

### Pre-Phase: Known Bugs & Issues (Discovered During Exploration)

The following bugs exist in the current codebase and must be fixed as part of the migration. These were identified by analyzing the full source tree.

| # | Severity | File(s) | Issue |
|---|----------|---------|-------|
| B1 | **Critical** | `mcp_server.py` | `mcp` package not in `requirements.txt` -- backend fails to start if not transitively installed |
| B2 | **Critical** | `mcp_server.py:40` | `embedder.embed_text(query)` -- method does not exist; should be `embed_query()` |
| B3 | **Critical** | `mcp_server.py:48` | `qdrant_store.query(...)` -- method does not exist; should be `hybrid_search()` |
| B4 | **High** | `mcp_server.py` | Duplicate service initialization (creates second `NVIDIAClient`, `QdrantStore`, etc.) causing duplicate Qdrant connections on startup |
| B5 | **High** | `safety.py:21` | `SafetyGuard.is_safe()` passes plain dicts to `ChatNVIDIA.invoke()` which expects LangChain `BaseMessage` objects -- exception is caught silently, safety check is a no-op |
| B6 | **Medium** | `frontend/page.tsx` | History duplication: current user message is in both `messages` array (client history) AND `query` parameter (sent to backend), causing the LLM to see the same message twice |
| B7 | **Medium** | `main.py:145` | Citations display RRF fusion `score` instead of `rerank_score` -- the frontend "relevance score" is pre-rerank |
| B8 | **Medium** | `main.py:176` | Upload uses raw client `filename` in temp path -- concurrent uploads with same filename collide; crafted names enable path traversal |
| B9 | **Low** | `deploy.yml` | CI "test" runs `pytest verify_nvidia.py -v || true` -- not a real test, swallows all errors, requires live NVIDIA key |
| B10 | **Low** | `requirements.txt` | `ragas` and `tenacity` are declared dependencies but never used in code |

### Phase 1: Foundation -- Fix Bugs & Gemini/FastEmbed Integration (Day 1)

**Goal:** Replace NVIDIA NIM with free alternatives. Fix all known bugs.

- [ ] **1.1** Create `backend/app/services/gemini_client.py` -- Gemini 2.0 Flash LLM wrapper
  - [ ] Implement `generate()` for multimodal (text + image) generation
  - [ ] Implement `generate_text()` for text-only tasks (routing, grading, rewriting)
  - [ ] Implement `embed()` using Gemini embedding API or local FastEmbed
  - [ ] Add retry logic with tenacity for rate limits
  - [ ] Add Gemini safety settings configuration

- [ ] **1.2** Create `backend/app/ingestion/fast_embedder.py` -- Local FastEmbed BGE-M3
  - [ ] Install and initialize `fastembed` with `BAAI/bge-m3`
  - [ ] Implement `embed_texts()` batch embedding
  - [ ] Implement `embed_query()` single query embedding
  - [ ] Change `DENSE_DIM` from 2048 to 1024 in `qdrant_store.py`

- [ ] **1.3** Create `backend/app/retrieval/cpu_reranker.py` -- FlashRank local reranker
  - [ ] Initialize FlashRank with `ms-marco-MiniLM-L-12-v2`
  - [ ] Implement `rerank()` method

- [ ] **1.4** Update `backend/app/config.py` -- New environment variables
  - [ ] Add `GEMINI_API_KEY`
  - [ ] Remove `NVIDIA_API_KEY` (or make optional)
  - [ ] Add `GEMINI_MODEL` defaults
  - [ ] Add `EMBEDDING_MODEL` defaults

- [ ] **1.5** Update `backend/app/services/nvidia_client.py` -> `backend/app/services/llm_client.py`
  - [ ] Rename to `LLMClient` with Gemini backend
  - [ ] Keep `generate()`, `generate_text()`, `rerank()`, `embed()` interfaces
  - [ ] Update all agent files to use `LLMClient` instead of `NVIDIAClient`

- [ ] **1.6** Update `backend/app/retrieval/qdrant_store.py`
  - [ ] Change `DENSE_DIM` to 1024 (BGE-M3 output)
  - [ ] Remove NVIDIA embedding references
  - [ ] Use `fastembed` for sparse BM25 encoding (already in place)

- [ ] **1.7** Fix MCP server bugs (B1, B2, B3, B4)
  - [ ] Add `mcp` to `requirements.txt` (B1 -- startup-breaking)
  - [ ] Fix `embedder.embed_text(query)` -> `embedder.embed_query(query)` (B2)
  - [ ] Fix `qdrant_store.query(...)` -> `qdrant_store.hybrid_search(...)` (B3)
  - [ ] Fix duplicate service initialization -- use shared instances or lazy init (B4)
  - [ ] Add `X-Session-ID` header forwarding to MCP tools
  - [ ] Add error handling for missing session context

- [ ] **1.8** Fix SafetyGuard no-op bug (B5)
  - [ ] Update `safety.py` to pass `HumanMessage`/`SystemMessage` objects (not plain dicts) to `ChatNVIDIA.invoke()`
  - [ ] Alternatively, replace with Gemini safety settings when migrating to Gemini
  - [ ] Add graceful fallback: if safety check fails, allow the request with a warning

- [ ] **1.9** Fix history duplication bug (B6)
  - [ ] In `frontend/page.tsx` `handleSend()`, exclude the current user message from the `history` parameter sent to `streamChat()`
  - [ ] Backend should receive only the *prior* conversation history, not the current turn

- [ ] **1.10** Fix citation score display (B7)
  - [ ] In `main.py`, change `doc.get("score")` to `doc.get("rerank_score", doc.get("score"))` in the sources formatter
  - [ ] Update frontend `Source` type to accept `rerank_score` as an alias

- [ ] **1.11** Fix upload path traversal vulnerability (B8)
  - [ ] Sanitize filename: use `secure_filename()` from werkzeug or manual strip of path separators
  - [ ] Use `uuid4()` + sanitized extension for temp file naming instead of raw filename
  - [ ] Add upload size limit middleware

- [ ] **1.12** Update `backend/requirements.txt`
  - [ ] Add: `google-generativeai`, `flashrank`, `mcp`
  - [ ] Remove: `langchain-nvidia-ai-endpoints` (replace with `langchain-google-genai`)
  - [ ] Remove: `ragas`, `tenacity` (unused -- B10)
  - [ ] Keep: `fastembed`, `qdrant-client`, `supabase`, `docling`

- [ ] **1.13** Test end-to-end
  - [ ] Ingest a sample PDF and verify embedding storage
  - [ ] Run a query and verify retrieval + generation
  - [ ] Test MCP tools with Claude Code
  - [ ] Verify safety guard works correctly
  - [ ] Verify no history duplication in chat responses

### Phase 2: Privacy & Session Isolation (Day 2)

**Goal:** Implement full multi-tenant session isolation.

- [ ] **2.1** Create `backend/app/middleware/session.py` -- Session middleware
  - [ ] UUID v4 validation on `X-Session-ID` header
  - [ ] Auto-generate UUID for anonymous requests
  - [ ] Exempt `/health`, `/docs`, `/openapi.json` paths

- [ ] **2.2** Update `backend/app/main.py` -- Register middleware
  - [ ] Add `SessionIsolationMiddleware` to app
  - [ ] Pass `request.state.session_id` to all endpoints
  - [ ] Add `X-Session-ID` to response headers

- [ ] **2.3** Update `backend/app/retrieval/qdrant_store.py` -- Session filters
  - [ ] Add `session_id` to all chunk payloads on upsert
  - [ ] Add `session_id` filter to `hybrid_search()`
  - [ ] Add `delete_by_session()` method for cleanup

- [ ] **2.4** Update `backend/app/services/supabase_client.py` -- Session-scoped queries
  - [ ] Add `session_id` parameter to `add_message()`
  - [ ] Add `session_id` filter to `get_session_history()`
  - [ ] Add `cleanup_session()` method
  - [ ] Add `delete_session()` method

- [ ] **2.5** Create `backend/supabase_migrations/002_session_rls.sql`
  - [ ] Enable RLS on messages, sessions tables
  - [ ] Create session isolation policies
  - [ ] Add indexes on `session_id` columns
  - [ ] Add `created_at`, `updated_at` timestamps

- [ ] **2.6** Update `frontend/lib/api.ts` -- Client-side UUID
  - [ ] Create `getOrCreateSessionUUID()` function
  - [ ] Add `X-Session-ID` header to all API calls
  - [ ] Add `sessionId` to SSE stream requests

- [ ] **2.7** Add session cleanup endpoints
  - [ ] `POST /api/sessions/{session_id}/cleanup`
  - [ ] `DELETE /api/sessions/{session_id}`

- [ ] **2.8** Test session isolation
  - [ ] Open two browser tabs with different UUIDs
  - [ ] Verify each tab only sees its own messages
  - [ ] Test session cleanup deletes all related data

### Phase 3: Contextual Chunking & Parent-Child Retrieval (Day 3)

**Goal:** Implement advanced ingestion pipeline with contextual headers and parent-child chunks.

- [ ] **3.1** Create `backend/app/ingestion/adaptive_parser.py`
  - [ ] PyMuPDF-based PDF parsing with table extraction
  - [ ] python-docx for DOCX files
  - [ ] python-pptx for PPTX files
  - [ ] Gemini Vision for image captioning
  - [ ] Keep Groq Whisper for audio (already configured)

- [ ] **3.2** Create `backend/app/ingestion/contextual_headers.py`
  - [ ] Gemini Flash-based header generation
  - [ ] Batch header generation for efficiency
  - [ ] Store both original and enriched text

- [ ] **3.3** Create `backend/app/ingestion/parent_child_chunker.py`
  - [ ] Parent splitter: 1024 tokens, 128 overlap
  - [ ] Child splitter: 128 tokens, 32 overlap
  - [ ] Hierarchical ID scheme: `{doc_id}_p_{page}_{idx}` / `{doc_id}_c_{page}_{parent}_{child}`
  - [ ] Parent-child relationship tracking

- [ ] **3.4** Update `backend/app/ingestion/pipeline.py`
  - [ ] Replace `DocumentParser` with `AdaptiveDocumentParser`
  - [ ] Add contextual header generation step
  - [ ] Replace `ChunkingService` with `ParentChildChunker`
  - [ ] Embed child chunks (for search), store parent chunks (for retrieval)
  - [ ] Upsert both parent and child chunks to Qdrant

- [ ] **3.5** Update `backend/app/retrieval/qdrant_store.py`
  - [ ] Add `parent_id` and `is_parent` fields to payloads
  - [ ] Query children, resolve to parents
  - [ ] `hybrid_search()` returns parent chunks after child-based search

- [ ] **3.6** Update `backend/app/ingestion/chunking.py`
  - [ ] Add `session_id`, `contextual_header`, `original_text` fields
  - [ ] Update `MultimodalChunk` model

- [ ] **3.7** Test ingestion pipeline
  - [ ] Ingest a multi-page PDF with tables
  - [ ] Verify contextual headers are generated
  - [ ] Verify parent-child chunk relationships
  - [ ] Verify search returns parent chunks from child hits

### Phase 4: Next.js UI Overhaul with Agent Streaming Badges (Day 4)

**Goal:** Polished frontend with agent progress indicators and streaming badges.

- [ ] **4.1** Update `frontend/lib/types.ts` -- New type definitions
  - [ ] Add `AgentStatus` type: `"routing" | "retrieving" | "grading" | "rewriting" | "generating" | "done"`
  - [ ] Add `AgentStatusEvent` type for SSE events
  - [ ] Add `RetrievalInfo` type with chunk count, rerank time, etc.

- [ ] **4.2** Update `frontend/lib/api.ts` -- Agent event parsing
  - [ ] Handle new SSE event types: `agent_status`, `retrieval_info`, `thinking`
  - [ ] Add `onAgentStatus` callback parameter

- [ ] **4.3** Create `frontend/components/AgentBadge.tsx`
  - [ ] Animated badge showing current agent phase
  - [ ] Spinner for active agent, checkmark for completed
  - [ ] Color-coded: routing (blue), retrieving (yellow), grading (orange), rewriting (purple), generating (green)

- [ ] **4.4** Create `frontend/components/StreamingMessage.tsx`
  - [ ] Token-by-token streaming with markdown rendering
  - [ ] Source citation expanders with modality icons
  - [ ] Thinking/reasoning indicators

- [ ] **4.5** Update `backend/app/main.py` -- Agent status SSE events
  - [ ] Emit `agent_status` events at each pipeline stage:
    - `{"type": "agent_status", "agent": "router", "status": "active"}`
    - `{"type": "agent_status", "agent": "retriever", "status": "active"}`
    - `{"type": "agent_status", "agent": "grader", "status": "active"}`
    - `{"type": "agent_status", "agent": "generator", "status": "active"}`
  - [ ] Emit `retrieval_info` with count and rerank metrics

- [ ] **4.6** Update LangGraph state to emit agent status
  - [ ] Modify agent nodes to push status events to a shared queue
  - [ ] SSE generator reads from queue in parallel

- [ ] **4.7** Update `frontend/app/page.tsx` -- UI layout improvements
  - [ ] Add sidebar with document list and upload area
  - [ ] Add session selector with new/cleanup buttons
  - [ ] Improve mobile responsiveness
  - [ ] Add dark mode toggle

- [ ] **4.8** Add design polish
  - [ ] Consistent color scheme (brand-neutral placeholder)
  - [ ] Typography improvements (system fonts or Inter)
  - [ ] Smooth animations for badge transitions
  - [ ] Loading states for all async operations

### Phase 5: Unit Tests, Integration Tests & Documentation (Day 5)

**Goal:** Comprehensive test coverage and final documentation.

- [ ] **5.1** Create `backend/tests/test_gemini_client.py`
  - [ ] Test `generate()` with mock responses
  - [ ] Test `generate_text()` for text-only tasks
  - [ ] Test retry logic on rate limits
  - [ ] Test multimodal input handling

- [ ] **5.2** Create `backend/tests/test_fast_embedder.py`
  - [ ] Test `embed_texts()` batch embedding
  - [ ] Test `embed_query()` single query
  - [ ] Test dimension consistency (1024-dim output)
  - [ ] Test empty input handling

- [ ] **5.3** Create `backend/tests/test_cpu_reranker.py`
  - [ ] Test `rerank()` score ordering
  - [ ] Test empty passage handling
  - [ ] Test score range (0.0 - 1.0)

- [ ] **5.4** Create `backend/tests/test_session_middleware.py`
  - [ ] Test valid UUID passthrough
  - [ ] Test invalid UUID rejection (401)
  - [ ] Test missing UUID auto-generation
  - [ ] Test exempt paths bypass

- [ ] **5.5** Create `backend/tests/test_parent_child_chunker.py`
  - [ ] Test parent chunk size (1024 tokens)
  - [ ] Test child chunk size (128 tokens)
  - [ ] Test parent-child ID relationships
  - [ ] Test table preservation

- [ ] **5.6** Create `backend/tests/test_contextual_headers.py`
  - [ ] Test header generation (mock Gemini)
  - [ ] Test header prepending to chunk text
  - [ ] Test batch processing

- [ ] **5.7** Create `backend/tests/test_qdrant_store.py`
  - [ ] Test `upsert()` with session_id in payload
  - [ ] Test `hybrid_search()` with session filter
  - [ ] Test `delete_by_session()` isolation
  - [ ] Test parent-child query resolution

- [ ] **5.8** Create `backend/tests/test_ingestion_pipeline.py`
  - [ ] Test full pipeline: parse -> header -> chunk -> embed -> store
  - [ ] Test PDF ingestion with tables
  - [ ] Test audio ingestion with Groq Whisper
  - [ ] Test session-scoped ingestion

- [ ] **5.9** Update `backend/pytest.ini` and test configuration
  - [ ] Add `conftest.py` with fixtures
  - [ ] Mock external services (Gemini, Groq)
  - [ ] Add coverage reporting

- [ ] **5.10** Fix CI pipeline (B9)
  - [ ] Replace `pytest verify_nvidia.py -v || true` in `.github/workflows/deploy.yml`
  - [ ] Add proper pytest test suite that runs without live API keys
  - [ ] Use mocked external services for CI
  - [ ] Add coverage reporting with `pytest-cov`

- [ ] **5.11** Update documentation
  - [ ] Update `README.md` with new free tech stack
  - [ ] Add setup instructions for all free APIs
  - [ ] Add architecture diagrams
  - [ ] Add API endpoint documentation
  - [ ] Update `backend/env.example` with all new environment variables

---



## 6. Setup Instructions for All Free APIs

### 6.1 Google Gemini 2.0 Flash (LLM + Vision)

**Free tier:** 15 requests per minute, 1 million tokens per day, 1,500 requests per day for Gemini 2.0 Flash.

**Setup steps:**

1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account
3. Click "Create API Key"
4. Copy the key (starts with `AIzaSy...`)

**Environment variable:**
```env
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
```

**Python installation:**
```bash
pip install google-generativeai
```

**Code example:**
```python
import google.generativeai as genai

genai.configure(api_key="YOUR_API_KEY")
model = genai.GenerativeModel("gemini-2.0-flash")

# Text generation
response = model.generate_content("Explain quantum computing in simple terms.")
print(response.text)

# Multimodal (text + image)
with open("image.png", "rb") as f:
    image_data = f.read()

response = model.generate_content([
    "Describe this image",
    {"mime_type": "image/png", "data": image_data}
])
print(response.text)
```

### 6.2 FastEmbed BGE-M3 (Local Embeddings)

**Free tier:** Unlimited -- runs locally on your CPU. No API key needed.

**Installation:**
```bash
pip install fastembed
```

**First run downloads the model (~1.2GB). Subsequent runs use the cache.**

**Code example:**
```python
from fastembed import TextEmbedding

model = TextEmbedding(model_name="BAAI/bge-m3")

# Batch embed
texts = ["Hello world", "This is a test document"]
embeddings = list(model.embed(texts))
print(f"Embedding dimension: {len(embeddings[0])}")  # 1024

# Query embedding
query_emb = list(model.embed(["What is machine learning?"]))[0]
print(f"Query vector shape: {len(query_emb)}")
```

**Configuration in `.env`:**
```env
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
```

### 6.3 FlashRank CPU Reranker (Local Reranking)

**Free tier:** Unlimited -- runs locally on your CPU. No API key needed.

**Installation:**
```bash
pip install flashrank
```

**First run downloads the model (~50MB). Subsequent runs use the cache.**

**Code example:**
```python
from flashrank import Rerank, RankRequest

reranker = Rerank(model="ms-marco-MiniLM-L-12-v2")

passages = [
    {"id": "1", "text": "Python is a programming language."},
    {"id": "2", "text": "The capital of France is Paris."},
    {"id": "3", "text": "Machine learning is a subset of AI."},
]

results = reranker.rerank(
    RankRequest(
        query="What is Python?",
        passages=passages
    )
)

for result in results:
    print(f"Score: {result.score:.3f} | {result.passage}")
```

### 6.4 Groq Whisper Large V3 (Audio Transcription)

**Free tier:** 7,000 tokens per minute (roughly 7 minutes of audio per minute).

**Setup steps:**

1. Go to https://console.groq.com/keys
2. Sign up or log in
3. Click "Create API Key"
4. Copy the key (starts with `gsk_...`)

**Environment variable:**
```env
GROQ_API_KEY=gsk_...
```

**Python installation:**
```bash
pip install groq
```

**Code example:**
```python
from groq import Groq

client = Groq(api_key="YOUR_API_KEY")

with open("audio.mp3", "rb") as audio_file:
    transcript = client.audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3",
        language="en"
    )
print(transcript.text)
```

### 6.5 Qdrant Free Tier / Local Docker

**Option A: Qdrant Cloud Free Tier (1GB storage)**
1. Go to https://cloud.qdrant.io/
2. Sign up for a free account
3. Create a free cluster (1GB storage)
4. Copy the cluster URL and API key

**Option B: Local Docker (unlimited, recommended for development)**
```bash
docker run -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:latest
```

**Environment variables:**
```env
# For cloud:
QDRANT_URL=https://your-cluster.qdrant.io:6333
QDRANT_API_KEY=your-api-key

# For local:
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
```

### 6.6 Supabase Free Tier

**Free tier:** 500MB database, 1GB file storage, 50,000 monthly active users, 500MB bandwidth.

**Setup steps:**

1. Go to https://supabase.com/
2. Sign up with GitHub
3. Click "New Project"
4. Choose a project name and database password
5. Select a region closest to you
6. Wait for the project to initialize (~2 minutes)
7. Go to Settings > API to find your keys

**Environment variables:**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ... (anon/public key)
SUPABASE_SERVICE_KEY=eyJ... (service_role key -- keep secret!)
```

**Run the schema migration:**
1. Go to the Supabase Dashboard > SQL Editor
2. Paste the contents of `backend/supabase_schema.sql`
3. Click "Run"

### 6.7 Complete `.env` Template

Create `backend/.env` with all free API keys:

```env
# === Google Gemini (LLM + Vision) ===
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
GEMINI_EMBEDDING_MODEL=text-embedding-004

# === Groq (Audio Transcription) ===
GROQ_API_KEY=gsk_...

# === Qdrant (Vector Store) ===
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=multimodal_rag

# === Supabase (Metadata DB) ===
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...

# === Embedding Model (Local, no API key) ===
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024

# === Application Settings ===
CORS_ORIGINS=http://localhost:3000
MAX_RETRIEVAL_RETRIES=3
TOP_K_RETRIEVE=20
TOP_K_RERANK=5
RELEVANCE_THRESHOLD=0.5
```

### 6.8 Quick Start Commands

```bash
# 1. Start Qdrant locally
docker run -p 6333:6333 -p 6334:6334 -v qdrant_data:/qdrant/storage qdrant/qdrant:latest

# 2. Install backend dependencies
cd backend
pip install -r requirements.txt

# 3. First run downloads FastEmbed + FlashRank models
python -c "from fastembed import TextEmbedding; m = TextEmbedding('BAAI/bge-m3'); print('Embedding model ready')"
python -c "from flashrank import Rerank; r = Rerank('ms-marco-MiniLM-L-12-v2'); print('Reranker model ready')"

# 4. Start the backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 5. Start the frontend
cd ../frontend
npm install
npm run dev

# 6. Access at http://localhost:3000
```

---

## Summary of Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM Provider | Gemini 2.0 Flash | Free tier (15 RPM, 1M tokens/day), multimodal native, fast |
| Embedding Model | BGE-M3 via FastEmbed | Local CPU, 1024-dim, multilingual, no API dependency |
| Reranker | FlashRank CPU | Local CPU, <50ms inference, ms-marco model |
| Chunk Strategy | Parent-Child (128/1024) | Small children for precise matching, large parents for context |
| Context Headers | Gemini-generated | Anthropic Contextual Retrieval pattern, improves relevance |
| Session Isolation | UUID + Qdrant payload filter + Supabase | Defense in depth: header validation + payload scoping + DB-level RLS |
| Safety | NemoGuard 8B (local) + Gemini safety | Graceful fallback, no paid API needed for safety |
| Chunk Size Ratio | 1:8 (child:parent) | 128 tokens for precision, 1024 for context -- well-tested ratio |

---

*This implementation plan is a living document. Check off items as you complete them, and update the plan if architectural decisions change during implementation.*
