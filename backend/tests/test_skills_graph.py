"""Unit tests for CRAG graph skill executor and routing."""
from unittest.mock import MagicMock
import pytest

from app.graph.crag_graph import build_crag_graph
from app.skills.skill_registry import Skill, SkillRegistry


class MockWebSkill(Skill):
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Mock web search"

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "web_search"

    def execute(self, state: dict) -> dict:
        state["retrieved_docs"] = [{"text_repr": "Web results found", "source": "web"}]
        state["web_results"] = [{"title": "Web Title", "url": "https://example.com"}]
        state["is_sufficient"] = True
        return state


class MockImageSkill(Skill):
    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return "Mock image gen"

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "image_gen"

    def execute(self, state: dict) -> dict:
        state["image_result"] = {"image_b64": "mock_b64_image", "prompt": state.get("query", "")}
        state["stream"] = None
        return state


def test_crag_graph_web_search_routing():
    router = MagicMock()
    router.route.side_effect = lambda s: {**s, "route": "web_search"}

    retriever = MagicMock()
    grader = MagicMock()
    rewriter = MagicMock()

    generator = MagicMock()
    generator.generate.side_effect = lambda s: {**s, "stream": ["Final answer with web info"]}

    registry = SkillRegistry()
    registry.register(MockWebSkill())

    graph = build_crag_graph(
        router=router,
        retriever=retriever,
        grader=grader,
        rewriter=rewriter,
        generator=generator,
        skill_registry=registry,
    )

    initial_state = {"query": "Find latest AI news", "route": None}
    res = graph.invoke(initial_state)

    assert res.get("route") == "web_search"
    assert "web_results" in res
    assert res.get("stream") == ["Final answer with web info"]
    # Retriever should not have been called for web_search route
    retriever.retrieve.assert_not_called()
    generator.generate.assert_called_once()


def test_crag_graph_image_gen_routing():
    router = MagicMock()
    router.route.side_effect = lambda s: {**s, "route": "image_gen"}

    retriever = MagicMock()
    grader = MagicMock()
    rewriter = MagicMock()
    generator = MagicMock()

    registry = SkillRegistry()
    registry.register(MockImageSkill())

    graph = build_crag_graph(
        router=router,
        retriever=retriever,
        grader=grader,
        rewriter=rewriter,
        generator=generator,
        skill_registry=registry,
    )

    initial_state = {"query": "Draw a sunset over the ocean", "route": None}
    res = graph.invoke(initial_state)

    assert res.get("route") == "image_gen"
    assert "image_result" in res
    assert res["image_result"]["image_b64"] == "mock_b64_image"
    # Neither retriever nor generator should be called for image_gen
    retriever.retrieve.assert_not_called()
    generator.generate.assert_not_called()
