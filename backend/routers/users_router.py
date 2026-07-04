"""
users_router.py — User and role management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from auth import get_current_user, get_password_hash
import models

router = APIRouter(prefix="/users", tags=["Users"])


class UserCreate(BaseModel):
    full_name: str
    email:     str
    role:      str
    password:  str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email:     Optional[str] = None
    role:      Optional[str] = None
    password:  Optional[str] = None


@router.get("")
def get_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return {
        "users": [{
            "id":               u.id,
            "full_name":        u.full_name,
            "email":            u.email,
            "role":             u.role,
            "is_active":        u.is_active,
            "created_at":       u.created_at.isoformat() if u.created_at else "",
            "last_login":       u.last_login.isoformat() if u.last_login else None,
            "clients_assigned": db.query(models.ClientAssignment).filter(
                models.ClientAssignment.agent_id == u.id
            ).count(),
        } for u in users]
    }


@router.post("")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="Not authorized")
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    user = models.User(
        full_name=data.full_name,
        email=data.email,
        role=data.role,
        hashed_password=get_password_hash(data.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    return {"message": "User created", "id": user.id}


@router.post("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="Not authorized")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.full_name: user.full_name = data.full_name
    if data.email:     user.email     = data.email
    if data.role:      user.role      = data.role
    if data.password:
        user.hashed_password = get_password_hash(data.password)
        from datetime import datetime as _dt
        user.tokens_valid_after = _dt.utcnow()   # log out all of this user's existing sessions
    db.commit()
    return {"message": "User updated"}


@router.post("/{user_id}/toggle-active")
def toggle_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="Not authorized")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"message": f"User {'activated' if user.is_active else 'deactivated'}"}
