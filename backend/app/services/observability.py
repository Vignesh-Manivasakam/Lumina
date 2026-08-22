"""LangSmith observability and end-to-end distributed tracing for Lumina RAG.

Provides execution tracing across the LangGraph multi-agent pipeline, tracking
per-agent latency, prompt/completion token usage, grader relevance scores,
and session metadata.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Configure standard LangChain / LangSmith environment variables
if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT


class TraceSpan:
    """Represents an individual agent or tool execution span."""

    def __init__(self, name: str, trace_id: str, run_id: Optional[str] = None) -> None:
        self.name = name
        self.trace_id = trace_id
        self.run_id = run_id or str(uuid.uuid4())
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.inputs: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def finish(
        self,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.end_time = time.time()
        if outputs:
            self.outputs.update(outputs)
        if error:
            self.error = error
        if metadata:
            self.metadata.update(metadata)

    @property
    def duration_ms(self) -> int:
        end = self.end_time or time.time()
        return int((end - self.start_time) * 1000)


class TraceContext:
    """Context holding the full pipeline trace for a single chat invocation."""

    def __init__(
        self,
        query: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.trace_id = str(uuid.uuid4())
        self.query = query
        self.session_id = session_id or "anonymous"
        self.model = model or "default"
        self.client = client
        self.start_time = time.time()
        self.spans: Dict[str, TraceSpan] = {}
        self.parent_run = None

        if self.client:
            try:
                self.parent_run = self.client.create_run(
                    name="lumina_crag_pipeline",
                    run_type="chain",
                    inputs={"query": query, "session_id": self.session_id},
                    extra={"metadata": {"session_id": self.session_id, "model": self.model}},
                    project_name=settings.LANGSMITH_PROJECT,
                )
            except Exception as exc:
                logger.debug("Could not create LangSmith parent run: %s", exc)

    def start_span(self, name: str, inputs: Optional[Dict[str, Any]] = None) -> TraceSpan:
        span = TraceSpan(name=name, trace_id=self.trace_id)
        if inputs:
            span.inputs = inputs
        self.spans[name] = span
        return span

    def end_span(
        self,
        name: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        span = self.spans.get(name)
        if span:
            span.finish(outputs=outputs, error=error, metadata=metadata)
            if self.client and self.parent_run:
                try:
                    self.client.create_run(
                        name=f"agent_{name}",
                        run_type="llm" if name in ("router", "grader", "rewriter", "generator") else "tool",
                        inputs=span.inputs,
                        outputs=span.outputs,
                        error=error,
                        parent_run_id=getattr(self.parent_run, "id", None),
                        project_name=settings.LANGSMITH_PROJECT,
                        extra={"metadata": {**span.metadata, "duration_ms": span.duration_ms}},
                    )
                except Exception as exc:
                    logger.debug("Could not write child span to LangSmith: %s", exc)

    def finish(
        self,
        final_response: str = "",
        route: Optional[str] = None,
        total_tokens: int = 0,
        error: Optional[str] = None,
    ) -> None:
        duration_ms = int((time.time() - self.start_time) * 1000)
        if self.client and self.parent_run:
            try:
                self.client.update_run(
                    self.parent_run.id,
                    outputs={"response": final_response[:500], "route": route},
                    error=error,
                    end_time=time.time(),
                    extra={
                        "metadata": {
                            "total_tokens": total_tokens,
                            "duration_ms": duration_ms,
                            "route": route,
                        }
                    },
                )
            except Exception as exc:
                logger.debug("Could not complete LangSmith parent run: %s", exc)


class ObservabilityService:
    """Observability singleton managing LangSmith tracing and run creation."""

    _instance: Optional[ObservabilityService] = None

    def __init__(self) -> None:
        self.client = None
        self._enabled = bool(settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY)
        if self._enabled:
            try:
                from langsmith import Client
                self.client = Client(api_key=settings.LANGSMITH_API_KEY)
                logger.info(
                    "LangSmith Observability initialized for project '%s'.",
                    settings.LANGSMITH_PROJECT,
                )
            except Exception as exc:
                logger.warning("Failed to initialize LangSmith Client (%s); tracing disabled.", exc)
                self.client = None

    @classmethod
    def get_instance(cls) -> ObservabilityService:
        if cls._instance is None:
            cls._instance = ObservabilityService()
        return cls._instance

    def create_trace(
        self,
        query: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TraceContext:
        """Create a new trace context for a chat request."""
        return TraceContext(
            query=query,
            session_id=session_id,
            model=model,
            client=self.client,
        )


observability = ObservabilityService.get_instance()

__all__ = ["ObservabilityService", "TraceContext", "TraceSpan", "observability"]
