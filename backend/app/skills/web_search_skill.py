"""Web search skill using Tavily API for live internet search and verified citations."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.config import settings
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class WebSearchSkill(Skill):
    """Executes live web searches via Tavily Cloud API and populates high-precision citations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.api_key = api_key if api_key is not None else getattr(settings, "TAVILY_API_KEY", "")
        self._client = None

        if self.api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
                logger.info("WebSearchSkill initialized with Tavily client.")
            except Exception as exc:
                logger.warning("Failed to initialize TavilyClient: %s", exc)
                self._client = None

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Searches the live web using Tavily API for real-time information and citations."

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "web_search"

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if not self.api_key or not self._client:
            logger.info("Tavily API key not configured for WebSearchSkill.")
            if thinking_emitter:
                thinking_emitter("skill_executor", "Web search not configured (missing TAVILY_API_KEY in backend/.env).")
            fallback_doc = {
                "chunk_id": "web-fallback",
                "id": "web-fallback",
                "modality": "text",
                "text_repr": "Web search is currently not configured. Set TAVILY_API_KEY in backend/.env to enable real-time internet search.",
                "url": "",
                "title": "Configuration Notice",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "web_search",
            }
            state["retrieved_docs"] = [fallback_doc]
            state["relevant_docs"] = [fallback_doc]
            state["source_docs"] = [fallback_doc]
            state["web_results"] = []
            state["is_sufficient"] = True
            return state

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Querying live web via Tavily API for: {query[:60]}...")

        try:
            search_response = self._client.search(
                query=query,
                max_results=5,
                search_depth="advanced",
                include_answer=False,
            )
            raw_results = search_response.get("results", []) if isinstance(search_response, dict) else []

            if not raw_results:
                if thinking_emitter:
                    thinking_emitter("skill_executor", "No web results returned for query.")
                doc_dict = {
                    "chunk_id": "web-no-results",
                    "id": "web-no-results",
                    "modality": "text",
                    "text_repr": f"No web search results found for '{query}'.",
                    "url": "",
                    "title": "No Results",
                    "score": 0.0,
                    "relevance_score": 0.0,
                    "rerank_score": 0.0,
                    "source": "web_search",
                }
                state["retrieved_docs"] = [doc_dict]
                state["relevant_docs"] = []
                state["source_docs"] = []
                state["web_results"] = []
                state["is_sufficient"] = True
                return state

            formatted_docs: List[Dict[str, Any]] = []
            web_results: List[Dict[str, Any]] = []

            for i, item in enumerate(raw_results):
                title = item.get("title") or f"Web Result {i+1}"
                url = item.get("url") or ""
                content = (item.get("content") or "").strip()
                score = float(item.get("score") if item.get("score") is not None else max(0.95 - (i * 0.05), 0.6))

                text_repr = f"Source Title: {title}\nSource URL: {url}\n\n{content}"
                chunk_id = f"web_{uuid.uuid4().hex[:8]}_{i}"

                doc_dict = {
                    "chunk_id": chunk_id,
                    "id": chunk_id,
                    "modality": "text",
                    "text_repr": text_repr,
                    "url": url,
                    "title": title,
                    "score": score,
                    "relevance_score": score,
                    "rerank_score": score,
                    "source": "web_search",
                }
                formatted_docs.append(doc_dict)

                web_results.append({
                    "title": title,
                    "url": url,
                    "content": content,
                    "score": score,
                })

            state["retrieved_docs"] = formatted_docs
            state["relevant_docs"] = formatted_docs
            state["source_docs"] = formatted_docs
            state["web_results"] = web_results
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter(
                    "skill_executor",
                    f"Surfaced {len(formatted_docs)} high-confidence live web sources from Tavily.",
                )

            logger.info("WebSearchSkill completed successfully: %d web sources retrieved.", len(formatted_docs))

        except Exception as exc:
            logger.exception("Web search execution failed: %s", exc)
            fallback_doc = {
                "chunk_id": "web-error",
                "id": "web-error",
                "modality": "text",
                "text_repr": f"Web search failed: {exc}",
                "url": "",
                "title": "Search Notice",
                "score": 0.5,
                "relevance_score": 0.5,
                "rerank_score": 0.5,
                "source": "web_search",
            }
            state["retrieved_docs"] = [fallback_doc]
            state["relevant_docs"] = []
            state["source_docs"] = []
            state["web_results"] = []
            state["is_sufficient"] = True

        return state
