"""Unit and integration tests for Skills system (WebSearch, ImageGen, MCPTool, SkillRegistry)."""
from unittest.mock import MagicMock, patch
import pytest

from app.skills.image_gen_skill import ImageGenSkill
from app.skills.mcp_tool_skill import MCPToolSkill
from app.skills.skill_registry import Skill, SkillRegistry
from app.skills.web_search_skill import WebSearchSkill


class DummySkill(Skill):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A dummy skill for testing"

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "dummy"

    def execute(self, state: dict) -> dict:
        state["dummy_executed"] = True
        return state


class TestSkillRegistry:
    def test_registry_registration_and_execution(self):
        registry = SkillRegistry()
        assert len(registry.list_skills()) == 0

        skill = DummySkill()
        registry.register(skill)

        assert len(registry.list_skills()) == 1
        assert registry.get_skill("dummy") is skill
        assert registry.get_skill("nonexistent") is None

        # Execute registered skill
        state = {"route": "dummy"}
        res = registry.execute(state)
        assert res.get("dummy_executed") is True

    def test_registry_invalid_type_raises_error(self):
        registry = SkillRegistry()
        with pytest.raises(TypeError):
            registry.register("not_a_skill")  # type: ignore

    def test_registry_unhandled_route_returns_unchanged_state(self):
        registry = SkillRegistry()
        registry.register(DummySkill())
        state = {"route": "unregistered_route", "query": "hello"}
        res = registry.execute(state)
        assert res == state


class TestWebSearchSkill:
    def test_web_search_graceful_no_key(self):
        skill = WebSearchSkill(api_key="")
        state = {"query": "Latest breakthroughs in AI", "route": "web_search"}
        res = skill.execute(state)

        assert "retrieved_docs" in res
        assert len(res["retrieved_docs"]) > 0
        assert "not configured" in res["retrieved_docs"][0]["text_repr"]
        assert res.get("is_sufficient") is True

    def test_web_search_with_mock_tavily_client(self):
        skill = WebSearchSkill(api_key="mock-tavily-key")
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Quantum AI 2026",
                    "url": "https://example.com/quantum",
                    "content": "Quantum processors achieved state-of-the-art benchmarks.",
                    "score": 0.98,
                }
            ]
        }
        skill._client = mock_client

        state = {"query": "Quantum AI progress", "route": "web_search"}
        res = skill.execute(state)

        assert len(res["retrieved_docs"]) == 1
        doc = res["retrieved_docs"][0]
        assert "Quantum AI 2026" in doc["text_repr"]
        assert doc["url"] == "https://example.com/quantum"
        assert len(res["web_results"]) == 1
        assert res["is_sufficient"] is True

    def test_web_search_empty_results(self):
        skill = WebSearchSkill(api_key="mock-key")
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        skill._client = mock_client

        state = {"query": "Obscure non-existent topic", "route": "web_search"}
        res = skill.execute(state)

        assert len(res["retrieved_docs"]) == 1
        assert "No web search results found" in res["retrieved_docs"][0]["text_repr"]

    def test_web_search_exception_handled(self):
        skill = WebSearchSkill(api_key="mock-key")
        mock_client = MagicMock()
        mock_client.search.side_effect = RuntimeError("Network timeout connecting to search provider")
        skill._client = mock_client

        state = {"query": "Failing query", "route": "web_search"}
        res = skill.execute(state)

        assert len(res["retrieved_docs"]) == 1
        assert "failed" in res["retrieved_docs"][0]["text_repr"].lower()


class TestImageGenSkill:
    def test_image_gen_no_key_fallback(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content="Refined prompt: a futuristic metropolis")
        skill = ImageGenSkill(api_key="", llm_client=mock_llm)

        with patch.object(skill, "_generate_fallback", return_value="mock_fallback_b64"):
            state = {"query": "Draw a futuristic metropolis", "route": "image_gen"}
            res = skill.execute(state)

            assert "image_result" in res
            assert res["image_result"]["image_b64"] == "mock_fallback_b64"
            assert res["stream"] is None

    def test_image_gen_prompt_refinement_and_generation(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content="A stunning panoramic sunset over futuristic glass skyscrapers, cinematic lighting, 8k"
        )

        skill = ImageGenSkill(api_key="mock-nvidia-key", llm_client=mock_llm)
        with patch.object(skill, "_generate_nvidia_nim", return_value="mock_nvidia_b64"):
            state = {"query": "Draw skyscrapers at sunset", "route": "image_gen"}
            res = skill.execute(state)

            assert "image_result" in res
            assert res["image_result"]["image_b64"] == "mock_nvidia_b64"
            assert res["image_result"]["refined_prompt"] == "A stunning panoramic sunset over futuristic glass skyscrapers, cinematic lighting, 8k"
            assert res["stream"] is None

    def test_image_gen_api_exception_handled(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content="Prompt text")
        skill = ImageGenSkill(api_key="mock-key", llm_client=mock_llm)

        with patch.object(skill, "_generate_nvidia_nim", return_value=None), \
             patch.object(skill, "_generate_fallback", return_value=None):
            state = {"query": "Draw an abstract sphere", "route": "image_gen"}
            res = skill.execute(state)

            assert "image_result" in res
            assert "error" in res["image_result"]
            assert res["image_result"]["image_b64"] == ""


class TestMCPToolSkill:
    def test_mcp_tool_skill_no_connections(self):
        mock_mcp_client = MagicMock()
        mock_mcp_client.list_connections.return_value = []
        skill = MCPToolSkill(mcp_client=mock_mcp_client)

        state = {"query": "Look up stock ticker for Lumina", "route": "mcp_tool"}
        res = skill.execute(state)

        assert "tool_result" in res
        assert res["tool_result"]["success"] is False
        assert len(res["retrieved_docs"]) > 0
        assert "No MCP server connections" in res["retrieved_docs"][0]["text_repr"]

    def test_mcp_tool_skill_invocation(self):
        mock_mcp_client = MagicMock()
        mock_mcp_client.list_connections.return_value = [
            {
                "name": "weather_service",
                "tools": [
                    {
                        "name": "get_current_weather",
                        "description": "Fetch current weather for location",
                        "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
                    }
                ],
            }
        ]
        mock_mcp_client.invoke_tool.return_value = {
            "success": True,
            "content": "Sunny, 22°C in San Francisco",
        }

        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content='{"server_name": "weather_service", "tool_name": "get_current_weather", "arguments": {"city": "San Francisco"}}'
        )

        skill = MCPToolSkill(mcp_client=mock_mcp_client, llm_client=mock_llm)

        state = {"query": "What is the weather in San Francisco?", "route": "mcp_tool"}
        res = skill.execute(state)

        assert res["tool_result"]["success"] is True
        assert "Sunny, 22°C" in res["retrieved_docs"][0]["text_repr"]
        assert res["is_sufficient"] is True
