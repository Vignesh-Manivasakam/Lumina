"""Skill base class and central registry for Lumina RAG skills.

Supports categorization (reasoning, search, creative, coding, analysis, integration),
intent matching, progressive parameter metadata, and manifest exports for the UI.
"""
from __future__ import annotations

import abc
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Skill(abc.ABC):
    """Abstract base class for all specialized RAG skills."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for the skill (matches router route name)."""
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of the skill's capability."""
        pass

    @property
    def category(self) -> str:
        """Category grouping: 'search', 'reasoning', 'creative', 'coding', 'analysis', 'integration'."""
        return "general"

    @property
    def tags(self) -> List[str]:
        """Searchable tags and keywords associated with this skill."""
        return []

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON schema describing input parameters."""
        return {"type": "object", "properties": {}}

    @abc.abstractmethod
    def can_handle(self, state: dict) -> bool:
        """Return True if this skill is capable of handling the current state."""
        pass

    @abc.abstractmethod
    def execute(self, state: dict) -> dict:
        """Execute the skill on the current state and return the updated state."""
        pass

    def to_manifest(self) -> Dict[str, Any]:
        """Return a structured dictionary describing this skill for UI/API listing."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "parameters_schema": self.parameters_schema,
        }


class SkillRegistry:
    """Registry maintaining available skills, categorization, and intent dispatch."""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill instance."""
        if not isinstance(skill, Skill):
            raise TypeError(f"Expected Skill instance, got {type(skill).__name__}")
        self._skills[skill.name] = skill
        logger.info("Registered skill: '%s' [Category: %s] (%s)", skill.name, skill.category, skill.description)

    def _ensure_populated_if_default(self) -> None:
        """Auto-populate only the global default_skill_registry singleton when accessed."""
        if self is default_skill_registry and not self._skills:
            try:
                from app.skills.causal_reasoning_skill import DeepCausalReasoningSkill
                from app.skills.code_analysis_skill import CodeAnalysisSkill
                from app.skills.contract_risk_skill import ContractRiskAnalyzerSkill
                from app.skills.data_extraction_skill import DataExtractionSkill
                from app.skills.deep_reasoning_skill import DeepReasoningSkill
                from app.skills.image_gen_skill import ImageGenSkill
                from app.skills.mcp_tool_skill import MCPToolSkill
                from app.skills.summarization_skill import SummarizationSkill
                from app.skills.web_search_skill import WebSearchSkill

                for cls_ in (
                    WebSearchSkill,
                    ImageGenSkill,
                    MCPToolSkill,
                    DeepReasoningSkill,
                    CodeAnalysisSkill,
                    SummarizationSkill,
                    DataExtractionSkill,
                    ContractRiskAnalyzerSkill,
                    DeepCausalReasoningSkill,
                ):
                    inst = cls_()
                    if inst.name not in self._skills:
                        self._skills[inst.name] = inst
            except Exception as exc:
                logger.debug("Deferred default registry population: %s", exc)

    def get_skill(self, route: str) -> Optional[Skill]:
        """Retrieve a skill by its route/name."""
        self._ensure_populated_if_default()
        return self._skills.get(route)

    def list_skills(self) -> List[Skill]:
        """Return a list of all registered skill instances."""
        self._ensure_populated_if_default()
        return list(self._skills.values())

    def list_categories(self) -> List[str]:
        """Return a list of unique categories across all registered skills."""
        self._ensure_populated_if_default()
        cats = {skill.category for skill in self._skills.values()}
        return sorted(list(cats))

    def get_skills_by_category(self, category: str) -> List[Skill]:
        """Return skills matching the specified category."""
        self._ensure_populated_if_default()
        cat_lower = category.strip().lower()
        return [s for s in self._skills.values() if s.category.lower() == cat_lower]

    def to_manifest(self) -> List[Dict[str, Any]]:
        """Return serialized list of all skills with metadata."""
        self._ensure_populated_if_default()
        return [skill.to_manifest() for skill in self._skills.values()]

    def get_skill_for_state(self, state: dict) -> Optional[Skill]:
        """Find a skill matching the state route or can_handle condition."""
        self._ensure_populated_if_default()
        route = state.get("route")
        if route and route in self._skills:
            return self._skills[route]
        for skill in self._skills.values():
            if skill.can_handle(state):
                return skill
        return None

    def match_intent(self, query: str) -> Optional[Skill]:
        """Heuristic intent classification matching query against skill tags and descriptions."""
        self._ensure_populated_if_default()
        q_lower = query.lower()
        for skill in self._skills.values():
            for tag in skill.tags:
                if tag.lower() in q_lower:
                    return skill
        return None

    def execute(self, state: dict) -> dict:
        """Execute the matching skill for the given state."""
        self._ensure_populated_if_default()
        route = state.get("route", "")
        skill = self.get_skill_for_state(state)
        if not skill:
            logger.warning("No skill found to handle route: '%s'", route)
            return state
        return skill.execute(state)


# Global default registry instance
default_skill_registry = SkillRegistry()

__all__ = ["Skill", "SkillRegistry", "default_skill_registry"]
