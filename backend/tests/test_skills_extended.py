"""Unit tests for Categorized Skill Registry and Extended Skills."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.skills import (
    CodeAnalysisSkill,
    DataExtractionSkill,
    DeepReasoningSkill,
    ImageGenSkill,
    MCPToolSkill,
    SkillRegistry,
    SummarizationSkill,
    WebSearchSkill,
    default_skill_registry,
)


class TestSkillRegistryCategorization:
    def test_all_skills_have_categories(self):
        skills = default_skill_registry.list_skills()
        assert len(skills) >= 7
        for skill in skills:
            assert skill.category in ("search", "creative", "integration", "reasoning", "coding", "analysis", "general")
            assert isinstance(skill.tags, list)
            assert isinstance(skill.description, str)

    def test_list_categories_returns_sorted_unique_list(self):
        cats = default_skill_registry.list_categories()
        assert "search" in cats
        assert "creative" in cats
        assert "reasoning" in cats
        assert "coding" in cats
        assert "analysis" in cats

    def test_get_skills_by_category(self):
        analysis_skills = default_skill_registry.get_skills_by_category("analysis")
        names = [s.name for s in analysis_skills]
        assert "summarization" in names
        assert "data_extraction" in names

    def test_manifest_serialization(self):
        manifest = default_skill_registry.to_manifest()
        assert isinstance(manifest, list)
        assert len(manifest) >= 7
        for item in manifest:
            assert "name" in item
            assert "category" in item
            assert "tags" in item
            assert "description" in item
            assert "parameters_schema" in item


class TestExtendedSkillsExecution:
    def test_deep_reasoning_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content="1. Step one\n2. Step two verified")
        skill = DeepReasoningSkill(llm_client=mock_llm)
        state = {"query": "Prove that the square root of 2 is irrational"}
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert len(res["retrieved_docs"]) == 1
        assert "Deep Reasoning Breakdown" in res["retrieved_docs"][0]["text_repr"]

    def test_code_analysis_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content="No bugs found. Time complexity O(N).")
        skill = CodeAnalysisSkill(llm_client=mock_llm)
        state = {"query": "def reverse(s): return s[::-1]"}
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Code Review" in res["retrieved_docs"][0]["text_repr"]

    def test_summarization_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content="- Executive Summary: All systems green.")
        skill = SummarizationSkill(llm_client=mock_llm)
        state = {"query": "Quarterly earnings report summary"}
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Executive Briefing" in res["retrieved_docs"][0]["text_repr"]

    def test_data_extraction_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(content='{"entities": [{"name": "Acme", "revenue": "$10M"}]}')
        skill = DataExtractionSkill(llm_client=mock_llm)
        state = {"query": "Acme Corp reported $10M revenue in Q3"}
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Extracted Structured Schema" in res["retrieved_docs"][0]["text_repr"]


class TestSkillsAPIEndpoints:
    def test_get_skills_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 7

    def test_get_skills_by_category_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills?category=coding")
        assert res.status_code == 200
        data = res.json()
        assert all(item["category"] == "coding" for item in data)

    def test_get_categories_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills/categories")
        assert res.status_code == 200
        assert "categories" in res.json()
