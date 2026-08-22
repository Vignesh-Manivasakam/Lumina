"""Skills API router exposing skill discovery, categories, and direct execution."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.skills import default_skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["Skills"])


class SkillExecuteRequest(BaseModel):
    query: str
    arguments: Optional[Dict[str, Any]] = None


@router.get("")
async def list_skills(category: Optional[str] = None):
    """List all registered agent skills, optionally filtered by category."""
    try:
        if category:
            skills = default_skill_registry.get_skills_by_category(category)
            return [s.to_manifest() for s in skills]
        return default_skill_registry.to_manifest()
    except Exception as exc:
        logger.exception("Failed to list skills: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/categories")
async def list_skill_categories():
    """List unique skill categories available in the registry."""
    try:
        return {"categories": default_skill_registry.list_categories()}
    except Exception as exc:
        logger.exception("Failed to list skill categories: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{skill_name}")
async def get_skill_details(skill_name: str):
    """Get metadata for a specific skill."""
    skill = default_skill_registry.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")
    return skill.to_manifest()


@router.post("/{skill_name}/execute")
async def execute_skill_direct(skill_name: str, payload: SkillExecuteRequest):
    """Directly test execution of a skill."""
    skill = default_skill_registry.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")

    state = {
        "query": payload.query,
        "route": skill_name,
        "arguments": payload.arguments or {},
        "retrieved_docs": [],
    }

    try:
        result_state = skill.execute(state)
        return {
            "skill": skill_name,
            "success": True,
            "result_docs": result_state.get("retrieved_docs", []),
            "web_results": result_state.get("web_results"),
            "image_result": result_state.get("image_result"),
            "tool_result": result_state.get("tool_result"),
        }
    except Exception as exc:
        logger.exception("Direct execution of skill %s failed: %s", skill_name, exc)
        raise HTTPException(status_code=500, detail=str(exc))
