content = '''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import models
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("")
def list_notifications(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT id, title, message, type, link, is_read, created_at
        FROM notifications
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 50
    """), {"uid": current_user.id}).fetchall()
    unread = db.execute(text("""
        SELECT COUNT(*) FROM notifications WHERE user_id = :uid AND is_read = FALSE
    """), {"uid": current_user.id}).scalar()
    return {
        "unread": unread or 0,
        "notifications": [{
            "id": r[0], "title": r[1], "message": r[2], "type": r[3],
            "link": r[4], "is_read": r[5], "created_at": str(r[6])
        } for r in rows]
    }

@router.post("/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE notifications SET is_read = TRUE WHERE id = :id AND user_id = :uid"),
               {"id": notif_id, "uid": current_user.id})
    db.commit()
    return {"ok": True}

@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.execute(text("UPDATE notifications SET is_read = TRUE WHERE user_id = :uid"), {"uid": current_user.id})
    db.commit()
    return {"ok": True}
'''
p = r"C:\broker-crm\backend\routers\notifications_router.py"
open(p, "w", encoding="utf-8").write(content)
print("Created notifications_router.py")

# Register in main.py
mp = r"C:\broker-crm\backend\main.py"
m = open(mp, encoding="utf-8").read()
if "notifications_router" not in m:
    m = m.replace("from routers import auth_router, clients_router",
                  "from routers import auth_router, clients_router, notifications_router")
    # add include
    if "app.include_router(clients_router.router)" in m:
        m = m.replace("app.include_router(clients_router.router)",
                      "app.include_router(clients_router.router)\napp.include_router(notifications_router.router)")
    open(mp, "w", encoding="utf-8").write(m)
    print("Registered in main.py")
else:
    print("Already registered")
