"""Unit tests for Smart Routing and LLM Direct shortcut."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.agents.router import RouterAgent
from app.graph.crag_graph import build_crag_graph


class TestSmartRouter:
    def test_math_calculation_routes_to_llm_direct(self):
        router = RouterAgent()
        state = {"query": "What is 2+2?", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "llm_direct"

    def test_coding_query_routes_to_llm_direct(self):
        router = RouterAgent()
        state = {"query": "Write a python function to reverse a string", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "llm_direct"

    def test_translation_query_routes_to_llm_direct(self):
        router = RouterAgent()
        state = {"query": "Translate hello world to Spanish", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "llm_direct"

    def test_creative_writing_routes_to_llm_direct(self):
        router = RouterAgent()
        state = {"query": "Write a poem about the sunrise", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "llm_direct"

    def test_general_explanation_routes_to_llm_direct(self):
        router = RouterAgent()
        state = {"query": "Explain how photosynthesis works", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "llm_direct"

    def test_image_gen_still_routes_correctly(self):
        router = RouterAgent()
        state = {"query": "Generate an image of a futuristic neon city", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "image_gen"

    def test_web_search_still_routes_correctly(self):
        router = RouterAgent()
        state = {"query": "Search the web for latest AI news today", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "web_search"

    def test_greeting_still_routes_to_direct(self):
        router = RouterAgent()
        state = {"query": "Hello there!", "chat_history": []}
        result = router.route(state)
        assert result["route"] == "direct"


class TestCRAGGraphRouting:
    def test_llm_direct_bypasses_retriever_and_grader(self):
        # Mock agents
        mock_router = MagicMock()
        mock_router.route.side_effect = lambda s: {**s, "route": "llm_direct"}

        mock_retriever = MagicMock()
        mock_grader = MagicMock()
        mock_rewriter = MagicMock()

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = lambda s: {**s, "stream": "Direct Response"}

        graph = build_crag_graph(
            router=mock_router,
            retriever=mock_retriever,
            grader=mock_grader,
            rewriter=mock_rewriter,
            generator=mock_generator,
        )

        state = {"query": "What is 2+2?"}
        result = graph.invoke(state)

        # Router and Generator must have run
        mock_router.route.assert_called_once()
        mock_generator.generate.assert_called_once()

        # Retriever and Grader must NOT have run (bypassed!)
        mock_retriever.retrieve.assert_not_called()
        mock_grader.grade.assert_not_called()
        mock_rewriter.rewrite.assert_not_called()
