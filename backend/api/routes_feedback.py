from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.database import get_db
from db.models import ChangeResult, Feedback, Tile

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    target_type: Literal["tile", "change_result"]
    target_id: str
    verdict: Literal["confirm", "reject"]
    analyst: str | None = None
    note: str | None = None


@router.post("")
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    target_model = Tile if payload.target_type == "tile" else ChangeResult
    if db.get(target_model, payload.target_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown {payload.target_type} target: {payload.target_id}")
    fb = Feedback(**payload.model_dump())
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"feedback_id": fb.feedback_id, "status": "recorded"}


@router.get("")
def list_feedback(db: Session = Depends(get_db)):
    rows = db.execute(select(Feedback).order_by(Feedback.created_at.desc())).scalars().all()
    return [
        {
            "feedback_id": r.feedback_id, "target_type": r.target_type,
            "target_id": r.target_id, "verdict": r.verdict,
            "analyst": r.analyst, "note": r.note,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
