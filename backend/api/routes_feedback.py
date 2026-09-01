from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.database import get_db
from db.models import Feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    target_type: str  # "tile" | "change_result"
    target_id: str
    verdict: str      # "confirm" | "reject"
    analyst: str | None = None
    note: str | None = None


@router.post("")
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    fb = Feedback(**payload.dict())
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
