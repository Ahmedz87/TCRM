from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
import login_guard
from auth import (verify_password, create_access_token, get_password_hash,
                  get_current_user, oauth2_scheme, settings)
from jose import jwt, JWTError
from datetime import datetime as _dt
import models
import rbac
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "sales_agent"
    language: Optional[str] = "en"

@router.post("/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # ── Brute-force lockout (P0): this endpoint authenticates staff AND clients and is
    # publicly reachable — throttle before verifying any password. Admin accounts move
    # real money, so they must not be brute-forceable. ──
    ident = (form_data.username or "").strip()
    ip = login_guard.client_ip(request)
    login_guard.check_and_raise(db, ident, ip)

    # ── STAFF first: the same email can ONLY be a staff user if it's in `users` ──
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if user:
        if not verify_password(form_data.password, user.hashed_password):
            login_guard.record(db, ident, ip, ok=False)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Account is disabled")
        login_guard.record(db, ident, ip, ok=True)
        token = create_access_token(data={"sub": user.email, "role": user.role, "user_type": "staff"})
        return {
            "access_token": token, "token_type": "bearer",
            "user": {
                "id": user.id, "full_name": user.full_name, "email": user.email,
                "role": user.role, "user_type": "staff", "language": user.language,
                "extension": user.extension or "",
                "must_change_password": bool(getattr(user, "must_change_password", False)),
                "can_reassign_agent": rbac.may_reassign_agent(user),
            }
        }

    # ── Not staff → CLIENT PORTAL: authenticate against the clients table (by email) ──
    crow = db.execute(text("""
        SELECT login, name, email, password_hash
        FROM clients
        WHERE LOWER(email) = LOWER(:e) AND COALESCE(password_hash,'') <> ''
        ORDER BY COALESCE(total_deposits,0) DESC, login ASC
        LIMIT 1
    """), {"e": form_data.username}).fetchone()
    if crow and verify_password(form_data.password, crow[3]):
        login_guard.record(db, ident, ip, ok=True)
        token = create_access_token(data={"sub": crow[2] or f"client{crow[0]}",
                                           "role": "client", "user_type": "client", "login": crow[0]})
        return {
            "access_token": token, "token_type": "bearer",
            "user": {
                "id": crow[0], "login": crow[0], "full_name": crow[1] or crow[2] or f"#{crow[0]}",
                "email": crow[2] or "", "role": "client", "user_type": "client",
                "must_change_password": False, "can_reassign_agent": False,
            }
        }
    login_guard.record(db, ident, ip, ok=False)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

# Roles a caller may assign when creating a staff account. Only super_admin may mint
# another super_admin; everything else is a normal staff role.
ASSIGNABLE_ROLES = {
    "sales_agent", "sales_manager", "team_leader", "sales_director",
    "support", "accountant", "admin", "super_admin",
}

@router.post("/register")
def register(user_data: UserCreate, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    """Create a staff account. ADMIN-ONLY — previously this was public and let anyone
    self-assign role=super_admin (full-system takeover). Now gated: only admins may call it,
    and the requested role is validated against an allowlist."""
    caller_role = (current_user.role or "").lower()
    if caller_role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can create staff accounts.")
    requested_role = (user_data.role or "sales_agent").lower()
    if requested_role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {user_data.role}")
    # Non-super-admins cannot mint a super_admin (privilege escalation guard).
    if requested_role == "super_admin" and caller_role != "super_admin":
        raise HTTPException(status_code=403, detail="Only a super_admin can create a super_admin.")
    existing = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = get_password_hash(user_data.password)
    user = models.User(
        full_name=user_data.full_name,
        email=user_data.email,
        hashed_password=hashed,
        phone=user_data.phone,
        role=requested_role,
        language=user_data.language
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User created successfully", "id": user.id}

@router.get("/me")
def get_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    _401 = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise _401

    # ── CLIENT token -> resolve from clients table ──
    if payload.get("user_type") == "client":
        login = payload.get("login")
        crow = db.execute(text("SELECT login, name, email FROM clients WHERE login=:l"), {"l": login}).fetchone()
        if not crow:
            raise _401
        return {
            "id": crow[0], "login": crow[0], "full_name": crow[1] or crow[2] or f"#{crow[0]}",
            "email": crow[2] or "", "role": "client", "user_type": "client",
            "must_change_password": False, "can_reassign_agent": False,
        }

    # ── STAFF token -> resolve from users (with the password-change session check) ──
    user = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
    if user is None:
        raise _401
    tva = getattr(user, "tokens_valid_after", None)
    if tva is not None:
        iat = payload.get("iat")
        tva_cmp = tva.replace(tzinfo=None) if tva.tzinfo else tva
        if iat is None or _dt.utcfromtimestamp(iat) < tva_cmp:
            raise _401
    # team-leader/manager scope context: powers the "My own data" toggle + section gating
    try:
        import rbac
        _is_lead = rbac.is_team_lead(db, user)
        _smode, _ssecs = rbac._overrides(db, user.id)
    except Exception:
        db.rollback(); _is_lead, _smode, _ssecs = False, "team", set()
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email,
        "role": user.role, "user_type": "staff", "language": user.language,
        "is_active": user.is_active, "extension": user.extension or "",
        "department": getattr(user, "department", None),
        "title": getattr(user, "title", "") or "",
        # team-lead flag -> frontend shows the "My own data" toggle on list pages; scope_mode/sections
        # let it hide pages a restricted leader can't see.
        "is_team_lead": bool(_is_lead),
        "scope_mode": _smode,
        "scope_sections": sorted(_ssecs),
        # per-user nav override ("small admin" granted specific pages). Empty -> role-based nav.
        "nav_keys": (db.execute(text("SELECT nav_keys FROM users WHERE id=:id"), {"id": user.id}).scalar() or ""),
        # when impersonating, never force a password change — the admin just wants to SEE the CRM
        "must_change_password": bool(getattr(user, "must_change_password", False)) and not payload.get("imp"),
        "can_reassign_agent": rbac.may_reassign_agent(user),
        # impersonation context (admin viewing the CRM AS this user, read-only)
        "impersonating": bool(payload.get("imp")),
        "impersonator_name": payload.get("imp_by_name") or "",
        "can_impersonate": (user.role or "").lower() in IMPERSONATE_ROLES and not payload.get("imp"),
    }


# roles allowed to "View as" another staff member (see the CRM through their eyes, read-only)
IMPERSONATE_ROLES = {"super_admin", "admin", "director"}


@router.post("/impersonate/{user_id}")
def impersonate(user_id: int, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    """Issue a READ-ONLY token that makes the CRM behave as `user_id` (their role + RBAC scope).
    Only admins/directors may do this, and an impersonation token can't impersonate again."""
    if (current_user.role or "").lower() not in IMPERSONATE_ROLES:
        raise HTTPException(status_code=403, detail="You don't have permission to view as another user.")
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="That's already you.")
    from datetime import timedelta
    token = create_access_token(
        {"sub": target.email, "imp": True, "imp_by": current_user.id,
         "imp_by_name": current_user.full_name},
        expires_delta=timedelta(hours=8),
    )
    return {
        "access_token": token, "token_type": "bearer",
        "impersonating": {"id": target.id, "name": target.full_name,
                          "role": target.role, "email": target.email},
    }


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
def change_password(data: ChangePassword, db: Session = Depends(get_db),
                    current_user = Depends(get_current_user)):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password or "") < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if verify_password(data.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from the current one")
    current_user.hashed_password = get_password_hash(data.new_password)
    current_user.must_change_password = False
    # Invalidate every existing session for this account, then hand back a fresh token so
    # the person who just changed their own password isn't kicked out mid-action.
    from datetime import datetime as _dt
    current_user.tokens_valid_after = _dt.utcnow()
    db.commit()
    from auth import create_access_token
    new_token = create_access_token({"sub": current_user.email})
    return {"message": "Password changed successfully", "access_token": new_token, "token_type": "bearer"}