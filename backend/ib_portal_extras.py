"""
ib_portal_extras.py — the remaining partner-portal features (Jul 15 2026):
  · notifications (in-portal bell)          · commission statement CSV
  · sub-IB override earnings                · profile edit + photo upload
  · IB agreement text + acceptance          · admin "IB Requests" queue (IB-manager acts,
                                              sales-manager reads)

Auth reuses ib_portal_auth: staff_or_own_ib (portal reads), get_current_staff (admin queue).
Everything is additive (CREATE TABLE IF NOT EXISTS) — safe on the live DB.
"""
import csv
import io
import os
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from ib_portal_auth import staff_or_own_ib, get_current_staff

router = APIRouter(prefix="/ibs", tags=["IB Portal Extras"])
padmin = APIRouter(prefix="/ib-admin", tags=["IB Admin Extras"])
pub = APIRouter(tags=["IB Public"])   # no prefix — avoids /ibs/{ib_id} collision

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "ib_photos")

_READY = False


def ensure_tables(db: Session):
    global _READY
    if _READY:
        return
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_notifications (
            id SERIAL PRIMARY KEY,
            ib_id INTEGER NOT NULL,
            kind VARCHAR(32),
            title VARCHAR(200),
            body TEXT,
            read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_ib_notif_ib ON ib_notifications (ib_id, read, created_at DESC);
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS photo_url VARCHAR(300);
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS agreement_accepted_at TIMESTAMPTZ;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS agreement_version VARCHAR(20);
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS bio TEXT;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS social_links JSONB;
        ALTER TABLE ibs ADD COLUMN IF NOT EXISTS applicant_profile JSONB;
    """))
    db.commit()
    _READY = True


def notify(db: Session, ib_id: int, kind: str, title: str, body: str = ""):
    """Emit an in-portal notification. Called from payout/challenge/promotion actions."""
    try:
        ensure_tables(db)
        db.execute(text("""INSERT INTO ib_notifications (ib_id, kind, title, body)
                           VALUES (:i,:k,:t,:b)"""),
                   {"i": ib_id, "k": kind[:32], "t": title[:200], "b": body})
        db.commit()
    except Exception:
        db.rollback()


# ── Notifications (portal bell) ───────────────────────────────────────────────
@router.get("/{ib_id}/notifications")
def list_notifications(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    ensure_tables(db)
    rows = db.execute(text("""SELECT id, kind, title, body, read, created_at
        FROM ib_notifications WHERE ib_id=:i ORDER BY created_at DESC LIMIT 50"""), {"i": ib_id}).fetchall()
    unread = db.execute(text("SELECT COUNT(*) FROM ib_notifications WHERE ib_id=:i AND NOT read"),
                        {"i": ib_id}).scalar() or 0
    return {"unread": int(unread), "items": [{
        "id": r[0], "kind": r[1] or "", "title": r[2] or "", "body": r[3] or "",
        "read": bool(r[4]), "at": r[5].isoformat() if r[5] else None} for r in rows]}


@router.post("/{ib_id}/notifications/read")
def mark_read(ib_id: int, data: dict = None, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    ensure_tables(db)
    db.execute(text("UPDATE ib_notifications SET read=TRUE WHERE ib_id=:i AND NOT read"), {"i": ib_id})
    db.commit()
    return {"ok": True}


# ── Announcements (desk → all IBs) ────────────────────────────────────────────
def _ensure_ann(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS ib_announcements (
        id SERIAL PRIMARY KEY, title VARCHAR(200), body TEXT, tone VARCHAR(16) DEFAULT 'info',
        active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.commit()


@router.get("/{ib_id}/announcements")
def portal_announcements(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    _ensure_ann(db)
    rows = db.execute(text("""SELECT id, title, body, tone, created_at FROM ib_announcements
        WHERE active ORDER BY created_at DESC LIMIT 10""")).fetchall()
    return {"items": [{"id": r[0], "title": r[1] or "", "body": r[2] or "", "tone": r[3] or "info",
                       "at": r[4].isoformat() if r[4] else None} for r in rows]}


@padmin.get("/announcements")
def admin_announcements(db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    _ensure_ann(db)
    rows = db.execute(text("SELECT id, title, body, tone, active, created_at FROM ib_announcements ORDER BY created_at DESC LIMIT 50")).fetchall()
    return {"items": [{"id": r[0], "title": r[1], "body": r[2], "tone": r[3], "active": r[4],
                       "at": r[5].isoformat() if r[5] else None} for r in rows]}


@padmin.post("/announcements")
def create_announcement(data: dict, db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    if (getattr(staff, "role", "") or "") not in ("super_admin", "admin", "director", "sales_manager", "ib_manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    _ensure_ann(db)
    aid = data.get("id")
    if data.get("delete") and aid:
        db.execute(text("UPDATE ib_announcements SET active=FALSE WHERE id=:i"), {"i": aid}); db.commit()
        return {"ok": True}
    db.execute(text("""INSERT INTO ib_announcements (title, body, tone) VALUES (:t,:b,:tone)"""),
               {"t": (data.get("title") or "").strip()[:200], "b": (data.get("body") or "").strip(),
                "tone": data.get("tone") or "info"})
    db.commit()
    return {"ok": True}


# ── Client drill-down (privacy-safe: account activity, NO extra PII) ───────────
@router.get("/{ib_id}/client/{login}")
def client_detail(ib_id: int, login: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    """Trade timeline + deposit summary for ONE of the IB's accounts. Confirms the account is
    under this IB first; returns no contact info the IB shouldn't see."""
    ib = db.execute(text("SELECT ext_ib_id FROM ibs WHERE id=:i"), {"i": ib_id}).fetchone()
    owns = db.execute(text("""SELECT c.name, c.country, c.group_name, COALESCE(c.platform,'MT5'), c.is_nda
        FROM clients c WHERE c.login=:l AND c.agent IN (
            SELECT agent_id FROM ibs WHERE id=:i OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id=:ext)) LIMIT 1"""),
        {"l": login, "i": ib_id, "ext": ib[0] if ib else None}).fetchone()
    if not owns:
        raise HTTPException(status_code=404, detail="That account is not under your IB")
    # deposits/withdrawals must match the AUTHORITATIVE Clients-page totals (update_client_totals):
    # cap huge balance-adjustment rows, drop bonus/fix/adjust-noted deposits, and EXCLUDE REJECTED
    # withdrawals (this view used to sum every 'withdrawal' row incl. rejected → over-reported).
    dep = db.execute(text("""SELECT
        COALESCE(SUM(CASE WHEN tx_type='deposit' AND amount<1000000
            AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust' THEN amount ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN tx_type='withdrawal' AND amount<1000000
            AND COALESCE(status,'')<>'rejected' THEN amount ELSE 0 END),0),
        MIN(CASE WHEN tx_type='deposit' THEN tx_date END) FROM transactions WHERE login=:l"""),
        {"l": login}).fetchone()
    trades = [{"date": str(r[0] or "")[:16].replace('T', ' '), "symbol": r[1], "side": "BUY" if str(r[2]).startswith('0') else "SELL",
               "lots": round(float(r[3] or 0) / 10000.0, 2)} for r in db.execute(text("""
        SELECT deal_date, symbol, action, volume FROM deals
        WHERE login=:l AND action IN (0,1) AND volume>0 ORDER BY NULLIF(deal_date,'') DESC LIMIT 40"""),
        {"l": login}).fetchall()]
    # lots from the OVERLAID ib_trades (the SAME source the client list uses): normalised across
    # MT4/MT5 and counts each trade ONCE. deals.volume/10000 double-counts the open+close legs (2×)
    # and is wrong-scaled for MT4 — that's why the drill-down showed 2× the list's lots.
    lots = db.execute(text("SELECT COALESCE(SUM(lots),0) FROM ib_trades WHERE login=:l"),
                      {"l": login}).scalar() or 0
    return {"login": login, "name": owns[0] or "", "country": owns[1] or "",
            "type": (owns[2] or ""), "platform": owns[3], "is_nda": bool(owns[4]),
            "deposits": float(dep[0] or 0), "withdrawals": float(dep[1] or 0),
            "first_deposit": str(dep[2] or "")[:10], "total_lots": round(float(lots), 1), "trades": trades}


# ── Marketing analytics — clicks → signups → funded, by source ────────────────
@router.get("/{ib_id}/campaign-analytics")
def campaign_analytics(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    if not db.execute(text("SELECT to_regclass('public.ib_ref_clicks')")).scalar():
        return {"funnel": {}, "by_source": [], "daily": []}
    clicks = db.execute(text("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_unique) FROM ib_ref_clicks WHERE ib_id=:i"), {"i": ib_id}).fetchone()
    signups = db.execute(text("SELECT COUNT(*) FROM ib_ref_signups WHERE ib_id=:i"), {"i": ib_id}).scalar() or 0
    by_src = [{"src": r[0] or "direct", "clicks": r[1], "signups": r[2]} for r in db.execute(text("""
        WITH cl AS (
            SELECT COALESCE(NULLIF(src,''),'direct') s, COUNT(*) c
            FROM ib_ref_clicks WHERE ib_id=:i GROUP BY 1),
        su AS (
            SELECT COALESCE(NULLIF(src,''),'direct') s, COUNT(*) n
            FROM ib_ref_signups WHERE ib_id=:i GROUP BY 1)
        SELECT cl.s, cl.c, COALESCE(su.n,0)
        FROM cl LEFT JOIN su ON su.s = cl.s
        ORDER BY cl.c DESC LIMIT 8"""), {"i": ib_id}).fetchall()]
    daily = [{"day": str(r[0]), "clicks": r[1]} for r in db.execute(text("""
        SELECT to_char(at,'YYYY-MM-DD'), COUNT(*) FROM ib_ref_clicks
        WHERE ib_id=:i AND at >= NOW() - INTERVAL '30 days' GROUP BY 1 ORDER BY 1"""), {"i": ib_id}).fetchall()]
    return {"funnel": {"clicks": clicks[0] or 0, "unique": clicks[1] or 0, "signups": int(signups)},
            "by_source": by_src, "daily": daily}


# ── Auto-withdraw job (Ovadot) — run from the 30-min ib_trades refresh ─────────
def run_auto_withdrawals(db) -> int:
    """Create a Pending Ovadot withdrawal for every IB whose available balance passed their
    threshold. Available = unpaid_commission − pending requests. Notifies the IB."""
    ensure_tables(db)
    # auto_wd_* columns are a one-time migration (Jul 20) — NOT created here per-run (see get_auto_withdraw).
    rows = db.execute(text("""SELECT id, ext_ib_id, name, email, COALESCE(unpaid_commission,0),
        auto_wd_threshold, auto_wd_wallet FROM ibs
        WHERE COALESCE(auto_wd_enabled,FALSE) AND COALESCE(auto_wd_threshold,0) >= 50
          AND COALESCE(auto_wd_wallet,'') <> ''
          AND COALESCE(ib_level,5) >= 6""")).fetchall()   # Level-5 lock: no withdrawals until promoted to 6
    n = 0
    for ib_id, ext, name, email, unpaid, thr, wallet in rows:
        pend = db.execute(text("""SELECT COALESCE(SUM(amount),0) FROM ib_operations
            WHERE status='Pending' AND (ib_id=:i OR (:ext IS NOT NULL AND ext_ib_id=:ext))"""),
            {"i": ib_id, "ext": ext}).scalar() or 0
        avail = round(float(unpaid) - float(pend), 2)
        if avail < float(thr or 0):
            continue
        db.execute(text("""INSERT INTO ib_operations(ext_ib_id, ib_id, name, email, request_type, amount,
            converted_amount, payment_type, status, to_account, comment, op_date, note)
            VALUES(:ext,:id,:nm,:em,'Wallet Withdrawal',:amt,:amt,'Ovadot Wallet','Pending',:w,
                   'auto-withdraw', NOW(), 'auto-created (threshold reached)')"""),
            {"ext": ext, "id": ib_id, "nm": name, "em": email, "amt": avail, "w": wallet})
        notify(db, ib_id, "payout", "Auto-withdrawal created 💸",
               f"Your balance reached ${avail:,.2f} — we've queued a withdrawal to your Ovadot wallet for approval.")
        n += 1
    db.commit()
    return n


# ── Partner Pulse — actionable intelligence for the IB's dashboard ────────────
@router.get("/{ib_id}/insights")
def insights(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    """A ranked list of "do this now" cards computed from the IB's live book. Makes the
    portal feel intelligent + gives the IB a reason to open it every day (desk Jul 15 2026)."""
    from ib_router import period_dates
    from ib_portal_auth import get_tier_reqs
    ib = db.execute(text("SELECT agent_id, ext_ib_id, ib_level, name FROM ibs WHERE id=:i"), {"i": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    agent, ext, level = ib[0], ib[1], (ib[2] or 5)
    # sibling agent set (same as get_ib)
    agents = [r[0] for r in db.execute(text("""
        SELECT DISTINCT a FROM (
          SELECT agent_id a FROM ibs WHERE id=:i OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id=:ext)
          UNION SELECT :agent
        ) q WHERE a IS NOT NULL"""), {"i": ib_id, "ext": ext, "agent": agent}).fetchall()] or [agent]
    cards = []

    # 1) CHURN — funded clients who've gone quiet (no trade in 14+ days)
    quiet = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT c.login, MAX(NULLIF(d.deal_date,'')) AS last_trade
            FROM clients c JOIN deals d ON d.login=c.login
            WHERE c.agent = ANY(:ag) AND d.action IN (0,1)
            GROUP BY c.login
            HAVING MAX(NULLIF(d.deal_date,'')) < to_char(NOW() - INTERVAL '14 days','YYYY-MM-DD')
               AND MAX(NULLIF(d.deal_date,'')) >= to_char(NOW() - INTERVAL '90 days','YYYY-MM-DD')
        ) x"""), {"ag": agents}).scalar() or 0
    if quiet:
        cards.append({"kind": "churn", "icon": "📵", "tone": "warn",
                      "title": f"{quiet} client{'s' if quiet>1 else ''} went quiet",
                      "body": "Traded before but nothing in the last 14 days — a quick message often brings them back.",
                      "cta": "See trading accounts", "tab": "clients"})

    # 2) HOT LEADS — VERIFIED (profile/KYC/phone/email) but NO deposit yet. These are the warmest
    #    calls: they trusted you enough to verify, they just haven't funded. Suggest one to ring now.
    hot = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE verified) AS n_ver, COUNT(*) AS n_all
        FROM (
          SELECT (COALESCE(l.phone_verified,FALSE) OR COALESCE(l.email_verified,FALSE)
                  OR COALESCE(l.kyc_id_verified,FALSE) OR COALESCE(l.kyc_id_uploaded,FALSE)) AS verified
          FROM leads l JOIN customers cu ON cu.customer_no=l.customer_no
          JOIN ibs i ON LOWER(TRIM(cu.ib))=LOWER(TRIM(i.name))
          WHERE i.id=:i AND NOT EXISTS (SELECT 1 FROM clients c2 WHERE c2.customer_no=l.customer_no)
        ) x"""), {"i": ib_id}).fetchone()
    n_ver, n_all = (hot[0] or 0) if hot else 0, (hot[1] or 0) if hot else 0
    if n_ver:
        # pick ONE verified, no-deposit lead to suggest calling (newest first)
        pick = db.execute(text("""
          SELECT l.full_name, l.phone FROM leads l JOIN customers cu ON cu.customer_no=l.customer_no
          JOIN ibs i ON LOWER(TRIM(cu.ib))=LOWER(TRIM(i.name))
          WHERE i.id=:i AND COALESCE(NULLIF(l.phone,''),'')<>''
            AND (COALESCE(l.phone_verified,FALSE) OR COALESCE(l.email_verified,FALSE)
                 OR COALESCE(l.kyc_id_verified,FALSE) OR COALESCE(l.kyc_id_uploaded,FALSE))
            AND NOT EXISTS (SELECT 1 FROM clients c2 WHERE c2.customer_no=l.customer_no)
          ORDER BY l.created_at DESC NULLS LAST LIMIT 1"""), {"i": ib_id}).fetchone()
        nm = (pick[0] or "this lead").split(" ")[0] if pick else "this lead"
        ph = pick[1] if pick else ""
        cards.append({"kind": "leads", "icon": "🔥", "tone": "warn",
                      "title": f"{n_ver} verified lead{'s' if n_ver>1 else ''} with no deposit",
                      "body": f"They verified their profile/KYC but haven't funded. Start with {nm}"
                              + (f" — call {ph} now." if ph else "."),
                      "call": ph, "cta": "Call your leads", "tab": "leads"})
    elif n_all:
        cards.append({"kind": "leads", "icon": "📞", "tone": "info",
                      "title": f"{n_all} lead{'s' if n_all>1 else ''} to follow up",
                      "body": "Registered under you but haven't deposited yet. One call can turn them into clients.",
                      "cta": "Call your leads", "tab": "leads"})

    # 3) ALMOST-THERE — closest gap to the next grade (since last promotion baseline)
    try:
        nxt = next((q for q in get_tier_reqs(db) if q["level"] == level + 1), None)
        if nxt:
            since = db.execute(text("""SELECT MAX(promo_date) FROM ib_promotions
                WHERE ib_id=:i OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id=:ext)"""),
                {"i": ib_id, "ext": ext}).scalar()
            sf = since.isoformat() if since else "1970-01-01"
            nda = db.execute(text("""SELECT COUNT(*) FROM (
                SELECT DISTINCT ON (c.customer_no) c.customer_no, c.agent, c.is_nda, NULLIF(c.first_deposit_at,'') fd
                FROM clients c WHERE c.agent = ANY(:ag) AND c.customer_no IS NOT NULL
                ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC) t
                WHERE t.agent = ANY(:ag) AND t.is_nda AND t.fd >= :f"""), {"ag": agents, "f": sf}).scalar() or 0
            need = max(0, int(nxt["min_accounts"]) - int(nda))
            if need and need <= max(3, int(nxt["min_accounts"]) * 0.25):
                cards.append({"kind": "promo", "icon": "🏆", "tone": "good",
                              "title": f"{need} new client{'s' if need>1 else ''} from {nxt['name']}",
                              "body": f"You're close to grade {nxt['name']} (${nxt['comm_per_lot']:.0f}/lot). {need} more NDA and your rate goes up.",
                              "cta": "See your progress", "tab": "dashboard"})
    except Exception:
        db.rollback()

    # 4) WEEKLY CHALLENGE — nudge if one is claimable-soon
    try:
        import ib_challenges
        cv = ib_challenges.list_all(db, ib_id)
        ready = [w for w in (cv.get("weekly") or []) if w.get("ready") and not w.get("claimed")]
        close = [w for w in (cv.get("weekly") or []) if not w.get("ready") and (w.get("pct") or 0) >= 50 and not w.get("claimed")]
        if ready:
            tot = sum(w.get("reward", 0) for w in ready)
            cards.append({"kind": "challenge", "icon": "🎁", "tone": "good",
                          "title": f"${tot:.0f} weekly reward ready to claim",
                          "body": "You've completed a weekly challenge — claim it before Sunday's reset.",
                          "cta": "Claim now", "tab": "challenges"})
        elif close:
            w = close[0]
            cards.append({"kind": "challenge", "icon": "⚡", "tone": "info",
                          "title": f"{w.get('pct')}% to a ${w.get('reward',0):.0f} reward",
                          "body": f"'{w.get('name')}' is almost done — a little push claims it this week.",
                          "cta": "See challenges", "tab": "challenges"})
    except Exception:
        db.rollback()

    # 5) BEST CHANNEL — top referral source this month
    try:
        if db.execute(text("SELECT to_regclass('public.ib_ref_clicks')")).scalar():
            top = db.execute(text("""SELECT COALESCE(NULLIF(src,''),'direct'), COUNT(*)
                FROM ib_ref_clicks WHERE ib_id=:i AND at >= date_trunc('month', NOW())
                GROUP BY 1 ORDER BY 2 DESC LIMIT 1"""), {"i": ib_id}).fetchone()
            if top and top[1] >= 3:
                cards.append({"kind": "channel", "icon": "📈", "tone": "info",
                              "title": f"{top[0].title()} is your best channel",
                              "body": f"{top[1]} clicks this month from {top[0]}. Double down where it's working.",
                              "cta": "Share your link", "tab": "campaigns"})
    except Exception:
        db.rollback()

    if not cards:
        cards.append({"kind": "ok", "icon": "✅", "tone": "good", "title": "You're all caught up",
                      "body": "No urgent actions right now. Share your link to keep the pipeline full.",
                      "cta": "Get your link", "tab": "campaigns"})
    return {"cards": cards[:5]}


# ── Leaderboard — ranked by NDA + deposits (volume is a tie-breaker only) ─────
# desk rule Jul 15 2026: reward genuine acquisition (NDA) + funding, NOT churned scalping volume.
LB_W_NDA, LB_W_DEP, LB_W_VOL = 1000.0, 0.01, 0.05   # 1 NDA ≈ $100k deposits ≈ 20k lots


@router.get("/{ib_id}/leaderboard")
def leaderboard(ib_id: int, period: str = "this_month", db: Session = Depends(get_db),
                current_user=Depends(staff_or_own_ib)):
    """Monthly partner leaderboard. Score = NDA×1000 + deposits×0.01 + lots×0.05 (NDA-first).
    Returns the top 15 (anonymised as 'Partner ####' except the caller) + the caller's own rank."""
    from ib_router import period_dates
    from datetime import date as _date, timedelta as _td
    p_from, p_to = period_dates(period, "", "")
    p_next = (_date.fromisoformat(p_to) + _td(days=1)).isoformat()
    # NDA in period per IB agent (first-deposit account new & under that IB), deposits + lots in period.
    rows = db.execute(text("""
        WITH nda AS (
          SELECT c.agent, COUNT(*) AS nda_n FROM (
            SELECT DISTINCT ON (customer_no) customer_no, agent, is_nda, NULLIF(first_deposit_at,'') fd
            FROM clients WHERE customer_no IS NOT NULL
            ORDER BY customer_no, NULLIF(first_deposit_at,'') ASC) c
          WHERE c.is_nda AND c.fd >= :pf AND c.fd < :pn GROUP BY c.agent),
        dep AS (
          SELECT cl.agent, SUM(t.amount) AS dep FROM transactions t JOIN clients cl ON cl.login=t.login
          WHERE t.tx_type='deposit' AND t.tx_date >= :pf AND t.tx_date < :pn GROUP BY cl.agent),
        vol AS (
          SELECT cl.agent, SUM(d.volume/10000.0) AS lots FROM deals d JOIN clients cl ON cl.login=d.login
          WHERE d.action IN (0,1) AND d.volume>0 AND d.deal_date >= :pf AND d.deal_date < :pn GROUP BY cl.agent)
        SELECT i.id, i.name, i.ib_code,
               COALESCE(n.nda_n,0) AS nda, COALESCE(dp.dep,0) AS dep, COALESCE(v.lots,0) AS lots,
               (COALESCE(n.nda_n,0)*:wn + COALESCE(dp.dep,0)*:wd + COALESCE(v.lots,0)*:wv) AS score
        FROM ibs i
        LEFT JOIN nda n ON n.agent=i.agent_id
        LEFT JOIN dep dp ON dp.agent=i.agent_id
        LEFT JOIN vol v ON v.agent=i.agent_id
        WHERE i.agent_id IS NOT NULL AND COALESCE(i.is_primary,TRUE)
          AND (COALESCE(n.nda_n,0)>0 OR COALESCE(dp.dep,0)>0 OR COALESCE(v.lots,0)>0)
        ORDER BY score DESC
    """), {"pf": p_from, "pn": p_next, "wn": LB_W_NDA, "wd": LB_W_DEP, "wv": LB_W_VOL}).fetchall()
    board, my_rank, my_row = [], None, None
    for rank, r in enumerate(rows, 1):
        is_me = (r[0] == ib_id)
        if rank <= 15 or is_me:
            board.append({"rank": rank, "me": is_me,
                          "name": (r[1] or "Partner") if is_me else f"Partner {str(r[2] or r[0])[-4:]}",
                          "nda": int(r[3]), "deposits": float(r[4]), "lots": round(float(r[5]), 1),
                          "score": round(float(r[6]))})
        if is_me:
            my_rank = rank
            my_row = {"rank": rank, "nda": int(r[3]), "deposits": float(r[4]), "lots": round(float(r[5]), 1)}
    board = sorted({b["rank"]: b for b in board}.values(), key=lambda b: b["rank"])
    return {"period": period, "total": len(rows), "my_rank": my_rank, "me": my_row, "board": board}


# ── Auto-withdraw (Ovadot only) ───────────────────────────────────────────────
@router.get("/{ib_id}/auto-withdraw")
def get_auto_withdraw(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    # NOTE: the auto_wd_* columns are a one-time migration (added Jul 20), NOT created per-request.
    # Running ALTER TABLE in the request path took an ACCESS EXCLUSIVE lock on ibs on EVERY call and
    # stormed the whole site under IB-portal load (lock pileup, all pages hung). Never DDL in a handler.
    r = db.execute(text("SELECT auto_wd_enabled, auto_wd_threshold, auto_wd_wallet FROM ibs WHERE id=:i"),
                   {"i": ib_id}).fetchone()
    return {"enabled": bool(r[0]), "threshold": float(r[1] or 0), "wallet": r[2] or "", "method": "Ovadot Wallet"}


@router.post("/{ib_id}/auto-withdraw")
def set_auto_withdraw(ib_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    enabled = bool(data.get("enabled"))
    threshold = float(data.get("threshold") or 0)
    wallet = (data.get("wallet") or "").strip()
    if enabled and (threshold < 50 or not wallet):
        raise HTTPException(status_code=400, detail="Set a threshold of at least $50 and your Ovadot wallet")
    db.execute(text("""UPDATE ibs SET auto_wd_enabled=:e, auto_wd_threshold=:t, auto_wd_wallet=:w WHERE id=:i"""),
               {"e": enabled, "t": threshold, "w": wallet, "i": ib_id})
    db.commit()
    return {"ok": True, "enabled": enabled, "threshold": threshold, "wallet": wallet}


# ── Commission statement CSV ──────────────────────────────────────────────────
@router.get("/{ib_id}/statement.csv")
def statement_csv(ib_id: int, period: str = "all_time", db: Session = Depends(get_db),
                  current_user=Depends(staff_or_own_ib)):
    """Per-client commission statement for the period, as CSV (IBs reconcile like accountants)."""
    from ib_router import period_dates
    from datetime import date as _date, timedelta as _td
    ib = db.execute(text("SELECT name, ib_code, ext_ib_id, agent_id FROM ibs WHERE id=:i"), {"i": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    p_from, p_to = period_dates(period, "", "")
    # close_time is stored as TEXT — compare as strings (like ib_router does), next-day bound in Python
    p_to_next = (_date.fromisoformat(p_to) + _td(days=1)).isoformat()
    rows = db.execute(text("""
        SELECT t.login, MAX(c.name) AS client, COUNT(*) AS trades,
               ROUND(SUM(t.lots)::numeric, 2) AS lots,
               ROUND(SUM(CASE WHEN t.eligible THEN t.commission ELSE 0 END)::numeric, 2) AS commission
        FROM ib_trades t JOIN ibs i ON i.id = t.ib_id
        LEFT JOIN clients c ON c.login = t.login
        WHERE (i.id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND i.ext_ib_id = :ext))
          AND t.close_time >= :pf AND t.close_time < :pn
        GROUP BY t.login ORDER BY commission DESC NULLS LAST
    """), {"ibid": ib_id, "ext": ib[2], "pf": p_from, "pn": p_to_next}).fetchall()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"TNFX Partner commission statement — {ib[0] or ib[1] or ('IB '+str(ib_id))}"])
    w.writerow([f"Period: {p_from} to {p_to}"])
    w.writerow([])
    w.writerow(["Client account", "Client", "Trades", "Lots", "Commission (USD)"])
    tot_l = tot_c = 0.0
    for r in rows:
        w.writerow([r[0], r[1] or "", r[2], float(r[3] or 0), float(r[4] or 0)])
        tot_l += float(r[3] or 0); tot_c += float(r[4] or 0)
    w.writerow([])
    w.writerow(["TOTAL", "", "", round(tot_l, 2), round(tot_c, 2)])
    buf.seek(0)
    fn = f"tnfx-statement-{ib_id}-{period}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={fn}"})


# ── Sub-IB override earnings ──────────────────────────────────────────────────
OVERRIDE_PCT = 0.10   # 10% of a sub-IB's commission goes to the parent


@router.get("/{ib_id}/sub-ibs")
def sub_ibs(ib_id: int, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    """The IB's sub-partners + the 10% override each earned them (desk Jul 15 2026)."""
    rows = db.execute(text("""
        SELECT s.id, s.name, s.ib_code, s.ib_level,
               COALESCE(s.total_clients,0), COALESCE(s.total_volume,0),
               COALESCE(s.total_commission,0)
        FROM ibs s WHERE s.parent_ib_id = :i ORDER BY s.total_commission DESC NULLS LAST
    """), {"i": ib_id}).fetchall()
    subs, override_total = [], 0.0
    for r in rows:
        their = float(r[6] or 0)
        ov = round(their * OVERRIDE_PCT, 2)
        override_total += ov
        subs.append({"id": r[0], "name": r[1] or "", "ib_code": r[2] or "", "ib_level": r[3] or 5,
                     "clients": int(r[4]), "volume": float(r[5]), "their_commission": their,
                     "your_override": ov})
    return {"sub_ibs": subs, "override_pct": OVERRIDE_PCT * 100,
            "override_total": round(override_total, 2), "count": len(subs)}


# ── Profile: edit + photo upload ──────────────────────────────────────────────
@router.post("/{ib_id}/profile")
def update_profile(ib_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    ensure_tables(db)
    fields, params = [], {"id": ib_id}
    for col, key in [("phone", "phone"), ("country", "country"), ("city", "city"), ("bio", "bio")]:
        if key in data:
            fields.append(f"{col} = :{key}")
            params[key] = (data.get(key) or "").strip()
    if not fields:
        return {"ok": True}
    db.execute(text(f"UPDATE ibs SET {', '.join(fields)} WHERE id = :id"), params)
    db.commit()
    return {"ok": True}


@router.post("/{ib_id}/social/add")
def add_social(ib_id: int, data: dict, db: Session = Depends(get_db), current_user=Depends(staff_or_own_ib)):
    """The IB ADDS a social channel from their Profile (verified the same way as at signup).
    ADD-ONLY: there is no IB edit/remove — only the desk can change an existing social link."""
    import json as _json
    import ib_social_verify as SV
    ensure_tables(db)
    platform = (data.get("platform") or "").strip().lower()
    url = (data.get("url") or "").strip()
    name = (data.get("name") or "").strip()
    res = SV.verify_link(platform, url, name)
    if not res.get("domain_ok"):
        raise HTTPException(status_code=400, detail=res.get("message") or "That doesn't look right.")
    if not res.get("verified"):
        raise HTTPException(status_code=400, detail=res.get("message") or "Couldn't verify that — check it.")
    row = db.execute(text("SELECT social_links FROM ibs WHERE id=:id"), {"id": ib_id}).fetchone()
    links = list(row[0] or []) if row else []
    final = res.get("final_url") or url
    if any((l.get("platform") == platform and l.get("url") in (final, url)) for l in links):
        return {"ok": True, "social_links": links, "message": "Already added"}
    links.append({"platform": platform, "label": (data.get("label") or platform.capitalize()),
                  "name": name, "url": final, "verified": True,
                  "name_match": res.get("name_match"), "added_by": "ib"})
    db.execute(text("UPDATE ibs SET social_links = CAST(:s AS jsonb) WHERE id=:id"),
               {"s": _json.dumps(links), "id": ib_id})
    db.commit()
    return {"ok": True, "social_links": links, "message": res.get("message") or "Added ✓"}


@router.post("/{ib_id}/photo")
async def upload_photo(ib_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                       current_user=Depends(staff_or_own_ib)):
    ensure_tables(db)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 5 MB)")
    fn = f"ib_{ib_id}{ext}"
    with open(os.path.join(UPLOAD_DIR, fn), "wb") as f:
        f.write(data)
    url = f"/api/ib-photos/{fn}"
    db.execute(text("UPDATE ibs SET photo_url=:u WHERE id=:i"), {"u": url, "i": ib_id})
    db.commit()
    return {"ok": True, "photo_url": url}


# ── IB agreement ──────────────────────────────────────────────────────────────
# BUMP THIS whenever the terms below change — every IB whose ibs.agreement_version differs is
# re-shown the onboarding + agreement gate on next login and must re-accept. Keep the hardcoded
# value in ib_portal_auth.py's signup INSERT in sync (it imports AGREEMENT_VERSION from here).
AGREEMENT_VERSION = "2026-07-v2"
AGREEMENT_URL = "https://tnfx.co/ib-agreement"   # canonical agreement on the public site

# Structured full text shown in the onboarding "read & agree" step. New Jul-2026 desk clauses:
# NDA definition, self/related zero-commission, Level-5 withdrawal lock, TNFX suspend/demote right.
_AGREEMENT_SECTIONS = [
    {"h": "1. Acceptance",
     "b": "This Introducing Broker Agreement is between TNFX (“the Company”, “we”) and you "
          "(“the Introducing Broker”, “IB”, “you”). By confirming below you acknowledge you "
          "have read, understood and agree to be bound by it. If you do not agree, do not use the IB Portal."},
    {"h": "2. Definitions",
     "b": "• Client — a person you introduce to TNFX who opens and funds a trading account.\n"
          "• FTD (First-Time Deposit) — a client’s first-ever deposit with TNFX. A client counts as "
          "YOUR FTD only if their globally-first deposit (across all their accounts, under any IB) was made "
          "under you; a client who first deposited elsewhere and later opens under you is an ADDITIONAL "
          "account, not your FTD.\n"
          "• NDA (New Deposit Account) — a genuinely new acquisition: an FTD made under you with NO "
          "strong relationship to any existing TNFX client (no shared identity, device, IP, payment source "
          "or family/household link). Accounts opened for yourself, family or friends that link to an "
          "existing client are NOT NDAs. ONLY NDAs count toward IB promotion and performance targets — "
          "raw FTD count alone does not.\n"
          "• IB Level — your grade (Levels 5–10), which sets your per-lot commission rate and privileges."},
    {"h": "3. Commission",
     "b": "You earn commission on the trading activity of the clients you genuinely introduce, at the "
          "per-lot rate of your IB Level, credited to your IB wallet.\n\n"
          "SELF-TRADING & RELATED ACCOUNTS. To keep the program fair, trading on your OWN accounts — or on "
          "accounts 100% related to you (a maximum 10/10 connection: same person, device, client ID/CID, "
          "family or payment wallet) — earns ZERO commission while you are at Level 5 or Level 6. Such "
          "accounts are marked “Zero commission — self / related account” in your portal. Commission on "
          "your own or fully-related accounts becomes payable only after you are promoted to Level 7.\n\n"
          "Commission may be withheld, adjusted or reversed where it arises from abuse, error, chargeback, "
          "fraud or breach of this Agreement."},
    {"h": "4. IB Levels, Withdrawals & Transfers",
     "b": "New IBs begin at Level 5. A Level 5 IB CANNOT withdraw or transfer commission or wallet funds "
          "until they have demonstrated genuine introducing-broker activity and been PROMOTED TO LEVEL 6. "
          "On promotion to Level 6, withdrawal and transfer are unlocked. Promotion between levels is based "
          "on genuine, verified performance (primarily NDAs and real client trading volume)."},
    {"h": "5. Company Rights — Suspension, Demotion & Termination",
     "b": "TNFX reserves the right, AT ITS SOLE DISCRETION AND AT ANY TIME, to suspend, terminate, "
          "downgrade (demote) or restrict your IB account — including withholding, freezing or reversing "
          "commissions and locking withdrawals/transfers — where it determines you have engaged in abuse, "
          "self-dealing, misrepresentation, farming of NDAs via family/friends, or any breach of this "
          "Agreement, or for any operational, legal or regulatory reason. TNFX’s determination on "
          "relationship/abuse scoring is final."},
    {"h": "6. Your Obligations",
     "b": "Act honestly and in the client’s interest; never guarantee profit, mislead clients, or trade "
          "on their behalf. Do not open, control or coordinate accounts to inflate your own targets or "
          "commission. Keep your credentials secure — you are responsible for activity under your account. "
          "Comply with all applicable laws, AML/KYC requirements and TNFX policies."},
    {"h": "7. General",
     "b": "TNFX may amend this Agreement; continued use of the IB Portal after an update constitutes "
          "acceptance of the updated terms. This Agreement does not create an employment, partnership or "
          "agency relationship beyond the limited introducing role described here. Licensed by the FSA."},
]

_AGREEMENT_SUMMARY = ("TNFX Introducing Broker Agreement. You introduce clients and earn commission per "
                      "traded lot by grade. Only genuinely-new deposit accounts (NDAs) count toward "
                      "promotion. Your own / 100%-related accounts earn NO commission at Levels 5–6 (they "
                      "unlock at Level 7). Level-5 IBs cannot withdraw or transfer until promoted to Level 6. "
                      "TNFX may suspend or demote an IB at any time for abuse or self-dealing.")


@pub.get("/ib-agreement")
def get_agreement():
    return {"version": AGREEMENT_VERSION, "url": AGREEMENT_URL,
            "summary": _AGREEMENT_SUMMARY, "sections": _AGREEMENT_SECTIONS}


# ── Admin: IB Requests queue (signup applications) ────────────────────────────
_MGR = {"super_admin", "admin", "director", "sales_manager"}


def _can_act(staff) -> bool:
    role = (getattr(staff, "role", "") or "").lower()
    # IB MANAGER + admins act; sales_manager is READ-ONLY
    return role in {"super_admin", "admin", "director", "ib_manager"}


@padmin.get("/requests")
def list_requests(status: str = "pending", db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    """Pending IB signup applications for the desk. IB-manager acts, sales-manager reads."""
    ensure_tables(db)
    rows = db.execute(text("""
        SELECT id, name, email, phone, country, city, ib_level, status,
               applicant_profile, social_links, bio, created_at, agent_id
        FROM ibs WHERE status = :st AND agent_id IS NULL
        ORDER BY created_at DESC NULLS LAST LIMIT 300
    """), {"st": status}).fetchall()
    return {"can_act": _can_act(staff), "requests": [{
        "id": r[0], "name": r[1] or "", "email": r[2] or "", "phone": r[3] or "",
        "country": r[4] or "", "city": r[5] or "", "ib_level": r[6] or 5, "status": r[7] or "",
        "profile": r[8] or {}, "social_links": r[9] or [], "bio": r[10] or "",
        "created_at": r[11].isoformat() if r[11] else None, "agent_id": r[12],
    } for r in rows]}


@padmin.post("/requests/{ib_id}/action")
def act_request(ib_id: int, data: dict, db: Session = Depends(get_db), staff=Depends(get_current_staff)):
    """approve (sales first-pass) / activate (IB-manager sets level + links MT agent) / reject."""
    if not _can_act(staff):
        raise HTTPException(status_code=403, detail="Only the IB manager can action requests (sales managers have read-only access)")
    ensure_tables(db)
    action = (data.get("action") or "").lower()
    ib = db.execute(text("SELECT id, status FROM ibs WHERE id=:i"), {"i": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="Request not found")
    if action == "reject":
        db.execute(text("UPDATE ibs SET status='rejected' WHERE id=:i"), {"i": ib_id})
        db.commit()
        return {"ok": True, "status": "rejected"}
    if action == "activate":
        level = int(data.get("ib_level") or 5)
        agent_id = data.get("agent_id")
        db.execute(text("""UPDATE ibs SET status='active', ib_level=:lv,
            agent_id = COALESCE(:ag, agent_id) WHERE id=:i"""),
            {"lv": max(5, min(10, level)), "ag": agent_id, "i": ib_id})
        db.commit()
        notify(db, ib_id, "approved", "Your partner account is active 🎉",
               f"Welcome aboard — you start at grade level {level}. Your dashboard is now live.")
        return {"ok": True, "status": "active"}
    # default: sales first-pass approval
    db.execute(text("UPDATE ibs SET status='approved' WHERE id=:i"), {"i": ib_id})
    db.commit()
    return {"ok": True, "status": "approved"}
