"""Skill base class and central registry for Lumina RAG skills.

Supports dynamic Markdown skills (domain reasoning, legal, finance, coding, synthesis)
alongside executable Tool skills (live web search, image gen, MCP).
"""
from __future__ import annotations

import abc
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.markdown_loader import (
    MarkdownSkill,
    MarkdownSkillLoader,
    default_markdown_skill_loader,
)

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
        """Category grouping: 'reasoning', 'legal', 'analysis', 'financial', 'coding', 'data', 'search', 'creative'."""
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


class DynamicMarkdownSkill(Skill):
    """Executes a dynamic Markdown skill definition using its markdown prompt protocol."""

    def __init__(self, markdown_skill: MarkdownSkill, llm_client: Optional[LLMClient] = None) -> None:
        self.md_skill = markdown_skill
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return self.md_skill.name

    @property
    def description(self) -> str:
        return self.md_skill.description

    @property
    def category(self) -> str:
        return self.md_skill.category

    @property
    def tags(self) -> List[str]:
        return self.md_skill.tags

    @property
    def title(self) -> str:
        return self.md_skill.title

    @property
    def prompt(self) -> str:
        return self.md_skill.prompt

    def can_handle(self, state: dict) -> bool:
        route = state.get("route", "")
        active_skill = state.get("active_skill", "")
        return route == self.name or active_skill == self.name

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Applying specialized skill protocol: {self.title} [{self.category}]")

        state["active_skill"] = self.name
        state["system_prompt"] = self.prompt

        # For direct skill execution endpoint (without CRAG retrieval graph)
        if state.get("_direct_execution"):
            try:
                resp = self.llm.generate_text(
                    [
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": query},
                    ],
                    max_tokens=1600,
                    temperature=0.2,
                )
                chunk_id = f"{self.name}_{uuid.uuid4().hex[:8]}"
                doc = {
                    "chunk_id": chunk_id,
                    "id": chunk_id,
                    "modality": "text",
                    "text_repr": resp.content.strip(),
                    "title": self.title,
                    "score": 1.0,
                    "relevance_score": 1.0,
                    "source": self.name,
                }
                state["retrieved_docs"] = [doc]
                state["relevant_docs"] = [doc]
                state["source_docs"] = [doc]
                state["is_sufficient"] = True
            except Exception as exc:
                logger.error("Direct execution failed for skill %s: %s", self.name, exc)

        return state


class SkillRegistry:
    """Registry maintaining available skills, dynamic markdown skills, and intent dispatch."""

    def __init__(self, loader: Optional[MarkdownSkillLoader] = None, auto_populate: bool = False) -> None:
        self._skills: Dict[str, Skill] = {}
        self.loader = loader or default_markdown_skill_loader
        self._auto_populate = auto_populate
        if auto_populate:
            self._populate_skills()

    def register(self, skill: Skill) -> None:
        """Register a skill instance."""
        if not isinstance(skill, Skill):
            raise TypeError(f"Expected Skill instance, got {type(skill).__name__}")
        self._skills[skill.name] = skill
        logger.info("Registered skill: '%s' [Category: %s]", skill.name, skill.category)

    def _ensure_populated_if_default(self) -> None:
        if self._auto_populate or self is default_skill_registry:
            self._populate_skills()

    def _populate_skills(self) -> None:
        """Populate default tool skills and dynamic markdown skills."""
        # 1. Register Tool Skills
        try:
            from app.skills.image_gen_skill import ImageGenSkill
            from app.skills.mcp_tool_skill import MCPToolSkill
            from app.skills.web_search_skill import WebSearchSkill

            for cls_ in (WebSearchSkill, ImageGenSkill, MCPToolSkill):
                inst = cls_()
                if inst.name not in self._skills:
                    self._skills[inst.name] = inst
        except Exception as exc:
            logger.debug("Tool skills registration notice: %s", exc)

        # 2. Register Dynamic Markdown Skills from Loader
        try:
            for md_skill in self.loader.global_skills.values():
                if md_skill.name not in self._skills:
                    dyn = DynamicMarkdownSkill(md_skill)
                    self._skills[dyn.name] = dyn
        except Exception as exc:
            logger.debug("Markdown skills registration notice: %s", exc)

    def get_skill(self, route: str, session_id: Optional[str] = None) -> Optional[Skill]:
        """Retrieve a skill by its route/name, checking session custom skills if provided."""
        self._ensure_populated_if_default()
        if session_id:
            custom_md = self.loader.get_skill(route, session_id=session_id)
            if custom_md:
                return DynamicMarkdownSkill(custom_md)
        return self._skills.get(route)

    def list_skills(self, session_id: Optional[str] = None) -> List[Skill]:
        """Return a list of all registered skills + current session custom skills."""
        self._ensure_populated_if_default()
        skills = list(self._skills.values())
        if session_id and session_id in self.loader.session_skills:
            for custom_md in self.loader.session_skills[session_id].values():
                skills.append(DynamicMarkdownSkill(custom_md))
        return skills

    def list_categories(self, session_id: Optional[str] = None) -> List[str]:
        """Return a list of unique categories across accessible skills."""
        self._ensure_populated_if_default()
        skills = self.list_skills(session_id=session_id)
        return sorted(list({skill.category for skill in skills}))

    def get_skills_by_category(self, category: str, session_id: Optional[str] = None) -> List[Skill]:
        """Return skills matching the specified category."""
        self._ensure_populated_if_default()
        skills = self.list_skills(session_id=session_id)
        cat_lower = category.strip().lower()
        return [s for s in skills if s.category.lower() == cat_lower]

    def to_manifest(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return serialized list of all accessible skills with metadata."""
        self._ensure_populated_if_default()
        skills = self.list_skills(session_id=session_id)
        return [skill.to_manifest() for skill in skills]

    def get_skill_for_state(self, state: dict) -> Optional[Skill]:
        """Find a skill matching the state route or can_handle condition."""
        self._ensure_populated_if_default()
        session_id = state.get("session_id")
        route = state.get("route")
        if route:
            skill = self.get_skill(route, session_id=session_id)
            if skill:
                return skill
        for skill in self.list_skills(session_id=session_id):
            if skill.can_handle(state):
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


# Global default registry instance with auto_populate=True
default_skill_registry = SkillRegistry(auto_populate=True)

__all__ = ["Skill", "DynamicMarkdownSkill", "SkillRegistry", "default_skill_registry"]
