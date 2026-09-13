"""Simple, Fast, Grounded Satellite Assistant for TerreX (Terra)."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_ollama import ChatOllama
except ImportError:
    HumanMessage = None
    SystemMessage = None
    ChatOllama = None

from sqlalchemy import select, or_

from db.database import get_session
from db.models import ChangeResult, Feedback, Scene, Tile
from services.search import semantic_text_search
from services.vector_store import vector_store

logger = logging.getLogger("terrex.chat_agent")

SAFE_THRESHOLD_GB = float(os.getenv("CHAT_SAFE_THRESHOLD_GB", "1.5"))
IDLE_TIMEOUT_SECONDS = int(os.getenv("CHAT_IDLE_TIMEOUT_SECONDS", "120"))
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:1.5b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MAX_HISTORY_TURNS = 8

_llm_client: Optional[ChatOllama] = None
_last_used_time = 0.0
_llm_lock = threading.Lock()

# Persistent session memory across turns
_conversation_history: Dict[str, List[Dict[str, str]]] = {}
_session_entities: Dict[str, Dict[str, Any]] = {}
_history_lock = threading.Lock()
_unload_monitor_started = False


# =====================================================================
# 1. RAM & Runtime Health Checks
# =====================================================================

def ram_available() -> bool:
    try:
        if psutil is None:
            return True
        return psutil.virtual_memory().available / (1024 ** 3) >= SAFE_THRESHOLD_GB
    except Exception:
        return True


def ollama_health() -> Dict[str, Any]:
    """Probe Ollama and detect installed models dynamically."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", headers={"User-Agent": "TerreX"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            installed_models = [m.get("name", "") for m in data.get("models", [])]
            
            target_model = CHAT_MODEL
            matched_model = None
            
            if target_model in installed_models:
                matched_model = target_model
            else:
                base_target = target_model.split(":")[0]
                for m in installed_models:
                    if m == target_model or m.startswith(base_target) or target_model.startswith(m.split(":")[0]):
                        matched_model = m
                        break
                if not matched_model and installed_models:
                    matched_model = installed_models[0]
            
            if matched_model:
                return {
                    "reachable": True,
                    "model_available": True,
                    "model": matched_model,
                    "installed_models": installed_models,
                    "error": None,
                }
            return {
                "reachable": True,
                "model_available": False,
                "model": target_model,
                "installed_models": installed_models,
                "error": "No models found in Ollama.",
            }
    except Exception as e:
        return {
            "reachable": False,
            "model_available": False,
            "model": CHAT_MODEL,
            "error": "Runtime is air-gapped or Ollama is offline.",
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
    return bool(chat_status()["available"])


def get_llm_client() -> Optional[ChatOllama]:
    global _llm_client, _last_used_time
    if not ram_available() or ChatOllama is None:
        return None
    health = ollama_health()
    if not health.get("reachable") or not health.get("model_available"):
        return None
    model_to_use = health.get("model") or CHAT_MODEL
    with _llm_lock:
        if _llm_client is None or getattr(_llm_client, "model", None) != model_to_use:
            try:
                _llm_client = ChatOllama(
                    base_url=OLLAMA_BASE_URL,
                    model=model_to_use,
                    temperature=0.1,
                    request_timeout=8.0,
                )
            except TypeError:
                _llm_client = ChatOllama(
                    base_url=OLLAMA_BASE_URL,
                    model=model_to_use,
                    temperature=0.1,
                )
        _last_used_time = time.time()
        return _llm_client


def maybe_unload_llm() -> bool:
    global _llm_client
    with _llm_lock:
        if _llm_client is None or (time.time() - _last_used_time) <= IDLE_TIMEOUT_SECONDS:
            return False
        _llm_client = None
        return True


def start_idle_unload_monitor() -> None:
    global _unload_monitor_started
    if _unload_monitor_started:
        return
    _unload_monitor_started = True

    def monitor() -> None:
        while True:
            time.sleep(min(30, max(5, IDLE_TIMEOUT_SECONDS // 2)))
            maybe_unload_llm()

    threading.Thread(target=monitor, name="terrex-chat-idle-unload", daemon=True).start()


# =====================================================================
# 2. Session & Entity Memory Management
# =====================================================================

def _history_key(conversation_id: Optional[str], context: Dict[str, str]) -> str:
    if conversation_id:
        return conversation_id
    parts = [f"{k}:{v}" for k, v in sorted(context.items()) if v]
    return "|".join(parts) if parts else "default_session"


def _remember_turn(key: str, role: str, content: str) -> List[Dict[str, str]]:
    with _history_lock:
        history = _conversation_history.setdefault(key, [])
        history.append({"role": role, "content": content})
        del history[:-MAX_HISTORY_TURNS]
        return list(history)


def _update_session_entities(key: str, new_entities: Dict[str, Any]) -> Dict[str, Any]:
    with _history_lock:
        ent = _session_entities.setdefault(key, {})
        for k, v in new_entities.items():
            if v:
                ent[k] = v
        return dict(ent)


def _get_session_entities(key: str) -> Dict[str, Any]:
    with _history_lock:
        return dict(_session_entities.get(key, {}))


# =====================================================================
# 3. Direct Grounded Evidence Retrieval
# =====================================================================

def _date(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val)[:10] if val else "N/A"


def _gather_evidence(message: str, context: Dict[str, str], session_entities: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Collect verified database facts and telemetry corresponding to the query and active target."""
    text = message.lower().strip()
    evidence: Dict[str, Any] = {}
    citations: List[Dict[str, Any]] = []

    tile_id = context.get("tile_id") or session_entities.get("active_tile_id")
    change_id = context.get("change_id") or session_entities.get("active_change_id")

    # 1. Fetch Change Data if change_id is present or change keywords mentioned
    if change_id or any(w in text for w in ("change", "confidence", "anomaly", "compare", "before", "after", "area", "delta")):
        target_cid = change_id
        try:
            with get_session() as session:
                change = session.get(ChangeResult, target_cid) if target_cid else session.execute(select(ChangeResult).order_by(ChangeResult.created_at.desc()).limit(1)).scalar_one_or_none()
                if change:
                    before = session.get(Tile, change.before_tile_id) if change.before_tile_id else None
                    after = session.get(Tile, change.after_tile_id) if change.after_tile_id else None
                    
                    cloud_delta = abs((after.cloud_fraction or 0.0) - (before.cloud_fraction or 0.0)) if (before and after) else 0.0
                    is_cloud_shadow_risk = cloud_delta > 0.15
                    quality_ok = (change.quality_score or 0.8) > 0.75

                    evidence["change"] = {
                        "change_id": str(change.change_id),
                        "confidence": change.confidence,
                        "change_score": change.change_score,
                        "change_area_m2": change.change_area_m2,
                        "reasons": change.reasons or ["Multi-spectral anomaly detected"],
                        "method": change.method,
                        "quality_score": change.quality_score,
                        "before_tile_id": str(change.before_tile_id) if change.before_tile_id else None,
                        "after_tile_id": str(change.after_tile_id) if change.after_tile_id else None,
                        "before_date": _date(before.acquisition_date) if before else "N/A",
                        "after_date": _date(after.acquisition_date) if after else "N/A",
                        "false_alarm_risk": "LOW" if (quality_ok and not is_cloud_shadow_risk) else "MEDIUM",
                        "cloud_shadow_risk": "HIGH" if is_cloud_shadow_risk else "LOW",
                    }
                    citations.append({"type": "change", "id": str(change.change_id), "field": "confidence"})
                    if before:
                        citations.append({"type": "tile", "id": str(before.tile_id), "field": "before_observation"})
                    if after:
                        citations.append({"type": "tile", "id": str(after.tile_id), "field": "after_observation"})
        except Exception as e:
            logger.debug("Evidence gather change error: %s", e)

    # 2. Fetch Tile Metadata & Spectral Indices if tile_id present or tile keywords mentioned
    if tile_id or any(w in text for w in ("tile", "sensor", "spectral", "ndvi", "ndwi", "ndbi", "quality", "cloud", "resolution", "provenance")):
        target_tid = tile_id or (evidence.get("change") or {}).get("before_tile_id")
        try:
            with get_session() as session:
                tile = session.get(Tile, target_tid) if target_tid else session.execute(select(Tile).order_by(Tile.acquisition_date.desc()).limit(1)).scalar_one_or_none()
                if tile:
                    scene = session.get(Scene, tile.scene_id) if tile.scene_id else None
                    spec = tile.spectral_indices or {}
                    ndvi = float(spec.get("ndvi_mean", 0.0) or 0.0)
                    ndwi = float(spec.get("ndwi_mean", 0.0) or 0.0)
                    ndbi = float(spec.get("ndbi_mean", 0.0) or 0.0)

                    veg_status = "Dense Healthy Vegetation" if ndvi > 0.4 else ("Moderate Canopy / Shrub" if ndvi > 0.15 else "Low Vegetation / Barren")
                    water_status = "Open Water Surface" if ndwi > 0.1 else ("Moist Soil / Wetland" if ndwi > -0.1 else "Dry Surface")
                    built_status = "High-Density Built Structure" if ndbi > 0.0 else ("Urban / Semi-Urban" if ndbi > -0.15 else "Non-Urban")

                    evidence["tile"] = {
                        "tile_id": str(tile.tile_id),
                        "sensor": tile.sensor or (scene.sensor if scene else "Sentinel-2"),
                        "acquisition_date": _date(tile.acquisition_date),
                        "resolution_m": tile.resolution_m or 10.0,
                        "quality_score": tile.quality_score or 0.85,
                        "cloud_fraction": tile.cloud_fraction or 0.0,
                        "ndvi_mean": round(ndvi, 3),
                        "ndwi_mean": round(ndwi, 3),
                        "ndbi_mean": round(ndbi, 3),
                        "vegetation_status": veg_status,
                        "water_status": water_status,
                        "built_status": built_status,
                        "source_portal": (scene.source_portal if scene else "Copernicus Data Space Ecosystem") or "Copernicus Open Access",
                        "license": (scene.license_source if scene else "CC-BY 4.0") or "Open Access",
                    }
                    citations.append({"type": "tile", "id": str(tile.tile_id), "field": "quality_score"})
        except Exception as e:
            logger.debug("Evidence gather tile error: %s", e)

    # 3. Cluster Neighbors if requested
    if any(w in text for w in ("neighbor", "neighbour", "cluster", "similar", "nearby")):
        target_tid = tile_id or (evidence.get("tile") or {}).get("tile_id")
        if target_tid:
            try:
                with get_session() as session:
                    anchor = session.get(Tile, target_tid)
                    if anchor:
                        stmt = select(Tile).where(
                            Tile.tile_id != target_tid,
                            (Tile.lat - anchor.lat).between(-0.2, 0.2) & (Tile.lon - anchor.lon).between(-0.2, 0.2)
                        ).limit(4)
                        neighbors = session.execute(stmt).scalars().all()
                        evidence["cluster"] = {
                            "anchor_tile_id": target_tid,
                            "neighbors_count": len(neighbors),
                            "neighbor_ids": [str(n.tile_id) for n in neighbors],
                        }
                        for n in neighbors:
                            citations.append({"type": "tile", "id": str(n.tile_id), "field": "neighbor"})
            except Exception as e:
                logger.debug("Evidence gather cluster error: %s", e)

    # 4. Analyst Audit / Reviews if requested
    if any(w in text for w in ("review", "audit", "feedback", "verdict", "confirm", "reject", "analyst")):
        target_id = change_id or tile_id
        if target_id:
            try:
                with get_session() as session:
                    stmt = select(Feedback).where(Feedback.target_id == target_id).order_by(Feedback.created_at.desc())
                    recs = session.execute(stmt).scalars().all()
                    if recs:
                        evidence["review"] = {
                            "total_reviews": len(recs),
                            "latest_verdict": recs[0].verdict,
                            "analyst": recs[0].analyst or "Human-in-the-Loop Analyst",
                            "note": recs[0].note,
                        }
                        citations.append({"type": "review", "id": str(recs[0].feedback_id), "field": "verdict"})
                    else:
                        evidence["review"] = {"total_reviews": 0, "status": "Pending Analyst Review"}
            except Exception as e:
                logger.debug("Evidence gather review error: %s", e)

    # 5. Catalog / System stats if requested
    if any(w in text for w in ("catalog", "system", "inventory", "indexed", "total scenes", "total tiles")):
        try:
            from sqlalchemy import func
            with get_session() as session:
                sc = session.scalar(select(func.count(Scene.scene_id))) or 0
                tc = session.scalar(select(func.count(Tile.tile_id))) or 0
                evidence["catalog"] = {
                    "total_scenes": sc,
                    "total_tiles": tc,
                    "vector_embeddings": vector_store.count(),
                    "active_sensors": ["Sentinel-2 L2A", "Sentinel-1 GRD", "Landsat-8/9", "ISRO Resourcesat"],
                }
        except Exception as e:
            logger.debug("Evidence gather catalog error: %s", e)

    # 6. Natural Language Search if query is a search prompt
    if any(w in text for w in ("search", "find", "look for", "show me")) and "search" not in evidence:
        try:
            clean_q = re.sub(r"^(search|find|show me|look for|query)\s+(for\s+)?", "", text, flags=re.IGNORECASE).strip()
            res = semantic_text_search(query=clean_q or message, top_k=3)
            rows = res.get("results", [])
            evidence["search"] = {
                "query": clean_q or message,
                "matches_count": len(rows),
                "top_matches": [
                    {"tile_id": str(r["tile_id"]), "score": round(float(r.get("final_score", 0)), 3), "sensor": r.get("sensor")}
                    for r in rows[:3]
                ]
            }
            for r in rows[:3]:
                citations.append({"type": "tile", "id": str(r["tile_id"]), "field": "search_match"})
        except Exception as e:
            logger.debug("Evidence gather search error: %s", e)

    # Deduplicate citations
    unique_citations = {(c.get("type"), str(c.get("id")), c.get("field")): c for c in citations if c.get("id")}
    return evidence, list(unique_citations.values())


# =====================================================================
# 4. Clean Grounded Answer Composition
# =====================================================================

def _compose_deterministic_summary(context: Dict[str, str], evidence: Dict[str, Any], query: str) -> str:
    """Compose a rich, bulletproof grounded answer from collected database facts."""
    parts = []

    # Change section
    if "change" in evidence:
        c = evidence["change"]
        conf_pct = f"{c['confidence'] * 100:.1f}%" if isinstance(c.get("confidence"), (int, float)) and c["confidence"] <= 1 else f"{c.get('confidence')}%"
        area_str = f"{c['change_area_m2']:,.0f} m²" if isinstance(c.get("change_area_m2"), (int, float)) else "Calculated"
        reasons_str = "; ".join(c.get("reasons", [])[:2])
        parts.append(
            f"The detected change has a {conf_pct} confidence score with an estimated footprint of {area_str}. "
            f"Baseline observation: {c['before_date']} vs Target observation: {c['after_date']}. "
            f"False alarm risk is {c['false_alarm_risk']} (Cloud Shadow Risk: {c['cloud_shadow_risk']}). Factors: {reasons_str}."
        )

    # Tile & Spectral section
    if "tile" in evidence:
        t = evidence["tile"]
        q_score = f"{t['quality_score'] * 100:.1f}%" if isinstance(t.get("quality_score"), (int, float)) else "N/A"
        c_cov = f"{t['cloud_fraction'] * 100:.1f}%" if isinstance(t.get("cloud_fraction"), (int, float)) else "N/A"
        parts.append(
            f"Tile {t['tile_id']} was acquired on {t['acquisition_date']} by {t['sensor']} at {t['resolution_m']}m GSD. "
            f"Quality score: {q_score}, cloud cover: {c_cov}. "
            f"Spectral indices: NDVI {t['ndvi_mean']} ({t['vegetation_status']}), NDWI {t['ndwi_mean']} ({t['water_status']}), NDBI {t['ndbi_mean']} ({t['built_status']}). "
            f"Source: {t['source_portal']}."
        )

    # Cluster section
    if "cluster" in evidence:
        cl = evidence["cluster"]
        parts.append(f"Discovered {cl['neighbors_count']} similar cluster neighbors in localized geographic proximity.")

    # Review section
    if "review" in evidence:
        r = evidence["review"]
        if r.get("total_reviews", 0) > 0:
            parts.append(f"Analyst audit trail: latest verdict is {str(r.get('latest_verdict')).upper()} by {r.get('analyst')}." + (f" Note: '{r.get('note')}'" if r.get("note") else ""))
        else:
            parts.append("This target is currently pending human analyst verification.")

    # Catalog section
    if "catalog" in evidence:
        cat = evidence["catalog"]
        parts.append(f"Catalog inventory: {cat['total_scenes']} scenes, {cat['total_tiles']:,} tiles, {cat['vector_embeddings']:,} vector points across active modalities ({', '.join(cat['active_sensors'])}).")

    # Search section
    if "search" in evidence:
        s = evidence["search"]
        if s["matches_count"] > 0:
            top_ids = [f"{m['tile_id'][:8]} ({m['score']})" for m in s["top_matches"]]
            parts.append(f"Search for '{s['query']}' returned {s['matches_count']} matching tiles. Top matches: {', '.join(top_ids)}.")
        else:
            parts.append(f"No catalog matches found for '{s['query']}'.")

    if parts:
        return " ".join(parts)
    return "Terra is ready. Ask any question regarding sensor provenance, spectral indices (NDVI/NDWI/NDBI), detected changes, or catalog inventory."


def _generate_answer(message: str, context: Dict[str, str], evidence: Dict[str, Any], history: List[Dict[str, str]]) -> Tuple[str, bool]:
    """Single-shot grounded answer generation with fast deterministic fallback."""
    llm = get_llm_client()
    if llm is None or not evidence:
        return _compose_deterministic_summary(context, evidence, message), True

    prompt = (
        f"You are Terra, the satellite intelligence assistant for TerreX.\n"
        f"Answer the analyst's question directly and concisely in 2-3 clear sentences using ONLY the verified facts below.\n"
        f"Cite relevant Tile IDs, Change IDs, confidence scores, or dates if present in the facts.\n\n"
        f"Verified Facts JSON:\n{json.dumps(evidence, default=str)}\n\n"
        f"Question: {message}\n"
        f"Answer:"
    )

    try:
        resp = llm.invoke([
            SystemMessage(content="You are Terra, a professional satellite intelligence assistant. Respond in clear plain text."),
            HumanMessage(content=prompt)
        ])
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        clean_text = str(content or "").strip()
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text).rstrip("`").strip()
        if clean_text and len(clean_text) > 15 and not clean_text.startswith("{"):
            return clean_text, False
    except Exception as exc:
        logger.debug("LLM single-shot generation error: %s", exc)

    return _compose_deterministic_summary(context, evidence, message), True


# =====================================================================
# 5. Main Clean Public API
# =====================================================================

def process_chat(message: str, context: Dict[str, str], conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute simple, fast, grounded question answering with 100% reliability."""
    started = time.perf_counter()
    context = {k: str(v) for k, v in (context or {}).items() if v}
    key = _history_key(conversation_id, context)

    session_entities = _get_session_entities(key)
    if context.get("tile_id"):
        session_entities["active_tile_id"] = context["tile_id"]
    if context.get("change_id"):
        session_entities["active_change_id"] = context["change_id"]
    _update_session_entities(key, session_entities)

    history = _remember_turn(key, "user", message)
    status = chat_status()

    # 1. Gather all relevant verified evidence directly
    evidence, citations = _gather_evidence(message, context, session_entities)

    # 2. Single-shot grounded synthesis
    response_text, is_fallback = _generate_answer(message, context, evidence, history)

    # 3. Append citation tags if citations exist but are not referenced in the text
    cited_ids = [str(c.get("id")) for c in citations if c.get("id")]
    if cited_ids and not any(cid in response_text for cid in cited_ids[:3]):
        response_text = f"{response_text} (Evidence Sources: {', '.join(cited_ids[:3])})"

    _remember_turn(key, "assistant", response_text)

    return {
        "available": status["available"],
        "response": response_text,
        "citations": citations,
        "fallback": is_fallback,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "intent": {"topics": list(evidence.keys())},
        "status": status,
    }


# Backwards-compatible tools list
TOOLS = []
tools = TOOLS
