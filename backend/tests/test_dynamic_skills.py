"""Unit tests for the Dynamic Markdown Skill System & Zero/Micro-Token Hybrid Skill Router."""
import pytest
from app.skills.markdown_loader import MarkdownSkillLoader, parse_markdown_skill
from app.skills.skill_router import SkillRouter
from app.skills.skill_registry import SkillRegistry, DynamicMarkdownSkill, default_skill_registry


def test_parse_markdown_skill():
    sample_md = """---
name: custom-audit
category: legal
title: "Custom Compliance Auditor"
description: "Audits GDPR compliance"
triggers:
  - "gdpr audit"
  - "privacy policy"
tags: [gdpr, privacy, compliance]
confidence_threshold: 0.70
---
# Custom Protocol
Check all data transfer mechanisms."""

    skill = parse_markdown_skill(sample_md, session_id="test-session-123")
    assert skill is not None
    assert skill.name == "custom-audit"
    assert skill.category == "legal"
    assert skill.title == "Custom Compliance Auditor"
    assert skill.description == "Audits GDPR compliance"
    assert "gdpr audit" in skill.triggers
    assert "privacy" in skill.tags
    assert skill.confidence_threshold == 0.70
    assert skill.session_id == "test-session-123"
    assert "Check all data transfer mechanisms." in skill.prompt


def test_global_skills_loading():
    loader = MarkdownSkillLoader()
    skills = loader.global_skills

    # Verify key curated skills are present
    assert "sonnet-reasoning" in skills
    assert "opus-reasoning" in skills
    assert "fable-reasoning" in skills
    assert "contract-risk-analyzer" in skills
    assert "causal-reasoning" in skills
    assert "financial-auditor" in skills
    assert "code-architect" in skills
    assert "structured-extraction" in skills
    assert "executive-briefing" in skills
    assert "prompt-architect" in skills

    assert len(skills) >= 10


def test_session_skill_isolation():
    loader = MarkdownSkillLoader()

    custom_md_a = """---
name: secret-alpha
category: internal
title: "Project Alpha Auditor"
description: "Confidential roadmap checks"
triggers:
  - "alpha roadmap"
---
# Alpha Protocol"""

    custom_md_b = """---
name: secret-beta
category: internal
title: "Project Beta Auditor"
description: "Confidential finance checks"
triggers:
  - "beta finance"
---
# Beta Protocol"""

    # Register for Session A and Session B
    loader.register_custom_skill(session_id="session-user-A", markdown_content=custom_md_a)
    loader.register_custom_skill(session_id="session-user-B", markdown_content=custom_md_b)

    # Session A should see global skills + secret-alpha, but NOT secret-beta
    skills_a = {s.name: s for s in loader.get_accessible_skills(session_id="session-user-A")}
    assert "sonnet-reasoning" in skills_a
    assert "secret-alpha" in skills_a
    assert "secret-beta" not in skills_a

    # Session B should see global skills + secret-beta, but NOT secret-alpha
    skills_b = {s.name: s for s in loader.get_accessible_skills(session_id="session-user-B")}
    assert "sonnet-reasoning" in skills_b
    assert "secret-beta" in skills_b
    assert "secret-alpha" not in skills_b

    # Anonymous session (no session_id) should see only global skills
    skills_anon = {s.name: s for s in loader.get_accessible_skills(session_id=None)}
    assert "secret-alpha" not in skills_anon
    assert "secret-beta" not in skills_anon

    # Deletion test
    assert loader.delete_custom_skill("session-user-A", "secret-alpha") is True
    assert loader.get_skill("secret-alpha", session_id="session-user-A") is None


def test_skill_router_tier1_triggers():
    router = SkillRouter()

    # 1. Contract risk query
    skill, tier = router.route_skill("Please review the contract and check the indemnity clause.")
    assert skill.name == "contract-risk-analyzer"
    assert tier == "tier1"

    # 2. Causal reasoning query
    skill, tier = router.route_skill("Why did the production database crash yesterday?")
    assert skill.name == "causal-reasoning"
    assert tier == "tier1"

    # 3. Financial audit query
    skill, tier = router.route_skill("Can you analyze our SaaS balance sheet and ARR?")
    assert skill.name == "financial-auditor"
    assert tier == "tier1"

    # 4. Code architecture query
    skill, tier = router.route_skill("Review code architecture for security vulnerability.")
    assert skill.name == "code-architect"
    assert tier == "tier1"


def test_skill_router_tier3_ladder():
    router = SkillRouter()

    # Generic short query with no domain triggers -> defaults to Sonnet practical mode
    skill, tier = router.route_skill("What is the capital of France?")
    assert skill.name == "sonnet-reasoning"
    assert tier == "tier3"

    # Generic long analytical query with comparative trade-off keyword -> Opus deliberate mode
    skill, tier = router.route_skill("I need an in-depth evaluation of database trade-offs for very high throughput event ingestion workloads across multi-region clusters.")
    assert skill.name == "opus-reasoning"
    assert tier in ("tier1", "tier2", "tier3")

    # Explicit Fable trigger query
    skill, tier = router.route_skill("Give me an intuitive mental model to understand quantum computing through analogy.")
    assert skill.name == "fable-reasoning"
    assert tier in ("tier1", "tier2", "tier3")


def test_skill_registry_manifest():
    manifest = default_skill_registry.to_manifest()
    assert len(manifest) >= 10
    names = [s["name"] for s in manifest]
    assert "contract-risk-analyzer" in names
    assert "web_search" in names
    assert "image_gen" in names
