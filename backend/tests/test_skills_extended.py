"""Unit tests for Categorized Skill Registry and Extended Skills."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.skills import (
    CodeAnalysisSkill,
    ContractRiskAnalyzerSkill,
    DataExtractionSkill,
    DeepCausalReasoningSkill,
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
        assert len(skills) >= 9
        for skill in skills:
            assert skill.category in (
                "search",
                "creative",
                "integration",
                "reasoning",
                "coding",
                "analysis",
                "legal-compliance",
                "analytical-reasoning",
                "general",
            )
            assert isinstance(skill.tags, list)
            assert isinstance(skill.description, str)

    def test_list_categories_returns_sorted_unique_list(self):
        cats = default_skill_registry.list_categories()
        assert "search" in cats
        assert "creative" in cats
        assert "reasoning" in cats
        assert "coding" in cats
        assert "analysis" in cats
        assert "legal-compliance" in cats
        assert "analytical-reasoning" in cats

    def test_get_skills_by_category(self):
        analysis_skills = default_skill_registry.get_skills_by_category("analysis")
        names = [s.name for s in analysis_skills]
        assert "summarization" in names
        assert "data_extraction" in names

        legal_skills = default_skill_registry.get_skills_by_category("legal-compliance")
        assert any(s.name == "contract_risk" for s in legal_skills)

        causal_skills = default_skill_registry.get_skills_by_category("analytical-reasoning")
        assert any(s.name == "causal_reasoning" for s in causal_skills)

    def test_manifest_serialization(self):
        manifest = default_skill_registry.to_manifest()
        assert isinstance(manifest, list)
        assert len(manifest) >= 9
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

    def test_contract_risk_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content="## Executive Summary\nHigh liability exposure due to uncapped direct indemnity."
        )
        skill = ContractRiskAnalyzerSkill(llm_client=mock_llm)
        state = {"query": "Review the liability and indemnification clauses in the vendor MSA", "route": "contract_risk"}
        assert skill.can_handle(state) is True
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Contract Risk Assessment" in res["retrieved_docs"][0]["text_repr"]

    def test_causal_reasoning_skill(self):
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            content="## Executive Answer\nCheckout drop was caused by deployment latency degradation."
        )
        skill = DeepCausalReasoningSkill(llm_client=mock_llm)
        state = {"query": "Why did conversion drop 15% in EU after release v2.4?", "route": "causal_reasoning"}
        assert skill.can_handle(state) is True
        res = skill.execute(state)
        assert res["is_sufficient"] is True
        assert "Deep Causal Investigation" in res["retrieved_docs"][0]["text_repr"]


class TestSkillsAPIEndpoints:
    def test_get_skills_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 9

    def test_get_skills_by_category_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills?category=legal-compliance")
        assert res.status_code == 200
        data = res.json()
        assert all(item["category"] == "legal-compliance" for item in data)

    def test_get_categories_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/skills/categories")
        assert res.status_code == 200
        cats = res.json()["categories"]
        assert "legal-compliance" in cats
        assert "analytical-reasoning" in cats
