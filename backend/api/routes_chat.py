from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, List

from services.chat_agent import process_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatContext(BaseModel):
    tile_id: Optional[str] = None
    change_id: Optional[str] = None
    cluster_id: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    context: Optional[ChatContext] = None
    conversation_id: Optional[str] = None

class Citation(BaseModel):
    type: str
    id: str
    field: Optional[str] = None

class ChatResponse(BaseModel):
    response: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    available: bool = False
    fallback: bool = False
    latency_ms: Optional[float] = None
    intent: Optional[Dict[str, object]] = None
    status: Optional[Dict[str, object]] = None

@router.post("", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    context_dict = payload.context.dict(exclude_none=True) if payload.context else {}
    if not context_dict:
        raise HTTPException(
            status_code=400,
            detail="Chat must be opened from a selected tile, change candidate, or cluster.",
        )
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    result = process_chat(payload.message, context_dict, payload.conversation_id)
    
    return ChatResponse(
        response=result.get("response"),
        citations=[Citation(**dict(c, id=str(c.get("id")))) for c in result.get("citations", [])],
        available=bool(result.get("available")),
        fallback=bool(result.get("fallback")),
        latency_ms=result.get("latency_ms"),
        intent=result.get("intent"),
        status=result.get("status"),
    )
