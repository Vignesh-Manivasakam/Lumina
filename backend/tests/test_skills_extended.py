"""Unit tests for Dynamic Markdown Skill Registry and Extended Skills API."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.skills import (
    DynamicMarkdownSkill,
    ImageGenSkill,
    MCPToolSkill,
    SkillRegistry,
    WebSearchSkill,
    default_skill_registry,
    default_markdown_skill_loader,
)


class TestSkillRegistryCategorization:
    def test_all_skills_have_categories(self):
        skills = default_skill_registry.list_skills()
        assert len(skills) >= 10
        for skill in skills:
            assert isinstance(skill.category, str)
            assert isinstance(skill.tags, list)
            assert isinstance(skill.description, str)

    def test_list_categories_returns_sorted_unique_list(self):
        cats = default_skill_registry.list_categories()
        assert "reasoning" in cats
        assert "legal" in cats
        assert "analysis" in cats
        assert "financial" in cats
        assert "coding" in cats
        assert "data" in cats
        assert "briefing" in cats
        assert "creative" in cats

    def test_get_skills_by_category(self):
        legal_skills = default_skill_registry.get_skills_by_category("legal")
        assert any(s.name == "contract-risk-analyzer" for s in legal_skills)

        causal_skills = default_skill_registry.get_skills_by_category("analysis")
        assert any(s.name == "causal-reasoning" for s in causal_skills)

        finance_skills = default_skill_registry.get_skills_by_category("financial")
        assert any(s.name == "financial-auditor" for s in finance_skills)

    def test_manifest_serialization(self):
        manifest = default_skill_registry.to_manifest()
        assert isinstance(manifest, list)
        assert len(manifest) >= 10
        for item in manifest:
            assert "name" in item
            assert "category" in item
            assert "tags" in item
            assert "description" in item
            assert "parameters_schema" in item


class TestExtendedSkillsExecution:
    def test_dynamic_markdown_skill_execution(self):
        md_skill = default_markdown_skill_loader.get_skill("contract-risk-analyzer")
        assert md_skill is not None

        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content="## Executive Summary\nHigh liability exposure due to uncapped direct indemnity."
        )
        dyn_skill = DynamicMarkdownSkill(md_skill, llm_client=mock_llm)
        state = {
            "query": "Review the liability and indemnification clauses in the vendor MSA",
            "route": "contract-risk-analyzer",
            "_direct_execution": True,
        }
        assert dyn_skill.can_handle(state) is True
        res = dyn_skill.execute(state)
        assert res["is_sufficient"] is True
        assert len(res["retrieved_docs"]) == 1
        assert "Contract Risk & Compliance Auditor" in res["retrieved_docs"][0]["title"]

    def test_causal_reasoning_execution(self):
        md_skill = default_markdown_skill_loader.get_skill("causal-reasoning")
        assert md_skill is not None

        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content="## Executive Finding\nLatency spike was caused by deployment degradation."
        )
        dyn_skill = DynamicMarkdownSkill(md_skill, llm_client=mock_llm)
        state = {
            "query": "Why did conversion drop 15% in EU after release v2.4?",
            "route": "causal-reasoning",
            "_direct_execution": True,
        }
        assert dyn_skill.can_handle(state) is True
        res = dyn_skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Deep Causal & Root Cause Diagnostician" in res["retrieved_docs"][0]["title"]


class TestSkillsAPIEndpoints:
    def test_get_skills_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 10

    def test_get_skills_by_category_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills?category=legal")
        assert res.status_code == 200
        data = res.json()
        assert all(item["category"] == "legal" for item in data)

    def test_get_categories_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills/categories")
        assert res.status_code == 200
        cats = res.json()["categories"]
        assert "legal" in cats
        assert "analysis" in cats
        assert "financial" in cats
