"""
settings_router.py — Score settings and general settings
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/settings", tags=["Settings"])

SCORE_DEFAULTS = {
    "no_contact_14d":         30,
    "no_contact_7d":          15,
    "call_later_reached":     25,
    "no_deposit_ever":        25,
    "no_deposit_21d":         20,
    "payment_rejected":       35,
    "first_dep_7d":           20,
    "withdrawal_pending":     15,
    "margin_below_50":        40,
    "margin_below_100":       25,
    "no_trade_30d":           15,
    "has_balance":            10,
    "min_days_between_calls": 14,
    "max_days_without_call":  14,
}


@router.get("/score")
def get_score_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        settings = db.query(models.ScoreSettings).all()
        result = {**SCORE_DEFAULTS}
        for s in settings:
            result[s.trigger] = s.points
        return result
    except:
        return SCORE_DEFAULTS


@router.post("/score")
def save_score_settings(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        for trigger, points in data.items():
            if trigger not in SCORE_DEFAULTS:
                continue
            existing = db.query(models.ScoreSettings).filter(
                models.ScoreSettings.trigger == trigger
            ).first()
            if existing:
                existing.points = int(points)
            else:
                db.add(models.ScoreSettings(trigger=trigger, points=int(points)))
        db.commit()
        return {"message": "Settings saved — scores will recalculate on next sync"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
