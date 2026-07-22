
"""Negative Balance Protection router"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import models, threading, time
from database import get_db, SessionLocal
from auth import get_current_user

router = APIRouter(prefix="/neg-cover", tags=["neg-cover"])

from mt_secrets import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD
BRIDGE_URL = "http://localhost:5000"

# Auto-cover background state
_auto_running = {"on": False, "thread": None}

# Always-on Negative Balance Protection config (persisted so it survives restarts).
# Defaults: ENABLED, and SKIP accounts in an open abuse case (don't auto-pay detected
# hedging/fraud — they still appear in the Neg Balance page for one-click manual cover).
NEG_AUTO_DEFAULT_ENABLED = True
NEG_AUTO_DEFAULT_SKIP_ABUSE = True

def _ensure_cfg():
    db = SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS neg_cover_config (
                id INT PRIMARY KEY, enabled BOOLEAN DEFAULT TRUE,
                skip_abuse BOOLEAN DEFAULT TRUE, updated_at TIMESTAMP DEFAULT NOW())
        """))
        # audit log of every cover (was missing on this DB -> covers threw after moving money)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS neg_cover_log (
                id SERIAL PRIMARY KEY, login BIGINT, platform VARCHAR(10),
                deficit NUMERIC, cover_amount NUMERIC,
                balance_before NUMERIC, credit_before NUMERIC,
                balance_after NUMERIC, credit_after NUMERIC,
                status VARCHAR(40), mode VARCHAR(20), agent_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW())
        """))
        db.execute(text("INSERT INTO neg_cover_config (id, enabled, skip_abuse) "
                        "VALUES (1, :e, :s) ON CONFLICT (id) DO NOTHING"),
                   {"e": NEG_AUTO_DEFAULT_ENABLED, "s": NEG_AUTO_DEFAULT_SKIP_ABUSE})
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def _cfg():
    db = SessionLocal()
    try:
        r = db.execute(text("SELECT COALESCE(enabled,TRUE), COALESCE(skip_abuse,TRUE) "
                            "FROM neg_cover_config WHERE id=1")).fetchone()
        return (bool(r[0]), bool(r[1])) if r else (NEG_AUTO_DEFAULT_ENABLED, NEG_AUTO_DEFAULT_SKIP_ABUSE)
    except Exception:
        return (NEG_AUTO_DEFAULT_ENABLED, NEG_AUTO_DEFAULT_SKIP_ABUSE)
    finally:
        db.close()

def _set_cfg(enabled=None, skip_abuse=None):
    db = SessionLocal()
    try:
        if enabled is not None:
            db.execute(text("UPDATE neg_cover_config SET enabled=:v, updated_at=NOW() WHERE id=1"), {"v": bool(enabled)})
        if skip_abuse is not None:
            db.execute(text("UPDATE neg_cover_config SET skip_abuse=:v, updated_at=NOW() WHERE id=1"), {"v": bool(skip_abuse)})
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

import os as _os
# Only ONE process may run the auto-cover loop — it opens an MT5Manager connection (one per MT
# login) and writes cover trades. When we run several uvicorn instances behind nginx, the web
# instances set RUN_INPROC_LOOPS=0 so ONLY the primary instance runs it; default "1" preserves
# the single-instance behavior.
_INPROC_LOOPS = _os.getenv("RUN_INPROC_LOOPS", "1") != "0"

def _start_auto_thread():
    if not _INPROC_LOOPS:
        return   # web-only instance — the primary instance runs the cover loop
    if not _auto_running["on"]:
        _auto_running["on"] = True
        t = threading.Thread(target=_auto_loop, daemon=True)
        _auto_running["thread"] = t
        t.start()

def _platform_clause(platform: str):
    """clients.platform is 'MT4' for MT4 and blank/NULL for MT5. Return (sql, params)."""
    if (platform or "").upper() == "MT4":
        return "platform = 'MT4'", {}
    return "(platform IS NULL OR platform = '' OR platform = 'MT5')", {}

def _get_mt5():
    import MT5Manager
    mgr = MT5Manager.ManagerAPI()
    if not mgr.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD):
        return None
    return mgr

def _is_flat(mgr, login):
    pos = mgr.PositionGet(login)
    return pos is None or len(pos) == 0

def _eval_account(mgr, login):
    """Return dict with eligibility info (no money moved)."""
    acc = mgr.UserAccountGet(login)
    if not acc:
        return None
    bal, cred = float(acc.Balance), float(acc.Credit)
    if bal >= 0:
        return None
    deficit = abs(bal)
    flat = _is_flat(mgr, login)
    if not flat:
        status = "has_positions"
    elif cred < deficit:
        status = "credit_low"
    else:
        status = "eligible"
    return {"login": login, "balance": bal, "credit": cred, "deficit": deficit,
            "cover_amount": min(deficit, cred), "flat": flat, "status": status}

def _do_cover(mgr, login, agent_id=None, mode="manual"):
    """Cover one account via the BRIDGE (which owns the live MT5 connection)."""
    import urllib.request as _u, json as _j
    try:
        req = _u.Request(f"{BRIDGE_URL}/neg-cover/cover/{login}", method="POST")
        r = _j.loads(_u.urlopen(req, timeout=60).read())
    except Exception as e:
        return {"login": login, "status": "error", "error": str(e)}
    # Log if covered — NEVER let a logging failure break the loop or hide that money moved.
    if r.get("status") == "covered":
        # cover_amount now records the ACTUAL credit reclaimed (not the deficit). If the bridge
        # could not fully pull the credit, mark it 'covered_credit_partial' so the 15-min reclaim
        # sweep re-attempts it.
        partial = not r.get("credit_ok", True)
        db = SessionLocal()
        try:
            db.execute(text("""
                INSERT INTO neg_cover_log (login, platform, deficit, cover_amount,
                    balance_before, credit_before, balance_after, credit_after, status, mode, agent_id, created_at)
                VALUES (:l,'MT5',:d,:cr,:bb,:cb,:ba,:ca,:st,:m,:ag,NOW())
            """), {"l":login,"d":r.get("deficit",0),"cr":r.get("credit_removed",0),
                   "bb":r.get("balance_before"),"cb":r.get("credit_before"),
                   "ba":r.get("balance_after",0),"ca":r.get("credit_after",0),
                   "st":"covered_credit_partial" if partial else "covered","m":mode,"ag":agent_id})
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"neg_cover_log write failed for #{login} (cover DID happen): {e}")
        finally:
            db.close()
    return r


def _reclaim_one(login, amount, agent_id=None):
    """Call the bridge to pull `amount` credit off a non-negative account; log the result."""
    import urllib.request as _u, json as _j
    try:
        req = _u.Request(f"{BRIDGE_URL}/neg-cover/reclaim-credit/{login}", method="POST",
                         data=_j.dumps({"amount": float(amount)}).encode(),
                         headers={"Content-Type": "application/json"})
        r = _j.loads(_u.urlopen(req, timeout=60).read())
    except Exception as e:
        return {"login": login, "status": "error", "error": str(e)}
    if r.get("status") == "reclaimed" and r.get("credit_removed", 0) > 0:
        db = SessionLocal()
        try:
            db.execute(text("""
                INSERT INTO neg_cover_log (login, platform, deficit, cover_amount,
                    balance_before, credit_before, balance_after, credit_after, status, mode, agent_id, created_at)
                VALUES (:l,'MT5',0,:cr,:bb,:cb,:bb,:ca,'credit_reclaimed',:m,:ag,NOW())
            """), {"l":login,"cr":r.get("credit_removed",0),"bb":r.get("balance_before"),
                   "cb":r.get("credit_before"),"ca":r.get("credit_after"),"m":"reclaim","ag":agent_id})
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"reclaim log write failed for #{login} (reclaim DID happen): {e}")
        finally:
            db.close()
    return r


def _credit_reclaim_pass():
    """Re-attempt credit-outs that a prior cover could not fully apply (status
    'covered_credit_partial'). Computes the intended-but-unremoved credit and pulls just that,
    then marks the partial rows resolved so we don't repeat. SAFE: only touches credit that the
    cover logic intended to remove (min(credit_before, deficit) minus what was actually removed),
    never legitimate surplus, and only on accounts now at balance>=0 (the bridge guards that).

    POLICY (per desk, Jul 2026): reclaim credit = the amount we covered on EVERY covered account,
    INCLUDING accounts that are actively trading (we used to skip open-position accounts). MT5 only
    releases credit when there's free margin, so an account still using the credit as margin fails
    the pull and stays flagged; we retry it every cycle and it clips the instant it frees up / goes
    flat. A row is resolved only once the credit is actually gone (or there's none left to pull)."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT login, deficit, credit_before, credit_after
            FROM neg_cover_log
            WHERE platform='MT5' AND status='covered_credit_partial'
              AND credit_before IS NOT NULL
        """)).fetchall()
    except Exception as e:
        db.close(); print(f"reclaim pass query failed: {e}"); return
    db.close()
    # aggregate the outstanding shortfall per login
    shortfall = {}
    for login, deficit, cb, ca in rows:
        cb = float(cb or 0); ca = float(ca or 0); deficit = float(deficit or 0)
        intended = min(cb, deficit)
        removed = cb - ca
        owed = round(intended - removed, 2)
        if owed > 0.01:
            shortfall[login] = round(shortfall.get(login, 0) + owed, 2)
    done = []  # logins whose credit-out is now fully applied -> safe to resolve the partial rows
    for login, owed in shortfall.items():
        if not _auto_running["on"]:
            break
        # Attempt the credit-out on EVERY covered account, active traders included. The bridge only
        # acts when balance>=0 and never pulls below 0 credit; MT applies what free margin allows.
        try:
            r = _reclaim_one(login, owed, agent_id=None)
        except Exception as e:
            print(f"reclaim error #{login}: {e}")
            continue
        removed = float(r.get("credit_removed") or 0)
        cred_after = r.get("credit_after")
        # Resolve only if we actually pulled ~all we owed, or there's no credit left to pull.
        # A still-margined active trader pulls 0 here -> stays flagged, retried next cycle.
        if r.get("status") in ("reclaimed", "nothing_to_reclaim") and (
                removed >= owed - 0.05 or (cred_after is not None and float(cred_after) <= 0.01)):
            done.append(login)
    # only resolve the partials whose credit is now actually gone; the rest stay flagged for retry
    if done:
        db = SessionLocal()
        try:
            db.execute(text("UPDATE neg_cover_log SET status='covered' "
                            "WHERE platform='MT5' AND status='covered_credit_partial' "
                            "AND login = ANY(:ls)"), {"ls": done})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    if shortfall:
        print(f"[neg-cover] credit-reclaim: resolved {len(done)}/{len(shortfall)} pending "
              f"credit-out(s) ({len(shortfall)-len(done)} still margined/awaiting free margin)")

@router.get("/scan")
def scan(platform: str = "MT5", db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """List all negative accounts with eligibility."""
    pclause, _ = _platform_clause(platform)
    rows = db.execute(text(f"""
        SELECT login, name, balance, COALESCE(no_auto_cover,FALSE),
               COALESCE(network_score,0), COALESCE(is_flagged,FALSE),
               COALESCE(credit,0)
        FROM clients
        WHERE balance < 0 AND {pclause} ORDER BY balance ASC
    """)).fetchall()

    # Canonical 0-10 network score (build_network_scores.py) — the SAME value every page shows
    edge_counts = {}
    try:
        _negl = [r[0] for r in rows]
        if _negl:
            edge_counts = {x[0]: int(x[1] or 0) for x in db.execute(text(
                "SELECT login, COALESCE(network_score,0) FROM clients WHERE login = ANY(:l)"),
                {"l": _negl}).fetchall()}
    except Exception:
        pass

    # Build abuse lookup with type + reason per login
    abuse_map = {}
    try:
        ar = db.execute(text("""
            SELECT login_a, login_b, abuse_type, severity, risk_score, evidence
            FROM abuse_cases WHERE status != 'dismissed'
        """)).fetchall()
        for row in ar:
            la, lb, atype, sev, risk, evid = row
            info = {"type": atype, "severity": sev, "risk": int(risk or 0), "reason": evid or ""}
            for lg in (la, lb):
                if lg and lg not in abuse_map:
                    abuse_map[lg] = info
    except Exception:
        pass
    abuse_logins = set(abuse_map.keys())

    # Pull credit from DB (fast) - clients table has credit column
    out = []
    for r in rows:
        login, name, db_bal, no_cover = r[0], r[1], float(r[2] or 0), r[3]
        net_score = edge_counts.get(login, 0)   # canonical 0-10 (build_network_scores.py)
        flagged = bool(r[5])
        credit = float(r[6] or 0) if len(r) > 6 else 0
        deficit = abs(db_bal)
        # 3 eligibility rules: balance >= -200, OR credit >= 50% deficit, OR credit >= full
        if db_bal >= -200 or credit >= deficit * 0.5 or credit >= deficit:
            status = "eligible"   # provisional - verified flat at cover time
        else:
            status = "credit_low"  # not auto-eligible, but manual Run still allowed
        item = {"login": login, "name": name or "", "balance": db_bal,
                "no_auto_cover": bool(no_cover), "status": status,
                "credit": credit, "deficit": deficit,
                "cover_amount": min(deficit, credit), "flat": None,
                "network_score": net_score, "is_flagged": flagged,
                "in_abuse": login in abuse_logins,
                "abuse_info": abuse_map.get(login)}
        out.append(item)

    # Sort: eligible first (by deficit desc), then everything else (credit_low) at bottom by balance
    def sort_key(a):
        tier = 0 if a["status"] == "eligible" else 1
        return (tier, -abs(a["balance"]))
    out.sort(key=sort_key)

    return {"platform": platform, "accounts": out,
            "eligible": sum(1 for a in out if a["status"]=="eligible" and not a["no_auto_cover"])}

def _deals_platform(platform: str) -> str:
    """deals.platform is 'MT4' or 'MT5'."""
    return "MT4" if (platform or "").upper() == "MT4" else "MT5"

# network_edges reasons that mean "same beneficiary / strong link" vs weak (same IB book)
_STRONG_REASONS = {"cid", "ip", "device", "mqid", "family", "phone", "email", "name"}

@router.get("/counterparties/{login}")
def counterparties(login: int, platform: str = "MT5",
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """For a negative account, find accounts that PROFITED in the SAME period on the
    SAME symbols (the likely hedge counterparties). Related (network) and strong-match
    (>=80% of the loss) accounts float to the top; unrelated ones are tagged 'no connection'."""
    plat = _deals_platform(platform)
    # 1) This account's loss window + symbols (closed trades only: action 0/1)
    win = db.execute(text("""
        SELECT min(deal_time) t0, max(deal_time) t1, -COALESCE(sum(profit),0) loss,
               min(deal_date) d0, max(deal_date) d1, count(*) n
        FROM deals WHERE login=:l AND action IN (0,1) AND platform=:p
    """), {"l": login, "p": plat}).fetchone()
    if not win or win[5] == 0 or win[0] is None:
        return {"login": login, "loss": 0, "period": None, "symbols": [], "counterparties": []}
    t0, t1, loss, d0, d1, n = win[0], win[1], float(win[2] or 0), win[3], win[4], win[5]
    loss = loss if loss > 0 else 0.0

    # 2) Candidate counterparties: same symbols, overlapping window, net positive
    rows = db.execute(text("""
        WITH syms AS (SELECT DISTINCT symbol FROM deals WHERE login=:l AND action IN (0,1) AND platform=:p)
        SELECT d.login, round(sum(d.profit)::numeric,2) prof, count(*) n,
               array_agg(DISTINCT d.symbol) syms
        FROM deals d
        WHERE d.action IN (0,1) AND d.platform=:p AND d.login<>:l
          AND d.deal_date BETWEEN :d0 AND :d1
          AND d.deal_time BETWEEN :t0 AND :t1
          AND d.symbol IN (SELECT symbol FROM syms)
        GROUP BY d.login
        HAVING sum(d.profit) > 0
        ORDER BY sum(d.profit) DESC
        LIMIT 25
    """), {"l": login, "p": plat, "d0": d0, "d1": d1, "t0": t0, "t1": t1}).fetchall()
    if not rows:
        return {"login": login, "loss": round(loss, 2),
                "period": {"from": d0, "to": d1, "from_ts": int(t0), "to_ts": int(t1)},
                "symbols": [], "counterparties": []}

    cand_logins = [r[0] for r in rows]

    # 3) Network relation map (neighbor -> strongest reason)
    rel = {}
    try:
        er = db.execute(text("""
            SELECT login_a, login_b, reason FROM network_edges
            WHERE login_a=:l OR login_b=:l
        """), {"l": login}).fetchall()
        for la, lb, reason in er:
            other = lb if la == login else la
            prev = rel.get(other)
            strong = (reason or "").lower() in _STRONG_REASONS
            # keep a strong reason over a weak one
            if prev is None or (strong and prev[1] is False):
                rel[other] = (reason, strong)
    except Exception:
        pass

    # 4) Names for the candidates
    names = {}
    try:
        nr = db.execute(text("SELECT DISTINCT ON (login) login, name FROM clients WHERE login = ANY(:ls)"),
                        {"ls": cand_logins}).fetchall()
        names = {r[0]: r[1] for r in nr}
    except Exception:
        pass

    out = []
    for lg, prof, cn, syms in rows:
        prof = float(prof or 0)
        pct = round(prof / loss * 100, 1) if loss > 0 else None
        r = rel.get(lg)
        related = r is not None
        reason = r[0] if r else None
        strong_link = bool(r[1]) if r else False
        out.append({
            "login": lg, "name": names.get(lg) or "",
            "profit": round(prof, 2), "trades": cn,
            "pct_of_loss": pct,
            "symbols": [s for s in (syms or []) if s][:6],
            "related": related, "reason": reason, "strong_link": strong_link,
            "note": None if related else "no connection",
            "strong_match": pct is not None and pct >= 80,
        })

    # 5) Sort: strong-match+related first, then strong-match, then related, then by profit
    def tier(c):
        if c["strong_match"] and c["related"]: return 0
        if c["strong_match"]: return 1
        if c["related"]: return 2
        return 3
    out.sort(key=lambda c: (tier(c), -c["profit"]))

    return {"login": login, "loss": round(loss, 2),
            "period": {"from": d0, "to": d1, "from_ts": int(t0), "to_ts": int(t1)},
            "trades": n,
            "counterparties": out}

@router.get("/network/{login}")
def network_detail(login: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Related clients for an account (shared cid/ip/device/family/phone/IB), with reasons,
    name and current balance. Strong links (same beneficiary) sort above weak (same IB book)."""
    try:
        er = db.execute(text("""
            SELECT CASE WHEN login_a=:l THEN login_b ELSE login_a END AS other, reason, value
            FROM network_edges WHERE login_a=:l OR login_b=:l
        """), {"l": login}).fetchall()
    except Exception as e:
        return {"login": login, "total": 0, "by_reason": {}, "related": [], "error": str(e)}

    # aggregate reasons per neighbor + overall reason counts
    neigh = {}          # other -> {reasons:set, values:set}
    by_reason = {}
    for other, reason, value in er:
        if not other or other == login:
            continue
        rs = (reason or "").lower()
        by_reason[rs] = by_reason.get(rs, 0) + 1
        d = neigh.setdefault(other, {"reasons": set(), "values": set()})
        d["reasons"].add(rs)
        if value:
            d["values"].add(str(value))
    total = len(neigh)

    # names + balances for the neighbors
    logins = list(neigh.keys())
    meta = {}
    if logins:
        try:
            mr = db.execute(text("""
                SELECT DISTINCT ON (login) login, name, COALESCE(balance,0)
                FROM clients WHERE login = ANY(:ls)
            """), {"ls": logins}).fetchall()
            meta = {r[0]: {"name": r[1] or "", "balance": float(r[2] or 0)} for r in mr}
        except Exception:
            pass

    related = []
    for other, d in neigh.items():
        reasons = sorted(d["reasons"])
        strong = any(r in _STRONG_REASONS for r in reasons)
        m = meta.get(other, {})
        related.append({
            "login": other, "name": m.get("name", ""),
            "balance": m.get("balance", 0.0),
            "reasons": reasons, "strong_link": strong,
            "shared": sorted(d["values"])[:3],
        })
    # strong links first, then accounts in profit (positive balance) first, then by |balance|
    related.sort(key=lambda x: (0 if x["strong_link"] else 1, 0 if x["balance"] > 0 else 1, -abs(x["balance"])))

    return {"login": login, "total": total, "by_reason": by_reason, "related": related[:40]}

@router.post("/cover/{login}")
def cover_one(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually cover one account (works even if no_auto_cover). Uses bridge."""
    return _do_cover(None, login, agent_id=current_user.id, mode="manual")

@router.post("/cover-all")
def cover_all(platform: str = "MT5", db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Sweep: cover all eligible in the BACKGROUND. Returns immediately."""
    pclause, _ = _platform_clause(platform)
    rows = db.execute(text(f"SELECT login FROM clients WHERE balance < 0 AND {pclause} AND COALESCE(no_auto_cover,FALSE)=FALSE")).fetchall()
    logins = [r[0] for r in rows]
    agent_id = current_user.id
    def _sweep():
        for login in logins:
            try:
                _do_cover(None, login, agent_id=agent_id, mode="sweep")
            except Exception as e:
                print(f"sweep cover error #{login}: {e}")
    t = threading.Thread(target=_sweep, daemon=True)
    t.start()
    return {"started": True, "queued": len(logins), "message": f"Sweeping {len(logins)} accounts in background"}

@router.post("/toggle-exclude/{login}")
def toggle_exclude(login: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Toggle the 'don't auto cover' flag."""
    cur = db.execute(text("SELECT COALESCE(no_auto_cover,FALSE) FROM clients WHERE login=:l LIMIT 1"), {"l":login}).scalar()
    newval = not bool(cur)
    db.execute(text("UPDATE clients SET no_auto_cover=:v WHERE login=:l"), {"v":newval,"l":login})
    db.commit()
    return {"login": login, "no_auto_cover": newval}

def _auto_loop():
    while _auto_running["on"]:
        try:
            enabled, skip_abuse = _cfg()
            if not enabled:
                _auto_running["on"] = False
                break
            db = SessionLocal()
            pclause, _ = _platform_clause("MT5")
            # always cover negatives, minus the manual exclude flag and (optionally) any
            # account currently in an OPEN abuse case so we don't auto-pay detected fraud.
            abuse_clause = ""
            if skip_abuse:
                abuse_clause = ("AND login NOT IN ("
                    "SELECT login_a FROM abuse_cases WHERE status <> 'dismissed' "
                    "UNION SELECT login_b FROM abuse_cases WHERE status <> 'dismissed' AND login_b IS NOT NULL)")
            rows = db.execute(text(
                f"SELECT login FROM clients WHERE balance < 0 AND {pclause} "
                f"AND COALESCE(no_auto_cover,FALSE)=FALSE {abuse_clause}")).fetchall()
            db.close()
            for (login,) in rows:
                if not _auto_running["on"]: break
                _do_cover(None, login, mode="auto")  # uses bridge (re-verifies live, flat-only)
            # EVERY cycle (~1 min): reclaim credit = the amount covered on every covered account,
            # active traders included, retrying until MT frees the margin (per desk policy Jul 2026).
            if _auto_running["on"]:
                _credit_reclaim_pass()
        except Exception as e:
            print(f"auto-cover error: {e}")
        for _ in range(60):
            if not _auto_running["on"]: break
            time.sleep(1)


@router.get("/verify/{login}")
def verify_account(login: int, current_user: models.User = Depends(get_current_user)):
    """Live-check one account via bridge: balance, credit, positions, floating PnL."""
    import urllib.request as _u, json as _j
    try:
        d = _j.loads(_u.urlopen(f"{BRIDGE_URL}/neg-cover/inspect/{login}", timeout=10).read())
    except Exception as e:
        return {"login": login, "error": str(e)}
    bal = d.get("Balance", 0)
    cred = d.get("Credit", 0)
    npos = d.get("positions", 0)
    pnl = d.get("floating_pnl", 0)
    deficit = abs(bal) if bal < 0 else 0
    # Determine status with the live data
    if bal >= 0:
        status = "not_negative_now"
    elif npos > 0 and pnl >= 10:
        status = "has_positions_positive_pnl"
    elif bal >= -200 or cred >= deficit * 0.5 or cred >= deficit:
        status = "eligible"
    else:
        status = "credit_low"
    return {"login": login, "balance": bal, "credit": cred, "deficit": deficit,
            "positions": npos, "floating_pnl": pnl, "status": status}

@router.post("/auto/start")
def auto_start(current_user: models.User = Depends(get_current_user)):
    _set_cfg(enabled=True)        # persists across restarts
    _start_auto_thread()
    return {"auto": True}

@router.post("/auto/stop")
def auto_stop(current_user: models.User = Depends(get_current_user)):
    _set_cfg(enabled=False)
    _auto_running["on"] = False
    return {"auto": False}

@router.get("/auto/status")
def auto_status(current_user: models.User = Depends(get_current_user)):
    enabled, skip_abuse = _cfg()
    return {"auto": _auto_running["on"], "enabled": enabled, "skip_abuse": skip_abuse}

@router.post("/auto/config")
def auto_config(payload: dict, current_user: models.User = Depends(get_current_user)):
    """Toggle whether auto-cover skips accounts in an open abuse case.
    skip_abuse=true (default) = don't auto-pay flagged fraud; false = cover EVERY negative."""
    if "skip_abuse" in (payload or {}):
        _set_cfg(skip_abuse=bool(payload.get("skip_abuse")))
    enabled, skip_abuse = _cfg()
    return {"enabled": enabled, "skip_abuse": skip_abuse}


# ── Always-on: ensure config + auto-start the cover loop shortly after boot ──
# (delay lets the backend + MT5 bridge settle before the first sweep). Runs at import,
# so it comes back on every restart unless someone has persisted enabled=FALSE.
_ensure_cfg()
def _boot_autocover():
    time.sleep(25)
    try:
        if _cfg()[0]:
            _start_auto_thread()
    except Exception as e:
        print(f"neg auto-cover boot error: {e}")
if _INPROC_LOOPS:   # web-only instances (RUN_INPROC_LOOPS=0) never boot the MT5 cover loop
    threading.Thread(target=_boot_autocover, daemon=True).start()
