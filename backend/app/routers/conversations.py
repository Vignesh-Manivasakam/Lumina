"""Conversations management endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.supabase_client import SupabaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])
supabase_service = SupabaseService()


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None
    metadata: Optional[dict] = None


@router.get("")
async def list_conversations(
    http_request: Request,
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List conversations for the current session or workspace."""
    try:
        trusted_session = getattr(http_request.state, "session_id", None)
        effective_session = session_id or trusted_session
        return supabase_service.list_conversations(session_id=effective_session, limit=limit)
    except Exception as exc:
        logger.exception("Failed to list conversations: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("")
async def create_conversation(data: ConversationCreate, http_request: Request):
    """Create a new conversation record."""
    try:
        trusted_session = getattr(http_request.state, "session_id", None)
        effective_session = data.session_id or trusted_session
        return supabase_service.create_conversation(
            title=data.title or "New Conversation",
            session_id=effective_session,
            metadata=data.metadata,
        )
    except Exception as exc:
        logger.exception("Failed to create conversation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Retrieve details of a specific conversation."""
    try:
        conv = supabase_service.get_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, data: ConversationUpdate):
    """Update title, archived status, or metadata of a conversation."""
    try:
        updated = supabase_service.update_conversation(
            conversation_id=conversation_id,
            title=data.title,
            archived=data.archived,
            metadata=data.metadata,
        )
        return updated
    except Exception as exc:
        logger.exception("Failed to update conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
