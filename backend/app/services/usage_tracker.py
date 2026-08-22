"""Usage & Token Tracking service for Lumina RAG.

Records per-query prompt/completion token consumption, latency, and model metrics
with Supabase persistence and local JSON fallback.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class UsageTracker:
    """Tracks token consumption and query metrics per session and tenant."""

    def __init__(self, supabase_service: Optional[Any] = None) -> None:
        self.supabase = supabase_service
        self._local_file = Path(__file__).resolve().parent.parent.parent / ".local_usage.json"
        self._local_usage: List[dict] = self._load_local()

    def _load_local(self) -> List[dict]:
        if self._local_file.exists():
            try:
                with open(self._local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.debug("Failed reading local usage file: %s", exc)
        return []

    def _save_local(self) -> None:
        try:
            with open(self._local_file, "w", encoding="utf-8") as f:
                json.dump(self._local_usage[-1000:], f, indent=2)
        except Exception as exc:
            logger.debug("Failed writing local usage file: %s", exc)

    def record_query(
        self,
        session_id: str,
        query: str,
        model: Optional[str] = None,
        route: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
    ) -> dict:
        """Record token consumption and execution latency for a query."""
        total_tokens = prompt_tokens + completion_tokens
        record = {
            "id": f"use-{uuid.uuid4().hex[:12]}",
            "session_id": session_id or "anonymous",
            "query": query[:120] if query else "",
            "model": model or "default",
            "route": route or "simple",
            "prompt_tokens": max(0, prompt_tokens),
            "completion_tokens": max(0, completion_tokens),
            "total_tokens": max(0, total_tokens),
            "latency_ms": max(0, latency_ms),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try Supabase persistence if active
        if self.supabase and getattr(self.supabase, "_enabled", False) and getattr(self.supabase, "_client", None):
            try:
                self.supabase._client.table("usage_log").insert({
                    "session_id": record["session_id"],
                    "query": record["query"],
                    "model": record["model"],
                    "route": record["route"],
                    "prompt_tokens": record["prompt_tokens"],
                    "completion_tokens": record["completion_tokens"],
                    "total_tokens": record["total_tokens"],
                    "latency_ms": record["latency_ms"],
                }).execute()
            except Exception as exc:
                logger.debug("Could not record usage in Supabase (%s); saving locally.", exc)

        self._local_usage.append(record)
        self._save_local()
        return record

    def get_session_usage(self, session_id: str) -> dict:
        """Get cumulative token metrics and statistics for a given session."""
        session_records = [r for r in self._local_usage if r.get("session_id") == session_id]

        # Try fetching from Supabase if online
        if self.supabase and getattr(self.supabase, "_enabled", False) and getattr(self.supabase, "_client", None):
            try:
                res = self.supabase._client.table("usage_log").select("*").eq("session_id", session_id).execute()
                if res.data:
                    session_records = res.data
            except Exception as exc:
                logger.debug("Supabase get_session_usage failed: %s", exc)

        total_queries = len(session_records)
        total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in session_records)
        total_completion_tokens = sum(r.get("completion_tokens", 0) for r in session_records)
        total_tokens = sum(r.get("total_tokens", 0) for r in session_records)
        avg_latency = (
            int(sum(r.get("latency_ms", 0) for r in session_records) / max(total_queries, 1))
            if total_queries > 0
            else 0
        )

        by_model = defaultdict(int)
        for r in session_records:
            m = r.get("model") or "unknown"
            by_model[m] += r.get("total_tokens", 0)

        by_route = defaultdict(int)
        for r in session_records:
            rt = r.get("route") or "unknown"
            by_route[rt] += 1

        return {
            "session_id": session_id,
            "total_queries": total_queries,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "average_latency_ms": avg_latency,
            "tokens_by_model": dict(by_model),
            "queries_by_route": dict(by_route),
        }


__all__ = ["UsageTracker"]
