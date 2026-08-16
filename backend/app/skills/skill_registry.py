"""Skill base class and central registry for Lumina RAG skills."""
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

    @abc.abstractmethod
    def can_handle(self, state: dict) -> bool:
        """Return True if this skill is capable of handling the current state."""
        pass

    @abc.abstractmethod
    def execute(self, state: dict) -> dict:
        """Execute the skill on the current state and return the updated state."""
        pass


class SkillRegistry:
    """Registry maintaining available skills and dispatching requests."""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill instance."""
        if not isinstance(skill, Skill):
            raise TypeError(f"Expected Skill instance, got {type(skill).__name__}")
        self._skills[skill.name] = skill
        logger.info("Registered skill: '%s' (%s)", skill.name, skill.description)

    def get_skill(self, route: str) -> Optional[Skill]:
        """Retrieve a skill by its route/name."""
        return self._skills.get(route)

    def list_skills(self) -> List[Skill]:
        """Return a list of all registered skill instances."""
        return list(self._skills.values())

    def get_skill_for_state(self, state: dict) -> Optional[Skill]:
        """Find a skill matching the state route or can_handle condition."""
        route = state.get("route")
        if route and route in self._skills:
            return self._skills[route]
        for skill in self._skills.values():
            if skill.can_handle(state):
                return skill
        return None

    def execute(self, state: dict) -> dict:
        """Execute the matching skill for the given state."""
        route = state.get("route", "")
        skill = self.get_skill_for_state(state)
        if not skill:
            logger.warning("No skill found to handle route: '%s'", route)
            return state
        return skill.execute(state)


# Global default registry instance
default_skill_registry = SkillRegistry()

__all__ = ["Skill", "SkillRegistry", "default_skill_registry"]
