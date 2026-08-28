<div align="center">
  <h1>Lumina</h1>
  <p><strong>Enterprise multimodal intelligence with corrective RAG, adaptive skills, and bidirectional MCP.</strong></p>

  <p>
    <a href="#quick-start"><img src="https://img.shields.io/badge/launch-local%20first-2864DC?style=for-the-badge&logo=rocket&logoColor=white" alt="Local-first" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-111827?style=for-the-badge" alt="MIT license" /></a>
    <a href="#architecture"><img src="https://img.shields.io/badge/architecture-CRAG%20%2B%20MCP-7C3AED?style=for-the-badge&logo=diagram&logoColor=white" alt="CRAG and MCP architecture" /></a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Next.js-14-111827?logo=next.js" alt="Next.js 14" />
    <img src="https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/LangGraph-corrective%20flow-F97316" alt="LangGraph" />
    <img src="https://img.shields.io/badge/Qdrant-hybrid%20retrieval-DC244C?logo=qdrant&logoColor=white" alt="Qdrant" />
    <img src="https://img.shields.io/badge/MCP-bidirectional-8B5CF6" alt="Model Context Protocol" />
    <img src="https://img.shields.io/badge/Tests-pytest%20%2B%20Node-16A34A?logo=pytest&logoColor=white" alt="Automated tests" />
  </p>
</div>

<div align="center">
  <img src="assets/Lumina.png" alt="Lumina — multimodal corrective RAG architecture overview" width="820" />
</div>

> **The short version:** upload documents in virtually any business format, ask a question, and Lumina retrieves, verifies, rewrites when evidence is weak, then streams a grounded answer with sources and an inspectable agent trace. It can also call external MCP tools, expose its own knowledge base over MCP, run focused reasoning skills, search the web, understand images, and process voice.

## Contents

- [Product tour](#product-tour)
- [What Lumina does](#what-lumina-does)
- [Architecture](#architecture)
- [Request lifecycle](#request-lifecycle)
- [Key capabilities](#key-capabilities)
- [Supported inputs and outputs](#supported-inputs-and-outputs)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API and streaming contract](#api-and-streaming-contract)
- [MCP integration](#mcp-integration)
- [Project map](#project-map)
- [Testing](#testing)
- [Deployment](#deployment)

## Product tour

> **Tour outline:** upload or select a document, ask a question in the multimodal composer, inspect citations and the agent trace, then open the Skills Hub or MCP Hub to extend the workflow.

The workspace combines the document library, session history, adaptive skills, and MCP connections in one research surface.

<div align="center">
  <table>
    <tr>
      <td align="center" width="46%"><img src="assets/concept-sketch.png" alt="Original notebook plan for Lumina" width="100%" /><br/><sub><strong>Where it started</strong> — the original notebook plan</sub></td>
      <td align="center" width="54%"><img src="assets/system-architecture.png" alt="Lumina system architecture diagram" width="100%" /><br/><sub><strong>Where it landed</strong> — the full system architecture</sub></td>
    </tr>
  </table>
</div>

## What Lumina does

| For a team that needs… | Lumina provides… |
| --- | --- |
| **Answers from private knowledge** | Hybrid dense + sparse retrieval, FlashRank reranking, and source cards that link the answer back to retrieved passages. |
| **Reliable retrieval when the first search is not enough** | A corrective RAG loop that grades evidence, rewrites the query with HyDE / step-back / decomposition techniques, and retries within a configured limit. |
| **One workspace for messy inputs** | Parsing and ingestion for documents, spreadsheets, presentations, images, audio, and video. |
| **A transparent agent experience** | Streaming answer tokens alongside agent status, reasoning notes, retrieval metrics, sources, tool results, and usage events over SSE. |
| **Specialist workflows without hard-coding prompts** | Markdown-defined skills with metadata, trigger routing, session-scoped custom skills, and a three-tier skill router. |
| **Interoperability with the agent ecosystem** | Lumina both **serves** knowledge-base tools to MCP clients and **consumes** tools discovered from remote MCP servers. |
| **Sane local development** | CPU-friendly embedding/reranking, Qdrant local or cloud, and graceful local JSON fallbacks when Supabase is not configured. |

## Architecture

<div align="center">
  <img src="assets/system-architecture.png" alt="Lumina system architecture — client layer, backend API, intelligence plane, data and storage layer, bidirectional MCP integration, and background workers" width="900" />
</div>

### Design principles

1. **Correct before fluent.** The graph grades retrieval results before synthesis and can rewrite/retrieve again when the evidence set is insufficient.
2. **Local-first by default.** Embeddings and reranking run on CPU; Qdrant can be local; Supabase is optional rather than a prerequisite for a usable workspace.
3. **Observability is part of the product.** The UI consumes structured agent and thinking events instead of presenting a black-box answer.
4. **Interoperability runs both ways.** Lumina can be an MCP server for IDE clients and an MCP client for external capabilities.
5. **Privacy is enforced at the request boundary.** A UUIDv4 session header scopes application requests; vector payloads and persisted conversations retain their session association.

## Request lifecycle

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant W as Web app
  participant A as API + middleware
  participant G as CRAG graph
  participant V as Qdrant
  participant L as LLM provider

  U->>W: Ask a question / attach a file or image
  W->>A: POST /api/chat + X-Session-ID
  A->>A: Validate/issue session; apply rate limit & safety checks
  A->>G: Route intent and select an optional skill
  alt Tool route
    G->>G: Execute web, image, or MCP tool skill
  else Knowledge route
    G->>V: Hybrid dense + BM25 search, RRF fusion, reranking
    V-->>G: Child chunks + resolved parent context
    G->>L: Batch-grade relevance
    alt Context insufficient and retries remain
      G->>L: Rewrite query / create retrieval strategy
      G->>V: Retry retrieval
    end
  end
  G->>L: Generate grounded streamed response
  L-->>A: Tokens, citations, trace metrics
  A-->>W: SSE events: status, thinking, text, sources, usage, DONE
  W-->>U: Answer, sources, and inspectable reasoning timeline
```

## Key capabilities

### 1) Multimodal ingestion that preserves useful structure

- **Adaptive format routing:** PDFs, Word, PowerPoint, CSV/TSV/JSON, plain text/code, images, audio, and video enter a single ingestion pipeline.
- **Document-aware chunking:** the orchestrator can select section, semantic, or parent-child strategies; parent context preserves coherence while smaller child chunks improve search precision.
- **Contextual headers:** chunks can receive document-level framing before embedding, improving retrieval for snippets that otherwise lack context.
- **Visual and spoken content:** image extraction supports visual content; audio is transcribed through the configured provider, while the video path extracts frame-level visual context.

### 2) Corrective hybrid RAG

- **Hybrid retrieval:** local dense BGE embeddings and BM25 sparse vectors are fused with reciprocal-rank fusion (RRF), then reranked by a CPU-friendly FlashRank cross-encoder.
- **Five-agent graph:** Router → Retriever → Grader → Rewriter → Generator, with a skill-executor node for tools.
- **Bounded correction:** the grader declares whether context is sufficient. If it is not, the rewriter selects query expansion techniques and the graph retries up to `MAX_RETRIEVAL_RETRIES`.
- **Grounded generation:** source passages are assembled for the generator and exposed as source cards in the application.

### 3) Adaptive skills and tools

| Skill path | Purpose |
| --- | --- |
| **Three-tier router** | Uses exact trigger matching first, then micro-LLM intent expansion with dense/sparse skill matching, then a Sonnet → Opus → Fable reasoning fallback. |
| **Markdown skill registry** | Loads built-in and session-scoped skills from Markdown front matter; lists, creates, reads, executes, and deletes custom session skills through the API. |
| **Domain skills** | Includes contract risk analysis, causal/root-cause reasoning, executive briefings, financial analysis, structured extraction, code architecture review, and creative prompt design. |
| **Web research** | Tavily-backed live web results are converted into cited tool context when configured. |
| **Image generation** | Refines image prompts and uses NVIDIA NIM SDXL with a high-reliability fallback path. |
| **External MCP tools** | Registers, probes, discovers, and invokes remote MCP tools subject to URL safety checks. |

### 4) Enterprise controls and persistence

- **Session isolation:** the API validates an `X-Session-ID` UUIDv4 (or issues one), returns it on responses, and scopes history and usage endpoints to it.
- **Rate limiting:** sliding-window limits apply per session or client IP.
- **Safety guard:** chat processing checks unsafe content before graph execution.
- **Dual persistence:** Supabase stores metadata, conversations, and usage when credentials exist; local JSON registries preserve a zero-dependency fallback.
- **Provider resilience:** a registry routes tasks across Gemini, Groq, and NVIDIA-compatible providers.

### 5) A research workspace, not a blank chat box

- Responsive Next.js workspace with document library, conversations, model selection, image/file attachment, dark mode, and error states.
- **Thinking Area** with timeline, agent matrix, and raw-log modes.
- Rich Markdown, code, tables, citations, web results, tool result cards, image result cards, and streaming message UI.
- Voice transcription and synthesis endpoints are available for audio workflows.

## Supported inputs and outputs

| Input | Processing path | Result |
| --- | --- | --- |
| PDF | PyMuPDF / PDF extraction + hierarchy-aware chunks | Searchable passages, tables, and visual context |
| DOCX / PPTX | `python-docx` / `python-pptx` | Headings, body text, notes, and tables become retrieval context |
| CSV / TSV / JSON | Adaptive text parser | Tabular and structured data become searchable text |
| TXT / Markdown / code | Native text parsing | Formatting-preserving chunks |
| PNG / JPG / WebP | Image extraction + multimodal generation | Visual question answering and image-aware responses |
| MP3 / WAV / M4A | Audio pipeline + optional transcription provider | Timestamped transcript-oriented retrieval |
| MP4 / AVI / MOV | Video pipeline | Frame-level visual context for retrieval |
| Query + optional image/file | CRAG graph or tool skill | Streaming answer, sources, trace, web/tool/image results |

## Quick start

### Prerequisites

- Python **3.11+** (the deployment configuration uses Python 3.12).
- Node.js **18.17+** (Node 20 is used for deployment).
- A Qdrant instance: local Docker or Qdrant Cloud.
- At least one generation provider key for a fully functional chat experience. Gemini is the default documented path.

### 1. Clone and configure the backend

```bash
git clone https://github.com/Vignesh-Manivasakam/Lumina.git
cd Lumina/backend

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp env.example .env
```

Set the minimum useful values in `backend/.env`:

```dotenv
GEMINI_API_KEY=your_key
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=multimodal_rag
```

For local Qdrant:

```bash
docker run -p 6333:6333 -p 6334:6334 -v qdrant_data:/qdrant/storage qdrant/qdrant:latest
```

Start the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`; interactive OpenAPI docs are at `http://localhost:8000/docs`.

### 2. Start the frontend

```bash
cd ../frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Set `NEXT_PUBLIC_API_URL` if the API is not running at the frontend's expected API origin.

## Configuration

Copy `backend/env.example` to `backend/.env`. The complete template includes provider, retrieval, session, and persistence settings; the most important values are below.

| Variable | Required | Default / example | Why it matters |
| --- | :---: | --- | --- |
| `GEMINI_API_KEY` | For Gemini | — | Primary generation and vision provider credential. |
| `GROQ_API_KEY` | No | — | Enables Groq provider and Whisper-oriented audio processing. |
| `NVIDIA_API_KEY` | No | — | Enables NVIDIA provider, image generation, speech, and transcription paths. |
| `QDRANT_URL` | Yes for persistent retrieval | `http://localhost:6333` | Qdrant local or cloud endpoint. |
| `QDRANT_API_KEY` | Cloud only | empty | Qdrant Cloud credential. |
| `QDRANT_COLLECTION` | No | `multimodal_rag` | Vector collection name. |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | No | empty | Enables cloud metadata, history, and usage persistence; otherwise Lumina degrades gracefully. |
| `TAVILY_API_KEY` | No | empty | Enables the live web-search skill. |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | No | BGE model / `1024` | Local dense embedding configuration. |
| `RERANK_MODEL` | No | MiniLM model | Cross-encoder reranker configuration. |
| `TOP_K_RETRIEVE` / `TOP_K_RERANK` | No | `20` / `5` | Retrieval depth and final context count. |
| `MAX_RETRIEVAL_RETRIES` | No | `3` | Maximum corrective RAG cycles. |
| `RELEVANCE_THRESHOLD` | No | `0.5` | Relevance cutoff used by the grader. |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Browser-origin access control. |

## API and streaming contract

### Core endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness response. |
| `POST` | `/api/chat` | Main chat entry point; streams structured SSE events. |
| `POST` | `/api/ingest` | Upload a file for asynchronous ingestion. |
| `GET` | `/api/ingest/{doc_id}/status` | Poll ingestion state. |
| `GET` / `DELETE` | `/api/documents` / `/api/documents/{doc_id}` | List or purge indexed documents. |
| `POST` / `GET` | `/api/sessions` / `/api/sessions/{session_id}/history` | Create a session and retrieve its history. |
| `POST` / `DELETE` | `/api/sessions/{session_id}/cleanup` / `/api/sessions/{session_id}` | Clear or delete session history. |
| `GET` | `/api/sessions/{session_id}/usage` | Get session usage. |
| `GET` / `POST` / `PATCH` | `/api/conversations` and `/api/conversations/{id}` | Conversation management. |
| `POST` / `GET` / `DELETE` | `/api/mcp/connections` | Register, list, and remove remote MCP connections. |
| `GET` / `POST` | `/api/skills` and `/api/skills/{skill_name}/execute` | Inspect and execute skills. |
| `POST` | `/api/voice/transcribe` | Transcribe uploaded audio. |
| `POST` | `/api/voice/synthesize` | Synthesize text to WAV audio. |

### What comes back over SSE

`POST /api/chat` streams events such as `agent_status`, `thinking`, `retrieval_info`, `text`, `sources`, `web_results`, `tool_result`, `image_result`, `usage`, and the terminal `[DONE]` marker. The frontend maps those events to the thinking trace, streamed message, citation list, and tool/image result cards.

```text
event: message
data: {"type":"agent_status","agent":"retriever","status":"active"}

event: message
data: {"type":"retrieval_info","info":{"retrieved_count":12,"reranked_count":5}}

event: message
data: {"type":"text","content":"Here is the grounded answer…"}

event: message
data: {"type":"sources","sources":[{"doc_title":"Policy.pdf","page":4,"score":0.94}]}

event: message
data: [DONE]
```

## MCP integration

### Use Lumina from an MCP client

Lumina exposes `query_knowledge_base` and `list_documents` through its MCP server. A Cursor/Windsurf HTTP configuration looks like:

```json
{
  "mcpServers": {
    "lumina-rag": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

For Claude Desktop's local stdio workflow:

```json
{
  "mcpServers": {
    "lumina-rag": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/Lumina/backend"
    }
  }
}
```

### Bring external tools into Lumina

Open the **MCP Hub** from the application, register an SSE-capable MCP endpoint, test it, discover its tool schemas, and then let the graph invoke those tools through the MCP tool skill. The backend verifies URLs before connecting and persists registrations through its configured persistence layer.

## Project map

```text
Lumina/
├── assets/                         # README artwork and demo media
├── backend/
│   ├── app/
│   │   ├── agents/                 # Router, retriever, grader, rewriter, generator
│   │   ├── graph/                  # LangGraph corrective-RAG topology
│   │   ├── ingestion/              # Parsers, adaptive chunking, embedding pipelines
│   │   ├── retrieval/              # Qdrant hybrid search and CPU reranking
│   │   ├── routers/                # Conversations, MCP, skills, and voice APIs
│   │   ├── services/               # Providers, safety, observability, persistence
│   │   ├── skills/                 # Built-in tools and Markdown skill system
│   │   ├── middleware/             # Session isolation and rate limiting
│   │   ├── main.py                 # FastAPI app, endpoints, and SSE orchestration
│   │   └── mcp_server.py           # Lumina-as-MCP-server entry point
│   ├── tests/                      # Unit, integration, security, and smoke tests
│   └── env.example                 # Fully annotated environment template
├── frontend/
│   ├── app/                        # Next.js App Router page and global styles
│   ├── components/                 # Workspace, chat, traces, citations, MCP, skills UI
│   ├── lib/                        # API/SSE client and shared TypeScript types
│   └── __tests__/                  # Frontend contract tests
├── render.yaml                     # Render service definitions
└── README.md
```

## Testing

```bash
# Backend: from repository root
cd backend
python -m pytest tests -v

# Frontend: from repository root
cd frontend
npm test
npm run build
```

The backend suite covers routing, CRAG graph behavior, retrieval and Qdrant weighting, grading, rewriting, ingestion/chunking, provider behavior, session isolation, rate limiting, MCP URL safety and client behavior, voice endpoints, skills, persistence fallback, and observability/usage flows. The frontend suite validates API-contract behavior.

## Deployment

`render.yaml` defines two free-tier services:

1. **FastAPI backend:** install `backend/requirements.txt`, start Uvicorn, and configure model/provider, Qdrant, Supabase, and web-search secrets in Render.
2. **Next.js frontend:** install and build `frontend`, then set `NEXT_PUBLIC_API_URL` from the backend service host.

The same separation maps cleanly to other hosts: deploy the API as a Python web service, the frontend as a Node/Next.js service, provision Qdrant, and supply the environment variables listed above.

## License

Lumina is released under the [MIT License](LICENSE).

<div align="center">
  <strong>Build answers your team can inspect, not just admire.</strong>
</div>
