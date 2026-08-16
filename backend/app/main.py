import os
import re
import json
import shutil
import tempfile
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from app.config import settings
from app.services.llm_client import LLMClient
from app.retrieval.qdrant_store import QdrantStore
from app.retrieval.cpu_reranker import CPUReranker
from app.ingestion.fast_embedder import LocalEmbedder
from app.ingestion.embedder import MultimodalEmbedder
from app.ingestion.pipeline import IngestionPipeline

from app.agents.router import RouterAgent
from app.agents.retriever import RetrieverAgent
from app.agents.grader import GraderAgent
from app.agents.rewriter import RewriterAgent
from app.agents.generator import GeneratorAgent
from app.graph.crag_graph import AGENT_ORDER, build_crag_graph

from app.services.safety import SafetyGuard
from app.middleware.session import SessionIsolationMiddleware

app = FastAPI(title="Lumina RAG API")

# Mount Routers
from app.routers.voice import router as voice_router  # noqa: E402
from app.routers.mcp import router as mcp_router  # noqa: E402
from app.routers.conversations import router as conversations_router  # noqa: E402

app.include_router(voice_router)
app.include_router(mcp_router)
app.include_router(conversations_router)

# MCP server (Phase 1.7: tools only; full session scoping in Phase 2)
from app.mcp_server import mcp  # noqa: E402
if mcp is not None and hasattr(mcp, "sse_app"):
    sse = mcp.sse_app()
    if sse is not None:
        app.mount("/mcp", sse)

# Setup CORS
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")] if settings.CORS_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2: register session-isolation middleware (validates UUID, injects
# request.state.session_id, auto-issues UUID for anonymous calls). Must
# be added AFTER CORS so it sees the parsed headers.
app.add_middleware(SessionIsolationMiddleware)


def _secure_filename(name: str) -> str:
    """Werkzeug-style sanitisation without the dependency.

    Strips directory components, drops characters outside
    ``[A-Za-z0-9._-]``, then trims leading/trailing dots/underscores.
    Falls back to ``"upload"`` for fully-invalid names.
    """
    name = os.path.basename(name or "")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.strip("._")
    return name or "upload"


# Initialize Services & Agents ------------------------------------------------
llm_client = LLMClient()
local_embedder = LocalEmbedder()
reranker = CPUReranker()
qdrant_store = QdrantStore()
embedder = MultimodalEmbedder(local_embedder)
safety_guard = SafetyGuard()

router_agent = RouterAgent(llm_client)
retriever_agent = RetrieverAgent(qdrant_store, embedder, llm_client, reranker)
grader_agent = GraderAgent(llm_client)
rewriter_agent = RewriterAgent(llm_client)
generator_agent = GeneratorAgent(llm_client)

crag_graph = build_crag_graph(
    router=router_agent,
    retriever=retriever_agent,
    grader=grader_agent,
    rewriter=rewriter_agent,
    generator=generator_agent,
)

pipeline = IngestionPipeline()


class ChatRequest(BaseModel):
    query: str
    history: Optional[List[dict]] = None
    image_b64: Optional[str] = None
    session_id: Optional[str] = None
    web_search_mode: Optional[str] = "auto"  # "auto" | "always" | "off"
    model: Optional[str] = None  # "gemini-flash-latest" | "nvidia/nemotron-mini-4b-instruct" | "llama-3.3-70b-versatile"
    attached_file_name: Optional[str] = None
    attached_file_content: Optional[str] = None
    attached_file_type: Optional[str] = None


# --- Ingestion Background Task ---------------------------------------------
def run_ingestion_task(file_path: str, dept: str, doc_id: str, session_id: Optional[str] = None):
    try:
        pipeline.run(file_path, dept, doc_id, session_id=session_id)
    except Exception as e:
        print(f"Background ingestion failed: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# --- Endpoints --------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "message": "Multimodal RAG API is healthy"}


@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    # Phase 2: prefer the session_id injected by SessionIsolationMiddleware
    # over the client-supplied value (which may be forged). They should
    # match in well-formed clients because the middleware echoes the
    # header back into state.session_id.
    trusted_session: Optional[str] = getattr(http_request.state, "session_id", None)
    effective_session: Optional[str] = trusted_session or request.session_id

    if not safety_guard.is_safe(request.query):
        async def unsafe_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': 'Flagged: User query violates content safety policies.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(unsafe_stream(), media_type="text/event-stream")

    async def event_stream():
        # asyncio.Queue carries agent_status events from the graph's
        # _wrap_with_status callbacks out to the SSE generator.
        status_queue: asyncio.Queue = asyncio.Queue()
        retrieval_started_at: float = time.monotonic()

        def _emit_status(agent: str, status: str, message: Optional[str] = None) -> None:
            step = AGENT_ORDER.index(agent) if agent in AGENT_ORDER else -1
            status_queue.put_nowait(
                {
                    "type": "agent_status",
                    "agent": agent,
                    "status": status,
                    "message": message,
                    "step": step,
                }
            )

        def _emit_thinking(agent: str, content: str) -> None:
            """Push a one-line thinking note onto the SSE queue."""
            step = AGENT_ORDER.index(agent) if agent in AGENT_ORDER else -1
            status_queue.put_nowait(
                {"type": "thinking", "agent": agent, "step": step, "content": content}
            )

        attached_file_data = None
        if request.attached_file_content or request.attached_file_name:
            attached_file_data = {
                "name": request.attached_file_name or "attached_document",
                "content": request.attached_file_content or "",
                "type": request.attached_file_type or "text",
            }

        state = {
            "query": request.query,
            "user_image_b64": request.image_b64,
            "attached_file": attached_file_data,
            "chat_history": request.history or [],
            "retrieval_count": 0,
            "filters": {},
            "rewritten_query": None,
            "sub_queries": [],
            "retrieved_docs": [],
            "retrieved_children": [],
            "relevant_docs": [],
            "is_sufficient": False,
            "stream": None,
            "source_docs": [],
            "session_id": effective_session,
            "web_search_mode": request.web_search_mode or "auto",
            "model": request.model,
            "use_parent_resolution": True,
            "status_emitter": _emit_status,
            "thinking_emitter": _emit_thinking,
        }

        # Run the graph in a background task so we can drain the
        # status queue in parallel with the LLM token stream.
        graph_task = asyncio.create_task(asyncio.to_thread(crag_graph.invoke, state))

        async def _stream_graph_output():
            """Yield status events while waiting for graph completion."""
            while True:
                try:
                    event = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    if graph_task.done():
                        # Drain anything left
                        while not status_queue.empty():
                            yield f"data: {json.dumps(status_queue.get_nowait())}\n\n"
                        return

        try:
            if effective_session:
                try:
                    pipeline.supabase.add_message(
                        session_id=effective_session,
                        role="user",
                        content=request.query,
                        image_b64=request.image_b64,
                    )
                except Exception as exc:
                    print(f"[Supabase] User message save error: {exc}")

            # Yield status events as they arrive while the graph runs.
            async for sse_status in _stream_graph_output():
                yield sse_status

            result = graph_task.result()
            stream = result.get("stream")
            retrieved_docs = result.get("retrieved_docs") or []

            # Emit skills results (image_result, web_results, tool_result)
            image_result = result.get("image_result")
            if image_result:
                yield f"data: {json.dumps({'type': 'image_result', **image_result})}\n\n"

            web_results = result.get("web_results")
            if web_results:
                yield f"data: {json.dumps({'type': 'web_results', 'results': web_results})}\n\n"

            tool_result = result.get("tool_result")
            if tool_result:
                yield f"data: {json.dumps({'type': 'tool_result', 'result': tool_result})}\n\n"

            # Emit retrieval_info once we know how many children/parents
            # we landed on. ``retrieved_children`` is set by the retriever
            # in Phase 3; ``retrieved_docs`` is the parent set.
            retrieval_ms = int((time.monotonic() - retrieval_started_at) * 1000)
            yield f"data: {json.dumps({'type': 'retrieval_info', 'info': {
                'retrieved_count': len(result.get('retrieved_children') or []),
                'reranked_count': len(retrieved_docs),
                'retrieval_ms': retrieval_ms,
                'is_sufficient': bool(result.get('is_sufficient', False)),
                'filters': state.get('filters') or {},
            }})}\n\n"

            full_response = ""
            if stream:
                for chunk in stream:
                    content = getattr(chunk, "content", "") or ""
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"

            # B7: prefer the post-rerank score when available, fall back to RRF
            sources = result.get("source_docs", [])
            formatted_sources = [
                {
                    "chunk_id": doc.get("chunk_id", doc.get("id", "")),
                    "modality": doc.get("modality", "text"),
                    "text_repr": doc.get("text_repr", ""),
                    "page_num": doc.get("page_num"),
                    "score": doc.get("rerank_score", doc.get("score")),
                    "rerank_score": doc.get("rerank_score"),
                }
                for doc in sources
            ]

            if effective_session:
                msg_content = full_response
                if not msg_content and image_result:
                    msg_content = f"Generated image for: {image_result.get('refined_prompt') or image_result.get('prompt', '')}"
                try:
                    pipeline.supabase.add_message(
                        session_id=effective_session,
                        role="assistant",
                        content=msg_content,
                        source_chunks=formatted_sources,
                    )
                except Exception as exc:
                    print(f"[Supabase] Assistant message save error: {exc}")

            yield f"data: {json.dumps({'type': 'sources', 'sources': formatted_sources})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/ingest")
async def ingest(
    background_tasks: BackgroundTasks,
    http_request: Request,
    file: UploadFile = File(...),
    dept: str = Form("General"),
):
    # B8: sanitise filename; use uuid-prefixed temp path so concurrent
    # uploads of the same source never collide and never escape the temp dir
    safe_name = _secure_filename(file.filename or "upload")
    unique = os.urandom(8).hex()
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, f"{unique}_{safe_name}")

    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # B8 (cont.): enforce upload size limit (50 MB)
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
    actual_size = os.path.getsize(temp_file_path)
    if actual_size > MAX_UPLOAD_BYTES:
        os.remove(temp_file_path)
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({actual_size / (1024*1024):.1f} MB). Maximum upload size is 50 MB.",
        )

    # Phase 2: tag the new document's chunks with the uploader's session
    session_id: Optional[str] = getattr(http_request.state, "session_id", None)

    try:
        file_ext = Path(safe_name).suffix.lower().replace(".", "")
        doc_record = pipeline.supabase.create_document(
            filename=safe_name,
            file_type=file_ext,
            dept=dept,
        )
        doc_id = doc_record.get("id")

        background_tasks.add_task(run_ingestion_task, temp_file_path, dept, doc_id, session_id)
        return {"doc_id": doc_id, "status": "processing"}
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize ingestion. Have you run the Supabase SQL migrations? Error: {e}",
        )


@app.get("/api/ingest/{doc_id}/status")
async def ingest_status(doc_id: str):
    try:
        status = pipeline.supabase.get_document_status(doc_id)
        return {"doc_id": doc_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
async def list_documents():
    try:
        docs = pipeline.supabase.get_all_documents()
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{doc_id}")
async def delete_document_endpoint(doc_id: str):
    try:
        qdrant_store.delete_by_doc_id(doc_id)
        res = pipeline.supabase.delete_document(doc_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sessions")
async def create_new_session():
    try:
        session = pipeline.supabase.create_session()
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}/history")
async def get_session_messages(session_id: str):
    try:
        messages = pipeline.supabase.get_session_history(session_id)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Phase 2: session lifecycle endpoints ----------------------------------
@app.post("/api/sessions/{session_id}/cleanup")
async def cleanup_session(session_id: str, http_request: Request):
    """Delete all chat messages AND Qdrant chunks owned by this session.

    Documents (Supabase ``documents`` rows) remain because they are
    workspace-shared. Only the per-chunk payload tag and the chat
    history are removed.
    """
    trusted_session: Optional[str] = getattr(http_request.state, "session_id", None)
    if trusted_session and trusted_session != session_id:
        # A session may only clean itself up.
        raise HTTPException(status_code=403, detail="Session mismatch")
    try:
        msgs = pipeline.supabase.cleanup_session(session_id)
        chunks_deleted = qdrant_store.delete_by_session(session_id)
        return {
            "session_id": session_id,
            "deleted_messages": msgs["deleted"],
            "deleted_chunks": chunks_deleted,
            "status": "cleaned",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, http_request: Request):
    """Permanent deletion of the session and all its data."""
    trusted_session: Optional[str] = getattr(http_request.state, "session_id", None)
    if trusted_session and trusted_session != session_id:
        raise HTTPException(status_code=403, detail="Session mismatch")
    try:
        chunks_deleted = qdrant_store.delete_by_session(session_id)
        result = pipeline.supabase.delete_session(session_id)
        result["deleted_chunks"] = chunks_deleted
        result["status"] = "deleted"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions")
async def list_recent_sessions():
    """List recent sessions (admin/debug helper, not filtered by session_id)."""
    try:
        sessions = pipeline.supabase.list_sessions(limit=50)
        return sessions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
