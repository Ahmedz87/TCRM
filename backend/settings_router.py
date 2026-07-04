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


# ───────────────────────── ARCHIVE (clients + leads) ─────────────────────────
from sqlalchemy import text  # noqa: E402


@router.get("/archive/leads")
def archive_leads(search: str = "", limit: int = 200, offset: int = 0,
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Archived leads (is_archived=TRUE) with their owning sales agent + details. Read-only list."""
    where = ["COALESCE(l.is_archived, FALSE) = TRUE"]
    params = {"lim": min(int(limit or 200), 500), "off": max(int(offset or 0), 0)}
    if search:
        where.append("(l.full_name ILIKE :q OR l.email ILIKE :q OR l.phone ILIKE :q)")
        params["q"] = f"%{search}%"
    wc = " AND ".join(where)
    # USER-WISE: one row per person (customer_no), de-duping multiple lead submissions of the same person.
    grp = "COALESCE(l.customer_no, 'L'||l.id)"
    total = db.execute(text(f"SELECT COUNT(DISTINCT {grp}) FROM leads l WHERE {wc}"), params).scalar() or 0
    rows = db.execute(text(f"""
        SELECT MIN(l.id) AS id, MAX(l.full_name) AS name, MAX(l.email) AS email, MAX(l.phone) AS phone,
               MAX(l.country) AS country, MAX(l.source) AS source, MAX(l.campaign_name) AS campaign,
               MAX(l.score) AS score, MAX(l.match_badge) AS match_badge,
               bool_or(COALESCE(l.reactivated_from_archive,FALSE)) AS reactivated,
               MAX(u.full_name) AS agent, MAX(l.legacy_sales_agent) AS legacy_agent,
               MAX(l.updated_at) AS updated_at, MIN(l.created_at) AS created_at, COUNT(*) AS n_subs
        FROM leads l LEFT JOIN users u ON u.id = l.assigned_agent_id
        WHERE {wc}
        GROUP BY {grp}
        ORDER BY MAX(l.updated_at) DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), params).fetchall()
    return {"total": int(total), "leads": [{
        "id": r[0], "name": r[1] or "", "email": r[2] or "", "phone": r[3] or "",
        "country": r[4] or "", "source": r[5] or "", "campaign": r[6] or "",
        "score": r[7], "match_badge": r[8] or "", "reactivated": bool(r[9]),
        "agent": r[10] or r[11] or "—", "updated_at": str(r[12] or ""), "created_at": str(r[13] or ""),
        "n_subs": r[14],
    } for r in rows]}


@router.get("/archive/clients")
def archive_clients(search: str = "", limit: int = 200, offset: int = 0,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """USER-archived clients (admin/TradeSoft decision — not interested / a problem), with their
    owning sales agent + first-deposit + last-activity. NOT the MT account-archive (that's a per-
    account tag on the Clients page); this is the person-level archive."""
    where = ["COALESCE(c.user_archived, FALSE) = TRUE"]
    params = {"lim": min(int(limit or 200), 500), "off": max(int(offset or 0), 0)}
    if search:
        where.append("(c.name ILIKE :q OR c.email ILIKE :q OR c.phone ILIKE :q OR CAST(c.login AS TEXT)=:s)")
        params["q"] = f"%{search}%"; params["s"] = search
    wc = " AND ".join(where)
    # USER-WISE: aggregate by person (customer_no), not per trading account. One row = one client,
    # their accounts' balances/deposits summed, all platforms combined.
    grp = "COALESCE(c.customer_no, 'L'||c.login)"
    total = db.execute(text(f"SELECT COUNT(DISTINCT {grp}) FROM clients c WHERE {wc}"), params).scalar() or 0
    rows = db.execute(text(f"""
        SELECT MIN(c.login) AS login, MAX(c.name) AS name, MAX(c.email) AS email, MAX(c.phone) AS phone,
               MAX(c.country) AS country,
               string_agg(DISTINCT COALESCE(NULLIF(c.platform,''),'MT5'), ', ') AS platform,
               SUM(COALESCE(c.balance,0)) AS balance, SUM(COALESCE(c.total_deposits,0)) AS deposits,
               MAX(c.user_archived_at) AS archived_at,
               bool_or(COALESCE(c.reactivated_from_archive,FALSE)) AS reactivated,
               MAX(u.full_name) AS agent, MAX(c.legacy_sales_agent) AS legacy_agent,
               COUNT(*) AS n_accounts, {grp} AS gkey
        FROM clients c LEFT JOIN users u ON u.id = c.assigned_agent_id
        WHERE {wc}
        GROUP BY {grp}
        ORDER BY MAX(c.user_archived_at) DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), params).fetchall()
    act = _archive_client_activity(db, [r[13] for r in rows])
    return {"total": int(total), "clients": [{
        "id": r[0], "login": r[0], "name": r[1] or "", "email": r[2] or "", "phone": r[3] or "",
        "country": r[4] or "", "platform": r[5] or "MT5", "balance": float(r[6]) if r[6] is not None else None,
        "total_deposits": float(r[7] or 0), "archived_at": str(r[8] or "")[:10], "reactivated": bool(r[9]),
        "agent": r[10] or r[11] or "—", "n_accounts": r[12],
        "first_deposit_date": act.get(r[13], {}).get("first_deposit", ""),
        "last_activity_date": act.get(r[13], {}).get("last_date", ""),
        "last_activity_type": act.get(r[13], {}).get("last_type", ""),
    } for r in rows]}


def _archive_client_activity(db, gkeys):
    """For each person group key (customer_no or 'L'+login), compute first-deposit date and the
    LAST activity across ALL their accounts: deposit / withdrawal / internal transfer (transactions)
    and last trade (deals.deal_time). Mirrors the Clients page (transactions-based) plus real MT
    trading. (mt_last_seen / last_login_at are deliberately NOT used — mt_last_seen is a bulk sync
    stamp, not a real login, and last_login_at isn't populated, so they'd falsely read 'today'.)
    Returns {gkey: {first_deposit, last_date, last_type}}."""
    from datetime import datetime, timezone
    out = {}
    keys = [k for k in gkeys if k]
    if not keys:
        return out
    cnos = [k for k in keys if not (k.startswith("L") and k[1:].isdigit())]
    null_logins = [int(k[1:]) for k in keys if k.startswith("L") and k[1:].isdigit()]
    # login -> gkey
    crows = db.execute(text("""
        SELECT login, COALESCE(customer_no, 'L'||login) AS gkey
        FROM clients WHERE customer_no = ANY(:cnos) OR login = ANY(:nl)
    """), {"cnos": cnos or [''], "nl": null_logins or [0]}).fetchall()
    login_gkey = {}
    def _bump(g, when, typ):
        if not when:
            return
        s = str(when)[:19]
        cur = out.setdefault(g, {"first_deposit": "", "last_date": "", "last_type": ""})
        if s > (cur["last_date"] or ""):
            cur["last_date"] = s; cur["last_type"] = typ
    for login, g in crows:
        login_gkey[login] = g
        out.setdefault(g, {"first_deposit": "", "last_date": "", "last_type": ""})
    logins = list(login_gkey.keys())
    if not logins:
        return out
    # transactions: first deposit + last money movement
    TLABEL = {"deposit": "Deposit", "withdrawal": "Withdrawal", "internal_transfer": "Transfer"}
    for login, tx_type, tx_date in db.execute(text("""
        SELECT login, tx_type, tx_date FROM transactions
        WHERE login = ANY(:ls) AND tx_type IN ('deposit','withdrawal','internal_transfer') AND tx_date IS NOT NULL
    """), {"ls": logins}).fetchall():
        g = login_gkey.get(login)
        if not g:
            continue
        s = str(tx_date)[:19]
        if tx_type == "deposit":
            cur = out[g]
            if not cur["first_deposit"] or s < cur["first_deposit"]:
                cur["first_deposit"] = s
        _bump(g, s, TLABEL.get(tx_type, tx_type))
    # last trade per login (deals.deal_time is epoch seconds)
    for login, last_deal in db.execute(text("""
        SELECT login, MAX(deal_time) FROM deals WHERE login = ANY(:ls) GROUP BY login
    """), {"ls": logins}).fetchall():
        g = login_gkey.get(login)
        if g and last_deal:
            try:
                _bump(g, datetime.fromtimestamp(int(last_deal), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "Trade")
            except Exception:
                pass
    # trim to date for display
    for g, v in out.items():
        v["first_deposit"] = (v["first_deposit"] or "")[:10]
        v["last_date"] = (v["last_date"] or "")[:10]
    return out


@router.post("/archive/sweep")
def archive_sweep(db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Re-capture archived clients who came back (deposited after being archived)."""
    import reactivation
    return reactivation.sweep(db)
