"""
users_router.py — User and role management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from database import get_db, SessionLocal
from auth import get_current_user, get_password_hash
import models
import user_permissions_catalog as PERMS

router = APIRouter(prefix="/users", tags=["Users"])

# management actions (edit/freeze/block/permissions) require an admin-level role
MGR_ROLES = ("super_admin", "admin", "director")


def _is_mgr(user) -> bool:
    return getattr(user, "role", "") in MGR_ROLES


def _require_mgr(user):
    if not _is_mgr(user):
        raise HTTPException(status_code=403, detail="Not authorized")


def _ensure_user_schema():
    """Add the columns/table the user-management actions need (freeze/block + per-user
    permissions). Additive + idempotent; runs once at import."""
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout = '4s'"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_frozen BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE"))
        # avatar_url may be a short VARCHAR — widen to TEXT so a data-URL photo fits
        db.execute(text("ALTER TABLE users ALTER COLUMN avatar_url TYPE TEXT"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id  INT NOT NULL,
                perm_key VARCHAR(80) NOT NULL,
                PRIMARY KEY (user_id, perm_key)
            )
        """))
        # positions = named job roles with a DEFAULT rule set (can be created/edited and applied)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS staff_positions (
                id         SERIAL PRIMARY KEY,
                name       VARCHAR(80) UNIQUE NOT NULL,
                perm_keys  TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # per-user team-leader/manager scope override (see rbac.py)
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS scope_mode VARCHAR(10)"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS scope_sections TEXT"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_ensure_user_schema()


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
    role: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # raw select so we can include the management fields (phone/department/avatar/freeze/block)
    # regardless of the ORM model, plus the assigned-clients count.
    # `role` filter honored (Leads assign-agent dropdown sends role=sales_agent — was ignored,
    # listing all ~100 staff as assignment targets).
    _rf, _params = "", {}
    if role:
        _rf = "WHERE u.role = ANY(:roles)"
        _params["roles"] = [r.strip() for r in role.split(",") if r.strip()]
    rows = db.execute(text(f"""
        SELECT u.id, u.full_name, u.email, u.phone, u.role, u.department, u.title,
               u.avatar_url, u.is_active, COALESCE(u.is_frozen, FALSE), COALESCE(u.is_blocked, FALSE),
               u.last_login_at, u.created_at,
               (SELECT COUNT(*) FROM client_assignments ca WHERE ca.agent_id = u.id) AS clients_assigned,
               (SELECT COUNT(*) FROM user_permissions up WHERE up.user_id = u.id) AS perm_count
        FROM users u
        {_rf}
        ORDER BY u.created_at DESC NULLS LAST, u.id DESC
    """), _params).fetchall()
    return {
        "users": [{
            "id":               r[0],
            "full_name":        r[1],
            "email":            r[2],
            "phone":            r[3] or "",
            "role":             r[4],
            "department":       r[5] or "",
            "title":            r[6] or "",
            "avatar_url":       r[7] or "",
            "is_active":        r[8],
            "is_frozen":        r[9],
            "is_blocked":       r[10],
            "created_at":       r[12].isoformat() if r[12] else "",
            "last_login":       r[11].isoformat() if r[11] else None,
            "clients_assigned": int(r[13] or 0),
            "perm_count":       int(r[14] or 0),
        } for r in rows]
    }


@router.post("")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="Not authorized")
    # only a super_admin may mint another super_admin
    if data.role == 'super_admin' and current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="Only a super admin can create super admins")
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
    _old_role = user.role
    if data.full_name: user.full_name = data.full_name
    if data.email:     user.email     = data.email
    if data.role:
        # only a super_admin may promote to (or demote) a super_admin
        if (data.role == 'super_admin' or user.role == 'super_admin') and current_user.role != 'super_admin':
            raise HTTPException(status_code=403, detail="Only a super admin can change super-admin roles")
        user.role = data.role
    if data.password:  user.hashed_password = get_password_hash(data.password)
    db.commit()
    if data.role and data.role != _old_role:
        import audit
        audit.log(db, current_user, "role_change", "user", user_id, old=_old_role, new=data.role)
    if data.password:
        import audit
        audit.log(db, current_user, "password_reset_by_admin", "user", user_id)
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


# ───────────────────────── ROW ACTIONS (the Action dropdown) ─────────────────────────
class FieldUpdate(BaseModel):
    value: str = ""

class FlagUpdate(BaseModel):
    on: bool = True

class PhotoUpload(BaseModel):
    image: str = ""        # data URL or base64 (stored on users.avatar_url)


def _get_user(db, user_id):
    u = db.execute(text("SELECT id FROM users WHERE id=:i"), {"i": user_id}).fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/{user_id}/email")
def change_email(user_id: int, data: FieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    email = (data.value or "").strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    dup = db.execute(text("SELECT id FROM users WHERE LOWER(email)=:e AND id<>:i"), {"e": email, "i": user_id}).fetchone()
    if dup:
        raise HTTPException(status_code=400, detail="That email is already used by another user")
    db.execute(text("UPDATE users SET email=:e, updated_at=NOW() WHERE id=:i"), {"e": email, "i": user_id}); db.commit()
    return {"ok": True, "message": "Email updated"}


@router.post("/{user_id}/phone")
def change_phone(user_id: int, data: FieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    db.execute(text("UPDATE users SET phone=:p, updated_at=NOW() WHERE id=:i"), {"p": (data.value or "").strip()[:40], "i": user_id}); db.commit()
    return {"ok": True, "message": "Phone updated"}


@router.post("/{user_id}/department")
def change_department(user_id: int, data: FieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    db.execute(text("UPDATE users SET department=:d, updated_at=NOW() WHERE id=:i"), {"d": (data.value or "").strip()[:80], "i": user_id}); db.commit()
    return {"ok": True, "message": "Department updated"}


@router.post("/{user_id}/title")
def change_title(user_id: int, data: FieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Change a user's POSITION (title). If the title matches a defined position, its default
    rules can be applied separately via /apply-position."""
    _require_mgr(current_user); _get_user(db, user_id)
    db.execute(text("UPDATE users SET title=:t, updated_at=NOW() WHERE id=:i"),
               {"t": (data.value or "").strip()[:80], "i": user_id}); db.commit()
    return {"ok": True, "message": "Position updated"}


@router.post("/{user_id}/photo")
def upload_photo(user_id: int, data: PhotoUpload, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    img = (data.image or "").strip()
    if img and not (img.startswith("data:image/") or len(img) > 32):
        raise HTTPException(status_code=400, detail="Invalid image")
    # cap ~5MB of base64 so a huge upload can't bloat the row
    if len(img) > 5_000_000:
        raise HTTPException(status_code=413, detail="Image too large (max ~3.5MB)")
    db.execute(text("UPDATE users SET avatar_url=:a, updated_at=NOW() WHERE id=:i"), {"a": img or None, "i": user_id}); db.commit()
    return {"ok": True, "message": "Photo updated"}


@router.post("/{user_id}/freeze")
def freeze_user(user_id: int, data: FlagUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't freeze your own account")
    db.execute(text("UPDATE users SET is_frozen=:b, updated_at=NOW() WHERE id=:i"), {"b": bool(data.on), "i": user_id}); db.commit()
    return {"ok": True, "message": "Account frozen" if data.on else "Account unfrozen"}


@router.post("/{user_id}/block")
def block_user(user_id: int, data: FlagUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't block your own account")
    # block also invalidates existing sessions (tokens issued before now are rejected)
    db.execute(text("UPDATE users SET is_blocked=:b, is_active=:act, tokens_valid_after=NOW(), updated_at=NOW() WHERE id=:i"),
               {"b": bool(data.on), "act": (not data.on), "i": user_id}); db.commit()
    return {"ok": True, "message": "User blocked" if data.on else "User unblocked"}


# ───────────────────────── PERMISSIONS (the rules page) ─────────────────────────
class PermSave(BaseModel):
    keys: List[str] = []


@router.get("/permissions/catalog")
def permissions_catalog(current_user=Depends(get_current_user)):
    """The full grouped permission catalog (35 categories, ~320 perms) for the editor grid."""
    return {"catalog": PERMS.CATALOG, "total": len(PERMS.ALL_KEYS)}


@router.get("/{user_id}/permissions")
def get_user_permissions(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _get_user(db, user_id)
    rows = db.execute(text("SELECT perm_key FROM user_permissions WHERE user_id=:i"), {"i": user_id}).fetchall()
    return {"granted": [r[0] for r in rows]}


@router.post("/{user_id}/permissions")
def set_user_permissions(user_id: int, data: PermSave, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user); _get_user(db, user_id)
    # only accept known catalog keys; replace the whole set
    keys = sorted({k for k in (data.keys or []) if k in PERMS.ALL_KEYS})
    db.execute(text("DELETE FROM user_permissions WHERE user_id=:i"), {"i": user_id})
    if keys:
        db.execute(text("INSERT INTO user_permissions (user_id, perm_key) "
                        "SELECT :i, unnest(:ks) ON CONFLICT DO NOTHING"),
                   {"i": user_id, "ks": keys})
    db.commit()
    return {"ok": True, "granted": keys, "count": len(keys)}


# ───────────────────────── DELETE USER ─────────────────────────
@router.post("/{user_id}/delete")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Hard-delete a staff user. Re-parents their team to this user's manager, unassigns their
    clients/leads, and clears their permissions. Guarded: not self, super_admins only by super_admins."""
    if current_user.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="Not authorized")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    row = db.execute(text("SELECT role, manager_id FROM users WHERE id=:i"), {"i": user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if (row[0] or "").lower() == 'super_admin' and current_user.role != 'super_admin':
        raise HTTPException(status_code=403, detail="Only a super admin can delete a super admin")
    parent = row[1]
    # detach dependents so nothing is orphaned/broken
    db.execute(text("UPDATE users SET manager_id=:p WHERE manager_id=:i"), {"p": parent, "i": user_id})
    for tbl in ("clients", "leads"):
        try:
            db.execute(text(f"UPDATE {tbl} SET assigned_agent_id=NULL WHERE assigned_agent_id=:i"), {"i": user_id})
        except Exception:
            db.rollback()
    for tbl in ("user_permissions",):
        db.execute(text(f"DELETE FROM {tbl} WHERE user_id=:i"), {"i": user_id})
    db.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})
    db.commit()
    return {"ok": True, "message": "User deleted"}


# ───────────────────────── TEAM-LEADER / MANAGER SCOPE ─────────────────────────
class ScopeSave(BaseModel):
    scope_mode: str = "team"           # team | self | none
    sections:   List[str] = []          # clients,leads,ibs,calls  (empty = all)


@router.get("/{user_id}/scope")
def get_user_scope(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    r = db.execute(text("SELECT COALESCE(scope_mode,'team'), COALESCE(scope_sections,'') FROM users WHERE id=:i"),
                   {"i": user_id}).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="User not found")
    return {"scope_mode": r[0] or "team",
            "sections": [s for s in (r[1] or "").split(",") if s]}


@router.post("/{user_id}/scope")
def set_user_scope(user_id: int, data: ScopeSave, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Customise what a team leader / sales manager may see (requirement #2):
      scope_mode: team (self+team) | self (only own book) | none (sees nothing)
      sections:   which pages they can access — clients/leads/ibs/calls (empty = all)."""
    _require_mgr(current_user); _get_user(db, user_id)
    mode = (data.scope_mode or "team").strip().lower()
    if mode not in ("team", "self", "none"):
        mode = "team"
    valid = {"clients", "leads", "ibs", "calls"}
    secs = ",".join([s.strip().lower() for s in (data.sections or []) if s.strip().lower() in valid])
    db.execute(text("UPDATE users SET scope_mode=:m, scope_sections=:s, updated_at=NOW() WHERE id=:i"),
               {"m": mode, "s": secs, "i": user_id})
    db.commit()
    return {"ok": True, "scope_mode": mode, "sections": [s for s in secs.split(",") if s]}


# ───────────────────────── POSITIONS (named default rule sets) ─────────────────────────
class PositionSave(BaseModel):
    name: str = ""
    keys: List[str] = []


@router.get("/positions")
def list_positions(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("SELECT id, name, COALESCE(perm_keys,''), created_at FROM staff_positions ORDER BY name")).fetchall()
    # also the distinct titles already in use, so the editor can offer them
    used = [r[0] for r in db.execute(text("SELECT DISTINCT title FROM users WHERE COALESCE(title,'')<>'' ORDER BY title")).fetchall()]
    return {"positions": [{
        "id": r[0], "name": r[1], "keys": [k for k in (r[2] or "").split(",") if k],
        "count": len([k for k in (r[2] or "").split(",") if k]),
    } for r in rows], "used_titles": used}


@router.post("/positions/save")
def upsert_position(data: PositionSave, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Create a new position or edit an existing one's default rules (by name)."""
    _require_mgr(current_user)
    name = (data.name or "").strip()[:80]
    if not name:
        raise HTTPException(status_code=400, detail="Position name required")
    keys = sorted({k for k in (data.keys or []) if k in PERMS.ALL_KEYS})
    db.execute(text("""INSERT INTO staff_positions (name, perm_keys) VALUES (:n, :k)
                       ON CONFLICT (name) DO UPDATE SET perm_keys=EXCLUDED.perm_keys"""),
               {"n": name, "k": ",".join(keys)})
    db.commit()
    return {"ok": True, "name": name, "count": len(keys)}


@router.post("/positions/{pos_id}/delete")
def delete_position(pos_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_mgr(current_user)
    db.execute(text("DELETE FROM staff_positions WHERE id=:i"), {"i": pos_id}); db.commit()
    return {"ok": True}


@router.post("/{user_id}/apply-position")
def apply_position(user_id: int, data: FieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Set the user's title to the position AND replace their permission rules with the
    position's default rule set (value = position name)."""
    _require_mgr(current_user); _get_user(db, user_id)
    name = (data.value or "").strip()
    pos = db.execute(text("SELECT perm_keys FROM staff_positions WHERE name=:n"), {"n": name}).fetchone()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    keys = sorted({k for k in (pos[0] or "").split(",") if k in PERMS.ALL_KEYS})
    db.execute(text("UPDATE users SET title=:t, updated_at=NOW() WHERE id=:i"), {"t": name[:80], "i": user_id})
    db.execute(text("DELETE FROM user_permissions WHERE user_id=:i"), {"i": user_id})
    if keys:
        db.execute(text("INSERT INTO user_permissions (user_id, perm_key) SELECT :i, unnest(:ks) ON CONFLICT DO NOTHING"),
                   {"i": user_id, "ks": keys})
    db.commit()
    return {"ok": True, "title": name, "applied_rules": len(keys)}
