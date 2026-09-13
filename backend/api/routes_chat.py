from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

from services.chat_agent import process_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatContext(BaseModel):
    model_config = {"extra": "ignore"}
    tile_id: Optional[str] = None
    change_id: Optional[str] = None
    cluster_id: Optional[str] = None

class ChatRequest(BaseModel):
    model_config = {"extra": "ignore"}
    message: str
    context: Optional[ChatContext] = None
    conversation_id: Optional[str] = None

class Citation(BaseModel):
    model_config = {"extra": "ignore"}
    type: str = "source"
    id: str
    field: Optional[str] = None

class AgentStep(BaseModel):
    model_config = {"extra": "ignore"}
    step_num: int
    thought: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    model_config = {"extra": "ignore"}
    response: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    steps: List[AgentStep] = Field(default_factory=list)
    available: bool = False
    fallback: bool = False
    latency_ms: Optional[float] = None
    intent: Optional[Dict[str, Any]] = None
    status: Optional[Dict[str, Any]] = None

AgentStep.model_rebuild()
ChatResponse.model_rebuild()

def _safe_citation(c: Any) -> Optional[Citation]:
    if not isinstance(c, dict):
        return None
    c_type = str(c.get("type") or "source")
    c_id = str(c.get("id") or "")
    if not c_id or c_id == "None":
        return None
    c_field = str(c.get("field")) if c.get("field") is not None else None
    return Citation(type=c_type, id=c_id, field=c_field)

def _to_json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    try:
        import json
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return str(obj)

@router.post("", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    
    try:
        context_dict = {}
        if payload.context:
            if hasattr(payload.context, "model_dump"):
                context_dict = payload.context.model_dump(exclude_none=True)
            elif hasattr(payload.context, "dict"):
                context_dict = payload.context.dict(exclude_none=True)
        
        result = process_chat(payload.message, context_dict, payload.conversation_id)
        
        raw_citations = result.get("citations", [])
        citations = []
        if isinstance(raw_citations, list):
            for c in raw_citations:
                sc = _safe_citation(c)
                if sc:
                    citations.append(sc)

        raw_steps = result.get("steps", [])
        steps = []
        if isinstance(raw_steps, list):
            for s in raw_steps:
                if isinstance(s, dict):
                    try:
                        safe_step = {
                            "step_num": int(s.get("step_num", 1)),
                            "thought": str(s.get("thought", "") or ""),
                            "tool_name": str(s.get("tool_name", "") or ""),
                            "tool_args": _to_json_safe(s.get("tool_args", {})),
                            "tool_result": _to_json_safe(s.get("tool_result", {})),
                        }
                        steps.append(AgentStep(**safe_step))
                    except Exception:
                        pass

        return ChatResponse(
            response=str(result.get("response") or "Terra is ready to analyze evidence."),
            citations=citations,
            steps=steps,
            available=bool(result.get("available")),
            fallback=bool(result.get("fallback", False)),
            latency_ms=float(result.get("latency_ms", 0.0)) if result.get("latency_ms") is not None else None,
            intent=_to_json_safe(result.get("intent")) if isinstance(result.get("intent"), dict) else None,
            status=_to_json_safe(result.get("status")) if isinstance(result.get("status"), dict) else None,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return ChatResponse(
            response=f"Terra encountered an issue processing the query. Grounded fallback is active.",
            citations=[],
            available=False,
            fallback=True,
            latency_ms=0.0,
            intent=None,
            status={"error": str(exc), "available": False},
        )

