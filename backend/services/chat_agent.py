"""Grounded, RAM-aware conversational orchestration for TerreX."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, TypedDict, Literal

try:
    import psutil
except ImportError:
    psutil = None

try:
    import requests
except ImportError:
    requests = None

from pydantic import BaseModel, Field

try:
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
    from langchain_core.tools import tool
    from langchain_ollama import ChatOllama
    from langgraph.graph import END, StateGraph
except ImportError:
    BaseMessage = None
    HumanMessage = None
    SystemMessage = None
    def tool(fn):
        return fn
    ChatOllama = None
    END = None
    StateGraph = None
from sqlalchemy import select

from db.database import get_session
from db.models import ChangeResult, Feedback, Scene, Tile
from services.search import semantic_text_search


SAFE_THRESHOLD_GB = float(os.getenv("CHAT_SAFE_THRESHOLD_GB", "1.5"))
IDLE_TIMEOUT_SECONDS = int(os.getenv("CHAT_IDLE_TIMEOUT_SECONDS", "120"))
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

_llm_client: Optional[ChatOllama] = None
_last_used_time = 0.0
_llm_lock = threading.Lock()
_conversation_history: Dict[str, List[Dict[str, str]]] = {}
_history_lock = threading.Lock()
MAX_HISTORY_TURNS = 6
_unload_monitor_started = False


def ram_available() -> bool:
    try:
        if psutil is None:
            return True
        return psutil.virtual_memory().available / (1024 ** 3) >= SAFE_THRESHOLD_GB
    except Exception:
        return True


def ollama_health() -> Dict[str, Any]:
    """Check the local Ollama daemon and configured model without external calls."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        available = CHAT_MODEL in names
        return {
            "reachable": True,
            "model_available": available,
            "model": CHAT_MODEL,
            "error": None if available else f"Model {CHAT_MODEL} is not installed in Ollama.",
        }
    except Exception as exc:
        return {
            "reachable": False,
            "model_available": False,
            "model": CHAT_MODEL,
            "error": str(exc),
        }


def chat_status() -> Dict[str, Any]:
    health = ollama_health()
    memory_ok = ram_available()
    return {
        **health,
        "ollama_reachable": health["reachable"],
        "ram_available": memory_ok,
        "available": bool(memory_ok and health["reachable"] and health["model_available"]),
        "safe_threshold_gb": SAFE_THRESHOLD_GB,
    }


def chat_available() -> bool:
    """Return whether RAM, Ollama, and the configured local model are ready."""
    return bool(chat_status()["available"])


def get_llm_client() -> Optional[ChatOllama]:
    """Construct the Ollama client only after the runtime RAM gate passes."""
    global _llm_client, _last_used_time
    if not ram_available():
        return None
    with _llm_lock:
        if _llm_client is None:
            _llm_client = ChatOllama(
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                model=CHAT_MODEL,
                temperature=0,
            )
        _last_used_time = time.time()
        return _llm_client


def maybe_unload_llm() -> bool:
    """Release the model from Ollama after the idle timeout."""
    global _llm_client
    with _llm_lock:
        if _llm_client is None or (time.time() - _last_used_time) <= IDLE_TIMEOUT_SECONDS:
            return False
        try:
            import requests
            requests.post(
                f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/generate",
                json={"model": CHAT_MODEL, "keep_alive": 0}, timeout=2,
            )
        except Exception:
            pass
        _llm_client = None
        return True


def start_idle_unload_monitor() -> None:
    """Start a lightweight daemon that releases an idle Ollama model."""
    global _unload_monitor_started
    if _unload_monitor_started:
        return
    _unload_monitor_started = True

    def monitor() -> None:
        while True:
            time.sleep(min(30, max(5, IDLE_TIMEOUT_SECONDS // 2)))
            maybe_unload_llm()

    threading.Thread(target=monitor, name="terrex-chat-idle-unload", daemon=True).start()


def _date(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def _tile_record(tile: Tile, scene: Optional[Scene] = None) -> Dict[str, Any]:
    return {
        "tile_id": tile.tile_id, "scene_id": tile.scene_id,
        "acquisition_date": _date(tile.acquisition_date),
        "sensor": tile.sensor or (scene.sensor if scene else None),
        "quality_score": tile.quality_score, "cloud_fraction": tile.cloud_fraction,
        "resolution_m": tile.resolution_m, "crs": tile.crs,
        "thumbnail_path": tile.thumbnail_path, "tile_path": tile.tile_path,
        "embedding_model": tile.embedding_model,
        "embedding_is_placeholder": bool(tile.embedding_is_placeholder),
        "processing_version": tile.processing_version,
        "provenance": {
            "source_filename": scene.source_filename if scene else None,
            "source_path": scene.source_path if scene else None,
            "scene_status": scene.status if scene else None,
            "scene_quality_score": scene.quality_score if scene else None,
            "ingested_at": _date(scene.ingested_at) if scene else None,
        },
    }


def _payload(data: Any = None, *, message: Optional[str] = None,
             citations: Optional[List[Dict[str, Any]]] = None,
             error: bool = False) -> Dict[str, Any]:
    return {"ok": not error, "data": data, "message": message, "citations": citations or []}


@tool
def search_archive(query_text: str = "", reference_tile_id: str = "", aoi: str = "", date_range: str = "", sensor: str = "") -> dict:
    """Search indexed imagery using the existing semantic search service."""
    if not query_text.strip():
        return _payload(message="A text query is required for archive search.")
    try:
        result = semantic_text_search(query=query_text, top_k=5, sensor=sensor or None)
        rows = result.get("results", [])
        return _payload({"query": query_text, "results": rows}, citations=[
            {"type": "tile", "id": row["tile_id"], "field": "final_score"} for row in rows
        ])
    except Exception:
        return _payload(message="Archive search failed.", error=True)


@tool
def get_change_result(change_id: str) -> dict:
    """Fetch a persisted change result and its two source tiles."""
    if not change_id:
        return _payload(message="A change_id is required.")
    try:
        with get_session() as session:
            change = session.get(ChangeResult, change_id)
            if not change:
                return _payload(message=f"No change data available for change_id {change_id}.")
            before = session.get(Tile, change.before_tile_id)
            after = session.get(Tile, change.after_tile_id)
            before_scene = session.get(Scene, before.scene_id) if before else None
            after_scene = session.get(Scene, after.scene_id) if after else None
            data = {
                "change_id": change.change_id, "change_score": change.change_score,
                "quality_score": change.quality_score, "confidence": change.confidence,
                "change_area_m2": change.change_area_m2, "reasons": change.reasons or [],
                "method": change.method, "is_placeholder_model": bool(change.is_placeholder_model),
                "created_at": _date(change.created_at),
                "before": _tile_record(before, before_scene) if before else None,
                "after": _tile_record(after, after_scene) if after else None,
            }
            return _payload(data, citations=[
                {"type": "change", "id": change.change_id, "field": "confidence"},
                {"type": "tile", "id": change.before_tile_id, "field": "acquisition_date"},
                {"type": "tile", "id": change.after_tile_id, "field": "acquisition_date"},
            ])
    except Exception:
        return _payload(message="Unable to read change data.", error=True)


@tool
def get_tile_metadata(tile_id: str) -> dict:
    """Fetch acquisition, sensor, quality, and provenance metadata for a tile."""
    if not tile_id:
        return _payload(message="A tile_id is required.")
    try:
        with get_session() as session:
            tile = session.get(Tile, tile_id)
            if not tile:
                return _payload(message=f"No metadata found for tile_id {tile_id}.")
            scene = session.get(Scene, tile.scene_id)
            return _payload(_tile_record(tile, scene), citations=[
                {"type": "tile", "id": tile.tile_id, "field": "quality_score"},
                {"type": "scene", "id": tile.scene_id, "field": "source_filename"},
            ])
    except Exception:
        return _payload(message="Unable to read tile metadata.", error=True)


@tool
def get_cluster_neighbors(tile_id: str, k: int = 10) -> dict:
    """Fetch clustered neighbors when the discovery index is available."""
    return _payload(message=f"No cluster data available for tile_id {tile_id}.")


@tool
def get_review_history(change_id: str) -> dict:
    """Fetch the confirm/reject audit trail for a change candidate."""
    if not change_id:
        return _payload(message="A change_id is required.")
    try:
        with get_session() as session:
            rows = session.execute(
                select(Feedback).where(Feedback.target_id == change_id).order_by(Feedback.created_at.asc())
            ).scalars().all()
            data = [{
                "feedback_id": row.feedback_id, "target_type": row.target_type,
                "target_id": row.target_id, "verdict": row.verdict,
                "analyst": row.analyst, "note": row.note, "created_at": _date(row.created_at),
            } for row in rows]
            return _payload(data, message=None if data else f"No review history for {change_id}.", citations=[
                {"type": "change", "id": change_id, "field": "review_history"}
            ] if data else [])
    except Exception:
        return _payload(message="Unable to read review history.", error=True)


TOOLS = [search_archive, get_change_result, get_tile_metadata, get_cluster_neighbors, get_review_history]
# Backwards-compatible names for callers that imported the initial prototype.
tools = TOOLS


class ChatIntent(BaseModel):
    """Validated, deterministic routing decision for one scoped question."""

    action: Literal["search", "change", "metadata", "cluster", "review", "unknown"]
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class AgentState(TypedDict, total=False):
    message: str
    context: Dict[str, str]
    history: List[Dict[str, str]]
    evidence: Dict[str, Any]
    intent: Dict[str, Any]
    tool_result: Dict[str, Any]
    final: str
    citations: List[Dict[str, Any]]
    fallback: bool


SYSTEM_PROMPT = """You are the TerreX Chat Enhancement Layer, a grounded retrieval assistant.
Your goal is to answer the user's question using the provided tools and injected evidence.
If the injected structured evidence does not contain the answer, you MUST use a tool (like get_change_result or search_archive) to fetch the required data.
Only state facts present in tool results or the injected structured evidence for this turn.
If a tool returns no data or an error, say so plainly and do not guess.
Every factual claim must cite its source tile ID, scene ID, change ID, or confidence field.
You have not looked at or seen any image; you reason only over structured metadata and computed results.
Keep the answer to 2-4 short sentences. Do not answer general world-knowledge questions."""
system_prompt = SYSTEM_PROMPT


def _context_evidence(context: Dict[str, str]) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}
    if context.get("tile_id"):
        evidence["tile"] = get_tile_metadata.invoke({"tile_id": context["tile_id"]})
    if context.get("change_id"):
        evidence["change"] = get_change_result.invoke({"change_id": context["change_id"]})
    if context.get("cluster_id"):
        evidence["cluster"] = get_cluster_neighbors.invoke({"tile_id": context["cluster_id"], "k": 10})
    return evidence


def _fallback_summary(context: Dict[str, str], evidence: Optional[Dict[str, Any]] = None) -> str:
    evidence = evidence or _context_evidence(context)
    selected = evidence.get("selected") or {}
    selected_data = selected.get("data") if isinstance(selected, dict) else None
    change = (evidence.get("change") or {}).get("data") or (selected_data if isinstance(selected_data, dict) and selected_data.get("change_id") else None)
    tile = (evidence.get("tile") or {}).get("data") or (selected_data if isinstance(selected_data, dict) and selected_data.get("tile_id") else None)
    if not change and isinstance(selected_data, list) and selected_data:
        return f"The evidence tool returned {len(selected_data)} records for this context."
    if not change and selected.get("message"):
        return str(selected["message"])
    if change:
        before, after = change.get("before") or {}, change.get("after") or {}
        confidence = change.get("confidence")
        confidence_text = f"{confidence * 100:.1f}%" if isinstance(confidence, (int, float)) and confidence <= 1 else str(confidence or "unknown")
        return (
            f"This tile has detected change with {confidence_text} confidence (change {change.get('change_id')}). "
            f"The compared observations are {before.get('acquisition_date') or 'unknown'} and {after.get('acquisition_date') or 'unknown'}; "
            f"quality score is {change.get('quality_score', 'unknown')}."
        )
    if tile:
        return (
            f"Tile {tile.get('tile_id')} was acquired on {tile.get('acquisition_date') or 'an unknown date'} "
            f"by {tile.get('sensor') or 'an unknown sensor'} with quality score {tile.get('quality_score', 'unknown')}."
        )
    return "No structured evidence is available for this context."


def _history_key(conversation_id: Optional[str], context: Dict[str, str]) -> str:
    return conversation_id or "|".join(f"{key}:{context.get(key, '')}" for key in ("tile_id", "change_id", "cluster_id"))


def _remember(key: str, role: str, content: str) -> List[Dict[str, str]]:
    with _history_lock:
        history = _conversation_history.setdefault(key, [])
        history.append({"role": role, "content": content})
        del history[:-MAX_HISTORY_TURNS]
        return list(history)


def parse_intent(message: str, context: Dict[str, str]) -> ChatIntent:
    """Route by explicit keywords and available scope; never accept raw model tool calls."""
    text = message.lower().strip()
    if any(word in text for word in ("review", "audit", "feedback", "verdict", "confirm", "reject")) and context.get("change_id"):
        return ChatIntent(action="review", tool_name="get_review_history", arguments={"change_id": context["change_id"]}, reason="review language")
    if any(word in text for word in ("neighbor", "neighbour", "cluster", "similar tile", "similar tiles")) and (context.get("tile_id") or context.get("cluster_id")):
        tile_id = context.get("tile_id") or context.get("cluster_id")
        return ChatIntent(action="cluster", tool_name="get_cluster_neighbors", arguments={"tile_id": tile_id, "k": 10}, reason="cluster language")
    if any(word in text for word in ("search", "find", "archive", "imagery", "scene")):
        return ChatIntent(action="search", tool_name="search_archive", arguments={"query_text": message}, reason="archive search language")
    if context.get("change_id") and any(word in text for word in ("change", "confidence", "compare", "before", "after", "area", "reason", "detected")):
        return ChatIntent(action="change", tool_name="get_change_result", arguments={"change_id": context["change_id"]}, reason="change language")
    if context.get("change_id") and not context.get("tile_id"):
        return ChatIntent(action="change", tool_name="get_change_result", arguments={"change_id": context["change_id"]}, reason="change scope")
    if context.get("tile_id"):
        return ChatIntent(action="metadata", tool_name="get_tile_metadata", arguments={"tile_id": context["tile_id"]}, reason="tile scope")
    if context.get("cluster_id"):
        return ChatIntent(action="cluster", tool_name="get_cluster_neighbors", arguments={"tile_id": context["cluster_id"], "k": 10}, reason="cluster scope")
    return ChatIntent(action="unknown", tool_name="", reason="no supported scoped intent")


_TOOL_BY_NAME = {getattr(item, "name", getattr(item, "__name__", str(item))): item for item in TOOLS}


def _execute_intent(intent: ChatIntent) -> Dict[str, Any]:
    if not intent.tool_name or intent.tool_name not in _TOOL_BY_NAME:
        return _payload(message="Ask about a selected tile, change candidate, or cluster.")
    try:
        fn = _TOOL_BY_NAME[intent.tool_name]
        if hasattr(fn, "invoke"):
            return fn.invoke(intent.arguments)
        return fn(**intent.arguments)
    except Exception:
        return _payload(message="The requested evidence could not be read.", error=True)


def _normalise_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(part.get("text", "")) for part in value if isinstance(part, dict)).strip()
    return str(value or "").strip()


def _build_graph():
    def parse_node(state: AgentState):
        return {"intent": parse_intent(state["message"], state["context"]).model_dump()}

    def select_node(state: AgentState):
        return state

    def execute_node(state: AgentState):
        intent = ChatIntent.model_validate(state["intent"])
        result = _execute_intent(intent)
        citations = list(result.get("citations", []))
        return {"tool_result": result, "citations": citations}

    def compose_node(state: AgentState):
        llm = get_llm_client()
        if llm is None:
            return {"fallback": True}
        evidence = {"selected_tool": state.get("intent", {}), "result": state.get("tool_result", {}), "context": state["context"]}
        prompt = (
            f"{SYSTEM_PROMPT}\n\nEvidence JSON (the only allowed source):\n{json.dumps(evidence, default=str)}\n"
            f"Conversation:\n{json.dumps(state.get('history', []), default=str)}\n\nQuestion: {state['message']}"
        )
        response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=state["message"])])
        final = _normalise_text(getattr(response, "content", response))
        if not final:
            return {"fallback": True}
        return {"final": final, "fallback": False}

    def fallback_node(state: AgentState):
        evidence = dict(state.get("evidence") or {})
        evidence["selected"] = state.get("tool_result", {})
        return {"final": _fallback_summary(state["context"], evidence), "fallback": True}

    def compose_next(state: AgentState) -> str:
        return "fallback" if state.get("fallback") else "done"

    if StateGraph is None:
        return None

    graph = StateGraph(AgentState)
    graph.add_node("parse_intent", parse_node)
    graph.add_node("select_tool", select_node)
    graph.add_node("execute_tool", execute_node)
    graph.add_node("compose_answer", compose_node)
    graph.add_node("fallback", fallback_node)
    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "select_tool")
    graph.add_edge("select_tool", "execute_tool")
    graph.add_edge("execute_tool", "compose_answer")
    graph.add_conditional_edges("compose_answer", compose_next, {"fallback": "fallback", "done": END})
    graph.add_edge("fallback", END)
    return graph.compile()


_chat_app = None


def process_chat(message: str, context: Dict[str, str], conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Process one scoped message and return text plus structured citations."""
    context = {key: value for key, value in (context or {}).items() if value}
    started = time.perf_counter()
    evidence = _context_evidence(context)
    status = chat_status()
    key = _history_key(conversation_id, context)
    history = _remember(key, "user", message)
    if not status["available"]:
        citations = [citation for item in evidence.values() for citation in item.get("citations", [])]
        response = _fallback_summary(context, evidence)
        return {"available": False, "response": response, "citations": citations, "fallback": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "status": status}

    global _chat_app
    try:
        if _chat_app is None:
            _chat_app = _build_graph()
        result = _chat_app.invoke({"message": message, "context": context, "history": history, "evidence": evidence})
        final = str(result.get("final") or _fallback_summary(context, evidence)).strip()
        citations = list(result.get("citations", []))
        unique = {(c.get("type"), c.get("id"), c.get("field")): c for c in citations}
        citations = list(unique.values())
        cited_ids = [str(c.get("id")) for c in citations if c.get("id")]
        if cited_ids and not any(source_id in final for source_id in cited_ids):
            final = f"{final} Sources: {', '.join(cited_ids[:4])}."
        _remember(key, "assistant", final)
        return {"available": True, "response": final, "citations": citations, "fallback": bool(result.get("fallback")), "latency_ms": round((time.perf_counter() - started) * 1000, 1), "intent": result.get("intent"), "status": status}
    except Exception:
        citations = [citation for item in evidence.values() for citation in item.get("citations", [])]
        return {"available": False, "response": _fallback_summary(context, evidence), "citations": citations, "fallback": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "status": status}
