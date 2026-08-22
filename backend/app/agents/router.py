"""Query router agent with heuristic pre-filtering and classification.

Routes queries into:
- 'direct'     → greeting/chitchat or meta queries, no retrieval needed
- 'image_gen'  → requests to generate or draw an image
- 'web_search' → requests explicitly requesting web search
- 'multimodal' → query contains or asks about an image/chart/table
- 'simple'     → single-hop factual query
- 'complex'    → multi-hop synthesis or multi-step reasoning

Also classifies query_type:
- 'keyword' | 'numerical' | 'semantic' | 'multi_hop' | 'greeting' | 'image_gen' | 'web_search' | 'multimodal'
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Literal, Optional, Tuple

from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Heuristic patterns for instant short-circuit routing (0 LLM tokens)
_GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|greetings|good\s+(?:morning|afternoon|evening|day)|thanks|thank\s+you|howdy)"
    r"(?:[,\s]+(?:how\s+are\s+you|there|assistant|bot|all))?[!.?\s]*$",
    re.IGNORECASE,
)

_IMAGE_GEN_RE = re.compile(
    r"\b(?:generate\s+(?:an?\s+|me\s+(?:the\s+|an?\s+)?)?(?:image|art|artwork|picture|photo|graphic|portrait|illustration)|"
    r"create\s+(?:an?\s+|me\s+(?:the\s+|an?\s+)?)?(?:picture|image|photo|graphic|art|illustration|portrait)|"
    r"draw\s+(?:an?\s+|me\s+(?:the\s+|an?\s+)?)?(?:picture|image|diagram|chart|illustration|art|portrait)|"
    r"make\s+(?:an?\s+|me\s+(?:the\s+|an?\s+)?)?(?:picture|image|art|portrait)|"
    r"render\s+(?:an?\s+|me\s+(?:the\s+|an?\s+)?)?(?:image|art|portrait)|"
    r"(?:ghibli|gibili|anime|cartoon|cyberpunk|sketch|portrait|watercolor)\s+(?:art|style|version|picture|image|drawing))\b",
    re.IGNORECASE,
)

_WEB_SEARCH_RE = re.compile(
    r"\b(?:search\s+(?:the\s+)?(?:web|internet|online)|search\s+for|look\s+up\s+online|"
    r"find\s+(?:on\s+the\s+web|online|on\s+google|on\s+the\s+internet)|browse\s+(?:the\s+)?web|"
    r"google\s+this|web\s+search|source\s+links|fact\s+check|market\s+cap|quarterly\s+earnings|"
    r"real-time\s+traffic|current\s+traffic|traffic\s+status|official\s+benchmarks|frontier\s+ai|open\s+weights)\b",
    re.IGNORECASE,
)

_MCP_TOOL_RE = re.compile(
    r"\b(?:mcp\s+tool|call\s+mcp|invoke\s+mcp|use\s+mcp|mcp:)\b",
    re.IGNORECASE,
)

# Heuristic patterns for specialized skills
_CONTRACT_RISK_RE = re.compile(
    r"\b(?:review\s+(?:the\s+)?contract|assess\s+risk\s+in\s+(?:the\s+)?(?:contract|agreement|nda|msa|sow)|"
    r"redline\s+(?:the\s+)?(?:nda|msa|sow|contract|agreement)|contract\s+risk\s+analysis|"
    r"indemnity\s+clause\s+risk|liability\s+cap\s+risk|silent\s+clauses\s+in\s+contract)\b",
    re.IGNORECASE,
)

_CAUSAL_RE = re.compile(
    r"\b(?:why\s+did\s+.+\s+(?:drop|spike|fail|increase|decrease|change|crash|slow\s+down)|"
    r"root\s+cause\s+of|what\s+caused\s+.+|post-?mortem\s+for|5-?whys\s+analysis|causal\s+analysis\s+of)\b",
    re.IGNORECASE,
)

# Heuristic pattern for direct LLM general knowledge, math, coding, creative generation
_DIRECT_LLM_RE = re.compile(
    r"^(?:\s*(?:what\s+is|calculate|compute|solve)?\s*[\d\s\+\-\*\/\^\(\)\.\%]+[?\s]*$)|"
    r"(?:\b(?:write\s+(?:a\s+|me\s+)?(?:python|javascript|typescript|c\+\+|java|go|rust|sql|html|css|bash|code|function|script|class|program)|"
    r"how\s+to\s+(?:code|write\s+a\s+function|implement\s+in)|debug\s+(?:this\s+)?(?:code|error|traceback)|"
    r"translate\s+(?:this\s+|the\s+following\s+)?to\s+[a-zA-Z]+|"
    r"write\s+(?:an?\s+)?(?:poem|essay|story|song|haiku|joke|email\s+draft|cover\s+letter)|"
    r"explain\s+(?:how\s+photosynthesis\s+works|quantum\s+computing|relativity|gravity|dna)|"
    r"what\s+is\s+(?:the\s+capital\s+of|photosynthesis|gravity|a\s+monad|a\s+closure))\b)",
    re.IGNORECASE,
)


class RouterAgent:
    """Classifies user queries with heuristic pre-filtering and LLM fallback."""

    SYSTEM_PROMPT = """You are a query classification and routing expert for an enterprise RAG system.
Given a user query, classify both the routing strategy and query type.

Routing categories:
- llm_direct: general knowledge, coding assistance, math calculations, logical reasoning, creative writing, or definitions that do NOT require searching uploaded documents
- contract_risk: requests to review, audit, assess risk, or redline commercial contracts/NDAs/MSAs
- causal_reasoning: requests investigating root causes, "why" questions, anomalies, or post-mortems
- simple: single factual question about uploaded documents or specific company records answerable from one passage
- complex: requires synthesizing multiple uploaded documents, cross-source comparisons, or multi-step reasoning over indexed holdings
- multimodal: asks about a chart, diagram, image, or visual layout
- direct: greetings, small talk, meta questions about the assistant
- image_gen: requests to generate, create, or draw an image
- web_search: requests specifically asking to search the live web / internet
- mcp_tool: requests explicitly asking to execute or call an MCP tool / external integration

Query types:
- keyword: specific acronym, ID, or exact term lookup
- numerical: requires numbers, statistics, metrics, dates, or financial figures
- semantic: conceptual, explanatory, or policy questions
- multi_hop: cross-document synthesis or comparative reasoning

Return ONLY a JSON object: {"route": "<route>", "query_type": "<query_type>"}"""

    REFORMULATOR_PROMPT = """Given a conversation history and a user's follow-up question, rewrite the follow-up question into a complete, standalone search query that resolves all coreferences, pronouns (e.g. 'it', 'this', 'that', 'the one', 'todays one'), elliptical phrases (e.g. 'In tamilnadu', 'what about next week'), and implicit context from earlier turns.
If the query is already completely self-contained, return it unchanged.
Output ONLY the rewritten standalone query string with no commentary, formatting, or quotation marks."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm = llm_client or LLMClient(task="router")
        # Back-compat alias for existing code / tests
        self.nvidia = self.llm

    def _contextualize_query(self, query: str, history: List[dict]) -> str:
        """Resolve pronouns and conversational coreferences into a standalone search query."""
        if not history or not query.strip():
            return query

        hist_lines = []
        for msg in history[-4:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = str(msg.get("content") or "")[:250]
            if content.strip():
                hist_lines.append(f"{role}: {content}")

        if not hist_lines:
            return query

        hist_text = "\n".join(hist_lines)
        try:
            res = self.llm.generate_text(
                [
                    {"role": "system", "content": self.REFORMULATOR_PROMPT},
                    {
                        "role": "user",
                        "content": f"Conversation History:\n{hist_text}\n\nFollow-up question:\n{query}",
                    },
                ],
                max_tokens=60,
                temperature=0.0,
            )
            cleaned = res.content.strip().strip('"\'')
            if cleaned and len(cleaned) > 2:
                return cleaned
        except Exception as exc:
            logger.warning("Contextual query reformulation failed: %s; using original query", exc)
        return query

    def _match_heuristics(self, query: str) -> Optional[Tuple[str, str]]:
        """Check for instant pre-filter pattern matches."""
        q = query.strip()
        if not q:
            return "direct", "greeting"
        if _GREETING_RE.search(q):
            return "direct", "greeting"
        if _IMAGE_GEN_RE.search(q):
            return "image_gen", "image_gen"
        if _WEB_SEARCH_RE.search(q):
            return "web_search", "web_search"
        if _MCP_TOOL_RE.search(q):
            return "mcp_tool", "mcp_tool"
        if _CONTRACT_RISK_RE.search(q):
            return "contract_risk", "semantic"
        if _CAUSAL_RE.search(q):
            return "causal_reasoning", "multi_hop"
        if _DIRECT_LLM_RE.search(q):
            return "llm_direct", "semantic"
        return None

    def route(self, state: dict) -> dict:
        """Route user query with heuristic pre-filter and LLM classifier."""
        query = state.get("query", "")
        has_image = bool(state.get("user_image_b64"))
        history = state.get("chat_history", [])

        # Step 0: Contextual query reformulation for follow-up turns
        if history and not has_image and query.strip():
            standalone_query = self._contextualize_query(query, history)
            if standalone_query and standalone_query.lower() != query.lower():
                state["original_query"] = query
                state["query"] = standalone_query
                query = standalone_query
                logger.info("Contextualized query from '%s' to '%s'", state.get("original_query"), query)

        # If user attached an image, bypass LLM routing and route to multimodal
        if has_image:
            state["route"] = "multimodal"
            state["query_type"] = "multimodal"
            state["filters"] = self._extract_filters(query)
            state["thinking_note"] = "Image attached — routing to multimodal path."
            return state

        # Explicit web search mode check
        web_search_mode = state.get("web_search_mode", "auto")
        if web_search_mode == "always":
            state["route"] = "web_search"
            state["query_type"] = "web_search"
            state["filters"] = self._extract_filters(query)
            state["thinking_note"] = "Web Search mode forced by user — routing to live internet search & temporary vector indexing."
            return state

        # Step 1: Heuristic pre-filter check
        heuristic_match = self._match_heuristics(query)
        if heuristic_match is not None:
            route, query_type = heuristic_match
            if web_search_mode == "off" and route == "web_search":
                route, query_type = "simple", "semantic"
            state["route"] = route
            state["query_type"] = query_type
            state["filters"] = self._extract_filters(query)
            dept_note = f" Detected dept filter: {state['filters']['dept']}." if state["filters"] else ""
            state["thinking_note"] = f"Heuristic pre-filter: routed to '{route}' ({query_type}).{dept_note}"
            return state

        # Step 2: LLM Classification for ambiguous queries
        route = "simple"
        query_type = "semantic"

        try:
            response = self.nvidia.generate_text([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ])
            content = response.content.strip()

            if "```" in content:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1).strip()

            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    route = parsed.get("route", "").strip().lower()
                    query_type = parsed.get("query_type", "").strip().lower()
            except Exception:
                # Handle single-word classification fallback
                clean_word = content.strip().lower().strip('"\'')
                if clean_word in ("simple", "complex", "multimodal", "direct", "llm_direct", "image_gen", "web_search", "mcp_tool", "contract_risk", "causal_reasoning"):
                    route = clean_word
        except Exception as exc:
            logger.warning("Router LLM call failed: %s; defaulting to simple", exc)
            route = "simple"

        # Validate against allowed routes
        allowed_routes = (
            "simple",
            "complex",
            "multimodal",
            "direct",
            "llm_direct",
            "image_gen",
            "web_search",
            "mcp_tool",
            "contract_risk",
            "causal_reasoning",
        )
        if route not in allowed_routes:
            route = "simple"

        allowed_query_types = (
            "keyword",
            "numerical",
            "semantic",
            "multi_hop",
            "greeting",
            "image_gen",
            "web_search",
            "multimodal",
            "mcp_tool",
        )
        if query_type not in allowed_query_types:
            query_type = "semantic"

        state["route"] = route
        state["query_type"] = query_type
        state["filters"] = self._extract_filters(query)
        dept_note = f" Detected dept filter: {state['filters']['dept']}." if state["filters"] else ""
        state["thinking_note"] = f"Classified as '{route}' ({query_type}).{dept_note}"
        return state

    def _extract_filters(self, query: str) -> dict:
        """Heuristic to detect department mentions and construct Qdrant filter."""
        filters = {}
        dept_keywords = {
            "hr": "HR",
            "finance": "Finance",
            "policy": "Policy",
            "legal": "Legal",
        }
        for kw, dept in dept_keywords.items():
            if kw in query.lower():
                filters["dept"] = dept
        return filters
