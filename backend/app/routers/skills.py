"""Skills API router exposing skill discovery, categories, session custom skills, and direct execution."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.skills import default_markdown_skill_loader, default_skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["Skills"])


class SkillExecuteRequest(BaseModel):
    query: str
    arguments: Optional[Dict[str, Any]] = None


class CustomSkillCreateRequest(BaseModel):
    content: str  # Markdown content with YAML frontmatter


@router.get("")
async def list_skills(request: Request, category: Optional[str] = None):
    """List all registered skills (global + current session custom skills)."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    try:
        if category:
            skills = default_skill_registry.get_skills_by_category(category, session_id=session_id)
            return [s.to_manifest() for s in skills]
        return default_skill_registry.to_manifest(session_id=session_id)
    except Exception as exc:
        logger.exception("Failed to list skills: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/categories")
async def list_skill_categories(request: Request):
    """List unique skill categories available in the registry for this session."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    try:
        return {"categories": default_skill_registry.list_categories(session_id=session_id)}
    except Exception as exc:
        logger.exception("Failed to list skill categories: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/custom")
async def create_custom_skill(request: Request, payload: CustomSkillCreateRequest):
    """Register a custom markdown skill scoped strictly to the current session."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    if not session_id:
        raise HTTPException(status_code=400, detail="A valid session_id is required to create a custom skill.")

    try:
        skill = default_markdown_skill_loader.register_custom_skill(
            session_id=session_id, markdown_content=payload.content
        )
        return {
            "success": True,
            "skill": skill.to_dict(),
            "message": f"Custom skill '{skill.name}' registered for session '{session_id}'.",
        }
    except ValueError as val_err:
        raise HTTPException(status_code=422, detail=str(val_err))
    except Exception as exc:
        logger.exception("Failed to register custom skill: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/custom/{skill_name}")
async def delete_custom_skill(request: Request, skill_name: str):
    """Delete a custom skill scoped to the current session."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    if not session_id:
        raise HTTPException(status_code=400, detail="A valid session_id is required.")

    deleted = default_markdown_skill_loader.delete_custom_skill(session_id=session_id, skill_name=skill_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found for this session.")

    return {"success": True, "message": f"Custom skill '{skill_name}' deleted."}


@router.get("/{skill_name}")
async def get_skill_details(request: Request, skill_name: str):
    """Get metadata for a specific skill."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    skill = default_skill_registry.get_skill(skill_name, session_id=session_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")
    return skill.to_manifest()


@router.post("/{skill_name}/execute")
async def execute_skill_direct(request: Request, skill_name: str, payload: SkillExecuteRequest):
    """Directly test execution of a skill."""
    session_id: Optional[str] = getattr(request.state, "session_id", None)
    skill = default_skill_registry.get_skill(skill_name, session_id=session_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")

    state = {
        "query": payload.query,
        "route": skill_name,
        "session_id": session_id,
        "arguments": payload.arguments or {},
        "retrieved_docs": [],
        "_direct_execution": True,
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
