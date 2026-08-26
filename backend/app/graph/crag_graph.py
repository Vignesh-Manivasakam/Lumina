from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.generator import GeneratorAgent
from app.agents.grader import GraderAgent
from app.agents.retriever import RetrieverAgent
from app.agents.rewriter import RewriterAgent
from app.agents.router import RouterAgent
from app.skills.skill_registry import SkillRegistry, default_skill_registry

logger = logging.getLogger(__name__)


class RAGState(TypedDict, total=False):
    query: str
    user_image_b64: Optional[str]
    route: Optional[str]
    query_type: Optional[str]
    filters: dict
    rewritten_query: Optional[str]
    sub_queries: List[str]
    retrieved_docs: List[dict]
    retrieved_children: List[dict]
    relevant_docs: List[dict]
    is_sufficient: bool
    retrieval_count: int
    chat_history: List[dict]
    stream: Optional[Any]
    source_docs: List[dict]
    # Dynamic Markdown & Tool Skills additions:
    active_skill: Optional[str]
    active_skill_title: Optional[str]
    system_prompt: Optional[str]
    image_result: Optional[dict]
    web_results: Optional[List[dict]]
    tool_result: Optional[dict]
    # Session & Observability additions:
    session_id: Optional[str]
    use_parent_resolution: bool
    status_emitter: Optional[Callable[[str, str, Optional[str]], None]]
    thinking_emitter: Optional[Callable[[str, str], None]]


# Ordered so each agent/node gets a deterministic step index in the trace.
AGENT_ORDER = ("router", "skill_executor", "retriever", "grader", "rewriter", "generator")


def _wrap_with_status(agent_name: str, step: int, fn):
    """Wrap an agent or node method so it emits ``agent_status`` events before/after."""

    def wrapped(state: dict) -> dict:
        emitter = state.get("status_emitter")
        thinker = state.get("thinking_emitter")
        try:
            if emitter:
                emitter(agent_name, "active", f"{agent_name} started")
            result = fn(state)
            if emitter:
                emitter(agent_name, "complete", f"{agent_name} finished")
            if thinker:
                note = (result or {}).get("thinking_note") if isinstance(result, dict) else None
                if not note and isinstance(result, dict):
                    note = (state.get("thinking") or {}).get(agent_name)
                if note:
                    thinker(agent_name, note)
            return result
        except Exception as exc:
            if emitter:
                emitter(agent_name, "skipped", f"{agent_name} failed: {exc}")
            raise

    return wrapped


def build_crag_graph(
    router: RouterAgent,
    retriever: RetrieverAgent,
    grader: GraderAgent,
    rewriter: RewriterAgent,
    generator: GeneratorAgent,
    skill_registry: Optional[SkillRegistry] = None,
):
    registry = skill_registry or default_skill_registry

    def execute_skill(state: dict) -> dict:
        return registry.execute(state)

    graph = StateGraph(RAGState)

    graph.add_node("router", _wrap_with_status("router", 0, router.route))
    graph.add_node("skill_executor", _wrap_with_status("skill_executor", 1, execute_skill))
    graph.add_node("retriever", _wrap_with_status("retriever", 2, retriever.retrieve))
    graph.add_node("grader", _wrap_with_status("grader", 3, grader.grade))
    graph.add_node("rewriter", _wrap_with_status("rewriter", 4, rewriter.rewrite))
    graph.add_node("generator", _wrap_with_status("generator", 5, generator.generate))

    graph.set_entry_point("router")

    def route_decision(state: RAGState) -> str:
        route = state.get("route")
        # Tool skill routes that require execution in skill_executor node
        if route in ("web_search", "image_gen", "mcp_tool"):
            return "skill_executor"
        if route in ("direct", "llm_direct"):
            return "generator"
        return "retriever"

    def skill_decision(state: RAGState) -> str:
        route = state.get("route")
        if route == "image_gen":
            return "end"
        return "generator"

    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "skill_executor": "skill_executor",
            "retriever": "retriever",
            "generator": "generator",
        },
    )

    graph.add_conditional_edges(
        "skill_executor",
        skill_decision,
        {
            "generator": "generator",
            "end": END,
        },
    )

    graph.add_edge("retriever", "grader")

    graph.add_conditional_edges(
        "grader",
        grader.should_rewrite,
        {"rewrite": "rewriter", "generate": "generator"},
    )

    graph.add_edge("rewriter", "retriever")

    graph.add_edge("generator", END)

    return graph.compile()
