"""
ib_router.py — IB Admin pages
Covers:
- IB list with KPIs and period selector
- IB profile with 5 tabs: Clients, Leads, Commission, Sub-IBs, Referral links
- Commission payment
- IB level promotion
- Sub-IB detection (IB who referred another IB)
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, date, timedelta
from database import get_db
from auth import get_current_user
import models
import rbac
from ib_portal_auth import staff_or_own_ib
import ib_challenges
from perf_cache import cached

router = APIRouter(prefix="/ibs", tags=["IBs"])


# go-live hardening: IB management writes (levels, thresholds, payouts, creation) are for
# the IB desk / management — not the whole floor.
_IB_MGMT = {"super_admin", "admin", "director", "sales_manager", "backoffice"}

def _assert_can_see_ib(db, user, ib_id):
    """Scope-gate a single IB profile for STAFF (the LIST is scoped, so the DETAIL must be too —
    else a scoped agent/leader could read ANY IB's client book by iterating ib_id). IB self-access
    (user is None, already ownership-checked by staff_or_own_ib) always passes.

    An IB is "yours" if the IB's OWN account (clients.login = ibs.agent_id) is assigned to a visible
    agent — the SAME rule the IB list uses."""
    if user is None:
        return
    if not rbac.section_allowed(db, user, "ibs"):
        raise HTTPException(status_code=403, detail="You don't have access to IB data.")
    scope = rbac.scope_agent_ids(db, user, section="ibs")
    if scope is None:
        return                      # all-access role
    if scope:
        agent_login = db.execute(text("SELECT agent_id FROM ibs WHERE id=:i"), {"i": ib_id}).scalar()
        if agent_login is not None:
            hit = db.execute(text("SELECT 1 FROM clients WHERE login=:a AND assigned_agent_id = ANY(:sc) LIMIT 1"),
                             {"a": agent_login, "sc": scope}).fetchone()
            if hit:
                return
    raise HTTPException(status_code=403, detail="This IB is not in your team.")


def _require_ib_mgmt(current_user):
    if (getattr(current_user, "role", "") or "").lower() not in _IB_MGMT:
        raise HTTPException(status_code=403, detail="IB management only")


@router.get("/access")
def ib_access(name: str = Query(...), db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    """Can THIS user open the details page for the IB named `name`?
    Powers the click-IB-name flow (leads/clients/transactions/trading-accounts): the first
    click filters the table, the second click opens the IB page ONLY if the IB is "under" the
    caller (same team-scope rule as _assert_can_see_ib) — else the UI shows "not yours".
    Returns {ib_id, can_view, reason}. Read-only; never raises to the caller."""
    try:
        row = db.execute(text("SELECT id FROM ibs WHERE name ILIKE :n ORDER BY id LIMIT 1"),
                         {"n": name}).fetchone()
    except Exception:
        db.rollback(); row = None
    if not row:
        return {"ib_id": None, "can_view": False, "reason": "not_found"}
    ib_id = int(row[0])
    try:
        _assert_can_see_ib(db, current_user, ib_id)
        return {"ib_id": ib_id, "can_view": True, "reason": "ok"}
    except HTTPException:
        db.rollback()
        return {"ib_id": ib_id, "can_view": False, "reason": "not_yours"}
    except Exception:
        db.rollback()
        return {"ib_id": ib_id, "can_view": False, "reason": "error"}

# commission points: FX pairs + gold (XAU*) earn the IB's level per lot; everything else 1.
_CUR = "USD|EUR|GBP|JPY|AUD|NZD|CAD|CHF|TRY|ZAR|MXN|SGD|HKD|NOK|SEK|DKK|PLN|CNH|CZK|HUF|RUB|INR|THB|CNY"
FX_OR_GOLD = (
    "(d.symbol ILIKE 'XAU%' OR upper(regexp_replace(d.symbol,'[^A-Za-z]','','g')) "
    f"~ '^({_CUR})({_CUR})')"
)
# grade ladder (desk sheet Jul 13 2026) — display names; requirements live in ib_tier_requirements
TIER_NAMES = {5: "Bronze", 6: "Silver", 7: "Golden", 8: "Diamond", 9: "Legendary", 10: "Prime IB"}

# ── FTD / NDA per IB — THE single source of truth (params :fn_from, :fn_to_next) ──────────
# DESK RULE (Jul 13 2026): a customer is this IB's FTD only if their FIRST-EVER deposited
# trading account — across ALL their accounts, under ANY IB — sits under THIS IB. Someone who
# first deposited elsewhere and later opened an account here is an ADDITIONAL account, not an
# FTD. NDA = an FTD here that is also genuinely new (is_nda).
#
# The IB profile (get_ib) restricts to the IB's own customers first, but that restriction is
# REDUNDANT: if a customer's globally-first deposited account belongs to this IB, they trivially
# have an account here. So the rule collapses to one cheap pass — "whose agent owns each
# customer's globally-first deposit" — grouped by agent, then summed over every agent login the
# person behind the IB owns (ext_ib_id siblings + IB-group accounts linked by email/customer_no).
# ~0.4s for all ~1.3k IBs, and verified to reproduce get_ib's per-IB numbers exactly.
#
# The IB Admin LIST used to filter `c.agent = ANY(...)` BEFORE the DISTINCT ON, which picked the
# first deposit among only THIS IB's accounts -> it counted customers who first deposited under a
# different IB and over-reported badly (one IB showed 65 FTD vs the profile's 9). Both the list
# and the ftd/nda sort now use THIS sql, so the list and the profile can never disagree again.
# It ALSO returns the live per-IB `accounts` / `persons` counts over the same agent set, because
# the list's Accounts column used the STORED ibs.active_clients (written by build_ibs with a
# narrower per-agent scope, only ext_ib_id-summed, and stale until build_ibs re-runs).
#   accounts = the IB's referred TRADING ACCOUNTS (raw clients rows; the IB's own account excluded)
#   persons  = those accounts merged into people by phone+platform — the same rule get_ib's
#              person_count uses for the profile's Clients tab.
# Returns: ib_id (primary ibs.id), agent_id (its primary agent), ftd, nda, accounts, persons.
IB_STATS_SQL = """
WITH ib_base AS (
    SELECT i.id, i.agent_id, i.ext_ib_id, LOWER(NULLIF(i.email,'')) AS em, cc.customer_no
    FROM ibs i LEFT JOIN clients cc ON cc.login = i.agent_id
    WHERE i.is_primary IS NOT FALSE
),
ib_agents AS (   -- every agent login belonging to the person behind each IB row
    SELECT b.id, s.agent_id AS agent FROM ib_base b
      JOIN ibs s ON (s.id = b.id OR (b.ext_ib_id IS NOT NULL AND s.ext_ib_id = b.ext_ib_id))
    UNION
    SELECT b.id, c.login FROM ib_base b JOIN clients c
      ON LOWER(c.email) = b.em AND c.group_name ~ '^(TNFX-IB-|IB.IB-)'
     WHERE b.em IS NOT NULL
    UNION
    SELECT b.id, c.login FROM ib_base b JOIN clients c
      ON c.customer_no = b.customer_no AND c.group_name ~ '^(TNFX-IB-|IB.IB-)'
     WHERE b.customer_no IS NOT NULL
    UNION
    SELECT b.id, b.agent_id FROM ib_base b
),
fa AS (          -- each customer's GLOBALLY-first deposited account
    SELECT DISTINCT ON (customer_no) customer_no, agent,
           NULLIF(first_deposit_at,'') AS fd, is_nda
    FROM clients
    WHERE NULLIF(first_deposit_at,'') IS NOT NULL AND customer_no IS NOT NULL
    ORDER BY customer_no, NULLIF(first_deposit_at,'') ASC
),
per_agent AS (
    SELECT fa.agent,
           COUNT(*) FILTER (WHERE fa.fd >= :fn_from AND fa.fd < :fn_to_next)                 AS ftd,
           COUNT(*) FILTER (WHERE fa.fd >= :fn_from AND fa.fd < :fn_to_next AND fa.is_nda)   AS nda
    FROM fa WHERE fa.agent IS NOT NULL GROUP BY fa.agent
),
ftd_ib AS (      -- a customer has exactly ONE globally-first account, so summing over the
                 -- person's agent logins counts each customer once (no double counting)
    SELECT ia.id, COALESCE(SUM(pa.ftd),0)::int AS ftd, COALESCE(SUM(pa.nda),0)::int AS nda
    FROM ib_agents ia LEFT JOIN per_agent pa ON pa.agent = ia.agent
    GROUP BY ia.id
),
cl_ib AS (       -- live referred accounts / merged people, same agent set as the profile
    SELECT ia.id,
           COUNT(*)::int AS accounts,
           COUNT(DISTINCT COALESCE(NULLIF(c.phone,''),'L'||c.login::text)
                          ||'|'||COALESCE(c.platform,'MT5'))::int AS persons
    FROM ib_agents ia
    JOIN clients c ON c.agent = ia.agent AND c.login <> c.agent
    GROUP BY ia.id
)
SELECT b.id AS ib_id, b.agent_id,
       COALESCE(f.ftd,0)       AS ftd,
       COALESCE(f.nda,0)       AS nda,
       COALESCE(cl.accounts,0) AS accounts,
       COALESCE(cl.persons,0)  AS persons
FROM ib_base b
LEFT JOIN ftd_ib f  ON f.id  = b.id
LEFT JOIN cl_ib  cl ON cl.id = b.id
"""


def get_status_thresholds(db):
    """IB status is based on how many of the IB's clients traded in the period.
    Thresholds are configurable (Settings). Defaults: low>=3, active>=10, elite>=25.
    Returns (low_min, active_min, elite_min)."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_status_config (
            id INT PRIMARY KEY DEFAULT 1,
            low_min INT DEFAULT 3,
            active_min INT DEFAULT 10,
            elite_min INT DEFAULT 25
        )
    """))
    db.execute(text("INSERT INTO ib_status_config (id, low_min, active_min) VALUES (1,3,10) ON CONFLICT (id) DO NOTHING"))
    # additive schema self-heal: add the Elite band to any pre-existing config row. Runs the
    # active-min policy bump EXACTLY ONCE (only when the column is first introduced) so the desk
    # can freely set active_min to anything afterwards without it being reverted.
    has_elite = db.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='ib_status_config' AND column_name='elite_min'
    """)).fetchone()
    if not has_elite:
        db.execute(text("ALTER TABLE ib_status_config ADD COLUMN elite_min INT DEFAULT 25"))
        # adopt the new desk policy (active >= 10) for the legacy row if it still holds the old
        # default of 5 (never customised). One-time — never fires again once the column exists.
        db.execute(text("UPDATE ib_status_config SET active_min=10 WHERE id=1 AND active_min=5"))
    db.commit()
    r = db.execute(text("SELECT low_min, active_min, elite_min FROM ib_status_config WHERE id=1")).fetchone()
    return (r[0] or 3), (r[1] or 10), (r[2] or 25)


def ib_status_for(trading_clients: int, low_min: int, active_min: int, elite_min: int = 25) -> str:
    if trading_clients >= elite_min:  return "elite"
    if trading_clients >= active_min: return "active"
    if trading_clients >= low_min:    return "low"
    if trading_clients >= 1:          return "inactive"
    return "super_inactive"


def can_change_ib_level(user) -> bool:
    """Only Zainab may change an IB's level (admin kept as a system failsafe)."""
    role  = (getattr(user, "role", "") or "").lower()
    name  = (getattr(user, "full_name", "") or "").lower()
    email = (getattr(user, "email", "") or "").lower()
    return role == "admin" or "zainab" in name or email.startswith("zainabw")


def period_dates(period: str, date_from: str = "", date_to: str = ""):
    """Return (from_ts, to_ts) INCLUSIVE Iraqi calendar dates for the period string.
    'today' is Iraq's today (UTC+3), not the UTC box clock — see crm_tz. Callers must
    convert these to UTC query bounds with crm_tz.day_lo/day_hi (NOT plain next-day)."""
    from crm_tz import today_local
    today = today_local()

    td = __import__('datetime').timedelta
    if period == "today":
        start = today; end = today
    elif period == "yesterday":
        start = today - td(days=1); end = start
    elif period == "last_7_days":
        start = today - td(days=6); end = today
    elif period == "last_30_days":
        start = today - td(days=29); end = today
    elif period == "all_time":
        start = date(2000, 1, 1); end = today
    elif period == "this_week":
        start = today - __import__('datetime').timedelta(days=today.weekday())
        end = today
    elif period == "last_week":
        start = today - __import__('datetime').timedelta(days=today.weekday() + 7)
        end = start + __import__('datetime').timedelta(days=6)
    elif period == "this_month":
        start = today.replace(day=1)
        end = today
    elif period == "last_month":
        first_this = today.replace(day=1)
        end = first_this - __import__('datetime').timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "last_year":
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)
    elif period == "custom" and date_from and date_to:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    else:
        start = today.replace(day=1)
        end = today

    return start.isoformat(), end.isoformat()


@router.get("")
async def get_ibs(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort:      str = Query("clients"),
    direction: str = Query(""),   # asc|desc from the column ▲▼ arrows (blank = per-column default)
    search:    str = Query(""),
    period:    str = Query("this_month"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    country:   str = Query(""),
    city:      str = Query(""),
    ib_level:  int = Query(0),
    sales_agent_id: int = Query(0),
    plugit:    str = Query(""),   # ''|synced|no_plugit_update -> Plugit sync filter
    own:       int = Query(0),    # 1 = team leader's "My own data" toggle (self only, not team)
    scope:     str = Query(""),   # 'all' = the 3-state toggle's "All data" state (all-access only)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    p_from, p_to = period_dates(period, date_from, date_to)

    # Role-based visibility scope (drives the SQL filter below AND the cache key so one
    # user's scoped IB list is never served to another). scope_agent_ids -> None = full
    # access (all roles); else a per-user subtree that is deterministic for that user id.
    # section='ibs' honors a leader restricted from IBs; own=1 = the "My own data" toggle.
    #
    # scope='all' ("All data") NEVER widens beyond the user's real access: it resolves to the
    # user's un-narrowed scope (own=False), so a scoped team-leader gets the SAME team subtree
    # they'd see by default, and only a genuine all-access user (scope -> None) sees everything.
    if scope == "all":
        _scope = rbac.scope_agent_ids(db, current_user, section="ibs", own=False)
        _all_access = _scope is None
    elif own:
        _scope = rbac.scope_agent_ids(db, current_user, section="ibs", own=True)
        _all_access = rbac.scope_agent_ids(db, current_user, section="ibs", own=False) is None
    else:
        _scope = rbac.scope_agent_ids(db, current_user, section="ibs", own=False)
        _all_access = _scope is None
    scope_key = "all" if _scope is None else f"u{getattr(current_user, 'id', 0)}{'o' if own else ''}"

    cache_key = (f"ibs:list:{scope_key}:{period}:{date_from}:{date_to}:{country}:{city}:"
                 f"{ib_level}:{sales_agent_id}:{plugit}:{sort}:{direction}:{search}:{page}:{page_size}")
    result = cached(cache_key, 90, lambda: _build_ibs(
        db, _scope, p_from, p_to, page, page_size, sort, search,
        country, city, ib_level, sales_agent_id, plugit, direction))
    # all_access (per-user, not cached with the list) tells the frontend whether to offer the
    # toggle's "All data" state — the button never grants access the backend wouldn't.
    return {**result, "all_access": _all_access}


def _build_ibs(db, _scope, p_from, p_to, page, page_size, sort, search,
               country, city, ib_level, sales_agent_id, plugit="", direction=""):
    # Show ONE row per PERSON: an IB has an MT4 + an MT5 record sharing ext_ib_id; only the
    # primary (commission-bearing) row is listed, and its clients/volume/accounts are combined
    # across both below. Standalone IBs (no ext_ib_id) are primary too.
    where = "WHERE ib.is_primary IS NOT FALSE"
    params: dict = {"p_from": p_from, "p_to": p_to}
    if search:
        where += " AND (ib.name ILIKE :s OR ib.phone ILIKE :s OR ib.ib_code ILIKE :s OR ib.email ILIKE :s)"
        params["s"] = f"%{search}%"
    if country:
        where += " AND ib.country ILIKE :country"; params["country"] = f"%{country}%"
    if city:
        where += " AND ib.city ILIKE :city"; params["city"] = f"%{city}%"
    if ib_level:
        where += " AND ib.ib_level = :iblevel"; params["iblevel"] = ib_level
    if plugit in ("no_plugit_update", "synced", "null_level", "null", "plugit_only"):
        where += " AND COALESCE(ib.plugit_status,'') = :plugit"; params["plugit"] = plugit
    if sales_agent_id:
        # IBs whose OWN account (clients.login = ib.agent_id) is assigned to this agent
        where += (" AND ib.agent_id IN (SELECT login FROM clients "
                  "WHERE assigned_agent_id = :sa_id)")
        params["sa_id"] = sales_agent_id
    # Role-based visibility: an IB is "yours" if the IB's OWN account (clients.login =
    # ib.agent_id) is assigned to you/your team — same rule as the sales_agent_id filter.
    # (The old rule — "any of the IB's clients is assigned to you" — matched nearly every IB
    # for a sales agent with thousands of auto-assigned clients, so sales saw ALL IBs.)
    if _scope is not None:
        if _scope:
            where += (" AND ib.agent_id IN (SELECT login FROM clients "
                      "WHERE assigned_agent_id = ANY(:rbac_agent_ids))")
            params["rbac_agent_ids"] = _scope
        else:
            where += " AND FALSE"

    # ── sort column + direction ────────────────────────────────────────────────
    # `direction` (asc|desc) comes from the column ▲▼ arrows; when blank each column
    # keeps its sensible default (numbers big-first, names A→Z).
    _d = str(direction).lower()
    _dir = "ASC" if _d == "asc" else ("DESC" if _d == "desc" else "")
    def _o(expr, default_dir):
        return f"{expr} {_dir or default_dir} NULLS LAST"

    # FTD / NDA are period-scoped per-IB counts (not columns on `ibs`), so sorting the
    # WHOLE list by them needs a join computed across ALL IBs before pagination. Only
    # built when actually sorting by ftd/nda (the clients-table scan is cheap but skipped
    # otherwise). Uses the same DISTINCT-ON-customer computation as /ibs/status-breakdown
    # so the sort order matches the values the UI overlays.
    ftd_join = ""
    if sort in ("ftd", "nda"):
        from crm_tz import day_lo, day_hi
        params["fn_from"] = day_lo(p_from)
        params["fn_to_next"] = day_hi(p_to)
        # same IB_STATS_SQL the list cells + the IB profile use, so sorting by FTD/NDA orders by
        # exactly the numbers shown in the column (~0.4s for all IBs, behind the 90s list cache)
        ftd_join = f"\n        LEFT JOIN ({IB_STATS_SQL}) fn ON fn.ib_id = ib.id"

    sort_col = _o("total_clients", "DESC")
    if sort == "volume":       sort_col = _o("total_volume", "DESC")
    elif sort == "commission": sort_col = _o("total_commission", "DESC")
    elif sort == "unpaid":     sort_col = _o("unpaid_commission", "DESC")
    elif sort == "payoff":     sort_col = _o("COALESCE(total_payoff,0)", "DESC")
    elif sort == "net":        sort_col = _o("(COALESCE(total_commission,0)-COALESCE(total_payoff,0))", "DESC")
    elif sort == "name":       sort_col = _o("ib.name", "ASC")
    elif sort == "new":        sort_col = _o("ib.created_at", "DESC")
    elif sort == "deposit":    sort_col = _o("total_deposits", "DESC")
    elif sort == "ib_since":   sort_col = _o("ib.ib_creation_date", "DESC")
    elif sort == "ftd":        sort_col = _o("COALESCE(fn.ftd,0)", "DESC")
    elif sort == "nda":        sort_col = _o("COALESCE(fn.nda,0)", "DESC")

    low_min, active_min, elite_min = get_status_thresholds(db)
    params["p_from"], params["p_to"] = p_from, p_to

    total = db.execute(text(f"SELECT COUNT(*) FROM ibs ib {where}"), params).scalar() or 0

    # IB list rows come straight from the small `ibs` table (fast, ~1k rows). The
    # trading-clients status count is computed separately (below) ONLY for the agents
    # on THIS page — NOT via a global join over all ~4M deals, which would time out on
    # a cold cache for period=all_time and blank the whole list (the 504 -> empty bug).
    rows = db.execute(text(f"""
        SELECT
            ib.id, ib.agent_id, ib.ib_code, ib.name, ib.email, ib.phone,
            ib.country, ib.city, ib.ib_level,
            CASE WHEN ib.ext_ib_id IS NULL THEN ib.total_clients
                 ELSE (SELECT COALESCE(SUM(s.total_clients),0)::int FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id) END AS total_clients,
            ib.active_clients,
            CASE WHEN ib.ext_ib_id IS NULL THEN ib.total_volume
                 ELSE (SELECT COALESCE(SUM(s.total_volume),0) FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id) END AS total_volume,
            ib.total_commission, ib.unpaid_commission, ib.paid_commission,
            ib.balance, ib.group_name,
            (SELECT COUNT(*) FROM ibs sub WHERE sub.parent_ib_id = ib.id) AS sub_ib_count,
            ib.plugit_status, ib.markup_pips, ib.ext_ib_id, ib.ib_creation_date, ib.is_sub_ib,
            COALESCE(ib.total_payoff,0) AS total_payoff,
            CASE WHEN ib.ext_ib_id IS NULL THEN
                    (CASE WHEN starts_with(COALESCE(ib.group_name,''),'TNFX') THEN 'MT4' ELSE 'MT5' END) || ' #' || ib.agent_id
                 ELSE (SELECT string_agg(DISTINCT
                        (CASE WHEN starts_with(COALESCE(s.group_name,''),'TNFX') THEN 'MT4' ELSE 'MT5' END) || ' #' || s.agent_id, '  ·  ')
                        FROM ibs s WHERE s.ext_ib_id = ib.ext_ib_id AND s.agent_id IS NOT NULL) END AS accounts_str
        FROM ibs ib{ftd_join}
        {where}
        ORDER BY {sort_col}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    # Cheap KPIs (no deals scan) — SCOPED with the same where as the list, so a sales agent's
    # cards show only THEIR IBs' numbers (was global: every role saw whole-company totals).
    kpis = db.execute(text(f"""
        SELECT
            COUNT(*) AS total_ibs,
            COALESCE(SUM(ib.total_clients),0) AS total_clients,
            COALESCE(SUM(ib.total_volume),0) AS total_volume,
            COALESCE(SUM(ib.total_commission),0) AS total_commission,
            COALESCE(SUM(ib.unpaid_commission),0) AS total_unpaid,
            COALESCE(SUM(ib.total_payoff),0) AS total_payoff
        FROM ibs ib {where}
    """), params).fetchone()

    # NOTE: per-IB trading_clients (drives the status pill) AND the active/low/inactive
    # tier BREAKDOWN both need a heavy scan over ~4M deals. On this box the deals buffer
    # cache churns under constant bridge writes, so even the top-page agents (the biggest
    # IBs, sorted first) cost ~10s for all_time. So NEITHER is computed here — both are
    # served LAZILY by GET /ibs/status-breakdown (which takes the page's agents) so the
    # list renders instantly and trading_clients/status/tiles fill in a moment later.

    # sales agent assigned to each IB's OWN account (clients.login = ib.agent_id)
    _ib_logins = [r[1] for r in rows if r[1]]
    ib_sales_agent = {}
    if _ib_logins:
        ib_sales_agent = {x[0]: (x[1], x[2]) for x in db.execute(text("""
            SELECT c.login, u.full_name, u.id
            FROM clients c JOIN users u ON u.id = c.assigned_agent_id
            WHERE c.login = ANY(:ids)
        """), {"ids": _ib_logins}).fetchall()}

    return {
        "ibs": [{
            "id":                r[0],
            "agent_id":          r[1],
            "sales_agent":       (ib_sales_agent.get(r[1]) or ("", None))[0],
            "sales_agent_id":    (ib_sales_agent.get(r[1]) or ("", None))[1],
            "ib_code":           r[2] or "",
            "name":              r[3] or "",
            "email":             r[4] or "",
            # RULE: IBs are clients too — always treated as verified (email + phone + KYC).
            "email_verified":    True,
            "phone_verified":    True,
            "kyc":               "verified",
            "phone":             r[5] or "",
            "country":           r[6] or "",
            "city":              r[7] or "",
            "ib_level":          r[8] or 5,
            "tier":              TIER_NAMES.get(r[8] or 5, "Bronze"),
            "total_clients":     r[9] or 0,
            "active_clients":    r[10] or 0,
            "total_volume":      float(r[11] or 0),
            "total_commission":  float(r[12] or 0),
            "unpaid_commission": float(r[13] or 0),
            "paid_commission":   float(r[14] or 0),
            "balance":           float(r[15] or 0),
            "group_name":        r[16] or "",
            "sub_ib_count":      r[17] or 0,
            "plugit_status":     (len(r) > 18 and r[18]) or "",
            "markup_pips":       (len(r) > 19 and r[19]) or None,
            "ext_ib_id":         (len(r) > 20 and r[20]) or None,
            "ib_creation_date":  (r[21].isoformat() if len(r) > 21 and r[21] else None),
            "is_sub_ib":         bool(len(r) > 22 and r[22]),
            "total_payoff":      float((len(r) > 23 and r[23]) or 0),
            "net_commission":    float((r[12] or 0)) - float((len(r) > 23 and r[23]) or 0),
            "accounts_str":      (len(r) > 24 and r[24]) or "",
            "trading_clients":   None,   # loaded lazily via /ibs/status-breakdown
            "status":            None,   # ditto (null -> frontend shows a "…" pill)
        } for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "kpis": {
            "total_ibs":          kpis[0] or 0,
            "total_clients":      kpis[1] or 0,
            "total_volume":       float(kpis[2] or 0),
            "total_commission":   float(kpis[3] or 0),
            "total_unpaid":       float(kpis[4] or 0),
            "total_payoff":       float(kpis[5] or 0),
            # tier counts are loaded lazily via /ibs/status-breakdown (null = "loading")
            "elite_ibs":          None,
            "active_ibs":         None,
            "low_ibs":            None,
            "inactive_ibs":       None,
            "super_inactive_ibs": None,
        },
        "thresholds": {"low_min": low_min, "active_min": active_min, "elite_min": elite_min},
        "period": {"from": p_from, "to": p_to},
    }


@router.get("/status-breakdown")
async def get_ib_status_breakdown(
    period:    str = Query("all_time"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    agents:    str = Query(""),   # CSV of the current page's IB agent_ids -> per-row trading
    own:       int = Query(0),    # mirror GET /ibs so the tier tiles reflect the same scope
    scope:     str = Query(""),   # 'all' = "All data" state (all-access only; never widens)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Per-IB trading_clients (for the passed `agents`) + elite/active/low/inactive tier counts
    for the period. Split out of GET /ibs so the IB list renders instantly — both need a
    heavy scan over ~4M deals (~10s cold for all_time on this box, whose deals cache churns
    under constant bridge writes) and are loaded lazily by the frontend. Guarded by a
    statement timeout so it degrades to nulls instead of hanging the request."""
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    # Iraqi-day UTC bounds (crm_tz); date-only cols (deal_date) keep D->D under these too
    p_from, p_to, p_to_next = day_lo(p_from), day_hi(p_to), day_hi(p_to)
    low_min, active_min, elite_min = get_status_thresholds(db)
    # SAME visibility scope as GET /ibs so the tier tiles match the (scoped) list + main KPIs
    # (fixes the "own data" bug where tiles stayed global while the list was scoped). 'all'
    # resolves to the un-narrowed scope and never widens beyond the user's real access.
    if scope == "all" or not own:
        _scope = rbac.scope_agent_ids(db, current_user, section="ibs", own=False)
    else:
        _scope = rbac.scope_agent_ids(db, current_user, section="ibs", own=True)
    scope_key = "all" if _scope is None else f"u{getattr(current_user, 'id', 0)}{'o' if (own and scope != 'all') else ''}"
    # PERF: heavy deals scan behind a 120s cache keyed by the full param set — the IB Admin
    # list reloads this on every visit (default all_time was rescanning every time)
    from perf_cache import cached as _pc
    _key = f"ibs:breakdown:{scope_key}:{period}:{date_from}:{date_to}:{agents}"
    return _pc(_key, 120, lambda: _compute_status_breakdown(
        db, p_from, p_to, p_to_next, low_min, active_min, elite_min, agents, _scope))


def _compute_status_breakdown(db, p_from, p_to, p_to_next, low_min, active_min, elite_min, agents, scope_ids=None):
    out = {"elite_ibs": None, "active_ibs": None, "low_ibs": None, "inactive_ibs": None,
           "super_inactive_ibs": None, "low_min": low_min, "active_min": active_min,
           "elite_min": elite_min, "trading": {}, "ftd": {}, "nda": {},
           "accounts": {}, "persons": {}}

    # per-page trading_clients (drives each row's status pill) for just the listed agents
    agent_ids = [int(a) for a in agents.split(",") if a.strip().lstrip("-").isdigit()]

    # per-IB FTD + NDA for the period (cheap — clients table only). FTD = unique CUSTOMERS whose
    # first deposit fell in the period under this IB; NDA = the genuinely-new subset (is_nda). IB
    # promotions are driven by NDA, not raw FTD (family/friend accounts don't count).
    if agent_ids:
        try:
            # IB_STATS_SQL = the SAME desk-rule computation the IB profile (get_ib) uses, so the
            # list cells and the profile always agree. It covers every IB in one ~0.4s pass; we
            # just keep the ones on this page (this whole endpoint is cached 120s). `accounts`
            # (live referred trading accounts) replaces the stale stored ibs.active_clients that
            # the Accounts column used to show.
            wanted = set(agent_ids)
            for _ib_id, a, ftd, nda, accounts, persons in db.execute(
                    text(IB_STATS_SQL), {"fn_from": p_from, "fn_to_next": p_to_next}).fetchall():
                if a in wanted:
                    out["ftd"][str(a)] = ftd
                    out["nda"][str(a)] = nda
                    out["accounts"][str(a)] = accounts
                    out["persons"][str(a)] = persons
        except Exception:
            db.rollback()

    if agent_ids:
        try:
            db.execute(text("SET statement_timeout = 25000"))
            for a, tc in db.execute(text("""
                SELECT c.agent, COUNT(DISTINCT d.login) AS tc
                FROM deals d JOIN clients c ON c.login = d.login
                WHERE c.agent = ANY(:agents) AND d.action IN (0,1) AND d.volume > 0
                  AND d.deal_date BETWEEN :p_from AND :p_to
                GROUP BY c.agent
            """), {"agents": agent_ids, "p_from": p_from, "p_to": p_to}).fetchall():
                out["trading"][str(a)] = tc
        except Exception:
            db.rollback()
        finally:
            db.execute(text("SET statement_timeout = 0"))

    # tier tiles scoped exactly like the list: None = all IBs, [] = none, [ids] = this book
    tier_where = ""
    tier_params = {"p_from": p_from, "p_to": p_to, "low_min": low_min,
                   "active_min": active_min, "elite_min": elite_min}
    if scope_ids is not None:
        if scope_ids:
            tier_where = ("WHERE ib.agent_id IN (SELECT login FROM clients "
                          "WHERE assigned_agent_id = ANY(:scope_ids))")
            tier_params["scope_ids"] = scope_ids
        else:
            tier_where = "WHERE FALSE"
    try:
        db.execute(text("SET statement_timeout = 25000"))
        sb = db.execute(text(f"""
            WITH trading AS (
                SELECT c.agent AS agent, COUNT(DISTINCT d.login) AS tc
                FROM deals d JOIN clients c ON c.login = d.login
                WHERE COALESCE(c.agent,0) <> 0 AND d.action IN (0,1) AND d.volume > 0
                  AND d.deal_date BETWEEN :p_from AND :p_to
                GROUP BY c.agent
            )
            SELECT
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= :elite_min) AS elite_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= :active_min AND COALESCE(t.tc,0) < :elite_min) AS active_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= :low_min AND COALESCE(t.tc,0) < :active_min) AS low_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) >= 1 AND COALESCE(t.tc,0) < :low_min) AS inactive_ibs,
                COUNT(*) FILTER (WHERE COALESCE(t.tc,0) = 0) AS super_inactive_ibs
            FROM ibs ib LEFT JOIN trading t ON t.agent = ib.agent_id
            {tier_where}
        """), tier_params).fetchone()
        out.update(elite_ibs=sb[0] or 0, active_ibs=sb[1] or 0, low_ibs=sb[2] or 0,
                   inactive_ibs=sb[3] or 0, super_inactive_ibs=sb[4] or 0)
    except Exception:
        db.rollback()  # statement-timeout/error -> leave tiers null (frontend shows "—")
    finally:
        db.execute(text("SET statement_timeout = 0"))
    return out


@router.get("/search")
async def search_ibs(
    q: str = Query(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Typeahead for the trades IB filter — match by IB name / email / code / login."""
    q = (q or "").strip()
    if len(q) < 1:
        return {"ibs": []}
    rows = db.execute(text("""
        SELECT id, ib_code, name, email, agent_id
        FROM ibs
        WHERE name ILIKE :q OR email ILIKE :q OR ib_code ILIKE :q OR CAST(agent_id AS TEXT) ILIKE :q
        ORDER BY total_clients DESC NULLS LAST
        LIMIT 20
    """), {"q": f"%{q}%"}).fetchall()
    return {"ibs": [{"id": r[0], "ib_code": r[1] or "", "name": r[2] or "",
                     "email": r[3] or "", "agent_id": r[4]} for r in rows]}


@router.get("/clients/search")
async def search_ib_clients(
    q: str = Query(""),
    ib_id: int = Query(0),   # 0 = search across all IBs' clients
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Typeahead for the trades client filter — match by client name / email / phone /
    login (account number). Optionally scoped to one IB's clients."""
    q = (q or "").strip()
    if len(q) < 1:
        return {"clients": []}
    where = "(c.name ILIKE :q OR c.email ILIKE :q OR c.phone ILIKE :q OR CAST(c.login AS TEXT) ILIKE :q)"
    params = {"q": f"%{q}%"}
    if ib_id:
        where = "c.agent = (SELECT agent_id FROM ibs WHERE id = :ib) AND " + where
        params["ib"] = ib_id
    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.email, c.phone
        FROM clients c
        WHERE {where}
        ORDER BY c.balance DESC NULLS LAST
        LIMIT 20
    """), params).fetchall()
    return {"clients": [{"login": r[0], "name": r[1] or "", "email": r[2] or "",
                         "phone": r[3] or ""} for r in rows]}


@router.get("/plugit-only")
async def plugit_only(
    search: str = Query(""), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user),
):
    """IBs that exist in the Plugit export but NOT in the CRM (new-tab list)."""
    if not db.execute(text("SELECT to_regclass('public.ib_plugit')")).scalar():
        return {"rows": [], "total": 0}
    w = "WHERE in_crm = FALSE"
    p: dict = {}
    if search:
        w += " AND (name ILIKE :s OR email ILIKE :s OR code ILIKE :s)"; p["s"] = f"%{search}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM ib_plugit {w}"), p).scalar() or 0
    rows = db.execute(text(f"""
        SELECT code, email, name, pips, level FROM ib_plugit {w}
        ORDER BY level DESC NULLS LAST, name LIMIT :lim OFFSET :off
    """), {**p, "lim": page_size, "off": (page-1)*page_size}).fetchall()
    return {"total": total, "page": page, "page_size": page_size,
            "rows": [{"code": r[0], "email": r[1] or "", "name": r[2] or "",
                      "pips": r[3], "level": r[4], "tier": TIER_NAMES.get(r[4] or 0, "")} for r in rows]}


@router.get("/operations")
async def all_ib_operations(
    request_type: str = Query(""),   # ''|Wallet Withdrawal|External Wallet Transfer|Internal Wallet Transfer
    status: str = Query(""),         # ''|Approved|Declined|Pending
    search: str = Query(""),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user),
):
    """All IB payouts (the Withdrawals page): withdrawals + internal/external transfers.
    Every row here originates from an IB, so the frontend colours them as IB withdrawals."""
    if not db.execute(text("SELECT to_regclass('public.ib_operations')")).scalar():
        return {"rows": [], "total": 0, "totals": {}}
    w = "WHERE 1=1"; p: dict = {}
    if request_type: w += " AND o.request_type = :rt"; p["rt"] = request_type
    if status:       w += " AND o.status = :st"; p["st"] = status
    if search:       w += " AND (o.name ILIKE :s OR o.email ILIKE :s OR o.account ILIKE :s)"; p["s"] = f"%{search}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM ib_operations o {w}"), p).scalar() or 0
    tot = db.execute(text(f"""SELECT
        COALESCE(SUM(amount) FILTER (WHERE status='Approved'),0),
        COUNT(*) FILTER (WHERE request_type='Internal Wallet Transfer' AND status='Pending'),
        COUNT(*) FILTER (WHERE status='Pending')
        FROM ib_operations o {w}"""), p).fetchone()
    rows = db.execute(text(f"""
        SELECT o.id, o.ib_id, o.ext_ib_id, o.name, o.email, o.account, o.request_type, o.amount,
               o.payment_type, o.status, o.to_account, o.op_date, o.action_date, o.note
        FROM ib_operations o {w}
        ORDER BY o.op_date DESC NULLS LAST LIMIT :lim OFFSET :off
    """), {**p, "lim": page_size, "off": (page-1)*page_size}).fetchall()
    return {
        "total": total, "page": page, "page_size": page_size,
        "totals": {"approved_amount": float(tot[0] or 0), "pending_transfers": tot[1] or 0, "pending": tot[2] or 0},
        "rows": [{
            "id": r[0], "ib_id": r[1], "ext_ib_id": r[2], "name": r[3] or "", "email": r[4] or "",
            "account": r[5] or "", "request_type": r[6] or "", "amount": float(r[7] or 0),
            "payment_type": r[8] or "", "status": r[9] or "", "to_account": r[10] or "",
            "op_date": r[11].isoformat() if r[11] else None,
            "action_date": r[12].isoformat() if r[12] else None, "note": r[13] or "",
            "is_ib": True,
        } for r in rows],
    }


@router.post("/operations/{op_id}/action")
async def act_on_ib_operation(op_id: int, data: dict, db: Session = Depends(get_db),
                              current_user: models.User = Depends(get_current_user)):
    """Desk approves/declines an IB payout request (from the Withdrawals page). STAFF ONLY.
    Approve => the amount counts as total_payoff (leaves the commission wallet); the
    enforce_ib_commission trigger then re-derives unpaid_commission. Decline => no money moves."""
    action = (data.get("action") or "").lower()
    if action not in ("approve", "decline"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'decline'")
    row = db.execute(text("""SELECT id, ib_id, ext_ib_id, status, amount, request_type
        FROM ib_operations WHERE id = :id"""), {"id": op_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if (row[3] or "") != "Pending":
        raise HTTPException(status_code=409, detail=f"Already {row[3] or 'processed'} — nothing to do")
    ib_id, ext_ib_id = row[1], row[2]
    new_status = "Approved" if action == "approve" else "Declined"
    db.execute(text("""UPDATE ib_operations SET status = :st, action_date = NOW(),
        note = TRIM(COALESCE(note,'') || :suffix) WHERE id = :id"""),
        {"st": new_status, "id": op_id,
         "suffix": f" · {new_status.lower()} by {current_user.email}" + (
             f": {data.get('reason')}" if action == "decline" and data.get("reason") else "")})
    # recompute total_payoff for THIS ib from its approved operations (matched by ib_id AND, if the
    # person has an ext group, ext_ib_id). Touching ibs re-fires enforce_ib_commission -> unpaid.
    if ib_id is not None:
        db.execute(text("""UPDATE ibs SET total_payoff = COALESCE((
            SELECT SUM(o.amount) FROM ib_operations o
            WHERE o.status='Approved'
              AND (o.ib_id = ibs.id OR (:ext IS NOT NULL AND o.ext_ib_id = :ext))), 0)
            WHERE id = :id OR (:ext IS NOT NULL AND ext_ib_id = :ext)"""),
            {"id": ib_id, "ext": ext_ib_id})
    db.commit()
    # notify the IB in their portal
    try:
        import ib_portal_extras
        amt = float(row[4] or 0)
        if action == "approve":
            ib_portal_extras.notify(db, ib_id, "payout", "Withdrawal approved 💸",
                                    f"Your ${amt:,.2f} withdrawal was approved and is being paid to your Ovadot wallet.")
        else:
            ib_portal_extras.notify(db, ib_id, "payout", "Withdrawal declined",
                                    f"Your ${amt:,.2f} withdrawal request was declined." + (
                                        f" Reason: {data.get('reason')}" if data.get("reason") else ""))
    except Exception:
        pass
    return {"ok": True, "id": op_id, "status": new_status, "amount": float(row[4] or 0)}


@router.get("/settings/status-thresholds")
async def get_ib_status_thresholds(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    low_min, active_min, elite_min = get_status_thresholds(db)
    return {"low_min": low_min, "active_min": active_min, "elite_min": elite_min}


@router.post("/settings/status-thresholds")
async def set_ib_status_thresholds(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _require_ib_mgmt(current_user)
    get_status_thresholds(db)
    low = max(1, int(data.get("low_min", 3)))
    act = max(low, int(data.get("active_min", 10)))
    elite = max(act, int(data.get("elite_min", 25)))
    db.execute(text("UPDATE ib_status_config SET low_min=:l, active_min=:a, elite_min=:e WHERE id=1"),
               {"l": low, "a": act, "e": elite})
    db.commit()
    return {"ok": True, "low_min": low, "active_min": act, "elite_min": elite}


def _record_level_change(db, ib, old_level, new_level, source="crm", note=""):
    """Log EVERY level change into ib_promotions. This date is the tier-criteria RESET point:
    promotion progress (NDA / lots / deposits) is counted from the LAST level change onward,
    so an IB who just reached Silver starts their Gold requirements from zero (desk rule Jul 2026)."""
    if old_level == new_level:
        return
    try:
        db.execute(text("""
            INSERT INTO ib_promotions (ib_id, ext_ib_id, promo_date, from_level, to_level,
                                       note, source, direction, created_at)
            VALUES (:ib, :ext, CURRENT_DATE, :f, :t, :n, :s, :d, NOW())
        """), {"ib": ib.id, "ext": getattr(ib, "ext_ib_id", None), "f": int(old_level), "t": int(new_level),
               "n": note, "s": source, "d": "promotion" if new_level > old_level else "demotion"})
    except Exception:
        db.rollback()   # missing table etc. must never block the level change itself


@router.post("/{ib_id}/action")
async def ib_action(ib_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Action taken after a call (like the client page) + management actions."""
    # Ticket 227 — the four ibs columns (last_outcome/last_contact_at/follow_up_at/target) already
    # exist. Running ALTER TABLE on EVERY action request was a hot-path DDL hazard: ADD COLUMN takes
    # an ACCESS EXCLUSIVE lock even when the column exists, and under any concurrent lock on `ibs` it
    # hits lock_timeout (5s) and 500s → the UI showed "Action failed". DDL removed from the handler
    # (see the hot-path-ddl-lock-storms rule: NEVER DDL in a request path).
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    act = data.get("action", "")

    if act in ("connected_done", "no_answer", "call_later", "not_interested"):
        follow = None
        if act == "no_answer":      follow = "NOW() + interval '2 hours'"
        elif act == "connected_done": follow = "NOW() + interval '14 days'"
        elif act == "call_later":
            days = int(data.get("days", 0)); hours = int(data.get("hours", 0))
            follow = f"NOW() + interval '{days} days' + interval '{hours} hours'"
        fexpr = follow or "NULL"
        db.execute(text(f"UPDATE ibs SET last_outcome=:o, last_contact_at=NOW(), follow_up_at={fexpr} WHERE id=:id"),
                   {"o": act, "id": ib_id})
        db.commit()
        return {"ok": True, "outcome": act}

    # only Zainab may change an IB's LEVEL (everyone can SEE promote/demote in the menu)
    if act in ("promote", "demote") and not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")

    if act == "promote":
        new = min(10, (ib.ib_level or 5) + 1)
        _record_level_change(db, ib, ib.ib_level or 5, new, source="crm_action")
        db.execute(text("UPDATE ibs SET ib_level=:l WHERE id=:id"), {"l": new, "id": ib_id})
        db.commit()
        return {"ok": True, "ib_level": new, "tier": TIER_NAMES.get(new, "Bronze")}
    if act == "demote":
        new = max(5, (ib.ib_level or 5) - 1)
        _record_level_change(db, ib, ib.ib_level or 5, new, source="crm_action")
        db.execute(text("UPDATE ibs SET ib_level=:l WHERE id=:id"), {"l": new, "id": ib_id})
        db.commit()
        return {"ok": True, "ib_level": new, "tier": TIER_NAMES.get(new, "Bronze")}
    if act == "set_target":
        db.execute(text("UPDATE ibs SET target=:t WHERE id=:id"), {"t": float(data.get("target", 0)), "id": ib_id})
        db.commit()
        return {"ok": True, "target": float(data.get("target", 0))}
    return {"ok": False, "error": "unknown action"}


@router.get("/{ib_id}")
async def get_ib(
    ib_id: int,
    period:    str = Query("this_month"),
    date_from: str = Query(""),
    date_to:   str = Query(""),
    country:   str = Query(""),
    city:      str = Query(""),
    db: Session = Depends(get_db),
    current_user = Depends(staff_or_own_ib)
):
    _assert_can_see_ib(db, current_user, ib_id)   # scope-gate the detail like the list
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")

    from crm_tz import day_lo, day_hi
    p_from_cal, p_to = period_dates(period, date_from, date_to)
    # Iraqi-day UTC bounds for VARCHAR/timestamp comparisons; the CAST(... AS date) sites
    # (op_date / daily-volume day / close_time-day) keep the plain CALENDAR dates — casting
    # a shifted '21:00' bound to date would move their window a whole day back.
    p_from    = day_lo(p_from_cal)
    p_to_next = day_hi(p_to)
    p_to_next_cal = (date.fromisoformat(p_to) + timedelta(days=1)).isoformat()
    level = ib.ib_level or 5
    agent = ib.agent_id
    # SELF-account identity: an IB's OWN trading accounts (same email / customer_no) show under him
    # tagged "self account". Sub-IBs are stand-alone (desk rule Jul 22) — his own & directly-linked
    # accounts belong to HIM, not his upline. Commission on SELF is already zeroed at L5-6 by
    # ib_self_related/ib_trades (t.eligible=false), so surfacing them here has no payout impact.
    _ib_email = (ib.email or "").lower().strip()
    _ib_cust  = db.execute(text("SELECT customer_no FROM clients WHERE login=:a LIMIT 1"), {"a": agent}).scalar() or ""
    # ALL the person's IB agent accounts: sibling ibs rows (ext_ib_id) + the MT4/MT5 IB-group
    # accounts linked by email/customer_no. Client-scoped queries use this set so an IB's MT4-agent
    # clients aren't missed (KPI said 50 clients / tab showed 39 — different scopes; fixed Jul 2026).
    agents_all = [r[0] for r in db.execute(text("""
        SELECT DISTINCT a FROM (
          SELECT agent_id AS a FROM ibs
          WHERE id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id = :ext)
          UNION
          SELECT c.login AS a FROM clients c
          WHERE c.group_name ~ '^(TNFX-IB-|IB.IB-)'
            AND ((COALESCE(:em,'') <> '' AND LOWER(c.email) = LOWER(:em))
                 OR (c.customer_no IS NOT NULL AND c.customer_no =
                        (SELECT customer_no FROM clients WHERE login = :agent LIMIT 1))
                 OR c.login = :agent)
        ) q WHERE a IS NOT NULL
    """), {"ibid": ib_id, "ext": getattr(ib, "ext_ib_id", None),
           "em": ib.email or "", "agent": agent}).fetchall()] or [agent]
    base = {"agents": agents_all, "p_from": p_from, "p_to": p_to, "p_to_next": p_to_next, "level": level}

    # period trading: volume (lots) + commission (lots * points), from real deals
    # NEW MODEL: commission = lots * comm_per_lot from the per-(level,symbol) rate table
    pk = db.execute(text("""
        SELECT COALESCE(SUM(d.volume/10000.0),0) AS lots,
               COALESCE(SUM((d.volume/10000.0) * r.comm_per_lot),0) AS commission,
               COUNT(DISTINCT d.login) AS active_traders
        FROM deals d
        JOIN clients c ON c.login = d.login
        JOIN commission_rates r ON r.ib_level = :level AND r.symbol = d.symbol
        WHERE c.agent = ANY(:agents) AND d.entry = 1 AND d.action IN (0,1) AND d.volume > 0
          AND d.deal_date >= :p_from AND d.deal_date < :p_to_next
    """), base).fetchone()

    # period money: deposits + withdrawals, from real transactions
    pm = db.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN t.tx_type='deposit' AND t.amount<1000000
                 AND COALESCE(t.notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust' THEN t.amount ELSE 0 END),0) AS dep,
               COALESCE(SUM(CASE WHEN t.tx_type='withdrawal' AND t.amount<1000000
                 AND COALESCE(t.status,'')<>'rejected' THEN t.amount ELSE 0 END),0) AS wd,
               COUNT(DISTINCT t.login) AS active_dep
        FROM transactions t JOIN clients c ON c.login = t.login
        WHERE c.agent = ANY(:agents)
          AND t.tx_date >= :p_from AND t.tx_date < :p_to_next
    """), base).fetchone()

    # period payoff: approved withdrawals/transfers by this IB (whole ext group) inside the period
    p_payoff = 0.0
    if db.execute(text("SELECT to_regclass('public.ib_operations')")).scalar():
        p_payoff = float(db.execute(text("""
            SELECT COALESCE(SUM(o.amount),0) FROM ib_operations o
            WHERE o.status='Approved'
              AND (o.ib_id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND o.ext_ib_id = :ext))
              AND o.op_date >= CAST(:p_from AS date) AND o.op_date < CAST(:p_to_next AS date)
        """), {"ibid": ib_id, "ext": getattr(ib, "ext_ib_id", None),
               "p_from": p_from_cal, "p_to_next": p_to_next_cal}).scalar() or 0)

    # PERIOD COMMISSION — authoritative: the Plugit per-day excel commission for the part of the
    # period up to EXCEL_CUTOFF, plus live ib_trades commission after it. The old deals-recompute
    # UNDERCOUNTS the excel era (an IB showed payoff > commission, impossible for a commission-only
    # wallet). Falls back to the deals recompute (pk) if the daily table isn't built.
    EXCEL_CUTOFF = "2026-07-17"   # keep in sync with ib_trades.EXCEL_CUTOFF
    p_commission = float(pk[1] or 0)
    _ext = getattr(ib, "ext_ib_id", None)
    if _ext is not None and db.execute(text("SELECT to_regclass('public.excel_commission_daily')")).scalar():
        exc = float(db.execute(text("""
            SELECT COALESCE(SUM(commission),0) FROM excel_commission_daily
            WHERE ext_ib_id = :ext AND day >= CAST(:p_from AS date)
              AND day < LEAST(CAST(:p_to_next AS date), CAST(:cut AS date) + 1)
        """), {"ext": _ext, "p_from": p_from_cal, "p_to_next": p_to_next_cal, "cut": EXCEL_CUTOFF}).scalar() or 0)
        live = float(db.execute(text("""
            SELECT COALESCE(SUM(t.commission),0) FROM ib_trades t
            JOIN ibs i ON i.id = t.ib_id
            WHERE (i.id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND i.ext_ib_id = :ext))
              AND t.eligible AND t.close_time > CAST(:cut AS date) + 1
              AND t.close_time >= CAST(:p_from AS date) AND t.close_time < CAST(:p_to_next AS date)
        """), {"ibid": ib_id, "ext": _ext, "p_from": p_from_cal, "p_to_next": p_to_next_cal,
               "cut": EXCEL_CUTOFF}).scalar() or 0)
        p_commission = exc + live
        # the UNDATED adjustment bucket (commission Plugit actually paid beyond what the reports
        # record + pre-2023 earnings; ibs.commission_computed) belongs to the whole account life —
        # include it when the window starts at/before the IB's first recorded commission day, so
        # full-history windows match the stored total and never show payoff > commission.
        first_day = db.execute(text(
            "SELECT MIN(day) FROM excel_commission_daily WHERE ext_ib_id = :ext"), {"ext": _ext}).scalar()
        if first_day and p_from_cal <= str(first_day):
            p_commission += float(getattr(ib, "commission_computed", 0) or 0)

    new_clients = db.execute(text("""
        SELECT COUNT(*) FROM clients c WHERE c.agent = ANY(:agents)
          AND c.reg_date >= :p_from AND c.reg_date < :p_to_next
    """), base).scalar() or 0
    leads_count    = db.execute(text("SELECT COUNT(*) FROM clients WHERE agent = ANY(:agents)"), base).scalar() or 0
    # RULE: every client is treated as verified, so verified count == client count.
    verified_leads = leads_count
    ftd_count      = db.execute(text("""SELECT COUNT(DISTINCT c.login) FROM clients c
        JOIN transactions t ON t.login=c.login AND t.tx_type='deposit' WHERE c.agent = ANY(:agents)"""), base).scalar() or 0
    # PERSONS (multi-account clients merged) — must match what the Clients tab shows
    person_count = db.execute(text("""
        SELECT COUNT(DISTINCT COALESCE(NULLIF(c.phone,''),'L'||c.login::text)||'|'||COALESCE(c.platform,'MT5'))
        FROM clients c WHERE c.agent = ANY(:agents) AND c.login <> c.agent
    """), base).scalar() or 0
    # FTD DEFINITION (desk rule Jul 13 2026): a customer is this IB's FTD only if their FIRST-EVER
    # deposited trading account (across ALL their accounts, any IB) sits under THIS IB. A customer
    # who first deposited elsewhere and later opened an account here is an ADDITIONAL account, not
    # an FTD. NDA = FTD here AND genuinely new (is_nda). The fa CTE picks each customer's globally
    # first deposited account and checks whose agent it belongs to.
    # ⚠ KEEP IN SYNC WITH `FTD_NDA_SQL` (top of this file) — the IB Admin list cells and the
    # FTD/NDA sort use that one. They are verified to return identical numbers; if you change the
    # rule here, change it there too or the list and the profile will disagree again.
    nda_row = db.execute(text("""
        WITH ib_cust AS (
            SELECT DISTINCT c.customer_no FROM clients c
            WHERE c.agent = ANY(:agents) AND c.customer_no IS NOT NULL
        ),
        fa AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.agent,
                   NULLIF(c.first_deposit_at,'') AS fd, c.is_nda
            FROM clients c JOIN ib_cust ic ON ic.customer_no = c.customer_no
            WHERE NULLIF(c.first_deposit_at,'') IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC
        )
        SELECT COUNT(*) FILTER (WHERE fa.agent = ANY(:agents) AND fa.fd >= :p_from AND fa.fd < :p_to_next)                AS ftd,
               COUNT(*) FILTER (WHERE fa.agent = ANY(:agents) AND fa.fd >= :p_from AND fa.fd < :p_to_next AND fa.is_nda)  AS nda,
               COUNT(*) FILTER (WHERE fa.agent = ANY(:agents) AND fa.is_nda)                                              AS nda_all,
               COUNT(*) FILTER (WHERE fa.agent = ANY(:agents))                                                            AS ftd_all
        FROM fa
    """), base).fetchone()
    ftd_period, nda_period, nda_all, ftd_all = (nda_row[0] or 0), (nda_row[1] or 0), (nda_row[2] or 0), (nda_row[3] or 0)
    sub_ibs = db.query(models.IB).filter(models.IB.parent_ib_id == ib_id).all()

    # ── TIER PROGRESS (promotion criteria) — RESETS at the last level change (desk rule Jul 2026).
    # Baseline = the IB's most recent ib_promotions row (promotion OR demotion, Plugit history +
    # CRM level changes via _record_level_change). An IB who just reached Silver starts the Gold
    # requirements from ZERO on that date. Never-changed IBs count their whole history (first promo).
    tp_since = None
    if db.execute(text("SELECT to_regclass('public.ib_promotions')")).scalar():
        tp_since = db.execute(text("""
            SELECT MAX(promo_date) FROM ib_promotions
            WHERE ib_id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id = :ext)
        """), {"ibid": ib_id, "ext": getattr(ib, "ext_ib_id", None)}).scalar()
    tp_from = tp_since.isoformat() if tp_since else "1970-01-01"
    # same FTD definition as above: only customers whose GLOBAL first deposited account is under
    # this IB count toward promotion — additional accounts of existing customers never do.
    tp_row = db.execute(text("""
        WITH ib_cust AS (
            SELECT DISTINCT c.customer_no FROM clients c
            WHERE c.agent = ANY(:agents) AND c.customer_no IS NOT NULL
        ),
        fa AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.agent,
                   NULLIF(c.first_deposit_at,'') AS fd, c.is_nda
            FROM clients c JOIN ib_cust ic ON ic.customer_no = c.customer_no
            WHERE NULLIF(c.first_deposit_at,'') IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC
        )
        SELECT COUNT(*) FILTER (WHERE fa.agent = ANY(:agents) AND fa.fd >= :f)               AS ftd,
               COUNT(*) FILTER (WHERE fa.agent = ANY(:agents) AND fa.fd >= :f AND fa.is_nda) AS nda
        FROM fa
    """), {"agents": agents_all, "f": tp_from}).fetchone()
    tp_ftd, tp_nda = (tp_row[0] or 0), (tp_row[1] or 0)
    tp_vol = 0.0
    if db.execute(text("SELECT to_regclass('public.ib_trades')")).scalar():
        tp_vol = float(db.execute(text("""
            SELECT COALESCE(SUM(t.lots),0) FROM ib_trades t JOIN ibs i ON i.id = t.ib_id
            WHERE (i.id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND i.ext_ib_id = :ext))
              AND t.close_time >= CAST(:f AS date)
        """), {"ibid": ib_id, "ext": getattr(ib, "ext_ib_id", None), "f": tp_from}).scalar() or 0)
    tp_dep = float(db.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN t.tx_type='deposit' THEN t.amount ELSE 0 END),0)
        FROM transactions t JOIN clients c ON c.login = t.login
        WHERE c.agent = ANY(:agents) AND t.tx_date >= :f
    """), {"agents": agents_all, "f": tp_from}).scalar() or 0)
    # promotion sheet criteria (Jul 13 2026): deposits / monthly-AVERAGE lots / funded accounts,
    # all counted since the last level change. Accounts = trading accounts whose FIRST deposit
    # landed after the baseline.
    tp_acct = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT t.login, MIN(t.tx_date) AS fd
            FROM transactions t JOIN clients c ON c.login = t.login
            WHERE c.agent = ANY(:agents) AND t.tx_type = 'deposit'
            GROUP BY t.login
        ) x WHERE x.fd >= :f
    """), {"agents": agents_all, "f": tp_from}).scalar() or 0
    _t0 = tp_since
    if not _t0 and getattr(ib, "ib_creation_date", None):
        _t0 = ib.ib_creation_date.date() if hasattr(ib.ib_creation_date, "date") else ib.ib_creation_date
    tp_months = max(1.0, ((date.today() - _t0).days / 30.44)) if _t0 else 12.0
    try:
        from ib_portal_auth import get_tier_reqs
        tier_next_req = next((q for q in get_tier_reqs(db) if q["level"] == level + 1), None)
    except Exception:
        tier_next_req = None

    # clients list with REAL deposits/withdrawals (transactions), country/city filter, campaign
    # exclude the IB's OWN account from its own client list (login = agent) — an IB is not its own client
    # Client list = agent-referred clients PLUS the IB's OWN trading accounts (self, by email/customer_no,
    # excluding his IB-group profile accounts). KPIs above stay agent-only so self doesn't inflate counts.
    cwhere = ("(c.agent = ANY(:agents) OR ("
              "  ((:ib_email <> '' AND LOWER(COALESCE(c.email,'')) = :ib_email)"
              "   OR (:ib_cust <> '' AND c.customer_no = :ib_cust))"
              "  AND c.group_name !~ '^(TNFX-IB-|IB.IB-)'"
              ")) AND c.login <> c.agent")
    cparams = {"agents": agents_all, "level": level, "ib_email": _ib_email, "ib_cust": _ib_cust}
    if country:
        cwhere += " AND c.country ILIKE :country"; cparams["country"] = f"%{country}%"
    if city:
        cwhere += " AND c.city ILIKE :city"; cparams["city"] = f"%{city}%"
    # ONE ROW PER PERSON: a client with several same-platform accounts (phone siblings) showed as
    # multiple rows sharing one primary account # (e.g. two MT5 logins -> "duplicate" lines). Group
    # by phone+platform (like the Clients list): keep the top-deposit login's identity, SUM money/
    # volume/commission across the person's accounts, and expose how many accounts merged.
    client_rows = db.execute(text(f"""
        SELECT * FROM (
        SELECT x.*,
               ROW_NUMBER() OVER (PARTITION BY x.person_key ORDER BY x.dep DESC, x.login) AS rn,
               SUM(x.dep)        OVER (PARTITION BY x.person_key) AS p_dep,
               SUM(x.wd)         OVER (PARTITION BY x.person_key) AS p_wd,
               SUM(x.volume)     OVER (PARTITION BY x.person_key) AS p_vol,
               SUM(x.commission) OVER (PARTITION BY x.person_key) AS p_comm,
               MIN(x.first_trade) OVER (PARTITION BY x.person_key) AS p_first_trade,
               COUNT(*)          OVER (PARTITION BY x.person_key) AS n_accounts,
               MAX(x.last_activity) OVER (PARTITION BY x.person_key) AS p_last_act
        FROM (
        SELECT c.login, c.name, c.phone, c.country, c.city, c.balance, c.kyc_status,
               -- NO created_at fallback: created_at is our IMPORT day (Jun 15 2026 for the bulk),
               -- which made "most registration dates = 15/Jun". Unknown stays blank.
               COALESCE(NULLIF(c.reg_date,''), td.first_dep::text) AS reg_date, c.utm_campaign,
               COALESCE(td.dep,0) AS dep, COALESCE(td.wd,0) AS wd,
               COALESCE(itc.lots,0) AS volume, tv.first_trade,
               dm.method AS top_method,
               GREATEST(COALESCE(net.cid_cnt,0),0) AS cid_cnt,
               GREATEST(COALESCE(net.ip_cnt,0),0)  AS ip_cnt,
               c.assigned_agent_id AS sales_agent_id,
               COALESCE(acct.account_number, c.login) AS account_number,
               -- commission from the OVERLAID ib_trades: excel-exact for the Plugit era,
               -- engine values after the cutoff (desk rule Jul 9 2026) — NOT the deals recompute
               COALESCE(itc.commission,0) AS commission,
               c.email, td.first_dep,
               c.customer_no, c.email_verified, c.phone_verified,
               -- last activity = latest of last trade / last money movement (like the Clients page)
               NULLIF(GREATEST(COALESCE(tv.last_trade,''), COALESCE(LEFT(td.last_tx,10),'')),'') AS last_activity,
               (COALESCE(NULLIF(c.phone,''),'L'||c.login::text) || '|' || COALESCE(c.platform,'MT5')) AS person_key
        FROM clients c
        LEFT JOIN (
            SELECT login,
                   SUM(CASE WHEN tx_type='deposit' AND amount<1000000
                     AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust' THEN amount ELSE 0 END) AS dep,
                   SUM(CASE WHEN tx_type='withdrawal' AND amount<1000000
                     AND COALESCE(status,'')<>'rejected' THEN amount ELSE 0 END) AS wd,
                   MIN(CASE WHEN tx_type='deposit' THEN tx_date END) AS first_dep,
                   MAX(LEFT(tx_date,10)) AS last_tx
            FROM transactions GROUP BY login
        ) td ON td.login = c.login
        LEFT JOIN LATERAL (
            -- all-time lots + first/last trade + commission this client earned the IB
            -- (commission model: eligible opening trades, rate per IB level & symbol)
            SELECT SUM(CASE WHEN {FX_OR_GOLD} THEN d.volume/10000.0 ELSE 0 END) AS lots,
                   MIN(NULLIF(d.deal_date,'')) AS first_trade,
                   MAX(NULLIF(d.deal_date,'')) AS last_trade,
                   COALESCE(SUM(CASE WHEN d.entry = 1 THEN (d.volume/10000.0) * r.comm_per_lot ELSE 0 END),0) AS commission
            FROM deals d
            LEFT JOIN commission_rates r ON r.ib_level = :level AND r.symbol = d.symbol
            WHERE d.login = c.login AND d.action IN (0,1) AND d.volume > 0
        ) tv ON TRUE
        LEFT JOIN LATERAL (
            -- from the OVERLAID ib_trades: commission (eligible only) + lots for ALL closed trades.
            -- lots MUST come from here, not deals: MT4 stores volume in a different scale, so the
            -- deals/10000 formula showed 0 lots for every MT4 client (ib_trades normalises it).
            SELECT SUM(CASE WHEN t.eligible THEN t.commission ELSE 0 END) AS commission,
                   SUM(t.lots) AS lots
            FROM ib_trades t WHERE t.login = c.login
        ) itc ON TRUE
        LEFT JOIN LATERAL (
            SELECT t.method FROM transactions t
            WHERE t.login = c.login AND t.tx_type='deposit' AND COALESCE(t.method,'') <> ''
            GROUP BY t.method ORDER BY COUNT(*) DESC LIMIT 1
        ) dm ON TRUE
        LEFT JOIN LATERAL (
            SELECT
              -- devices = cid AND mqid (mqid covers MT4 terminals; backfilled Jul 2026)
              (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b WHERE b.identifier_type IN ('cid','mqid')
                 AND b.identifier_value IN (SELECT identifier_value FROM account_identifiers
                                            WHERE login=c.login AND identifier_type IN ('cid','mqid'))) - 1 AS cid_cnt,
              (SELECT COUNT(DISTINCT b.login) FROM account_identifiers b WHERE b.identifier_type='ip'
                 AND b.identifier_value IN (SELECT identifier_value FROM account_identifiers
                                            WHERE login=c.login AND identifier_type='ip')) - 1 AS ip_cnt
        ) net ON TRUE
        LEFT JOIN LATERAL (
            -- #101 (Zainab): the trading-account number = the person's primary login,
            -- defined exactly like the Clients list (#73): the HIGHEST POSITIVE-balance
            -- login among the same phone+platform siblings, else the highest-balance one.
            -- NOTE: written WITHOUT a CASE in the WHERE so the ix_clients_phone_platform index
            -- is actually used (the CASE form seq-scanned clients per row -> ~10s/IB). A client
            -- with null/empty/'0' phone matches no sibling here, so the outer
            -- COALESCE(acct.account_number, c.login) falls back to its own login (same result).
            SELECT COALESCE(
                (array_agg(s.login ORDER BY s.balance DESC NULLS LAST)
                    FILTER (WHERE s.balance > 0))[1],
                (array_agg(s.login ORDER BY s.balance DESC NULLS LAST))[1]
            ) AS account_number
            FROM clients s
            WHERE c.phone IS NOT NULL AND c.phone <> '' AND c.phone <> '0'
              AND s.phone = c.phone AND COALESCE(s.platform,'MT5') = COALESCE(c.platform,'MT5')
        ) acct ON TRUE
        WHERE {cwhere}
        ) x ) y
        -- ACCOUNT-WISE (desk rule Jul 13 2026): every trading account is its OWN row (the portal
        -- 'Trading accounts' tab lists them all, name repeated); person grouping/merging happens
        -- client-side via customer_no. Sort keeps a person's accounts together, biggest book first.
        ORDER BY y.p_dep DESC, y.person_key, y.dep DESC, y.login
        LIMIT 600
    """), cparams).fetchall()

    # per-client commission breakdown for the period (from deals)
    # per-client commission for the period from the OVERLAID ib_trades (excel-exact era + engine after)
    comm_rows = db.execute(text("""
        SELECT t.login, MAX(t.client_name) AS name,
               SUM(t.lots) AS lots,
               SUM(t.commission) AS comm
        FROM ib_trades t
        JOIN clients c ON c.login = t.login
        WHERE c.agent = ANY(:agents) AND t.eligible
          AND t.close_time >= CAST(:p_from AS timestamp) AND t.close_time < CAST(:p_to_next AS timestamp)
        GROUP BY t.login ORDER BY comm DESC LIMIT 200
    """), base).fetchall()

    # abuse flags for this IB's clients (from the abuse engine's per-account table)
    ib_flags = {}
    _cl = [r[0] for r in client_rows if r and r[0]]
    if _cl and db.execute(text("SELECT to_regclass('public.abuse_account_flags')")).scalar():
        ib_flags = {a[0]: {"type": a[1], "severity": a[2], "hot": a[3]} for a in db.execute(text(
            "SELECT login, abuse_type, severity, hot FROM abuse_account_flags WHERE login = ANY(:l)"),
            {"l": _cl}).fetchall()}
    # canonical 0-10 network score (build_network_scores.py) — same value every page shows.
    # network_reason = WHY a related account is linked (top relation signal) → shown on the red badge.
    ib_netmap, ib_reasonmap = {}, {}
    if _cl:
        for lg, sc, rsn in db.execute(text(
            "SELECT login, COALESCE(network_score,0), COALESCE(network_reason,'') FROM clients WHERE login = ANY(:l)"),
            {"l": _cl}).fetchall():
            ib_netmap[lg] = int(sc or 0)
            ib_reasonmap[lg] = rsn or ""

    # sales-agent names (clients.assigned_agent_id -> users.full_name) for the Sales agent column
    _sa_ids = list({r[16] for r in client_rows if len(r) > 16 and r[16]})
    sales_agent_map = {}
    if _sa_ids:
        sales_agent_map = {u[0]: u[1] for u in db.execute(text(
            "SELECT id, full_name FROM users WHERE id = ANY(:ids)"), {"ids": _sa_ids}).fetchall()}
    _ABUSE_LBL = {'margin_partner': 'Margin-Out', 'bonus_ring': 'Bonus Ring',
                  'bonus_cashout': 'Bonus Cash-Out', 'chip_dump': 'Chip Dump',
                  'swap_carry': 'Swap Carry', 'toxic_arb': 'Toxic'}

    # The IB's real account manager = the sales agent assigned to the IB's OWN client
    # account (clients.login = ib.agent_id). Falls back to that agent's manager if none.
    manager = None
    mrow = db.execute(text("""
        SELECT u.full_name, u.title, u.role, u.email, u.phone, u.avatar_url, u.extension, u.department
        FROM clients c JOIN users u ON u.id = c.assigned_agent_id
        WHERE c.login = :agent LIMIT 1
    """), {"agent": agent}).fetchone()
    if mrow:
        _ROLE_LBL = {"sales_agent": "Sales Agent", "sales_manager": "Sales Manager",
                     "retention_agent": "Retention Agent", "admin": "Administrator",
                     "sales_director": "Sales Director"}
        manager = {
            "name": mrow[0] or "", "title": mrow[1] or _ROLE_LBL.get(mrow[2] or "", "Account Manager"),
            "role": mrow[2] or "", "email": mrow[3] or "", "phone": mrow[4] or "",
            "avatar_url": mrow[5] or "", "extension": mrow[6] or "", "department": mrow[7] or "",
        }

    # Both MT accounts of this IB (person) — fetch the ACTUAL MT accounts from clients that sit in
    # an IB group: MT5 = IB\IB-N, MT4 = TNFX-IB-N. Linked by email / customer_no / this login, so we
    # surface the MT4 account even when it isn't a separate ibs row.
    acct_rows = db.execute(text("""
        SELECT DISTINCT c.login, COALESCE(c.platform,'MT5') AS platform, c.group_name
        FROM clients c
        WHERE c.group_name ~ '^(TNFX-IB-|IB.IB-)'
          AND (
            (COALESCE(:em,'') <> '' AND LOWER(c.email) = LOWER(:em))
            OR (c.customer_no IS NOT NULL AND c.customer_no = (SELECT customer_no FROM clients WHERE login = :agent LIMIT 1))
            OR c.login = :agent
          )
    """), {"em": ib.email, "agent": agent}).fetchall()
    accounts = sorted(
        [{"account": a[0], "platform": a[1], "group": a[2],
          "ib_level": (int(a[2].split("-")[-1]) if a[2] and a[2].split("-")[-1].isdigit() else None)}
         for a in acct_rows],
        key=lambda x: (x["platform"] != "MT4", x["account"]))
    if not accounts:
        accounts = [{"account": agent, "platform": "MT5", "group": ib.group_name or "", "ib_level": level}]
    # master IB (parent)
    master = None
    if getattr(ib, "parent_ib_id", None):
        m = db.execute(text("SELECT id, agent_id, name, ext_ib_id FROM ibs WHERE id=:p"), {"p": ib.parent_ib_id}).fetchone()
        if m: master = {"id": m[0], "agent_id": m[1], "name": m[2] or "", "ext_ib_id": m[3]}

    # NDA verdict + review status per client row (portal shows the VERDICT, never the evidence).
    # Separate lookups (not extra columns in the big window query) so positional r[i] mapping is safe.
    _logins = [r[0] for r in client_rows]
    # logins that are the IB's OWN accounts (live email/customer_no match) — tag them self even if the
    # ib_self_related table hasn't been rebuilt yet for this (often brand-new) IB.
    _self_logins = {r[0] for r in client_rows
                    if (len(r) > 19 and r[19] and _ib_email and str(r[19]).lower() == _ib_email)
                    or (len(r) > 21 and r[21] and _ib_cust and r[21] == _ib_cust)}
    # ftd_here: did this customer's FIRST-ever deposit land under this IB? (else: additional account)
    _agents_set = set(agents_all)
    _cust_nos = list({r[21] for r in client_rows if len(r) > 21 and r[21]})
    ftd_here_map = {}
    if _cust_nos:
        for cn, ag in db.execute(text("""
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.agent
            FROM clients c
            WHERE c.customer_no = ANY(:cns) AND NULLIF(c.first_deposit_at,'') IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC
        """), {"cns": _cust_nos}).fetchall():
            ftd_here_map[cn] = ag in _agents_set
    nda_map, rev_map, arch_map, grp_map, nda_pend_map, nda_lots_map = {}, {}, {}, {}, {}, {}
    if _logins:
        for l, n, arch, grp, plat, rst, ndl in db.execute(text("""
                SELECT login, is_nda,
                       (COALESCE(is_archived,FALSE) OR COALESCE(user_archived,FALSE)),
                       COALESCE(group_name,''), COALESCE(NULLIF(platform,''),'MT5'),
                       COALESCE(relation_state,''), COALESCE(nda_lots,0)
                FROM clients WHERE login = ANY(:l)"""), {"l": _logins}).fetchall():
            nda_map[l] = n
            arch_map[l] = bool(arch)
            grp_map[l] = (grp, plat)
            nda_pend_map[l] = (rst == 'nda_pending')   # yellow: relation-free FTD below the 1.0-lot floor
            nda_lots_map[l] = float(ndl or 0)          # customer's Gold+FX lots (for the '0.XX / 1.0' nudge)
        if db.execute(text("SELECT to_regclass('public.ib_nda_reviews')")).scalar():
            for l, s in db.execute(text("""
                SELECT DISTINCT ON (login) login, status FROM ib_nda_reviews
                WHERE ib_id = :ib AND login = ANY(:l)
                ORDER BY login, requested_at DESC
            """), {"ib": ib_id, "l": _logins}).fetchall():
                rev_map[l] = s

    # SELF / RELATED accounts (anti-abuse): which of this IB's trading accounts are the IB's OWN or
    # 100%-related to them (ib_self_related, built by ib_trades / ib_self_related.build). Drives the
    # portal "self / related · zero commission" badge + the L5/L6 zero-commission rule. Matched by
    # login (each client login belongs to one IB).
    sr_map = {}
    if _logins and db.execute(text("SELECT to_regclass('public.ib_self_related')")).scalar():
        for l, kind, reason in db.execute(text("""
            SELECT DISTINCT ON (login) login, kind, reason FROM ib_self_related
            WHERE login = ANY(:l) ORDER BY login, (kind='self') DESC
        """), {"l": _logins}).fetchall():
            sr_map[l] = (kind, reason)
    # agreement acceptance state (columns are written by signup / the accept endpoint; the ORM
    # model may not map them, so read raw) — the portal gates its onboarding popup on the version.
    # social_links (from signup) shown read-only on the IB's Profile (add-only; edit/remove = admin).
    _agr = db.execute(text("SELECT agreement_version, agreement_accepted_at, social_links, status FROM ibs WHERE id=:i"),
                      {"i": ib_id}).fetchone()

    # PURE LEADS (desk request Jul 15): people who registered under this IB (TradeSoft
    # customers.ib carries the IB's Plugit name) but have NO trading account yet. The IB
    # gets their REAL phone/email so he can call and follow up.
    lead_rows = []
    if (ib.name or "").strip():
        try:
            lead_rows = [{
                "name": lr[0] or "", "phone": lr[1] or "", "email": lr[2] or "",
                "reg": str(lr[3] or "")[:10], "country": lr[4] or "", "city": lr[5] or "",
                "stage": lr[6] or "",
                "phone_verified": bool(lr[7]), "email_verified": bool(lr[8]),
                "kyc": "verified" if lr[9] else ("pending" if lr[10] else ""),
            } for lr in db.execute(text("""
                SELECT l.full_name, l.phone, l.email, l.created_at, l.country, l.city,
                       COALESCE(NULLIF(l.stage,''), l.status),
                       COALESCE(l.phone_verified, FALSE), COALESCE(l.email_verified, FALSE),
                       COALESCE(l.kyc_id_verified, FALSE), COALESCE(l.kyc_id_uploaded, FALSE)
                FROM leads l
                JOIN customers cu ON cu.customer_no = l.customer_no
                WHERE LOWER(TRIM(cu.ib)) = LOWER(TRIM(:ibname))
                  AND NOT EXISTS (SELECT 1 FROM clients c2 WHERE c2.customer_no = l.customer_no)
                ORDER BY l.created_at DESC NULLS LAST
                LIMIT 400
            """), {"ibname": ib.name}).fetchall()]
        except Exception:
            db.rollback()

    return {
        "id":                ib.id,
        "ext_ib_id":         getattr(ib, "ext_ib_id", None),
        "ib_creation_date":  (ib.ib_creation_date.isoformat() if getattr(ib, "ib_creation_date", None) else None),
        "is_sub_ib":         bool(getattr(ib, "is_sub_ib", False)),
        "master_ib":         master,
        "accounts":          accounts,
        "manager":           manager,
        "agent_id":          agent,
        "ib_code":           ib.ib_code or "",
        "name":              ib.name or "",
        "email":             ib.email or "",
        # RULE: IBs are clients too — always treated as verified (email + phone + KYC).
        "email_verified":    True,
        "phone_verified":    True,
        "kyc":               "verified",
        "phone":             ib.phone or "",
        "country":           ib.country or "",
        "city":              ib.city or "",
        "photo_url":         getattr(ib, "photo_url", None) or "",
        "bio":               getattr(ib, "bio", None) or "",
        "ib_level":          level,
        "tier":              TIER_NAMES.get(level, "Bronze"),
        "group_name":        ib.group_name or "",
        "balance":           float(ib.balance or 0),
        "total_clients":     person_count or ib.total_clients or 0,   # merged PERSONS = what the tab shows
        "active_clients":    ib.active_clients or 0,
        "total_volume":      float(ib.total_volume or 0),
        "total_commission":  float(ib.total_commission or 0),
        "unpaid_commission": float(ib.unpaid_commission or 0),
        "paid_commission":   float(ib.paid_commission or 0),
        "total_payoff":      float(getattr(ib, "total_payoff", 0) or 0),
        "net_commission":    float(ib.total_commission or 0) - float(getattr(ib, "total_payoff", 0) or 0),
        "commission_excel":    float(getattr(ib, "commission_excel", 0) or 0),
        "commission_computed": float(getattr(ib, "commission_computed", 0) or 0),
        "commission_source":   getattr(ib, "commission_source", None) or "",
        # agreement/onboarding gate — the portal shows the intro+agreement popup when the IB's
        # accepted version differs from the current AGREEMENT_VERSION (fetched from /ib-agreement).
        "agreement_version":     (_agr[0] if _agr else "") or "",
        "agreement_accepted_at": (_agr[1].isoformat() if (_agr and _agr[1]) else None),
        "social_links":          (_agr[2] if (_agr and len(_agr) > 2) else None) or [],
        "status":                (_agr[3] if (_agr and len(_agr) > 3) else None) or "",
        "period": {
            "from":           p_from,
            "to":             p_to,
            "commission":     p_commission,   # excel-daily (authoritative) + live; pk fallback
            "volume":         float(pk[0] or 0),
            "deposits":       float(pm[0] or 0),
            "withdrawals":    float(pm[1] or 0),
            "new_clients":    new_clients,
            "active_clients": max(pk[2] or 0, pm[2] or 0),
            "ftd":            ftd_period,   # new deposit accounts (unique customers) in the period
            "nda":            nda_period,   # of those, genuinely new (promotion-eligible)
            "payoff":         p_payoff,     # approved withdrawals/transfers in the period
        },
        "funnel": {
            "clicks":         0,
            "leads":          leads_count,
            "verified_leads": verified_leads,
            "ftd":            ftd_all,      # customers whose FIRST-ever deposit was under this IB
            "nda":            nda_all,      # of those, genuinely new
            "sub_ibs":        len(sub_ibs),
        },
        "lead_rows":         lead_rows,   # registered under the IB, no trading account yet
        # promotion criteria counted from the LAST level change (null since = whole history)
        "tier_progress": {
            "since":    (tp_since.isoformat() if tp_since else None),
            "ftd":      int(tp_ftd),
            "nda":      int(tp_nda),
            "volume":   tp_vol,
            "deposits": tp_dep,
            "accounts": int(tp_acct),                       # funded accounts since the baseline
            "months":   round(tp_months, 1),
            "lots_avg": round(tp_vol / tp_months, 1),       # monthly-average lots
        },
        # what the NEXT grade requires (ib_tier_requirements, desk sheet) — null at Prime IB
        "tier_next": tier_next_req,
        "clients": [{
            "login":       r[0],
            "name":        r[1] or "",
            # the account UNDER THIS IB (r[0]) — NOT the person's global primary account (r[17]),
            # which can belong to a DIFFERENT IB and made rows look wrong/'empty' (Hamza case).
            "account_number": r[0],
            "phone":       r[2] or "",
            "country":     r[3] or "",
            "city":        r[4] or "",
            "balance":     float(r[5] or 0),
            "kyc":         "verified",   # RULE: clients are always approved KYC
            "reg_date":    str(r[7])[:10] if r[7] else "",
            "campaign":    r[8] or "",
            # PER-ACCOUNT values (rows are one-per-account since Jul 13 2026; the frontend
            # person-merges by customer_no where person totals are needed). n_accounts (r[32])
            # still says how many accounts the person holds under this IB.
            "total_dep":   float(r[9] or 0),
            "total_with":  float(r[10] or 0),
            "volume":      float(r[11] or 0),
            "first_trade": str(r[12] or "")[:10],
            "deposit_method": r[13] or "",
            # SELF accounts earn ZERO commission at L5-6 (unlock at L7) — enforce it on the value too,
            # not just the badge, so a self account's trades never pay out at those levels.
            "commission":  (0.0 if (r[0] in _self_logins and level < 7) else float(r[18] or 0)),
            "accounts":    int((len(r) > 32 and r[32]) or 1),   # accounts the person holds here
            "last_activity": str((len(r) > 24 and r[24]) or "")[:10],
            "email":       (len(r) > 19 and r[19]) or "",
            "first_deposit": str(r[20])[:10] if (len(r) > 20 and r[20]) else "",
            "customer_no": (len(r) > 21 and r[21]) or "",
            # SELF account = the IB's own trading account (same email / customer_no). Tagged in the UI;
            # earns no commission at L5-6 (handled by ib_trades eligibility). Sub-IB stand-alone rule.
            "is_self":     r[0] in _self_logins,
            "email_verified": True,   # RULE: clients are always verified
            "phone_verified": True,
            "is_nda":      bool(nda_map.get(r[0])),
            # yellow "pending NDA": a relation-free unique FTD who hasn't yet traded 1.0 Gold+FX lot
            # (summed across the customer's accounts). Not counted for promotion until they qualify.
            "nda_pending": bool(nda_pend_map.get(r[0])),
            "nda_lots":    round(nda_lots_map.get(r[0], 0.0), 2),
            # archived accounts STAY in the list AND in FTD/NDA history (desk rule Jul 14) —
            # the flag is display-only so the IB understands why the account shows no activity
            "is_archived": arch_map.get(r[0], False),
            "group_name":  grp_map.get(r[0], ("", "MT5"))[0],
            "platform":    grp_map.get(r[0], ("", "MT5"))[1],
            # REAL verification for the LEADS tab (the always-verified rule is for CLIENTS only)
            "email_verified_real": bool(len(r) > 22 and r[22]),
            "phone_verified_real": bool(len(r) > 23 and r[23]),
            "kyc_real":    (r[6] or "").strip().lower(),
            # no customer_no → can't check globally; fall back to "has a deposit here"
            "ftd_here":    ftd_here_map.get((len(r) > 21 and r[21]) or None, bool(len(r) > 20 and r[20])),
            "nda_review":  rev_map.get(r[0], ""),      # '' | pending | approved | rejected
            "network_score": ib_netmap.get(r[0], 0),   # canonical 0-10, same as all pages
            "relation_reason": ib_reasonmap.get(r[0], ""),   # why a Related account is linked (top signal)
            "abuse_flag":  _ABUSE_LBL.get((ib_flags.get(r[0]) or {}).get("type"), "") if ib_flags.get(r[0]) else "",
            "abuse_severity": (ib_flags.get(r[0]) or {}).get("severity", ""),
            "abuse_hot":   bool((ib_flags.get(r[0]) or {}).get("hot")),
            "sales_agent": sales_agent_map.get(r[16] if len(r) > 16 else None, ""),
            # anti-abuse: 'self' = the IB's own account, 'related' = 100% (10/10) linked to the IB;
            # these earn ZERO commission at Level 5/6 (unlock at Level 7). None = a normal client acct.
            "self_related":        (sr_map.get(r[0]) or (('self', 'Your own trading account') if r[0] in _self_logins else (None, "")))[0],
            "self_related_reason": (sr_map.get(r[0]) or (('self', 'Your own trading account') if r[0] in _self_logins else (None, "")))[1],
        } for r in client_rows],
        "sub_ibs": [{
            "id":           s.id,
            "agent_id":     s.agent_id,
            "ib_code":      s.ib_code or "",
            "name":         s.name or "",
            "ib_level":     s.ib_level or 5,
            "total_clients":s.total_clients or 0,
            "total_volume": float(s.total_volume or 0),
            "total_commission": float(s.total_commission or 0),
            "unpaid_commission": float(s.unpaid_commission or 0),
            "balance":      float(s.balance or 0),
            "status":       "active" if (s.total_clients or 0) > 0 else "inactive",
        } for s in sub_ibs],
        "commissions": [{
            "client_login":   r[0],
            "client_name":    r[1] or f"#{r[0]}",
            "lots":           float(r[2] or 0),
            "pts_per_lot":    level,
            "commission_usd": float(r[3] or 0),
            "status":         "unpaid",
        } for r in comm_rows],
        "referral_links": [],
    }


@router.get("/{ib_id}/operations")
def ib_operations(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """This IB's payout operations (withdrawals + internal/external transfers) for the IB profile."""
    _assert_can_see_ib(db, current_user, ib_id)
    if not db.execute(text("SELECT to_regclass('public.ib_operations')")).scalar():
        return {"operations": [], "summary": {}}
    rows = db.execute(text("""
        SELECT request_type, amount, payment_type, status, to_account, op_date, action_date, note, account
        FROM ib_operations WHERE ib_id = :id ORDER BY op_date DESC NULLS LAST LIMIT 500
    """), {"id": ib_id}).fetchall()
    summ = db.execute(text("""
        SELECT COALESCE(SUM(amount) FILTER (WHERE status='Approved'),0) AS paid_out,
               COALESCE(SUM(amount) FILTER (WHERE status='Approved' AND request_type='Wallet Withdrawal'),0) AS withdrawn,
               COALESCE(SUM(amount) FILTER (WHERE status='Approved' AND request_type LIKE '%Transfer'),0) AS transferred,
               COUNT(*) FILTER (WHERE status='Pending') AS pending
        FROM ib_operations WHERE ib_id = :id
    """), {"id": ib_id}).fetchone()
    return {
        "summary": {"paid_out": float(summ[0] or 0), "withdrawn": float(summ[1] or 0),
                    "transferred": float(summ[2] or 0), "pending": summ[3] or 0},
        "operations": [{
            "request_type": r[0] or "", "amount": float(r[1] or 0), "payment_type": r[2] or "",
            "status": r[3] or "", "to_account": r[4] or "", "account": r[8] or "",
            "op_date": r[5].isoformat() if r[5] else None,
            "action_date": r[6].isoformat() if r[6] else None, "note": r[7] or "",
        } for r in rows],
    }


@router.post("/{ib_id}/agreement/accept")
def accept_agreement(ib_id: int, data: dict = None, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """The IB confirms they have read the onboarding intro + IB Agreement. Records acceptance
    (agreement_accepted_at + current version) so the intro popup shows only once, until the
    agreement version changes."""
    _assert_can_see_ib(db, current_user, ib_id)
    import ib_portal_extras
    ver = ib_portal_extras.AGREEMENT_VERSION
    db.execute(text("UPDATE ibs SET agreement_accepted_at = NOW(), agreement_version = :v WHERE id = :i"),
               {"v": ver, "i": ib_id})
    db.commit()
    return {"ok": True, "agreement_version": ver}


@router.post("/{ib_id}/operations")
def create_ib_operation(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """IB requests a payout from the portal: withdrawal or internal transfer (-> his trading acct).
    Creates a Pending row that shows up on the admin Withdrawals page for approval."""
    _assert_can_see_ib(db, current_user, ib_id)
    db.execute(text("""CREATE TABLE IF NOT EXISTS ib_operations(id SERIAL PRIMARY KEY, ext_ib_id INTEGER,
        ib_id INTEGER, account VARCHAR, name VARCHAR, email VARCHAR, request_type VARCHAR, amount DOUBLE PRECISION,
        converted_amount DOUBLE PRECISION, payment_type VARCHAR, status VARCHAR, to_account VARCHAR,
        referral_id VARCHAR, comment TEXT, op_date TIMESTAMPTZ, action_date TIMESTAMPTZ, order_id VARCHAR, note TEXT)"""))
    ib = db.execute(text("SELECT ext_ib_id, name, email, COALESCE(unpaid_commission,0), COALESCE(ib_level,5) FROM ibs WHERE id=:id"),
                    {"id": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    # LEVEL-5 LOCK (desk rule, Jul 2026): a Level 5 IB cannot withdraw or transfer until they have
    # proven genuine IB activity and been promoted to Level 6. Enforced here (backend) + in the UI.
    if int(ib[4] or 5) < 6:
        raise HTTPException(status_code=403,
            detail="Withdrawals and transfers unlock at Level 6. As a Level 5 IB, keep introducing "
                   "genuine new clients — once you're promoted to Level 6 this is enabled.")
    kind = (data.get("kind") or "").lower()
    amount = round(float(data.get("amount") or 0), 2)
    MIN_PAYOUT = 50.0
    if amount < MIN_PAYOUT:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal / internal transfer is ${MIN_PAYOUT:.0f}")
    # available = pending commission balance (earned − paid − approved payouts, kept by the DB
    # trigger) MINUS requests that are still Pending approval (not yet counted in total_payoff),
    # so stacked pending requests can't exceed the balance either.
    pend = db.execute(text("""SELECT COALESCE(SUM(amount),0) FROM ib_operations
        WHERE status='Pending' AND (ib_id = :id OR (:ext IS NOT NULL AND ext_ib_id = :ext))"""),
        {"id": ib_id, "ext": ib[0]}).scalar() or 0
    available = round(float(ib[3]) - float(pend), 2)
    if amount > available:
        raise HTTPException(status_code=400,
            detail=f"Amount exceeds your available commission balance (${max(available,0):,.2f} available)")
    rtype = "Internal Wallet Transfer" if kind == "transfer" else "Wallet Withdrawal"
    db.execute(text("""INSERT INTO ib_operations(ext_ib_id, ib_id, name, email, request_type, amount, converted_amount,
        payment_type, status, to_account, comment, op_date, note)
        VALUES(:ext,:id,:nm,:em,:rt,:amt,:amt,:pm,'Pending',:to,:cm,NOW(),:nt)"""),
        {"ext": ib[0], "id": ib_id, "nm": ib[1], "em": ib[2], "rt": rtype, "amt": amount,
         "pm": (data.get("payment_type") or ("Transfer" if kind == "transfer" else "USDt")),
         "to": (data.get("to_account") or ""), "cm": data.get("comment") or "",
         "nt": "requested from portal"})
    db.commit()
    return {"ok": True, "request_type": rtype, "amount": amount, "status": "Pending"}


@router.get("/{ib_id}/promotions")
def ib_promotions(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """This IB's level-change history (from the broker Commission Report): a per-lot commission-rate
    step-up on gold/majors == a promotion; a step-DOWN == a demotion (IB levels are not fixed)."""
    _assert_can_see_ib(db, current_user, ib_id)
    if not db.execute(text("SELECT to_regclass('public.ib_promotions')")).scalar():
        return {"promotions": []}
    has_dir = db.execute(text("SELECT to_regclass('public.ib_promotions') IS NOT NULL AND EXISTS ("
        "SELECT 1 FROM information_schema.columns WHERE table_name='ib_promotions' AND column_name='direction')")).scalar()
    dircol = "direction" if has_dir else "'promotion'"
    rows = db.execute(text(f"""
        SELECT promo_date, from_level, to_level, note, source, created_at, {dircol}
        FROM ib_promotions WHERE ib_id = :id ORDER BY promo_date ASC
    """), {"id": ib_id}).fetchall()
    return {"promotions": [{
        "date": r[0].isoformat() if r[0] else None,
        "from_level": r[1], "to_level": r[2], "note": r[3] or "",
        "source": r[4] or "", "detected_at": r[5].isoformat() if r[5] else None,
        "direction": r[6] or "promotion",
    } for r in rows]}


@router.get("/{ib_id}/trades")
def ib_trades_list(
    ib_id: int,
    client_login: int = None, country: str = None, city: str = None,
    ticket: int = None,              # exact Trade ID (deal_id) lookup
    platform: str = None, account_type: str = None, campaign: str = None,
    f_ib_id: int = None,             # narrow the all-IBs view to a single selected IB
    period: str = "this_month", date_from: str = None, date_to: str = None,
    view: str = "eligible",          # eligible | short | credit | all
    group_by: str = None,            # day | week | month | year -> aggregated buckets
    page: int = 1, page_size: int = 100,
    db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib),
):
    _assert_can_see_ib(db, current_user, ib_id)
    """Per-trade list for an IB's clients (the IB 'Trades' / 'Credit Trades' tab).
    Filterable by client / country / city / platform / account-type / period; the `view`
    splits eligible (paid), short (<5min, unpaid) and credit (bonus, unpaid) trades."""
    from crm_tz import day_lo, day_hi
    p_from, p_to = period_dates(period, date_from, date_to)
    # Iraqi-day UTC bounds (crm_tz) — close_time is a UTC timestamp
    where = ["t.close_time >= :pf AND t.close_time < :ptn"]
    params = {"pf": day_lo(p_from), "pt": p_to, "ptn": day_hi(p_to)}
    if ib_id and ib_id > 0:                # ib_id <= 0  ->  ALL IBs (admin-wide view)
        where.insert(0, "t.ib_id = :ib"); params["ib"] = ib_id
    elif f_ib_id:                          # all-IBs view narrowed to one selected IB
        where.insert(0, "t.ib_id = :fib"); params["fib"] = f_ib_id
    if client_login: where.append("t.login = :cl"); params["cl"] = client_login
    if ticket:       where.append("t.deal_id = :tk"); params["tk"] = ticket
    if country:      where.append("t.country = :co"); params["co"] = country
    if city:         where.append("t.city = :ci"); params["ci"] = city
    if platform:     where.append("t.platform = :pl"); params["pl"] = platform
    if account_type: where.append("t.account_type = :at"); params["at"] = account_type
    if campaign:     where.append("EXISTS (SELECT 1 FROM clients c WHERE c.login = t.login AND c.utm_campaign ILIKE :camp)"); params["camp"] = f"%{campaign}%"
    if view == "eligible":  where.append("t.eligible = TRUE")
    elif view == "short":   where.append("t.eligible = FALSE AND t.reason LIKE 'short%'")
    elif view == "credit":  where.append("t.reason = 'credit'")
    w = " AND ".join(where)

    # Display granularity: aggregate into time buckets instead of per-trade rows.
    groups = None
    _UNIT = {"day": "day", "week": "week", "month": "month", "year": "year"}.get((group_by or "").lower())
    if _UNIT:
        grows = db.execute(text(f"""
            SELECT date_trunc('{_UNIT}', t.close_time::timestamp) AS bucket,
                   COUNT(*) AS trades, COALESCE(SUM(t.lots),0) AS lots,
                   COALESCE(SUM(t.commission),0) AS commission, COALESCE(SUM(t.profit),0) AS profit
            FROM ib_trades t WHERE {w}
            GROUP BY 1 ORDER BY 1 DESC LIMIT 500
        """), params).fetchall()
        groups = [{"bucket": str(g[0])[:10], "trades": g[1], "lots": float(g[2] or 0),
                   "commission": float(g[3] or 0), "profit": float(g[4] or 0)} for g in grows]

    # potential ("saved / not paid") uses the ENGINE per-lot rate (eng_cpl) so credit/short trades
    # are valued even in the excel era (where comm_per_lot is the excel value = $0 for unpaid trades).
    tot = db.execute(text(f"""SELECT COUNT(*), COALESCE(SUM(lots),0), COALESCE(SUM(commission),0),
                              COALESCE(SUM(profit),0), COALESCE(SUM(lots*COALESCE(eng_cpl,comm_per_lot)),0)
                              FROM ib_trades t WHERE {w}"""), params).fetchone()
    rows = db.execute(text(f"""
        SELECT t.login, t.client_name, t.country, t.city, t.platform, t.account_type, t.symbol, t.direction,
               t.open_time, t.close_time, t.hold_sec, t.lots, t.open_price, t.close_price, t.profit, t.commission, t.eligible, t.reason,
               t.deal_id, ib.ib_code, ib.name AS ib_name
        FROM ib_trades t
        LEFT JOIN ibs ib ON ib.id = t.ib_id
        WHERE {w}
        ORDER BY t.close_time DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), {**params, "lim": page_size, "off": (page - 1) * page_size}).fetchall()
    ibf = "ib_id=:ib AND" if (ib_id and ib_id > 0) else ""
    opts = db.execute(text(f"""SELECT
        ARRAY(SELECT DISTINCT country FROM ib_trades WHERE {ibf} COALESCE(country,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT city FROM ib_trades WHERE {ibf} COALESCE(city,'')<>'' ORDER BY 1),
        ARRAY(SELECT DISTINCT account_type FROM ib_trades {('WHERE ib_id=:ib') if (ib_id and ib_id>0) else ''} ORDER BY 1),
        ARRAY(SELECT DISTINCT platform FROM ib_trades {('WHERE ib_id=:ib') if (ib_id and ib_id>0) else ''} ORDER BY 1)
    """), ({"ib": ib_id} if (ib_id and ib_id > 0) else {})).fetchone()
    # campaign options (only for a specific IB — else far too many)
    camp_opts = []
    if ib_id and ib_id > 0:
        camp_opts = [c[0] for c in db.execute(text("""
            SELECT DISTINCT utm_campaign FROM clients
            WHERE agent = (SELECT agent_id FROM ibs WHERE id = :ib) AND COALESCE(utm_campaign,'') <> ''
            ORDER BY 1 LIMIT 100
        """), {"ib": ib_id}).fetchall()]
    result = {
        "totals": {"trades": tot[0], "lots": float(tot[1] or 0), "commission": float(tot[2] or 0),
                   "profit": float(tot[3] or 0), "potential": float(tot[4] or 0)},
        "filters": {"countries": list(opts[0] or []), "cities": list(opts[1] or []),
                    "account_types": list(opts[2] or []), "platforms": list(opts[3] or []),
                    "campaigns": camp_opts},
        "groups": groups,
        "page": page, "page_size": page_size,
        "trades": [{
            "deal_id": r[18],
            "ib_code": r[19] or "", "ib_name": r[20] or "",
            "login": r[0], "client": r[1], "country": r[2], "city": r[3], "platform": r[4],
            "account_type": r[5], "symbol": r[6], "direction": r[7],
            "open_time": str(r[8]) if r[8] else None, "close_time": str(r[9]) if r[9] else None,
            "hold_min": round(r[10] / 60.0, 1) if r[10] is not None else None,
            "lots": float(r[11] or 0), "open_price": r[12], "close_price": r[13],
            "profit": float(r[14] or 0), "commission": float(r[15] or 0),
            "eligible": r[16], "reason": r[17],
        } for r in rows],
    }
    # staff_or_own_ib returns None for IB self-access. An IB must NOT see client P&L (whether
    # their clients win or lose money) — strip profit + entry/exit prices for the IB caller only.
    if current_user is None:
        result["totals"].pop("profit", None)
        for g in (result["groups"] or []):
            g.pop("profit", None)
        for tr in result["trades"]:
            tr.pop("profit", None); tr.pop("open_price", None); tr.pop("close_price", None)
    return result


# ─── NDA review requests (portal "Request review" on a not-NDA account) ─────────
def _ensure_nda_review_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_nda_reviews (
            id           SERIAL PRIMARY KEY,
            ib_id        INTEGER NOT NULL,
            login        BIGINT  NOT NULL,
            customer_no  TEXT,
            status       VARCHAR DEFAULT 'pending',    -- pending | approved | rejected
            requested_at TIMESTAMPTZ DEFAULT NOW(),
            reviewed_by  TEXT,
            reviewed_at  TIMESTAMPTZ,
            note         TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_ib_nda_reviews_ib ON ib_nda_reviews (ib_id, login);
    """))
    db.commit()


@router.post("/{ib_id}/nda-review")
def request_nda_review(ib_id: int, data: dict, db: Session = Depends(get_db),
                       current_user = Depends(staff_or_own_ib)):
    """IB disputes an account classified FTD-but-not-NDA. Creates a pending review case;
    the desk decides on the full evidence (staff side) — the IB only ever sees the verdict."""
    _ensure_nda_review_table(db)
    try:
        login = int(data.get("login") or 0)
    except (TypeError, ValueError):
        login = 0
    if not login:
        raise HTTPException(status_code=400, detail="login is required")
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    row = db.execute(text("""
        SELECT c.customer_no, c.is_nda FROM clients c
        WHERE c.login = :login AND c.agent IN (
            SELECT agent_id FROM ibs
            WHERE id = :ibid OR (CAST(:ext AS bigint) IS NOT NULL AND ext_ib_id = :ext)
        ) LIMIT 1
    """), {"login": login, "ibid": ib_id, "ext": getattr(ib, "ext_ib_id", None)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="That account is not under your IB")
    if row[1]:
        return {"ok": True, "status": "approved", "detail": "Already counted as NDA"}
    pending = db.execute(text("""
        SELECT status FROM ib_nda_reviews WHERE ib_id=:ib AND login=:l
        ORDER BY requested_at DESC LIMIT 1"""), {"ib": ib_id, "l": login}).fetchone()
    if pending and pending[0] == "pending":
        return {"ok": True, "status": "pending", "detail": "Review already requested"}
    db.execute(text("""
        INSERT INTO ib_nda_reviews (ib_id, login, customer_no, status)
        VALUES (:ib, :l, :cn, 'pending')"""), {"ib": ib_id, "l": login, "cn": row[0]})
    db.commit()
    return {"ok": True, "status": "pending",
            "detail": "Review requested — our team will re-check this account"}


# ─── Challenges (career path + weekly) ──────────────────────────────────────────
@router.get("/{ib_id}/challenges")
def get_challenges(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    _assert_can_see_ib(db, current_user, ib_id)
    return ib_challenges.list_all(db, ib_id)


@router.post("/{ib_id}/challenges/accept")
def accept_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    _assert_can_see_ib(db, current_user, ib_id)
    try:
        return ib_challenges.accept(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/claim")
def claim_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    try:
        res = ib_challenges.claim(db, ib_id, data.get("key", ""))
        try:
            import ib_portal_extras
            ib_portal_extras.notify(db, ib_id, "challenge", "Reward claimed 🏆",
                                    "Your challenge reward has been credited to your commission balance.")
        except Exception:
            pass
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/rechallenge")
def rechallenge_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    try:
        return ib_challenges.rechallenge(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ib_id}/challenges/claim-weekly")
def claim_weekly_challenge(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    try:
        return ib_challenges.claim_weekly(db, ib_id, data.get("key", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Campaigns (create + referral links) ────────────────────────────────────────
def _ensure_campaign_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ib_campaigns (
            id         SERIAL PRIMARY KEY,
            ib_id      INTEGER NOT NULL,
            name       VARCHAR NOT NULL,
            platform   VARCHAR,
            website    VARCHAR,
            ref_code   VARCHAR UNIQUE NOT NULL,
            clicks     INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """))
    db.commit()


def _ref_link(ref_code: str) -> str:
    return f"https://my1.tnfx.co/register?ref={ref_code}"


@router.get("/{ib_id}/ref")
def ib_ref(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """The IB's ONE solid standalone referral link + click/signup stats (desk Jul 15 2026).
    Link = my1.tnfx.co/r/<CODE>; unique clicks feed the weekly challenges; source breakdown."""
    import ib_referral
    code = ib_referral.get_or_create_code(db, ib_id)
    total = db.execute(text("SELECT COUNT(*) FROM ib_ref_clicks WHERE ib_id=:i"), {"i": ib_id}).scalar() or 0
    uniq = ib_referral.unique_clicks(db, ib_id)
    signups = db.execute(text("SELECT COUNT(*) FROM ib_ref_signups WHERE ib_id=:i"), {"i": ib_id}).scalar() or 0
    by_src = [{"src": r[0] or "direct", "clicks": r[1]} for r in db.execute(text("""
        SELECT COALESCE(NULLIF(src,''),'direct'), COUNT(*) FROM ib_ref_clicks
        WHERE ib_id=:i GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""), {"i": ib_id}).fetchall()]
    return {"code": code, "link": f"https://my1.tnfx.co/r/{code}",
            "clicks": int(total), "unique_clicks": int(uniq), "signups": int(signups), "by_source": by_src}


@router.get("/{ib_id}/referral-links")
def ib_referral_links(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    """The IB's EXISTING (Plugit) referral links — imported so they keep working."""
    _assert_can_see_ib(db, current_user, ib_id)
    if not db.execute(text("SELECT to_regclass('public.ib_referral_links')")).scalar():
        return {"links": []}
    rows = db.execute(text("""
        SELECT banner, referrer_id, campaign_code, custom_link, clicks
        FROM ib_referral_links WHERE ib_id = :ib ORDER BY id
    """), {"ib": ib_id}).fetchall()
    return {"links": [{"banner": r[0] or "", "referrer_id": r[1] or "", "campaign_code": r[2] or "",
                       "custom_link": r[3] or "", "clicks": r[4] or 0, "source": "plugit"} for r in rows]}


@router.get("/{ib_id}/campaigns")
def list_campaigns(ib_id: int, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    _assert_can_see_ib(db, current_user, ib_id)
    _ensure_campaign_table(db)
    rows = db.execute(text("""
        SELECT id, name, platform, website, ref_code, clicks, created_at
        FROM ib_campaigns WHERE ib_id = :ib ORDER BY created_at DESC
    """), {"ib": ib_id}).fetchall()
    return {"campaigns": [{
        "id": r[0], "name": r[1], "platform": r[2] or "", "website": r[3] or "",
        "ref_code": r[4], "ref_link": _ref_link(r[4]), "clicks": r[5] or 0,
        "created_at": r[6].isoformat() if r[6] else None,
    } for r in rows]}


@router.post("/{ib_id}/campaigns")
def create_campaign(ib_id: int, data: dict, db: Session = Depends(get_db), current_user = Depends(staff_or_own_ib)):
    _ensure_campaign_table(db)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    ib = db.execute(text("SELECT ib_code FROM ibs WHERE id = :id"), {"id": ib_id}).fetchone()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    # ref_code = IB code (sans 'IB') + short slug from name + a uniquifier
    import re, secrets
    base = (ib[0] or "").replace("IB", "")
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:8] or "camp"
    ref_code = f"{base}-{slug}-{secrets.token_hex(2)}"
    db.execute(text("""
        INSERT INTO ib_campaigns (ib_id, name, platform, website, ref_code)
        VALUES (:ib, :n, :p, :w, :rc)
    """), {"ib": ib_id, "n": name, "p": (data.get("platform") or "").strip(),
           "w": (data.get("website") or "").strip(), "rc": ref_code})
    db.commit()
    return {"ok": True, "ref_code": ref_code, "ref_link": _ref_link(ref_code)}


class PayCommissionRequest(BaseModel):
    ib_id: int
    amount: Optional[float] = None  # None = pay all unpaid


_PAY_ROLES = {"super_admin", "admin", "director", "accountant"}

@router.post("/pay-commission")
async def pay_commission(
    data: PayCommissionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Paying commission moves money on the books — restrict to admin/finance roles.
    if (current_user.role or "").lower() not in _PAY_ROLES:
        raise HTTPException(status_code=403, detail="You don't have permission to pay commissions.")
    ib = db.query(models.IB).filter(models.IB.id == data.ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")

    amount = data.amount or ib.unpaid_commission
    ib.unpaid_commission = max(0, (ib.unpaid_commission or 0) - amount)
    ib.paid_commission   = (ib.paid_commission or 0) + amount

    # Mark commission records as paid
    db.execute(text("""
        UPDATE ib_commissions SET status = 'paid'
        WHERE ib_id = :ib_id AND status = 'unpaid'
    """), {"ib_id": data.ib_id})
    db.commit()
    return {"message": f"Paid ${amount:.2f} to {ib.name}", "remaining": ib.unpaid_commission}


class SetLevelRequest(BaseModel):
    ib_level: Optional[int] = None
    level: Optional[int] = None     # accept either key name


@router.post("/{ib_id}/level")
async def set_ib_level(
    ib_id: int,
    data: SetLevelRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Quick inline level change from the IB Admin list (tickets #59 / #53).
    Sets ibs.ib_level directly. Validates the IB-5..IB-10 (Bronze..Master) range."""
    if not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")
    new_level = data.ib_level if data.ib_level is not None else data.level
    if new_level is None:
        raise HTTPException(status_code=400, detail="ib_level is required")
    try:
        new_level = int(new_level)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ib_level must be a number")
    if new_level < 5 or new_level > 10:
        raise HTTPException(status_code=400, detail="Level must be between IB-5 (Bronze) and IB-10 (Master)")
    ib = db.query(models.IB).filter(models.IB.id == ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    _record_level_change(db, ib, ib.ib_level or 5, new_level, source="crm_level_edit")
    ib.ib_level = new_level
    db.commit()
    return {
        "ok": True,
        "id": ib_id,
        "name": ib.name or "",
        "ib_level": new_level,
        "tier": TIER_NAMES.get(new_level, "Bronze"),
    }


class PromoteIBRequest(BaseModel):
    ib_id: int
    new_level: int


@router.post("/promote")
async def promote_ib(
    data: PromoteIBRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not can_change_ib_level(current_user):
        raise HTTPException(status_code=403, detail="Only Zainab can change an IB level.")
    if data.new_level < 5 or data.new_level > 10:
        raise HTTPException(status_code=400, detail="Level must be between 5 and 10")
    ib = db.query(models.IB).filter(models.IB.id == data.ib_id).first()
    if not ib:
        raise HTTPException(status_code=404, detail="IB not found")
    _record_level_change(db, ib, ib.ib_level or 5, data.new_level, source="crm_promote")
    ib.ib_level = data.new_level
    db.commit()
    return {"message": f"{ib.name} promoted to level {data.new_level}"}


# ── Create / add a new IB (ticket #12: the "+ Add IB" button did nothing) ──
@router.post("")
@router.post("/")
def create_ib(payload: dict, db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_user)):
    _require_ib_mgmt(current_user)
    """Create an IB from an MT login (agent_id). Auto-fills name/contact from that
    client account when available; the form fields override."""
    try:
        agent_id = int(payload.get("agent_id") or payload.get("login") or 0)
    except (TypeError, ValueError):
        agent_id = 0
    if not agent_id:
        raise HTTPException(status_code=400, detail="Enter the IB's trading account login")

    # don't double-create for the same login
    exists = db.execute(text("SELECT id FROM ibs WHERE agent_id=:a"), {"a": agent_id}).fetchone()
    if exists:
        raise HTTPException(status_code=409, detail=f"An IB already exists for login {agent_id} (#{exists[0]})")

    # pull details from the client account if it exists
    c = db.execute(text("""
        SELECT name, email, phone, country, city, group_name FROM clients WHERE login=:a LIMIT 1
    """), {"a": agent_id}).fetchone()

    def pick(key, idx):
        v = (payload.get(key) or "").strip() if isinstance(payload.get(key), str) else payload.get(key)
        return v or (c[idx] if c else None)

    name = (payload.get("name") or "").strip() or (c[0] if c else None)
    if not name:
        raise HTTPException(status_code=400, detail="Name is required (account not found — enter it manually)")
    try:
        level = int(payload.get("ib_level") or 5)
    except (TypeError, ValueError):
        level = 5
    level = max(5, min(10, level))

    ib_code = f"IB{agent_id}"
    new_id = db.execute(text("""
        INSERT INTO ibs (agent_id, ib_code, name, email, phone, country, city, ib_level,
                         status, kyc_status, total_clients, active_clients, unique_ftds,
                         total_volume, net_deposits, total_commission, unpaid_commission,
                         paid_commission, balance, referral_link, created_at, updated_at)
        VALUES (:a,:code,:n,:e,:p,:co,:ci,:lvl,'active','pending',0,0,0,0,0,0,0,0,0,
                :link, NOW(), NOW())
        RETURNING id
    """), {"a": agent_id, "code": ib_code, "n": name,
           "e": pick("email", 1), "p": pick("phone", 2),
           "co": pick("country", 3), "ci": pick("city", 4), "lvl": level,
           "link": f"https://my1.tnfx.co/r/{ib_code}"}).scalar()

    # ── Ticket #12(a): auto-link this IB's existing referred clients. ──
    # IB→clients linkage is via clients.agent (the MT agent login) = ibs.agent_id.
    # We additively stamp the denormalized clients.ib_id on the matching rows only.
    linked = db.execute(text("""
        UPDATE clients SET ib_id = :ib_id
        WHERE agent = :agent_id AND ib_id IS DISTINCT FROM :ib_id
    """), {"ib_id": new_id, "agent_id": agent_id}).rowcount
    db.commit()

    return {
        "ok": True,
        "id": new_id,
        "linked_clients": linked,
        # Ticket #12(b): setting the IB up as an agent on the MT server is a gated
        # MT-provisioning action — NOT performed here; flag it for separate approval.
        "mt_agent_setup": "pending_approval",
        "message": (f"IB '{name}' (login {agent_id}) created; "
                    f"linked {linked} existing referred client(s). "
                    f"MT-server agent setup needs separate approval."),
    }
