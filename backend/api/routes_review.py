from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from db.database import get_db
from db.models import ChangeResult, Feedback, Scene, Tile

router = APIRouter(prefix="/api/review", tags=["review"])


def _date(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _observation(tile: Optional[Tile], scene: Optional[Scene]) -> Optional[dict]:
    if tile is None:
        return None
    return {
        "tile_id": tile.tile_id,
        "scene_id": tile.scene_id,
        "acquisition_date": _date(tile.acquisition_date),
        "sensor": tile.sensor or (scene.sensor if scene else None),
        "thumbnail_path": tile.thumbnail_path,
        "tile_path": tile.tile_path,
        "quality_score": tile.quality_score,
        "cloud_fraction": tile.cloud_fraction,
        "lon": tile.lon,
        "lat": tile.lat,
        "embedding_model": tile.embedding_model,
        "embedding_is_placeholder": bool(tile.embedding_is_placeholder),
    }


@router.get("")
def get_review_queue(
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|rejected)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    BeforeTile = aliased(Tile)
    AfterTile = aliased(Tile)
    BeforeScene = aliased(Scene)
    AfterScene = aliased(Scene)
    changes = db.execute(
        select(ChangeResult, BeforeTile, AfterTile, BeforeScene, AfterScene)
        .join(BeforeTile, BeforeTile.tile_id == ChangeResult.before_tile_id)
        .join(AfterTile, AfterTile.tile_id == ChangeResult.after_tile_id)
        .join(BeforeScene, BeforeScene.scene_id == BeforeTile.scene_id, isouter=True)
        .join(AfterScene, AfterScene.scene_id == AfterTile.scene_id, isouter=True)
    ).all()

    feedback_rows = db.execute(select(Feedback).where(Feedback.target_type == "change_result")).scalars().all()
    by_target = defaultdict(list)
    for row in feedback_rows:
        by_target[row.target_id].append(row)

    queue = []
    for change, before_tile, after_tile, before_scene, after_scene in changes:
        feedback = by_target.get(change.change_id, [])
        latest = max(feedback, key=lambda row: row.created_at or datetime.min) if feedback else None
        item_status = {
            "confirm": "confirmed",
            "reject": "rejected",
        }.get(latest.verdict, "pending") if latest else "pending"
        if status and item_status != status:
            continue

        confirms = sum(row.verdict == "confirm" for row in feedback)
        rejects = sum(row.verdict == "reject" for row in feedback)
        feedback_adjustment = 0.05 * confirms - 0.05 * rejects
        priority = max(0.0, min(1.0, float(change.confidence or 0.0) + feedback_adjustment))
        queue.append({
            "id": change.change_id,
            "targetId": change.after_tile_id,
            "type": "Change candidate",
            "confidence": float(change.confidence or 0.0),
            "priority": priority,
            "dateRange": f"{_date(before_tile.acquisition_date) or 'unknown'} to {_date(after_tile.acquisition_date) or 'unknown'}",
            "location": f"{after_tile.lat:.4f}N, {after_tile.lon:.4f}E",
            "coordinates": [after_tile.lon, after_tile.lat],
            "sensor": after_tile.sensor or (after_scene.sensor if after_scene else "Unknown"),
            "areaM2": float(change.change_area_m2 or 0.0),
            "status": item_status,
            "evidenceCount": int(bool(change.change_mask_path)) + int(before_tile is not None) + int(after_tile is not None),
            "thumbnailBefore": before_tile.thumbnail_path,
            "thumbnailAfter": after_tile.thumbnail_path,
            "notes": (change.reasons or [None])[0] if isinstance(change.reasons, list) else None,
            "reviewedAt": _date(latest.created_at) if latest else None,
            "evidence": {
                "before": _observation(before_tile, before_scene),
                "after": _observation(after_tile, after_scene),
                "change_score": change.change_score,
                "quality_score": change.quality_score,
                "confidence": change.confidence,
                "change_area_m2": change.change_area_m2,
                "change_mask_path": change.change_mask_path,
                "reasons": change.reasons or [],
                "method": change.method,
                "is_placeholder_model": bool(change.is_placeholder_model),
            },
            "feedback": {
                "confirm_count": confirms,
                "reject_count": rejects,
                "ranking_adjustment": round(feedback_adjustment, 4),
            },
        })

    queue.sort(key=lambda item: (item["status"] != "pending", -item["priority"], -item["confidence"]))
    return {"count": len(queue[:limit]), "results": queue[:limit]}
