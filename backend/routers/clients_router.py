"""
clients_router.py
Groups trading accounts by phone number to show unique clients.
All changes included:
- Group by phone → unique clients
- Real balance, deposits, withdrawals aggregated across all accounts
- IB name display
- First deposit date + amount
- Deposit count
- Last activity (client actions from transactions)
- Last comment (sales agent actions from call_actions)
- Network score (IP + CID + City + IB + Phone prefix)
- Priority score calculation
- Real data inside client detail (deposits, withdrawals, accounts, calls, network)
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from database import get_db, SessionLocal
from auth import get_current_user, get_password_hash
import models
import rbac

router = APIRouter(prefix="/clients", tags=["Clients"])

# ── PERFORMANCE: precomputed per-login transaction totals ────────────────────────
# The Clients list used to re-aggregate the whole `transactions` table (now ~2M rows)
# THREE times per page load (count + stats + main query) — ~5s of pure aggregation that
# scaled badly as the data grew 22x. We keep a tiny per-login summary table that the list
# JOINs instead, rebuilt at most once every few minutes. It computes EXACTLY what the inline
# subqueries did (plain GROUP BY login over transactions), so the numbers are unchanged.
_TX_AGG_MAX_AGE = 180          # rebuild at most every 3 minutes
_TX_AGG_LOCK    = 778801       # advisory-lock key so only ONE request rebuilds at a time


def _ensure_tx_agg():
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout='4s'"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS client_tx_agg (
                login BIGINT PRIMARY KEY,
                dep_sum DOUBLE PRECISION DEFAULT 0,
                wd_sum  DOUBLE PRECISION DEFAULT 0,
                dep_cnt INTEGER DEFAULT 0,
                first_tx_date TEXT
            )
        """))
        db.execute(text("CREATE TABLE IF NOT EXISTS client_tx_agg_meta (id INT PRIMARY KEY, refreshed_at TIMESTAMPTZ)"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _refresh_tx_agg(db):
    """Rebuild client_tx_agg if it's older than _TX_AGG_MAX_AGE (or empty). Uses an advisory
    lock so concurrent requests don't all rebuild; the rebuild runs DELETE+INSERT in one txn so
    readers (via MVCC) keep seeing the old rows until it commits — never an empty window."""
    try:
        row = db.execute(text("SELECT refreshed_at FROM client_tx_agg_meta WHERE id=1")).fetchone()
        from datetime import datetime as _dt, timezone as _tz
        if row and row[0]:
            age = (_dt.now(_tz.utc) - row[0]).total_seconds()
            if age < _TX_AGG_MAX_AGE and db.execute(text("SELECT 1 FROM client_tx_agg LIMIT 1")).fetchone():
                return
        if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _TX_AGG_LOCK}).scalar():
            return   # another request is rebuilding — use the slightly-stale table
        try:
            db.execute(text("SET LOCAL idle_in_transaction_session_timeout=0"))
            db.execute(text("DELETE FROM client_tx_agg"))
            db.execute(text("""
                INSERT INTO client_tx_agg (login, dep_sum, wd_sum, dep_cnt, first_tx_date)
                SELECT login,
                       SUM(CASE WHEN tx_type='deposit'    THEN amount ELSE 0 END),
                       SUM(CASE WHEN tx_type='withdrawal' AND COALESCE(status,'')<>'rejected' THEN amount ELSE 0 END),
                       COUNT(*) FILTER (WHERE tx_type='deposit'),
                       MIN(tx_date) FILTER (WHERE tx_type='deposit')
                FROM transactions GROUP BY login
            """))
            db.execute(text("INSERT INTO client_tx_agg_meta (id, refreshed_at) VALUES (1, NOW()) "
                            "ON CONFLICT (id) DO UPDATE SET refreshed_at=NOW()"))
            db.commit()
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TX_AGG_LOCK}); db.commit()
    except Exception:
        db.rollback()


_ensure_tx_agg()

# ── Internal non-method labels (tickets #85/#86, Jwan) ──────────────────────────
# Some transactions rows are internal balance adjustments rather than real client
# money. MT5-sourced ones carry method='MT5' (notes like 'Negative balance payoff',
# 'Deposit Fix', 'Cashback'); MT4 journal-sourced ones put that internal note in the
# method column itself ('Deposit Fix' / 'Deposit fix' / 'Deposit/fix', 'Deposit Fees',
# 'Cashback', 'Stop out compensation', ...). They must be excluded from a client's
# REAL total deposits/withdrawals (consistent with the Deposits view in
# transactions_router). Mirror of transactions_router.INTERNAL_LABEL_RE.
_INTERNAL_LABEL_RE = (
    r"(deposit\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance"
    r"|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back"
    r"|credit\s*(in|out)|bonus\s*adjustment)"
)
# TRUE only for a real (non-internal) deposit/withdrawal method.
_REAL_METHOD_SQL = "(method IS NULL OR (method <> 'MT5' AND method !~* :internal_re))"


class ContactUpdate(BaseModel):
    """Admin edit of a client's contact details / portal credentials. All fields optional —
    only the ones provided are changed."""
    email:          str | None = None
    phone:          str | None = None
    password:       str | None = None   # new portal password (None/'' = leave unchanged)
    date_of_birth:  str | None = None
    full_name_en:   str | None = None
    email_verified: bool | None = None
    phone_verified: bool | None = None


class ActionCreate(BaseModel):
    login:            int
    action:           str
    note:             str = ""
    call_later_days:  int = 0
    call_later_hours: int = 0
    pass_to_manager:  bool = False


class AdditionalAccount(BaseModel):
    """Admin-only: create an ADDITIONAL real MT trading account for an existing client.
    CREATE ONLY — there is deliberately no delete counterpart (ticket #98)."""
    account_type:   str   = "Standard"
    platform:       str   = "MT5"
    islamic:        bool  = False
    leverage:       int   = 500
    initial_credit: float = 0.0


def score_breakdown(c: dict, settings: dict) -> list:
    """The actual reasons that built call_score (mirrors calc_priority_score), as a
    [{label, points}] list — so the Score hover shows REAL triggers, not a guess."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    out = []

    def _days(v):
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return (now - d).days
        except Exception:
            return None

    lad = c.get("last_action_date", "")
    ds = _days(lad) if lad else None
    if not lad:
        out.append({"label": "Never contacted", "points": settings.get("no_contact_14d", 30)})
    elif ds is not None and ds >= 14:
        out.append({"label": f"No contact {ds}d (≥14)", "points": settings.get("no_contact_14d", 30)})
    elif ds is not None and ds >= 7:
        out.append({"label": f"No contact {ds}d (≥7)", "points": settings.get("no_contact_7d", 15)})

    total_dep = float(c.get("total_deposit", 0) or 0)
    balance = float(c.get("balance", 0) or 0)
    if balance > 0 and total_dep == 0:
        out.append({"label": "Has balance, never deposited", "points": settings.get("no_deposit_ever", 25)})
    if total_dep > 0 and c.get("last_activity_type") in ("deposit",):
        d2 = _days(c.get("last_activity_date", ""))
        if d2 is not None and d2 >= 21:
            out.append({"label": f"No deposit in {d2}d", "points": settings.get("no_deposit_21d", 20)})
    fdd = _days(c.get("first_deposit_date", ""))
    if fdd is not None and fdd <= 7:
        out.append({"label": "First deposit ≤7d (fresh)", "points": settings.get("first_dep_7d", 20)})
    if balance > 0:
        out.append({"label": "Has balance", "points": settings.get("has_balance", 10)})
    margin = float(c.get("margin_level", 0) or 0)
    if 0 < margin < 50:
        out.append({"label": f"Margin {margin:.0f}% (<50)", "points": settings.get("margin_below_50", 40)})
    elif 50 <= margin < 100:
        out.append({"label": f"Margin {margin:.0f}% (<100)", "points": settings.get("margin_below_100", 25)})
    return out


def calc_priority_score(c: dict, settings: dict) -> int:
    """Calculate client priority score based on configurable settings."""
    score = 0
    now = datetime.now(timezone.utc)

    # --- Overdue contact ---
    last_action_date = c.get("last_action_date", "")
    if last_action_date:
        try:
            lad = datetime.fromisoformat(str(last_action_date).replace("Z", "+00:00"))
            if lad.tzinfo is None:
                lad = lad.replace(tzinfo=timezone.utc)
            days_since = (now - lad).days
            if days_since >= 14:
                score += settings.get("no_contact_14d", 30)
            elif days_since >= 7:
                score += settings.get("no_contact_7d", 15)
        except:
            score += settings.get("no_contact_14d", 30)
    else:
        score += settings.get("no_contact_14d", 30)

    # --- Deposit triggers ---
    total_dep = float(c.get("total_deposit", 0) or 0)
    balance   = float(c.get("balance", 0) or 0)

    if balance > 0 and total_dep == 0:
        score += settings.get("no_deposit_ever", 25)

    if total_dep > 0:
        last_dep_date = c.get("last_activity_date", "")
        if last_dep_date and c.get("last_activity_type") in ("deposit",):
            try:
                ldd = datetime.fromisoformat(str(last_dep_date).replace("Z", "+00:00"))
                if ldd.tzinfo is None:
                    ldd = ldd.replace(tzinfo=timezone.utc)
                if (now - ldd).days >= 21:
                    score += settings.get("no_deposit_21d", 20)
            except:
                pass

    first_dep_date = c.get("first_deposit_date", "")
    if first_dep_date:
        try:
            fdd = datetime.fromisoformat(str(first_dep_date).replace("Z", "+00:00"))
            if fdd.tzinfo is None:
                fdd = fdd.replace(tzinfo=timezone.utc)
            if (now - fdd).days <= 7:
                score += settings.get("first_dep_7d", 20)
        except:
            pass

    # --- Account health ---
    if balance > 0:
        score += settings.get("has_balance", 10)

    margin = float(c.get("margin_level", 0) or 0)
    if 0 < margin < 50:
        score += settings.get("margin_below_50", 40)
    elif 50 <= margin < 100:
        score += settings.get("margin_below_100", 25)

    return min(score, 100)


def get_score_settings(db: Session) -> dict:
    try:
        settings = db.query(models.ScoreSettings).all()
        return {s.trigger: s.points for s in settings}
    except:
        return {}



def _ocr_english_name(db: Session, c) -> str:
    """Suggested English/Latin full name from this client's KYC OCR (registrations.ocr_fields
    -> full_name), used to pre-fill 'Full name (English, 3-part)'. Returns '' if none."""
    try:
        logins = [c.login]
        if c.phone and c.phone not in ("", "0"):
            sib = db.execute(text(
                "SELECT login FROM clients WHERE phone=:p"), {"p": c.phone}).fetchall()
            logins = list({c.login, *[r[0] for r in sib]})
        row = db.execute(text("""
            SELECT ocr_fields->>'full_name' AS fn
            FROM registrations
            WHERE mt_login = ANY(:lg) AND ocr_fields->>'full_name' IS NOT NULL
              AND ocr_fields->>'full_name' <> ''
            ORDER BY processed_at DESC NULLS LAST LIMIT 1
        """), {"lg": logins}).fetchone()
        name = (row[0] if row else "") or ""
        # only return if it looks Latin/English (has ASCII letters)
        return name if any("a" <= ch.lower() <= "z" for ch in name) else ""
    except Exception:
        return ""


def _get_last_activity_type(last_dep, last_with):
    """Return the type of the most recent activity."""
    if last_dep and last_with:
        return 'deposit' if str(last_dep) >= str(last_with) else 'withdrawal'
    if last_dep: return 'deposit'
    if last_with: return 'withdrawal'
    return ''

@router.get("")
async def get_clients(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    sort:      str = Query("balance"),
    search:    str = Query(""),
    country:   str = Query(""),
    city:      str = Query(""),
    ib:        str = Query(""),
    agent:     str = Query(""),
    kyc:       str = Query(""),
    risk:      str = Query(""),
    sources:   str = Query(""),
    archived:  str = Query(""),    # ''/'active' = active only, 'archived' = archived only, 'all' = both
    deposits:  str = Query(""),    # deposit-count filter: 'D1','D2','D3','D4','D5+' (#60)
    birthday:  str = Query(""),    # '' = off, 'week' = birthday-window clients, 'unclaimed' = window & not claimed
    date_from: str = Query(""),    # reg_date >= (YYYY-MM-DD) (#62)
    date_to:   str = Query(""),    # reg_date <= (YYYY-MM-DD) (#62)
    period:    str = Query("all_time"),  # scopes the deposit/withdrawal/net KPIs to a period
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # keep the precomputed per-login transaction totals fresh (cheap; rebuilds at most every 3 min)
    _refresh_tx_agg(db)
    # A CLIENT stays a client even if their trading ACCOUNTS are archived by MT (gone / low balance) —
    # those just get an Archived account tag. But a USER-archived person (admin/TradeSoft decision:
    # not interested / a problem) is removed from this page entirely — they live on Settings -> Archive
    # and return here automatically on any re-engagement. So the Clients page = active client people.
    base_where = ("cu.kind = 'client' AND COALESCE(c.user_archived, FALSE) = FALSE"
                  " AND (c.login IS NULL OR (c.group_name NOT ILIKE '%retail%' AND c.group_name NOT ILIKE '%demo%'))")
    params: dict = {}
    extra_where = ""
    # A CLIENT stays a client even if their MT accounts are archived (gone from MT / low balance) —
    # TradeSoft still counts them as a client, so the DEFAULT shows the full client base (~the legacy
    # 27k). is_archived is a per-account, view-only detail (no deposit/transfer on that account), NOT a
    # reason to hide the person. The chips still narrow: 'active' = live accounts only, 'archived' =
    # archived accounts only, '' / 'all' (default) = both.
    if archived == "archived":
        extra_where += " AND COALESCE(c.is_archived, FALSE) = TRUE"
    elif archived == "active":
        extra_where += " AND COALESCE(c.is_archived, FALSE) = FALSE"
    # Date-range on registration date (#62). reg_date is stored as text (YYYY-MM-DD...),
    # so a lexical comparison on the date prefix is correct and index-friendly.
    if date_from:
        extra_where += " AND c.reg_date IS NOT NULL AND LEFT(c.reg_date,10) >= :date_from"
        params["date_from"] = date_from[:10]
    if date_to:
        extra_where += " AND c.reg_date IS NOT NULL AND LEFT(c.reg_date,10) <= :date_to"
        params["date_to"] = date_to[:10]
    if search:
        extra_where += " AND (CAST(c.login AS TEXT) LIKE :s OR c.name ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s OR c.country ILIKE :s OR c.city ILIKE :s)"
        params["s"] = f"%{search}%"
    if country:
        extra_where += " AND c.country = :country"
        params["country"] = country
    if city:
        extra_where += " AND c.city ILIKE :city"
        params["city"] = f"%{city}%"
    if ib:
        # Filter by IB name - look up agent_id from ibs table
        ib_row = db.execute(text("SELECT agent_id FROM ibs WHERE name ILIKE :n LIMIT 1"), {"n": f"%{ib}%"}).fetchone()
        if ib_row:
            extra_where += " AND c.agent = :ib_agent_id"
            params["ib_agent_id"] = ib_row[0]
    if agent:
        agent_user = db.execute(text("SELECT id FROM users WHERE full_name ILIKE :a LIMIT 1"), {"a": f"%{agent}%"}).fetchone()
        if agent_user:
            # match the agent on the client row OR the customer master (covers customers
            # whose accounts aren't in the clients table but carry the legacy owner name)
            extra_where += " AND (c.assigned_agent_id = :agent_id OR cu.assigned_agent_id = :agent_id)"
            params["agent_id"] = agent_user[0]
    if kyc:
        extra_where += " AND c.kyc_status = :kyc"
        params["kyc"] = kyc
    if risk:
        extra_where += " AND c.risk_score = :risk"
        params["risk"] = risk
    if sources:
        src_list = [s.strip() for s in sources.split(',')]
        extra_where += " AND c.source = ANY(:sources)"
        params["sources"] = src_list
    # Birthday bonus overlay: clients whose birthday falls in the claim window today. Computed once
    # (cheap — only clients with a DOB), reused for the filter below and the per-row 🎂/+100 overlay.
    import birthday_engine as BDE
    bcfg = BDE.cfg_birthday(db)
    bwin = BDE.birthday_window_logins(db, bcfg)   # login -> {birthday_date, occ_year, days_to}
    # logins that still get the +100 priority boost (in window AND not yet greeted) — fed into the SQL
    # 'score' sort so birthday clients rise to the TOP globally, not just within a page.
    bday_boost = []
    if bwin:
        _est_all = BDE.event_state(db, list(bwin.keys()))
        bday_boost = [l for l in bwin.keys() if not _est_all.get(l, {}).get("greeted")]
    params["bday_boost_logins"] = bday_boost or [0]
    if birthday in ("week", "unclaimed"):
        win_logins = list(bwin.keys())
        if birthday == "unclaimed" and win_logins:
            _est = BDE.event_state(db, win_logins)
            win_logins = [l for l in win_logins if not _est.get(l, {}).get("claimed")]
        if win_logins:
            # include the whole PERSON (all phone+platform siblings) if any of their logins has the
            # birthday, so the aggregated row keeps its real balance/deposits.
            extra_where += " AND cu.customer_no IN (SELECT customer_no FROM clients WHERE login = ANY(:bday_logins))"
            params["bday_logins"] = win_logins
        else:
            extra_where += " AND FALSE"   # no birthdays in window -> empty result

    # Role-based visibility: agent -> own clients; manager -> own + team; director/admin -> all
    rbac_sql, rbac_params = rbac.agent_filter(rbac.scope_agent_ids(db, current_user),
                                              col="COALESCE(c.assigned_agent_id, cu.assigned_agent_id)")
    extra_where += rbac_sql
    params.update(rbac_params)
    where = f"WHERE {base_where}{extra_where}"

    # Deposit-count filter (#60) — count of deposit transactions across ALL of the person's
    # logins, applied as a HAVING on the aggregated (phone+platform) row. D5+ = 5 or more.
    having = ""
    dep_cnt_expr = "SUM(COALESCE(td.dep_cnt,0))"
    dep_map = {"D1": "= 1", "D2": "= 2", "D3": "= 3", "D4": "= 4", "D5+": ">= 5"}
    if deposits in dep_map:
        having = f" HAVING {dep_cnt_expr} {dep_map[deposits]}"

    # sort balance/equity by the SAME sanitized values shown (exclude demo/seed accounts with no
    # deposit/withdrawal), so the top rows aren't fake $100M demo accounts displaying $0.
    # Real balance/equity must (a) come from an account that moved real money (a deposit or
    # withdrawal) AND (b) be PLAUSIBLE vs what was deposited. The MT feed seeds demo/test accounts
    # with round balances ($500k, $100k, $100M, $300M …) unrelated to deposits, so we cap each
    # account at 10× its deposits + $10k buffer (generous for real trading gains) and drop the rest.
    _real = "(COALESCE(td.dep_sum,0) > 0 OR COALESCE(td.wd_sum,0) > 0)"
    _cap  = "(COALESCE(td.dep_sum,0) * 10 + 10000)"
    _real_bal = f"SUM(CASE WHEN {_real} AND c.balance <= {_cap} THEN c.balance ELSE 0 END)"
    _real_eq  = (f"SUM(CASE WHEN {_real} AND COALESCE(NULLIF(c.equity,0), c.balance) <= {_cap} "
                 f"THEN COALESCE(NULLIF(c.equity,0), c.balance) ELSE 0 END)")
    sort_col = f"{_real_bal} DESC"
    if sort == "name":         sort_col = "MIN(c.name) ASC"
    elif sort == "login":      sort_col = "MIN(c.login) DESC"
    elif sort == "new":        sort_col = "MIN(td.first_tx_date) DESC NULLS LAST"
    elif sort == "score":      sort_col = (f"(COALESCE(MAX(c.call_score),0) + CASE WHEN MAX(c.lead_badge)='recapture' THEN 50 ELSE 0 END"
                                           f" + MAX(CASE WHEN c.login = ANY(:bday_boost_logins) THEN 100 ELSE 0 END)) DESC, {_real_bal} DESC")
    elif sort == "deposits":   sort_col = "SUM(COALESCE(td.dep_sum,0)) DESC"
    elif sort == "equity":     sort_col = f"{_real_eq} DESC"
    elif sort == "total_dep":  sort_col = "SUM(COALESCE(td.dep_sum,0)) DESC"
    elif sort == "total_with": sort_col = "SUM(COALESCE(td.wd_sum,0)) DESC"
    elif sort == "country":    sort_col = "MIN(c.country) ASC"
    elif sort == "city":       sort_col = "MIN(c.city) ASC"
    # (no recapture pin — Priority sorts purely by score, Newest by date)

    # Count unique clients by phone. When a deposit-count filter is active we must join the
    # per-login deposit counts and apply the same HAVING so the total reflects the filtered set.
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT cu.customer_no as ck
            FROM customers cu
            LEFT JOIN clients c ON c.customer_no = cu.customer_no
            LEFT JOIN client_tx_agg td ON td.login = c.login
            {where}
            GROUP BY ck{having}
        ) x
    """
    total = db.execute(text(count_sql), params).scalar() or 0

    # Summary statistics over the FULL filtered set (#60). The KPI bar must reflect the
    # SAME filters as the list — including the deposit-count filter — not just the visible
    # page and not the global dashboard KPIs. We aggregate at the same phone+platform grain
    # (applying the HAVING), then sum each person's deposit/withdrawal/balance.
    stats_sql = f"""
        SELECT
            COUNT(*)                          AS clients,
            COALESCE(SUM(dep_sum),0)          AS deposits,
            COALESCE(SUM(wd_sum),0)           AS withdrawals,
            COALESCE(SUM(dep_sum),0) - COALESCE(SUM(wd_sum),0) AS net_deposit,
            COALESCE(SUM(bal),0)              AS balance
        FROM (
            SELECT cu.customer_no as ck,
                   SUM(COALESCE(td.dep_sum,0)) AS dep_sum,
                   SUM(COALESCE(td.wd_sum,0))  AS wd_sum,
                   {_real_bal} AS bal
            FROM customers cu
            LEFT JOIN clients c ON c.customer_no = cu.customer_no
            LEFT JOIN client_tx_agg td ON td.login = c.login
            {where}
            GROUP BY ck{having}
        ) s
    """
    srow = db.execute(text(stats_sql), params).fetchone()
    stats = {
        "clients":      int(srow[0] or 0),
        "deposits":     float(srow[1] or 0),
        "withdrawals":  float(srow[2] or 0),
        "net_deposit":  float(srow[3] or 0),
        "balance":      float(srow[4] or 0),
    }

    # The deposit/withdrawal/net KPIs above are LIFETIME (from client_tx_agg). When a specific period
    # is selected, recompute them from transactions WITHIN that period for the SAME filtered clients,
    # so picking "This month" + an agent shows that agent's clients' deposits/withdrawals THIS MONTH.
    if period and period != "all_time":
        from ib_router import period_dates
        from datetime import date as _date, timedelta as _td
        mp_from, mp_to = period_dates(period, date_from, date_to)
        try:
            mp_to_next = (_date.fromisoformat(mp_to) + _td(days=1)).isoformat()
        except Exception:
            mp_to_next = mp_to
        pm = {**params, "mp_from": mp_from, "mp_to_next": mp_to_next}
        period_money_sql = f"""
            SELECT
                COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='deposit'),0)    AS deposits,
                COALESCE(SUM(t.amount) FILTER (WHERE t.tx_type='withdrawal'),0) AS withdrawals
            FROM customers cu
            LEFT JOIN clients c ON c.customer_no = cu.customer_no
            JOIN transactions t ON t.login = c.login
            {where} AND t.tx_date >= :mp_from AND t.tx_date < :mp_to_next
        """
        prow = db.execute(text(period_money_sql), pm).fetchone()
        stats["deposits"] = float(prow[0] or 0)
        stats["withdrawals"] = float(prow[1] or 0)
        stats["net_deposit"] = stats["deposits"] - stats["withdrawals"]

    # Main query — aggregate by phone
    query_sql = f"""
        SELECT
            MIN(c.login)              as login,
            COALESCE(MIN(c.name), MIN(cu.name))       as name,
            COALESCE(MIN(c.email), MIN(cu.email))     as email,
            COALESCE(MIN(c.phone), MIN(cu.phone))     as phone,
            COALESCE(MIN(c.country), MIN(cu.country)) as country,
            MIN(c.city)               as city,
            MIN(c.last_ip)            as ip,
            MIN(c.cid)                as cid,
            -- balance/equity from REAL accounts only (had a deposit/withdrawal and value < $1M);
            -- demo/seed accounts (e.g. 1ECN/2ECN seeded at $100k / $100M / $300M) are excluded.
            {_real_bal} as balance,
            {_real_eq} as equity,
            AVG(CASE WHEN c.margin_level IS NOT NULL AND c.margin_level > 0 THEN c.margin_level END) as margin_level,
            SUM(COALESCE(c.credit,0))  as bonus,
            SUM(COALESCE(td.dep_sum,0))  as total_deposit,
            SUM(COALESCE(td.wd_sum,0))   as total_withdraw,
            SUM(COALESCE(td.dep_sum,0)) - SUM(COALESCE(td.wd_sum,0)) as net_deposit,
            MIN(c.agent)              as agent,
            MIN(c.reg_date)           as reg_date,
            MIN(td.first_tx_date)     as first_deposit_at,
            MIN(c.first_deposit_amount) as first_deposit_amount,
            MAX(c.last_deposit_at)    as last_deposit_at,
            MAX(c.last_withdraw_at)   as last_withdraw_at,
            COALESCE(MIN(c.kyc_status), MIN(cu.kyc_status)) as kyc,
            MIN(c.risk_score)         as risk,
            COUNT(*)                  as account_count,
            BOOL_OR(COALESCE(c.is_flagged, FALSE)) as is_flagged,
            COALESCE(MIN(c.assigned_agent_id), MIN(cu.assigned_agent_id)) as assigned_agent_id,
            array_agg(DISTINCT c.login) as all_logins,
            MAX(c.lead_badge)         as lead_badge,
            MAX(c.matched_lead_id)    as matched_lead_id,
            cu.customer_no as ck,
            MAX(ml.meta_created)      as recapture_form_date,
            SUM(COALESCE(td.dep_cnt,0)) as dep_tx_count,
            array_agg(DISTINCT COALESCE(c.platform,'MT5')) as platforms,
            array_agg(DISTINCT c.group_name) FILTER (WHERE c.group_name IS NOT NULL AND c.group_name <> '') as group_names,
            BOOL_OR(COALESCE(c.is_archived, FALSE)) as is_archived,
            -- #73 (Zainab): the account number shown in the Clients list must be the
            -- person's account WITH A BALANCE — preferring the HIGHEST balance; if no
            -- account is positive, fall back to the highest-balance account overall.
            -- 1) login of the highest POSITIVE-balance account (NULL if none positive)
            (array_agg(c.login ORDER BY c.balance DESC NULLS LAST)
                FILTER (WHERE c.balance > 0))[1]                 as acct_pos_login,
            -- 2) login of the highest-balance account overall (the fallback)
            (array_agg(c.login ORDER BY c.balance DESC NULLS LAST))[1] as acct_top_login,
            MIN(cu.customer_no)       as customer_no,
            BOOL_AND(COALESCE(c.is_archived, FALSE)) as all_archived,
            COUNT(*) FILTER (WHERE COALESCE(c.is_archived, FALSE)) as archived_count,
            COALESCE(MIN(c.legacy_sales_agent), MIN(cu.sales_agent)) as sales_agent,
            MIN(cu.ib)                as customer_ib
        FROM customers cu
        LEFT JOIN clients c ON c.customer_no = cu.customer_no
        LEFT JOIN client_tx_agg td ON td.login = c.login
        LEFT JOIN leads ml ON ml.id = c.matched_lead_id
        {where}
        GROUP BY ck{having}
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """
    params["limit"]  = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(text(query_sql), params).fetchall()

    if not rows:
        return {"clients": [], "total": total, "page": page, "page_size": page_size, "stats": stats}

    logins_list = [r[0] for r in rows]
    # Every login maps to its person's representative (displayed) login = MIN(login).
    # Deposits/trades may sit on ANY of the person's accounts (MT4 + MT5), so we must
    # aggregate across all of them, not just the representative login.
    login_to_rep = {}
    all_logins_flat = []
    for r in rows:
        rep = r[0]
        logs = list(r[26]) if len(r) > 26 and r[26] else [r[0]]
        for lg in logs:
            login_to_rep[lg] = rep
            all_logins_flat.append(lg)

    # IB names in batch
    agent_ids = list({r[15] for r in rows if r[15]})
    ib_map = {}
    if agent_ids:
        ibs = db.query(models.IB).filter(models.IB.agent_id.in_(agent_ids)).all()
        ib_map = {ib.agent_id: ib.name for ib in ibs}

    # Deposits / withdrawals / last-activity aggregated across ALL of each person's logins
    last_tx_map = {}
    dep_stats_map = {}
    with_stats_map = {}
    dep_count_map = {}
    first_dep_amount_map = {}
    if all_logins_flat:
        txs = db.execute(text(
            "SELECT login, tx_type, amount, tx_date FROM transactions WHERE login = ANY(:logins)"
        ), {"logins": all_logins_flat}).fetchall()
        agg = {}
        for lg, tt, amt, txd in txs:
            rep = login_to_rep.get(lg, lg)
            a = agg.setdefault(rep, {"dep_total": 0.0, "dep_count": 0, "wd_total": 0.0,
                                     "first_dep_date": None, "first_dep_amount": 0.0,
                                     "last_date": "", "last_type": "", "last_amount": 0.0})
            amt = float(amt or 0); txd = str(txd or "")
            if tt == 'deposit':
                a["dep_total"] += amt; a["dep_count"] += 1
                if a["first_dep_date"] is None or (txd and txd < a["first_dep_date"]):
                    a["first_dep_date"] = txd; a["first_dep_amount"] = amt
            elif tt == 'withdrawal':
                a["wd_total"] += amt
            # "Last activity" = last REAL money movement. bonus_deposit / bonus_withdrawal are
            # secondary side-effects of a real deposit/withdrawal (same timestamp) — skip them so
            # they don't mask the actual activity.
            if tt in ('deposit', 'withdrawal', 'internal_transfer') and txd > a["last_date"]:
                a["last_date"] = txd; a["last_type"] = tt; a["last_amount"] = amt
        for rep, a in agg.items():
            dep_stats_map[rep] = {"dep_count": a["dep_count"],
                                  "first_dep_date": a["first_dep_date"] or "",
                                  "total_dep": a["dep_total"]}
            with_stats_map[rep] = a["wd_total"]
            dep_count_map[rep] = a["dep_count"]
            first_dep_amount_map[rep] = a["first_dep_amount"]
            last_tx_map[rep] = {"type": a["last_type"], "amount": a["last_amount"], "date": a["last_date"]}

    # Agent name lookup
    assigned_agent_ids = list({r[25] for r in rows if len(r) > 25 and r[25]})
    agent_name_map = {}
    if assigned_agent_ids:
        agents = db.execute(text("SELECT id, full_name FROM users WHERE id=ANY(:ids)"), {"ids": assigned_agent_ids}).fetchall()
        agent_name_map = {a[0]: a[1] for a in agents}

    # (dep_count_map / first_dep_amount_map / dep_stats_map are already computed above,
    #  aggregated across ALL of each person's logins — do not recompute here.)
    first_dep_map = {rep: v.get("first_dep_date") for rep, v in dep_stats_map.items()}

    # Last client activity (transactions)
    last_activity_map = {}
    try:
        acts = db.execute(text("""
            SELECT MIN(c.login) as rep_login, t.tx_type, MAX(t.tx_date) as last_date
            FROM transactions t
            JOIN clients c ON c.login = t.login
            WHERE t.tx_type IN ('deposit','withdrawal','internal_transfer')
            AND c.login = ANY(:logins)
            GROUP BY
                CASE WHEN c.phone IS NOT NULL AND c.phone != '' AND c.phone != '0'
                    THEN c.phone ELSE CAST(c.login AS TEXT) END,
                t.tx_type
            ORDER BY last_date DESC
        """), {"logins": logins_list}).fetchall()
        for a in acts:
            rep = a[0]
            if rep not in last_activity_map:
                last_activity_map[rep] = {"type": a[1], "date": str(a[2]) if a[2] else ""}
            elif a[2] and str(a[2]) > last_activity_map[rep].get("date", ""):
                last_activity_map[rep] = {"type": a[1], "date": str(a[2]) if a[2] else ""}
    except:
        pass

    # Last sales action (call_actions)
    last_action_map = {}
    try:
        login_list_str = ",".join(str(l) for l in logins_list)
        actions = db.execute(text(f"""
            SELECT DISTINCT ON (login) login, action, note, created_at, call_later_at
            FROM call_actions
            WHERE login IN ({login_list_str})
            ORDER BY login, created_at DESC
        """)).fetchall()
        for a in actions:
            last_action_map[a[0]] = {
                "type":          a[1],
                "note":          a[2],
                "date":          str(a[3]) if a[3] else "",
                "call_later_at": str(a[4]) if a[4] else "",
            }
    except:
        pass

    # Network scores (IP/CID + City + IB + Phone prefix). net_breakdown keeps the per-component
    # contribution + count so the hover can EXPLAIN how the number was reached (not a static legend).
    net_scores = {}
    net_breakdown = {}
    def _add_net(lg, label, pts, cnt):
        if pts <= 0:
            return
        net_scores[lg] = net_scores.get(lg, 0) + pts
        net_breakdown.setdefault(lg, []).append({"label": label, "points": pts, "count": cnt})
    try:
        nets = db.execute(text("""
            SELECT login_a as login, COUNT(*) as cnt FROM network_edges
            WHERE login_a = ANY(:logins) GROUP BY login_a
            UNION ALL
            SELECT login_b as login, COUNT(*) as cnt FROM network_edges
            WHERE login_b = ANY(:logins) GROUP BY login_b
        """), {"logins": logins_list}).fetchall()
        for r in nets:
            _add_net(r[0], "Shared device / IP link", r[1], r[1])

        # Same city
        city_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON c2.city = c1.city AND c2.login != c1.login
                AND c1.city IS NOT NULL AND c1.city != ''
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in city_counts:
            _add_net(r[0], "Same city", min(r[1], 10), r[1])

        # Same IB
        ib_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON c2.agent = c1.agent AND c2.login != c1.login
                AND c1.agent IS NOT NULL AND c1.agent != 0
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in ib_counts:
            _add_net(r[0], "Same IB", min(r[1], 5), r[1])

        # Same phone prefix (family)
        phone_counts = db.execute(text("""
            SELECT c1.login, COUNT(c2.login) as cnt
            FROM clients c1
            JOIN clients c2 ON LEFT(c2.phone, 7) = LEFT(c1.phone, 7)
                AND c2.login != c1.login
                AND c1.phone IS NOT NULL AND LENGTH(c1.phone) >= 7
            WHERE c1.login = ANY(:logins)
            GROUP BY c1.login
        """), {"logins": logins_list}).fetchall()
        for r in phone_counts:
            _add_net(r[0], "Same phone prefix (family)", min(r[1] * 3, 15), r[1])
    except:
        pass

    # Score settings
    settings = get_score_settings(db)

    # Birthday overlay for the visible page: map each person's rep login -> {cake_color, greeted,
    # claimed, ...}. The DOB may sit on any of a person's sibling logins, so we scan all_logins.
    page_bflags = {}
    if bwin:
        _win_set = set(bwin.keys())
        _in_page = [lg for lg in all_logins_flat if lg in _win_set]
        _est = BDE.event_state(db, _in_page) if _in_page else {}
        for r in rows:
            rep = r[0]
            sibs = list(r[26]) if len(r) > 26 and r[26] else [r[0]]
            bl = next((lg for lg in sibs if lg in _win_set), None)
            if bl is not None:
                info = bwin[bl]; s = _est.get(bl, {})
                greeted, claimed = bool(s.get("greeted")), bool(s.get("claimed"))
                page_bflags[rep] = {"in_window": True, "greeted": greeted, "claimed": claimed,
                                    "cake_color": BDE._cake_color(greeted, claimed),
                                    "birthday_date": info["birthday_date"], "days_to": info["days_to"]}

    clients = []
    for r in rows:
        login  = r[0]
        agent  = r[15]
        la     = last_action_map.get(login, {})
        lact   = last_activity_map.get(login, {})

        mapped = {
            "login":               login,
            "name":                r[1] or "",
            "email":               r[2] or "",
            "phone":               r[3] or "",
            "country":             r[4] or "",
            "city":                r[5] or "",
            "ip":                  r[6] or "",
            "cid":                 r[7] or "",
            "balance":             float(r[8] or 0),
            "equity":              float(r[9] or 0),
            "margin_level":        float(r[10] or 0) if r[10] else 0.0,
            "bonus":               float(r[11] or 0),
            "total_deposit":       dep_stats_map.get(login, {}).get("total_dep") or float(r[12] or 0),
            "total_withdraw":      with_stats_map.get(login) or float(r[13] or 0),
            "dep_count":           dep_stats_map.get(login, {}).get("dep_count", 0),
            "net_deposit":         dep_stats_map.get(login, {}).get("total_dep", 0) - with_stats_map.get(login, 0),
            "ib":                  str(agent or ""),
            # prefer a NAME: account-agent IB name (ibs) -> customer's referrer IB name -> #number
            "ib_display":          (ib_map.get(agent) or (r[41] if len(r) > 41 and r[41] else None)
                                    or (f"#{agent}" if agent else "")),
            "reg_date":            r[16] or "",
            "kyc":                 "verified",   # RULE: clients are always approved KYC
            "email_verified":      True,
            "phone_verified":      True,
            "risk":                r[22] or "low",
            "account_count":       r[23] or 1,
            "first_deposit_date":  dep_stats_map.get(login, {}).get("first_dep_date", "") or (str(r[17]) if len(r) > 17 and r[17] else ""),
            "first_deposit_amount": first_dep_amount_map.get(login, 0) or (float(r[18] or 0) if len(r) > 18 and r[18] else 0),
            "deposit_count":       dep_count_map.get(login, 0),
            "last_activity_type":  last_tx_map.get(login, {}).get("type", _get_last_activity_type(r[19], r[20]) if len(r) > 20 else ""),
            "last_activity_date":  last_tx_map.get(login, {}).get("date", str(max(filter(None, [r[19] if len(r)>19 else None, r[20] if len(r)>20 else None]), default="")) if len(r) > 19 else ""),
            "last_activity_amount": last_tx_map.get(login, {}).get("amount", 0),
            "assigned_agent_id": r[25] if len(r)>25 else None,
            "last_action_type":    la.get("type", ""),
            "last_action_note":    la.get("note", ""),
            "last_action_date":    la.get("date", ""),
            "last_action":         la,
            "network_score":       net_scores.get(login, 0),
            "network_breakdown":   net_breakdown.get(login, []),
            "flags":               [],
            "agent_name":          agent_name_map.get(r[25] if len(r)>25 else None, ""),
            "all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],
            "lead_badge":          r[27] if len(r)>27 else None,
            "matched_lead_id":     r[28] if len(r)>28 else None,
            "recapture_form_date": str(r[30]) if len(r) > 30 and r[30] else "",
            # #73 (Zainab): account number = the person's account WITH a balance,
            # preferring the highest balance; fall back to the highest-balance account
            # overall, then to the representative login. (#44/#61 unchanged otherwise.)
            "account_number":      (r[35] if len(r) > 35 and r[35] else
                                    (r[36] if len(r) > 36 and r[36] else login)),
            "dep_tx_count":        int(r[31]) if len(r) > 31 and r[31] is not None else 0,
            "platforms":           [p for p in (list(r[32]) if len(r) > 32 and r[32] else []) if p],
            "account_types":       [g for g in (list(r[33]) if len(r) > 33 and r[33] else []) if g],
            "is_archived":         bool(r[34]) if len(r) > 34 and r[34] else False,
            "customer_no":         (r[37] if len(r) > 37 else None),
            "all_archived":        bool(r[38]) if len(r) > 38 and r[38] else False,
            "archived_count":      int(r[39]) if len(r) > 39 and r[39] else 0,
            "sales_agent":         (r[40] if len(r) > 40 else None),
            "source":              "none",
        }
        mapped["call_score"] = calc_priority_score(mapped, settings)
        mapped["score_breakdown"] = score_breakdown(mapped, settings)
        if mapped.get("lead_badge") == "recapture":
            mapped["call_score"] += 50
            mapped["score_breakdown"] = [{"label": "Recapture lead (re-deposited)", "points": 50}] + mapped["score_breakdown"]
        # Birthday overlay: 🎂 cake + a +100 priority boost until the client is greeted (called).
        bf = page_bflags.get(login)
        if bf:
            mapped["birthday"] = bf
            if not bf["greeted"]:
                mapped["call_score"] += 100
                mapped["score_breakdown"] = [{"label": "🎂 Birthday this week", "points": 100}] + mapped["score_breakdown"]
        clients.append(mapped)

    # If sorting by priority, sort by call_score desc
    if sort == "score":
        clients.sort(key=lambda x: x["call_score"], reverse=True)

    return {"clients": clients, "total": total, "page": page, "page_size": page_size, "stats": stats}


# ── Admin-only: create an ADDITIONAL real MT account for an existing client (ticket #98) ──
# CREATE ONLY. There is NO delete endpoint here by design — the user explicitly approved
# "create yes, delete no". Do not add one. mt_provision.delete_account is never called.
_PROVISION_ROLES = {"super_admin", "admin", "director"}


@router.post("/{login}/additional-account")
async def create_additional_account(
    login: int,
    body: AdditionalAccount,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ── admin-only gate ─────────────────────────────────────────────────────────
    if rbac._role(current_user) not in _PROVISION_ROLES:
        raise HTTPException(status_code=403, detail="Only admins can create trading accounts")

    # ── load the existing client (the person we're adding an account FOR) ───────
    c = db.query(models.Client).filter(models.Client.login == login).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    platform = (body.platform or "MT5").strip().upper()
    if platform != "MT5":
        # Only MT5 provisioning is wired through the bridge (same limitation as
        # registration_router.activate). Be explicit rather than silently failing.
        raise HTTPException(status_code=400,
                            detail="Only MT5 account creation is supported right now (MT4 not wired)")

    # split the person's name into first/last (best-effort, mirrors registration)
    full = (c.name or "").strip()
    parts = full.split()
    first = parts[0] if parts else (full or "Client")
    last = " ".join(parts[1:]) if len(parts) > 1 else ""

    import mt_provision
    group = mt_provision.real_group(body.account_type, bool(body.islamic))
    try:
        lev = int(body.leverage or 500)
    except Exception:
        lev = 500

    res = mt_provision.create_account(
        group, first, last, leverage=lev,
        email=c.email or "", phone=c.phone or "",
        country=c.country or "", city=c.city or "",
        agent=int(c.agent or 0),
    )
    if not res.get("ok") or not res.get("login"):
        # bridge failure — surface the real error, never fabricate success
        raise HTTPException(status_code=502,
                            detail=f"MT bridge could not create the account: {res.get('error') or 'unknown error'}")
    new_login = int(res["login"])

    # ── optional initial credit ────────────────────────────────────────────────
    credit_res = None
    if body.initial_credit and body.initial_credit > 0:
        credit_res = mt_provision.credit_account(new_login, float(body.initial_credit), "Initial credit")

    # ── persist additively so the new account shows up in the CRM immediately ───
    # A new clients row for the SAME person (copy contact details, new login), and a
    # matching trading_accounts row (same shape import_mt4_clients / bridge sync use).
    try:
        db.execute(text("""
            INSERT INTO clients (login, name, email, phone, country, city, nationality,
                                 group_name, leverage, agent, platform, account_type,
                                 reg_date, source, is_flagged, assigned_agent_id, ib_id)
            VALUES (:lg,:nm,:em,:ph,:co,:ci,:nat,:g,:lev,:agent,:pl,:at,
                    NOW(),'admin_created',FALSE,:aaid,:ibid)
            ON CONFLICT (login) DO NOTHING
        """), {"lg": new_login, "nm": c.name, "em": c.email, "ph": c.phone,
               "co": c.country, "ci": c.city, "nat": c.nationality,
               "g": group, "lev": lev, "agent": c.agent, "pl": platform,
               "at": body.account_type, "aaid": c.assigned_agent_id, "ibid": c.ib_id})

        db.execute(text("""
            INSERT INTO trading_accounts (login, client_id, name, email, phone, group_name,
                                          account_type, is_islamic, leverage, balance, credit,
                                          agent, country, city, platform, reg_date, source,
                                          is_active, created_at)
            VALUES (:lg,:cid,:nm,:em,:ph,:g,:at,:isl,:lev,0,:credit,:agent,:co,:ci,
                    :pl,NOW(),'admin_created',TRUE,NOW())
            ON CONFLICT (login) DO NOTHING
        """), {"lg": new_login, "cid": None, "nm": c.name, "em": c.email, "ph": c.phone,
               "g": group, "at": body.account_type, "isl": bool(body.islamic), "lev": lev,
               "credit": float(body.initial_credit or 0), "agent": c.agent,
               "co": c.country, "ci": c.city, "pl": platform})
        db.commit()
    except Exception as e:
        # The MT account WAS created on the server; only the CRM mirror failed. Roll back
        # the session and report it — the bridge sync loop will pick the account up anyway.
        db.rollback()
        return {"ok": True, "login": new_login, "password": res.get("master"),
                "investor_password": res.get("investor"), "group": group,
                "credit": credit_res,
                "warning": f"account created on MT server but CRM mirror failed: {e}"}

    return {"ok": True, "login": new_login, "password": res.get("master"),
            "investor_password": res.get("investor"), "group": group, "credit": credit_res}


@router.get("/{login}")
async def get_client(
    login: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    c = db.query(models.Client).filter(models.Client.login == login).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    # Role-based visibility: agents/managers may only open their own/team clients
    if not rbac.can_see_agent(db, current_user, c.assigned_agent_id):
        raise HTTPException(status_code=403, detail="Not authorized to view this client")

    # All accounts with same phone
    accounts = []
    if c.phone and c.phone not in ('', '0'):
        accounts = db.query(models.Client).filter(
            models.Client.phone == c.phone
        ).all()
    if not accounts:
        accounts = [c]

    all_logins = [a.login for a in accounts]

    # IB info
    ib_display = ""
    if c.agent:
        ib = db.query(models.IB).filter(models.IB.agent_id == c.agent).first()
        if ib:
            ib_display = f"{ib.name} ({ib.ib_code})"

    # Transactions
    deposits = db.query(models.Transaction).filter(
        models.Transaction.login.in_(all_logins),
        models.Transaction.tx_type == "deposit"
    ).order_by(models.Transaction.tx_date.desc()).limit(200).all()

    withdrawals = db.query(models.Transaction).filter(
        models.Transaction.login.in_(all_logins),
        models.Transaction.tx_type == "withdrawal"
    ).order_by(models.Transaction.tx_date.desc()).limit(200).all()

    # Internal transfers between the client's own accounts (ticket #87, Jwan).
    # tx_type='internal_transfer'; the counterparty login is named in method/notes,
    # e.g. 'Transfer - from 438906 [MT4]' (money IN) / 'Transfer - to 437991 [MT4]'
    # (money OUT). We parse from→to the same way transactions_router does.
    transfers = db.query(models.Transaction).filter(
        models.Transaction.login.in_(all_logins),
        models.Transaction.tx_type == "internal_transfer"
    ).order_by(models.Transaction.tx_date.desc()).limit(300).all()

    # Activity dates derived from REAL data — the clients.*_at columns are stale/empty
    # (deposit truth lives in transactions, trade truth in deals).
    _dep_dates = [d.tx_date for d in deposits if d.tx_date]
    _wd_dates  = [d.tx_date for d in withdrawals if d.tx_date]
    act_first_dep_date = str(min(_dep_dates)) if _dep_dates else str(c.first_deposit_at or "")
    act_last_dep_date  = str(max(_dep_dates)) if _dep_dates else str(c.last_deposit_at or "")
    act_last_wd_date   = str(max(_wd_dates))  if _wd_dates  else str(c.last_withdraw_at or "")
    act_first_dep_amt  = float(min(deposits, key=lambda d: d.tx_date).amount or 0) if _dep_dates else float(c.first_deposit_amount or 0)
    try:
        _lt = db.execute(
            text("SELECT MAX(deal_date) FROM deals WHERE login = ANY(:lg) AND action IN (0,1)"),
            {"lg": all_logins},
        ).scalar()
        act_last_trade_date = str(_lt) if _lt else str(c.last_trade_at or "")
    except Exception:
        act_last_trade_date = str(c.last_trade_at or "")

    import re as _re_xfer
    _XFER_RE = _re_xfer.compile(r"\b(from|to)\b\s*#?\s*(\d+)", _re_xfer.I)

    def _parse_transfer(login, method, notes):
        blob = f"{method or ''} || {notes or ''}"
        m = _XFER_RE.search(blob)
        me = str(login) if login is not None else ""
        if not m:
            return ("", "")
        direction, other = m.group(1).lower(), m.group(2)
        return (other, me) if direction == "from" else (me, other)

    # Network connections
    connections = []
    try:
        from sqlalchemy import or_
        edges = db.query(models.NetworkEdge).filter(
            or_(
                models.NetworkEdge.login_a == login,
                models.NetworkEdge.login_b == login,
            )
        ).limit(30).all()
        for e in edges:
            other = e.login_b if e.login_a == login else e.login_a
            other_c = db.query(models.Client).filter(models.Client.login == other).first()
            connections.append({
                "login":   other,
                "name":    other_c.name if other_c else f"#{other}",
                "reason":  e.reason or "",
                "value":   e.value or "",
                "risk":    other_c.risk_score if other_c else "low",
            })
    except:
        pass

    # Call actions
    actions = db.query(models.CallAction).filter(
        models.CallAction.login == login
    ).order_by(models.CallAction.created_at.desc()).all()

    # Timeline — merge all activities
    timeline = []
    for d in deposits[:10]:
        timeline.append({"type": "deposit", "amount": float(d.amount or 0), "method": d.method or "", "date": str(d.tx_date), "account": d.login})
    for d in withdrawals[:5]:
        timeline.append({"type": "withdrawal", "amount": float(d.amount or 0), "method": d.method or "", "date": str(d.tx_date), "account": d.login})
    for a in actions[:5]:
        timeline.append({"type": "call_action", "action": a.action, "note": a.note or "", "date": a.created_at.isoformat() if a.created_at else "", "agent": a.agent_id})
    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)

    total_balance  = sum(float(a.balance or 0) for a in accounts)
    total_equity   = sum(float(a.equity or a.balance or 0) for a in accounts)
    all_logins = [a.login for a in accounts]
    # Total deposits / withdrawals (ticket #86, Jwan): sum the client's REAL
    # transactions across ALL of the person's logins, EXCLUDING internal MT5
    # balance adjustments (method='MT5') and the MT4 'Deposit Fix' / 'Cashback' /
    # 'Stop out compensation' non-deposit labels — consistent with the Deposits
    # view. The old code summed the stale clients.total_deposits column (often
    # NULL/wrong) and only fell back to (unfiltered) transactions when it was 0.
    total_deposits = 0.0
    total_withdraw = 0.0
    if all_logins:
        drow = db.execute(text(f"""
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit'    AND {_REAL_METHOD_SQL}),0) AS dep,
                COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND {_REAL_METHOD_SQL}),0) AS wd
            FROM transactions WHERE login=ANY(:l)
        """), {"l": all_logins, "internal_re": _INTERNAL_LABEL_RE}).fetchone()
        total_deposits = float(drow[0] or 0)
        total_withdraw = float(drow[1] or 0)
    # Lowest non-zero margin across all accounts
    margins = [float(a.margin_level) for a in accounts if a.margin_level and float(a.margin_level) > 0]
    min_margin = min(margins) if margins else 0

    return {
        "login":          c.login,
        "customer_no":    getattr(c, "customer_no", None) or "",
        "sales_agent":    getattr(c, "legacy_sales_agent", None) or "",
        "name":           c.name or "",
        "email":          c.email or "",
        "phone":          c.phone or "",
        "country":        c.country or "",
        "city":           c.city or "",
        "ip":             c.last_ip or "",
        "cid":            str(c.cid or ""),
        "date_of_birth":  c.date_of_birth or "",
        "full_name_en":   getattr(c, "full_name_en", None) or "",
        # RULE: anyone in the clients list is treated as fully verified (KYC + email + phone).
        "email_verified": True,
        "phone_verified": True,
        "ocr_name_en":    _ocr_english_name(db, c),
        "balance":        total_balance,
        "equity":         total_equity,
        "bonus":          sum(float(a.credit or 0) for a in accounts),
        "margin_level":   min_margin,
        "total_deposit":  total_deposits,
        "total_withdraw": total_withdraw,
        "net_deposit":    total_deposits - total_withdraw,
        "ib":             str(c.agent or ""),
        "ib_display":     ib_display,
        "reg_date":       str(c.first_deposit_at or c.reg_date or ""),
        "kyc":            "verified",   # RULE: clients are always approved KYC
        "risk":           c.risk_score or "low",
        "account_count":  len(accounts),
        "first_deposit_date":   act_first_dep_date,
        "first_deposit_amount": act_first_dep_amt,
        "last_deposit_date":    act_last_dep_date,
        "last_withdraw_date":   act_last_wd_date,
        "last_trade_date":      act_last_trade_date,
        "last_login_date":      str(c.last_login_at or ""),
        # Account group + leverage (ticket #50) — from the client's MT account record
        "group":          c.group_name or "",
        "group_name":     c.group_name or "",
        "leverage":       c.leverage or 0,
        "platform":       getattr(c, "platform", None) or "MT5",
        "related_accounts": [{
            "login":      a.login,
            "balance":    float(a.balance or 0),
            "equity":     float(a.equity or 0),
            "group":      a.group_name or "",
            "group_name": a.group_name or "",
            "leverage":   a.leverage or 0,
            "platform":   getattr(a, "platform", None) or "MT5",
            "is_active":  a.is_active,
            "archived":   bool(getattr(a, "archived_at", None)),
        } for a in accounts],
        "deposits_list": [{
            "deal_id": d.deal_id, "amount": float(d.amount or 0),
            "date": str(d.tx_date), "method": d.method or "",
            "account": d.login, "status": d.status or "approved"
        } for d in deposits],
        "withdrawals_list": [{
            "deal_id": d.deal_id, "amount": float(d.amount or 0),
            "date": str(d.tx_date), "method": d.method or "",
            "account": d.login, "status": d.status or "approved"
        } for d in withdrawals],
        "transfers_list": [
            {
                "deal_id": d.deal_id,
                "amount": float(d.amount or 0),
                "date": str(d.tx_date),
                "account": d.login,
                "from_account": (_pt := _parse_transfer(d.login, d.method, d.notes))[0],
                "to_account": _pt[1],
                "notes": d.notes or "",
                "status": d.status or "approved",
            }
            for d in transfers
        ],
        "network_connections": connections,
        "timeline": timeline,
        "actions_history": [{
            "action":     a.action,
            "note":       a.note or "",
            "created_at": a.created_at.isoformat() if a.created_at else "",
            "agent_id":   a.agent_id,
        } for a in actions],
        "flags":      [],
        "call_score": 0,
        "source":     "none",
    }


@router.patch("/{login}/contact")
async def update_client_contact(
    login: int,
    data: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Admin edit of a client's email / phone / portal password / date of birth /
    English name / verification flags. Setting a new password also bumps tokens_valid_after
    so the client's existing portal sessions are logged out (per CLAUDE.md session-invalidation).
    """
    c = db.query(models.Client).filter(models.Client.login == login).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    if not rbac.can_see_agent(db, current_user, c.assigned_agent_id):
        raise HTTPException(status_code=403, detail="Not authorized to edit this client")

    sets: dict = {}
    params: dict = {"lg": login}

    if data.email is not None:
        email = (data.email or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email cannot be empty")
        if "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(status_code=400, detail="Invalid email address")
        sets["email"] = ":email"; params["email"] = email

    if data.phone is not None:
        sets["phone"] = ":phone"; params["phone"] = (data.phone or "").strip()

    if data.date_of_birth is not None:
        sets["date_of_birth"] = ":dob"; params["dob"] = (data.date_of_birth or "").strip() or None

    if data.full_name_en is not None:
        sets["full_name_en"] = ":fne"; params["fne"] = (data.full_name_en or "").strip() or None

    if data.email_verified is not None:
        sets["email_verified"] = ":ev"; params["ev"] = bool(data.email_verified)

    if data.phone_verified is not None:
        sets["phone_verified"] = ":pv"; params["pv"] = bool(data.phone_verified)

    pw = (data.password or "").strip()
    if pw:
        if len(pw) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        sets["password_hash"] = ":pwh"; params["pwh"] = get_password_hash(pw)
        # log out the client's existing portal sessions
        sets["tokens_valid_after"] = "NOW()"

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    # apply to THIS login plus all the person's phone+platform siblings (same aggregation as the
    # Clients list) so the edited contact details stay consistent across their accounts.
    target_logins = [login]
    if data.email is not None or data.phone is not None:
        # contact (email/phone) is per-person -> propagate to siblings sharing the phone
        if c.phone and c.phone not in ("", "0"):
            sib = db.execute(text("SELECT login FROM clients WHERE phone=:p"), {"p": c.phone}).fetchall()
            target_logins = list({login, *[r[0] for r in sib]})
    params["target"] = target_logins

    set_clause = ", ".join(f"{col}={expr}" for col, expr in sets.items())
    db.execute(text(f"UPDATE clients SET {set_clause} WHERE login = ANY(:target)"), params)
    db.commit()

    c2 = db.query(models.Client).filter(models.Client.login == login).first()
    return {
        "message": "Updated",
        "login": login,
        "email": c2.email or "",
        "phone": c2.phone or "",
        "date_of_birth": c2.date_of_birth or "",
        "full_name_en": getattr(c2, "full_name_en", None) or "",
        "email_verified": bool(getattr(c2, "email_verified", False)),
        "phone_verified": bool(getattr(c2, "phone_verified", False)),
        "password_changed": bool(pw),
        "updated_logins": target_logins,
    }


# ───────────────────────── ADMIN: block / delete an account ─────────────────────────
_ADMIN_ROLES = {"super_admin", "admin", "director"}


def _person_logins(db: Session, login: int):
    """All logins of the person behind `login` (their phone+account siblings), so block/delete
    apply to the whole account, not one trading login."""
    phone = db.execute(text("SELECT phone FROM clients WHERE login=:l"), {"l": login}).scalar()
    if phone and str(phone) not in ("", "0"):
        rs = db.execute(text("SELECT login FROM clients WHERE phone=:p"), {"p": phone}).fetchall()
        return list({login, *[r[0] for r in rs]})
    return [login]


@router.post("/{login}/block")
def block_client(login: int, data: dict | None = None, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """ADMIN: block (or unblock) a client account — disables the client portal login and freezes
    their trading accounts. Reversible."""
    if (current_user.role or "").lower() not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="You don't have permission to block accounts.")
    db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE")); db.commit()
    blocked = True if data is None else bool(data.get("blocked", True))
    logins = _person_logins(db, login)
    db.execute(text("UPDATE clients SET is_blocked=:b, updated_at=NOW() WHERE login = ANY(:ls)"),
               {"b": blocked, "ls": logins})
    db.execute(text("UPDATE trading_accounts SET is_active=:act WHERE login = ANY(:ls)"),
               {"act": (not blocked), "ls": logins})
    db.commit()
    return {"ok": True, "blocked": blocked, "count": len(logins), "logins": logins}


@router.delete("/{login}")
def delete_client(login: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """ADMIN: permanently delete a client account and all of its data (trading accounts, transactions,
    deals, device links, portal requests). Destructive & irreversible — admin only."""
    if (current_user.role or "").lower() not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="You don't have permission to delete accounts.")
    logins = _person_logins(db, login)
    deleted = {}
    for tbl in ("account_identifiers", "portal_money_requests", "portal_kyc_submissions",
                "transactions", "deals", "trading_accounts", "clients"):
        try:
            r = db.execute(text(f"DELETE FROM {tbl} WHERE login = ANY(:ls)"), {"ls": logins})
            deleted[tbl] = r.rowcount
            db.commit()
        except Exception:
            db.rollback()   # table/column may not exist for every login set — skip cleanly
    return {"ok": True, "deleted_logins": logins, "rows": deleted}


@router.post("/action")
def save_action(
    data: ActionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    call_later_at = None
    if data.action == "call_later":
        now = datetime.now(timezone.utc)
        call_later_at = now + timedelta(
            days=data.call_later_days or 0,
            hours=data.call_later_hours or 0
        )
    db.add(models.CallAction(
        login=data.login,
        agent_id=current_user.id,
        action=data.action,
        note=data.note,
        call_later_at=call_later_at,
        passed_to_manager=data.pass_to_manager or False,
    ))
    db.commit()
    # A successful call ('Connected & Done') during the client's birthday window records the greeting:
    # the +100 birthday priority score drops off and the 🎂 cake turns gold (no-op outside the window).
    if data.action == "connected_done":
        try:
            import birthday_engine as BD
            BD.mark_greeted(db, data.login, by=getattr(current_user, "email", "") or "staff")
        except Exception:
            db.rollback()
    return {"message": "Action saved"}


@router.post("/assign")
def assign_client(
    login: int, agent_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    existing = db.query(models.ClientAssignment).filter(
        models.ClientAssignment.login == login
    ).first()
    if existing:
        existing.agent_id = agent_id
    else:
        db.add(models.ClientAssignment(login=login, agent_id=agent_id))
    db.commit()
    return {"message": "Assigned"}


class ArchiveRequest(BaseModel):
    """Archive / unarchive one or more clients (#57). Pass logins to bulk-toggle, or use the
    per-row path param. archived=True archives, False unarchives. The flag is applied to the
    client's phone+platform siblings too so an aggregated list row archives as one unit."""
    logins:   list[int] = []
    archived: bool = True


@router.post("/archive")
def archive_clients(
    data: ArchiveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not data.logins:
        raise HTTPException(status_code=400, detail="No logins provided")
    # Expand each login to its phone+platform siblings so the aggregated row toggles together.
    rows = db.execute(text("""
        SELECT login FROM clients
        WHERE phone IN (SELECT phone FROM clients WHERE login = ANY(:lg)
                        AND phone IS NOT NULL AND phone NOT IN ('', '0'))
           OR login = ANY(:lg)
    """), {"lg": data.logins}).fetchall()
    targets = list({r[0] for r in rows} | set(data.logins))
    # Admin archive = USER-wise (person removed from the Clients page -> Archive page). NOT the MT
    # per-account archive (that's automatic, weekly). Unarchive clears it.
    if data.archived:
        db.execute(text("UPDATE clients SET user_archived=TRUE, user_archived_at=NOW(), updated_at=NOW() WHERE login = ANY(:lg)"),
                   {"lg": targets})
    else:
        db.execute(text("UPDATE clients SET user_archived=FALSE, user_archived_at=NULL, updated_at=NOW() WHERE login = ANY(:lg)"),
                   {"lg": targets})
    db.commit()
    return {"message": "archived" if data.archived else "unarchived",
            "archived": bool(data.archived), "count": len(targets), "logins": targets}


@router.post("/{login}/archive")
def archive_client(
    login: int,
    data: dict | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    archived = True if data is None else bool(data.get("archived", True))
    c = db.query(models.Client).filter(models.Client.login == login).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    targets = [login]
    if c.phone and c.phone not in ("", "0"):
        sib = db.execute(text("SELECT login FROM clients WHERE phone=:p"), {"p": c.phone}).fetchall()
        targets = list({login, *[r[0] for r in sib]})
    # Admin archive = USER-wise (removes the person from the Clients page). Unarchive clears it.
    if archived:
        db.execute(text("UPDATE clients SET user_archived=TRUE, user_archived_at=NOW(), updated_at=NOW() WHERE login = ANY(:lg)"),
                   {"lg": targets})
    else:
        db.execute(text("UPDATE clients SET user_archived=FALSE, user_archived_at=NULL, updated_at=NOW() WHERE login = ANY(:lg)"),
                   {"lg": targets})
    db.commit()
    return {"message": "archived" if archived else "unarchived",
            "archived": archived, "count": len(targets), "logins": targets}


@router.post("/{login}/unarchive")
def unarchive_client(
    login: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Convenience inverse of /{login}/archive (#57) — moves a client back to the active list."""
    return archive_client(login, {"archived": False}, db, current_user)


@router.post("/{login}/comment")
async def post_comment(
    login: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from models import CallAction
    action = CallAction(
        login=login,
        agent_id=current_user.id,
        action="comment",
        note=data.get("note",""),
        created_at=datetime.utcnow()
    )
    db.add(action)
    db.commit()
    return {"message": "Comment posted"}
