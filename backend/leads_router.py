"""
leads_router.py — Full leads management
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models
import rbac
from datetime import datetime, date, timedelta

router = APIRouter(prefix="/leads", tags=["Leads"])


# ---------------------------------------------------------------------------
# Stage canonicalization (ticket #180 — "filter by CONTACTED shows empty list")
# The leads LIST shows a lead's stage via the frontend stageOf(): it prefers the
# `stage` column but falls back to mapping the legacy lowercase `status` onto a
# stage label (contacted->Contacted, callback->Contacted, converted->Won, ...).
# The Stage FILTER must match that SAME canonical label, case-insensitively, or a
# lead shown as "Contacted" won't come back when you filter by "Contacted" (the
# old exact, case-sensitive `stage=:v OR status=:v` missed legacy/lowercase rows).
# ---------------------------------------------------------------------------

# any incoming filter value (any case / legacy code) -> canonical stage label
_STAGE_CANON = {
    "new": "New Lead", "new lead": "New Lead",
    "contacted": "Contacted", "callback": "Contacted",
    "converted": "Won", "won": "Won",
    "dead": "Not Interested", "not interested": "Not Interested",
    "no_answer": "No Answer", "no answer": "No Answer",
    "interested": "Interested in Training",
    "interested in training": "Interested in Training",
}


def _canon_stage_req(v: str) -> str:
    """Canonicalize a requested Stage filter value to its display label, so old
    lowercase links (?status=contacted) and the dropdown label both resolve the
    same way."""
    v = (v or "").strip()
    return _STAGE_CANON.get(v.lower(), v)


# SQL expression reproducing the frontend stageOf() for a leads row aliased `l`:
# the canonical stage label actually shown in the list.
_CANON_STAGE_SQL = """CASE lower(COALESCE(NULLIF(btrim(l.stage), ''), l.status, 'new'))
    WHEN 'new'        THEN 'New Lead'
    WHEN 'new lead'   THEN 'New Lead'
    WHEN 'contacted'  THEN 'Contacted'
    WHEN 'callback'   THEN 'Contacted'
    WHEN 'converted'  THEN 'Won'
    WHEN 'won'        THEN 'Won'
    WHEN 'dead'       THEN 'Not Interested'
    WHEN 'no_answer'  THEN 'No Answer'
    WHEN 'interested' THEN 'Interested in Training'
    ELSE COALESCE(NULLIF(btrim(l.stage), ''), 'New Lead')
END"""


@router.get("")
def get_leads(
    page:      int   = Query(1, ge=1),
    page_size: int   = Query(20, ge=1, le=500),
    search:    str   = Query(""),
    status:    str   = Query(""),
    source:    str   = Query(""),
    country:   str   = Query(""),
    city:      str   = Query(""),
    agent:     str   = Query(""),
    ib:        str   = Query(""),
    platform:  str   = Query(""),
    verified:  str   = Query(""),
    kyc:       str   = Query(""),    # 'verified' = KYC-verified leads only (#6)
    sort:      str   = Query("created_at"),
    badge:     str   = Query(""),
    period:    str   = Query("all_time"),
    archived:  str   = Query(""),    # ''/'active' = active only, 'archived' = archived, 'all' = both (#57)
    date_from: str   = Query(""),    # created_at >= (YYYY-MM-DD) (#62)
    date_to:   str   = Query(""),    # created_at <= (YYYY-MM-DD) (#62)
    own:       int   = Query(0),     # 1 = team leader's "My own data" toggle (self only, not team)
    connected: int   = Query(0),     # 1 = "Connected (last 7d)" tab: only leads contacted in the last week
    lead_id:   int   = Query(0),     # deep-link: fetch ONE lead by id (right-click open-in-tab)
    include_converted: int = Query(0),  # #215: 1 = also show leads that already deposited (became clients)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    where = ["1=1"]
    params: dict = {}

    # Deep-link fetch of a single lead (?lead_id=) — bypasses paging/filters so a URL like
    # ?lead=<id> always resolves the profile regardless of which list page it's on.
    if lead_id:
        where.append("l.id = :lead_id")
        params["lead_id"] = lead_id

    # Archive filter (#57) — default view = active (is_archived=false)
    if archived == "archived":
        where.append("COALESCE(l.is_archived, FALSE) = TRUE")
    elif archived == "all":
        pass
    else:
        where.append("COALESCE(l.is_archived, FALSE) = FALSE")

    # #215: a lead that made an APPROVED DEPOSIT has become a client — it now lives on the Clients
    # page, so drop it from the active Leads list by default (its owner is moved sales->retention in
    # TradeSoft; the CRM fetches that change). A single deep-link fetch (lead_id) and the explicit
    # include_converted=1 / archived views bypass this so the record is still reachable.
    if not include_converted and not lead_id and archived not in ("archived", "all"):
        where.append("""NOT EXISTS (SELECT 1 FROM clients cc
            WHERE cc.login IN (l.converted_login, l.matched_login)
              AND COALESCE(cc.total_deposits, 0) > 0)""")

    # Date-range on created_at (#62). Index-friendly: compare the RAW column to date
    # strings (no ::date cast). 'to' stays day-INCLUSIVE via a < (date_to + 1 day) bound.
    if date_from:
        where.append("l.created_at >= :date_from")
        params["date_from"] = date_from[:10]
    if date_to:
        where.append("l.created_at < :date_to_next")
        params["date_to_next"] = (
            datetime.strptime(date_to[:10], "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()

    if search:
        where.append("(l.full_name ILIKE :s OR l.phone ILIKE :s OR l.email ILIKE :s OR l.country ILIKE :s OR l.city ILIKE :s OR l.campaign_name ILIKE :s)")
        params["s"] = f"%{search}%"
    if status:
        # 'status' filter carries a STAGE name (New Lead / Contacted / ...). Match the
        # CANONICAL displayed stage (mirrors frontend stageOf) so filtering by e.g.
        # "Contacted" returns every lead the list shows as Contacted — including legacy
        # rows that only carry a lowercase `status` (contacted/callback). Case-insensitive;
        # old lowercase links (?status=contacted) still resolve via _canon_stage_req. (#180)
        where.append(f"({_CANON_STAGE_SQL}) = :stage_label")
        params["stage_label"] = _canon_stage_req(status)
    if source:
        where.append("l.source ILIKE :source")
        params["source"] = f"%{source}%"
    if country:
        where.append("l.country = :country")
        params["country"] = country
    if city:
        where.append("l.city ILIKE :city")
        params["city"] = f"%{city}%"
    if badge:
        where.append("l.match_badge = :badge")
        params["badge"] = badge
    if platform:
        where.append("l.platform = :platform")
        params["platform"] = platform
    # Verification filter
    if verified == 'verified':       where.append("l.is_verified=TRUE")
    elif verified == 'phone_only':   where.append("l.phone_verified=TRUE AND l.email_verified=FALSE")
    elif verified == 'email_only':   where.append("l.email_verified=TRUE AND l.phone_verified=FALSE")
    elif verified == 'unverified':   where.append("l.is_verified=FALSE AND l.phone_verified=FALSE")
    elif verified == 'repeated_ip':  where.append("l.ip_count > 1")
    elif verified == 'repeated_cid': where.append("l.cid_count > 0")
    elif verified == 'kyc_id':       where.append("l.kyc_id_uploaded=TRUE")
    elif verified == 'kyc_address':  where.append("l.kyc_address_uploaded=TRUE")
    if kyc == 'verified':            where.append("l.kyc_status = 'verified'")
    if agent:
        au = db.execute(text("SELECT id FROM users WHERE full_name ILIKE :a LIMIT 1"), {"a": f"%{agent}%"}).fetchone()
        if au:
            where.append("l.assigned_agent_id = :aid")
            params["aid"] = au[0]
        else:
            # not a current staff member — treat as a TradeSoft legacy sales-agent name
            where.append("l.legacy_sales_agent ILIKE :legacy_agent")
            params["legacy_agent"] = f"%{agent}%"
    if ib:
        # a lead's IB = the IB of the client it matched to (matched_login -> clients.agent -> ibs)
        where.append("""l.matched_login IN (
            SELECT c.login FROM clients c JOIN ibs ibx ON ibx.agent_id = c.agent
            WHERE ibx.name ILIKE :ib)""")
        params["ib"] = f"%{ib}%"

    # Verification filter
    if verified == 'verified':
        where.append("l.is_verified=TRUE")
    elif verified == 'phone_only':
        where.append("l.phone_verified=TRUE AND l.email_verified=FALSE")
    elif verified == 'email_only':
        where.append("l.email_verified=TRUE AND l.phone_verified=FALSE")
    elif verified == 'unverified':
        where.append("l.is_verified=FALSE AND l.phone_verified=FALSE")
    elif verified == 'repeated_ip':
        where.append("l.ip_count > 1")
    elif verified == 'repeated_cid':
        where.append("l.cid_count > 0")

    # Period filter — bound on the IRAQI (Baghdad, UTC+3) calendar so the buckets match the dates
    # the list actually shows (the frontend renders created_at in the viewer's local Iraq time).
    # Ticket 193: with UTC bounds a lead created e.g. 19/7 23:49 UTC (= 20/7 02:49 Baghdad) fell in
    # "last week" by SQL yet displayed as 20/7, so "last week" leaked this-week rows. Comparing the
    # lead's Baghdad wall-clock against Baghdad-anchored week/day/month bounds keeps the two in sync.
    if period != 'all_time':
        L = "(l.created_at AT TIME ZONE 'Asia/Baghdad')"          # lead time as Baghdad wall-clock
        N = "(NOW() AT TIME ZONE 'Asia/Baghdad')"                 # 'now' as Baghdad wall-clock
        period_sql = {
            'today':      f"{L} >= date_trunc('day', {N}) AND {L} < date_trunc('day', {N}) + interval '1 day'",
            'yesterday':  f"{L} >= date_trunc('day', {N}) - interval '1 day' AND {L} < date_trunc('day', {N})",
            'this_week':  f"{L} >= date_trunc('week', {N})",
            'last_week':  f"{L} >= date_trunc('week', {N}) - interval '1 week' AND {L} < date_trunc('week', {N})",
            'this_month': f"{L} >= date_trunc('month', {N})",
            'last_month': f"{L} >= date_trunc('month', {N}) - interval '1 month' AND {L} < date_trunc('month', {N})",
            'this_year':  f"{L} >= date_trunc('year', {N})",
            'last_year':  f"{L} >= date_trunc('year', {N}) - interval '1 year' AND {L} < date_trunc('year', {N})",
        }
        if period in period_sql:
            where.append(period_sql[period])

    # Role-based visibility: agent -> own leads; manager -> own + team; director/admin -> all.
    # section='leads' honors a restricted leader; own=1 = the "My own data" toggle.
    _scope = rbac.scope_agent_ids(db, current_user, section="leads", own=bool(own))
    if _scope is not None:
        if _scope:
            where.append("l.assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where.append("FALSE")

    # "Connected (last 7d)" tab: only leads this scope contacted in the last week, newest contact first.
    # last_call_at is stamped by /leads/{id}/log-call, so this is exactly "who we connected with".
    if connected:
        where.append("l.last_call_at IS NOT NULL AND l.last_call_at >= NOW() - INTERVAL '7 days'")

    wc = " AND ".join(where)
    sort_map = {
        'created_at': 'l.created_at DESC',
        'name':       'l.full_name ASC',
        'status':     'l.status ASC',
        'country':    'l.country ASC',
    }
    sort_map['score'] = 'l.score DESC NULLS LAST'
    sort_map['network'] = 'COALESCE(l.network_score,0) DESC, l.created_at DESC'
    # Last login (opt-in sort only): correlated on the lead's own account so the common paths pay nothing.
    sort_map['last_login'] = ("(SELECT MAX(ai.last_seen) FROM account_identifiers ai "
                              "WHERE ai.login = COALESCE(l.converted_login, l.matched_login)) DESC NULLS LAST")
    # in the Connected tab, ALWAYS sort by most-recent contact (the user's spec: "sorted by last action")
    order = 'l.last_call_at DESC NULLS LAST' if connected else sort_map.get(sort, 'l.created_at DESC')
    # No pinning - pure sort. Recaptures rise on Priority via their +50 score.

    total = db.execute(text(f"SELECT COUNT(*) FROM leads l WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT l.id, l.full_name, l.phone, l.email, l.country, l.city,
               l.language, l.source, l.platform, l.campaign_name, l.ad_set_name, l.ad_name,
               l.status, l.assigned_agent_id, u.full_name as agent_name,
               l.kyc_status, l.notes, l.call_attempts, l.last_call_at,
               l.converted_login, l.converted_at,
               l.utm_source, l.utm_medium, l.utm_campaign,
               l.created_at, l.updated_at,
               l.meta_lead_id, l.google_lead_id, l.meta_stage, l.meta_platform, l.meta_quality,
               l.match_badge, l.matched_login, l.score,
               l.phone_verified, l.email_verified, l.is_verified,
               l.ip_address, l.ip_count, l.cid, l.cid_count,
               l.bonus_eligible, l.bonus_claimed, l.bonus_blocked_reason,
               l.kyc_id_uploaded, l.kyc_id_verified,
               l.kyc_address_uploaded, l.kyc_address_verified, l.kyc_notes,
               -- IB column: the referring IB. customers.ib (text, e.g. 'Iraq-MQL5') is the
               -- authoritative referrer; fall back to the IB resolved via a matched client's agent.
               COALESCE(NULLIF(TRIM(cust.ib),''), ibx.name) AS ib_name, l.meta_created, l.last_call_outcome,
               COALESCE(l.is_archived, FALSE) AS is_archived,
               (l.password_hash IS NOT NULL) AS has_password,
               l.date_of_birth, l.customer_no, l.legacy_sales_agent, l.stage,
               -- OLD record (the client this recapture lead matched): show its ORIGINAL reg date,
               -- name and deposits so the desk can SEE who this really is (58,59,60)
               mc.name, mc.reg_date, mc.total_deposits,
               l.training_need, tr.stage AS training_stage
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_agent_id
        LEFT JOIN clients mc ON mc.login = l.matched_login
        LEFT JOIN training_requests tr ON tr.lead_id = l.id
        LEFT JOIN ibs ibx ON ibx.agent_id = mc.agent
        LEFT JOIN customers cust ON cust.customer_no = l.customer_no
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    # canonical network score (0-10) — the SAME column every page reads (build_network_scores.py).
    # fetched separately to avoid disturbing this query's positional row indexing.
    _lids = [r[0] for r in rows]
    netmap = {}
    if _lids:
        netmap = {x[0]: int(x[1] or 0) for x in db.execute(text(
            "SELECT id, COALESCE(network_score,0) FROM leads WHERE id = ANY(:l)"),
            {"l": _lids}).fetchall()}

    # #183: last login (last time seen online by the MT5 bridge) for verified leads that already
    # have a matched/converted trading account. Lets the desk spot verified accounts that still
    # log in — the ones worth a deposit call — vs. verified-years-ago accounts that went cold.
    _llmap = {}
    _login_by_lead = {r[0]: (r[19] or r[32]) for r in rows if (r[19] or r[32])}
    if _login_by_lead:
        _logins = list({v for v in _login_by_lead.values() if v})
        _ls = {x[0]: x[1] for x in db.execute(text(
            "SELECT login, MAX(last_seen) FROM account_identifiers "
            "WHERE login = ANY(:l) AND last_seen IS NOT NULL GROUP BY login"),
            {"l": _logins}).fetchall()}
        for _lid, _lg in _login_by_lead.items():
            _v = _ls.get(_lg)
            if _v:
                _llmap[_lid] = _v

    # KPIs
    kpis = db.execute(text(f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status='new') as new_leads,
            COUNT(*) FILTER (WHERE status='contacted') as contacted,
            COUNT(*) FILTER (WHERE status='callback') as callback,
            COUNT(*) FILTER (WHERE status='converted') as converted,
            COUNT(*) FILTER (WHERE status='dead') as dead,
            COUNT(*) FILTER (WHERE lower(source)='facebook') as from_facebook,
            COUNT(*) FILTER (WHERE lower(source)='instagram') as from_instagram,
            COUNT(*) FILTER (WHERE lower(source) IN ('messenger','audience_network')) as from_meta_other,
            COUNT(*) FILTER (WHERE lower(source)='google') as from_google
        FROM leads l WHERE {wc}
    """), params).fetchone()

    return {
        "leads": [{
            "id": r[0], "full_name": r[1] or "", "phone": r[2] or "",
            "email": r[3] or "", "country": r[4] or "", "city": r[5] or "",
            "language": r[6] or "", "source": r[7] or "manual",
            "platform": r[8] or "manual",
            "campaign_name": r[9] or "", "ad_set_name": r[10] or "",
            "ad_name": r[11] or "", "status": r[12] or "new",
            "assigned_agent_id": r[13], "agent_name": r[14] or "",
            "kyc_status": r[15] or "pending", "notes": r[16] or "",
            "call_attempts": r[17] or 0,
            "last_call_at": str(r[18]) if r[18] else "",
            "last_call_outcome": (r[51] or ""),
            "converted_login": r[19],
            "converted_at": str(r[20]) if r[20] else "",
            "last_login": (_llmap.get(r[0]).isoformat() if _llmap.get(r[0]) else ""),  # #183
            "utm_source": r[21] or "", "utm_medium": r[22] or "",
            "utm_campaign": r[23] or "",
            "created_at": str(r[24]) if r[24] else "",
            "updated_at": str(r[25]) if r[25] else "",
            "meta_lead_id": r[26] or "", "google_lead_id": r[27] or "",
            "meta_stage": r[28] or "", "meta_platform": r[29] or "",
            "meta_stage_status": r[30] or "", "meta_quality": r[30] or "",
            "match_badge": r[31] or "", "matched_login": r[32], "score": r[33] or 0,
            "network_score": netmap.get(r[0], 0),   # 0-10 canonical (build_network_scores.py)
            "phone_verified": r[34] or False, "email_verified": r[35] or False,
            "is_verified": r[36] or False,
            "ip_address": r[37] or "", "ip_count": r[38] or 0,
            "cid": r[39] or "", "cid_count": r[40] or 0,
            "bonus_eligible": r[41], "bonus_claimed": r[42] or False,
            "bonus_blocked_reason": r[43] or "",
            "kyc_id_uploaded": r[44] or False,
            "kyc_id_verified": r[45] or False,
            "kyc_address_uploaded": r[46] or False,
            "kyc_address_verified": r[47] or False,
            "kyc_notes": r[48] or "",
            "ib_name": r[49] or "",
            "meta_created": str(r[50]) if r[50] else "",
            # tail columns by EXPLICIT index (51..57) — negative indexing drifted twice
            # when columns were appended; SELECT order: ...ib_name(49), meta_created(50),
            # last_call_outcome(51), is_archived(52), has_password(53), date_of_birth(54),
            # customer_no(55), legacy_sales_agent(56), stage(57)
            "is_archived": bool(r[52]),
            "has_password": bool(r[53]),
            "date_of_birth": str(r[54]) if r[54] else "",
            "customer_no": (r[55] or ""),
            "legacy_sales_agent": (r[56] or ""),
            "stage": (r[57] or "New Lead"),
            # the matched OLD record (recapture): original registration date + who they already are
            "matched_name": (r[58] or ""),
            "matched_reg_date": str(r[59]) if r[59] else "",
            "matched_deposits": float(r[60]) if r[60] is not None else 0.0,
            "training_need": (r[61] or ""),          # sales-chosen level (beginner / needs_improvement / …)
            "training_stage": (r[62] or ""),         # training team's current stage on the board
        } for r in rows],
        "total": total,
        "kpis": {
            "total": kpis[0], "new": kpis[1], "contacted": kpis[2],
            "callback": kpis[3], "converted": kpis[4], "dead": kpis[5],
            "from_facebook": kpis[6], "from_instagram": kpis[7],
            "from_meta_other": kpis[8], "from_google": kpis[9],
        }
    }


@router.post("")
def create_lead(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    import re as _re2
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    p9 = _re2.sub(r"\D", "", phone)[-9:] if len(_re2.sub(r"\D", "", phone)) >= 9 else ""

    # RULE 1: a lead must be reachable — at least one of phone / email.
    if not email and not phone:
        raise HTTPException(status_code=400, detail="At least a phone number or an email is required")

    # RULE 2: uniqueness across ALL of TNFX (leads + clients). Whoever first registered this
    # person keeps them — sales can't create a duplicate lead to grab an existing contact.
    def _agent_name(uid):
        if not uid:
            return None
        r = db.execute(text("SELECT full_name FROM users WHERE id=:i"), {"i": uid}).fetchone()
        return r[0] if r else None

    dup = db.execute(text("""
        SELECT id, full_name, assigned_agent_id, legacy_sales_agent FROM leads
        WHERE (:em <> '' AND lower(TRIM(email)) = :em)
           OR (:p9 <> '' AND right(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) = :p9)
        LIMIT 1"""), {"em": email, "p9": p9}).fetchone()
    if dup:
        owner = _agent_name(dup[2]) or (dup[3] or "unassigned")
        raise HTTPException(status_code=409,
            detail=f"Already exists in TNFX as lead #{dup[0]} ({dup[1] or 'no name'}) — sales agent: {owner}")

    dupc = db.execute(text("""
        SELECT login, name, assigned_agent_id, legacy_sales_agent FROM clients
        WHERE (:em <> '' AND lower(TRIM(email)) = :em)
           OR (:p9 <> '' AND right(regexp_replace(COALESCE(phone,''),'[^0-9]','','g'),9) = :p9)
        LIMIT 1"""), {"em": email, "p9": p9}).fetchone()
    if dupc:
        owner = _agent_name(dupc[2]) or (dupc[3] or "unassigned")
        raise HTTPException(status_code=409,
            detail=f"Already a TNFX client — account #{dupc[0]} ({dupc[1] or 'no name'}) — sales agent: {owner}")

    # RULE 3: a sales agent can only create leads for THEMSELVES (managers/admins may assign).
    agent_id = data.get("assigned_agent_id") or None
    if getattr(current_user, "role", "") == "sales_agent":
        agent_id = current_user.id

    result = db.execute(text("""
        INSERT INTO leads (full_name, phone, email, country, city, language,
                           source, platform, campaign_name, status, stage, assigned_agent_id, notes, created_at, updated_at)
        VALUES (:name, :phone, :email, :country, :city, :lang,
                :source, :platform, :campaign, :status, 'New Lead', :agent, :notes, NOW(), NOW())
        RETURNING id
    """), {
        "name": data.get("full_name",""), "phone": phone,
        "email": email, "country": data.get("country",""),
        "city": data.get("city",""), "lang": data.get("language","ar"),
        "source": data.get("source","manual"), "platform": data.get("platform","manual"),
        "campaign": data.get("campaign_name",""), "status": data.get("status","new"),
        "agent": agent_id, "notes": data.get("notes",""),
    })
    db.commit()
    return {"id": result.fetchone()[0], "message": "Lead created"}


@router.patch("/{lead_id}")
def update_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    allowed = ["full_name","phone","email","country","city","status","stage","assigned_agent_id","notes","kyc_status","call_attempts","training_need"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return {"message": "Nothing to update"}
    # RBAC (go-live hardening): a scoped agent may only edit their OWN leads, and only
    # managers/admins may (re)assign a lead to an agent — otherwise any agent could
    # silently steal leads by PATCHing assigned_agent_id.
    import rbac
    # Changing a lead's sales agent is restricted to admins and Rahaf ONLY (desk rule Jul 2026).
    if "assigned_agent_id" in updates and not rbac.may_reassign_agent(current_user):
        raise HTTPException(status_code=403, detail="Only admins can change a lead's sales agent")
    # A lead's IDENTITY/CONTACT info (name/phone/email/country/city/KYC) may only be edited by
    # supervisory/ops roles — a plain agent may still change stage/notes/calls but NOT the lead's
    # core data (ticket #191, critical security). Workflow fields stay editable by the scoped agent.
    _LEAD_INFO_FIELDS = {"full_name", "phone", "email", "country", "city", "kyc_status"}
    if (_LEAD_INFO_FIELDS & updates.keys()) and not rbac.may_edit_lead_info(db, current_user):
        raise HTTPException(status_code=403, detail="You are not permitted to edit lead information")
    scope = rbac.scope_agent_ids(db, current_user)
    if scope is not None:
        owner = db.execute(text("SELECT assigned_agent_id FROM leads WHERE id=:id"),
                           {"id": lead_id}).scalar()
        if owner is not None and owner not in scope:
            raise HTTPException(status_code=403, detail="Not your lead")
    set_clause = ", ".join([f"{k}=:{k}" for k in updates])
    updates["id"] = lead_id
    updates["updated_at"] = datetime.utcnow()
    db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=:updated_at WHERE id=:id"), updates)
    db.commit()
    # When sales set a training need, mirror it onto the Training board so the training team picks it up.
    if updates.get("training_need"):
        lr = db.execute(text("SELECT full_name, phone, country, customer_no FROM leads WHERE id=:i"), {"i": lead_id}).fetchone()
        if lr:
            db.execute(text("""INSERT INTO training_requests
                (lead_id, customer_no, subject_name, phone, country, source, stage, level, requested_by, requested_by_name)
                VALUES (:lid,:cn,:nm,:ph,:co,'lead','requested',:lv,:by,:byn)
                ON CONFLICT (lead_id) WHERE lead_id IS NOT NULL
                DO UPDATE SET level=EXCLUDED.level, updated_at=NOW(), updated_by_name=EXCLUDED.requested_by_name"""),
                {"lid": lead_id, "cn": lr[3], "nm": lr[0], "ph": lr[1], "co": lr[2],
                 "lv": updates["training_need"], "by": current_user.id,
                 "byn": (getattr(current_user, "full_name", None) or getattr(current_user, "email", None) or "Staff")})
            db.commit()
    return {"message": "Updated"}


import re as _re

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.patch("/{lead_id}/contact")
def update_lead_contact(lead_id: int, data: dict, db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    """Edit a lead's contact details — email, phone, date of birth and (optionally) portal password (#90, Nuha).

    Body: {email?, phone?, date_of_birth?, password?}. All optional but at least one required.
    - email validated against a basic pattern (blank allowed to clear).
    - phone normalised to '+'/digits only; must be >=6 digits if provided.
    - date_of_birth: 'YYYY-MM-DD' string -> leads.date_of_birth (blank/"" clears it).
    - password (if a non-empty string) is bcrypt-hashed into leads.password_hash
      (column added additively this session). Min length 6.
    """
    # Editing a lead's contact details (incl. portal password) is lead-information editing —
    # restricted to supervisory/ops roles, not plain sales agents (ticket #191, critical security).
    import rbac
    if not rbac.may_edit_lead_info(db, current_user):
        raise HTTPException(status_code=403, detail="You are not permitted to edit lead information")
    # a scoped supervisor may still only touch leads within their own team book
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        _owner = db.execute(text("SELECT assigned_agent_id FROM leads WHERE id=:id"),
                            {"id": lead_id}).scalar()
        if _owner is not None and _owner not in _scope:
            raise HTTPException(status_code=403, detail="Not your lead")
    updates: dict = {}

    # Date of birth — accept YYYY-MM-DD (blank clears). Validate the format/range.
    if "date_of_birth" in data:
        dob = (data.get("date_of_birth") or "").strip()
        if dob:
            if not _re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
                return {"error": "Date of birth must be YYYY-MM-DD"}
            try:
                _y, _m, _d = (int(x) for x in dob.split("-"))
                datetime(_y, _m, _d)  # validates real calendar date
                if _y < 1900 or _y > datetime.utcnow().year:
                    return {"error": "Date of birth year is out of range"}
            except ValueError:
                return {"error": "Date of birth is not a valid date"}
            updates["date_of_birth"] = dob
        else:
            updates["date_of_birth"] = None

    # Email — allow clearing with "" ; validate when non-empty
    if "email" in data:
        email = (data.get("email") or "").strip()
        if email and not _EMAIL_RE.match(email):
            return {"error": "Invalid email address"}
        updates["email"] = email or None

    # Phone — keep leading + and digits only
    if "phone" in data:
        raw = (data.get("phone") or "").strip()
        if raw:
            cleaned = _re.sub(r"[^\d+]", "", raw)
            digits = _re.sub(r"\D", "", cleaned)
            if len(digits) < 6:
                return {"error": "Phone number looks too short"}
            updates["phone"] = cleaned
        else:
            updates["phone"] = None

    # Password — bcrypt-hash into leads.password_hash (only if a value is supplied)
    if data.get("password"):
        pw = str(data.get("password"))
        if len(pw) < 6:
            return {"error": "Password must be at least 6 characters"}
        from auth import get_password_hash
        updates["password_hash"] = get_password_hash(pw)

    if not updates:
        return {"message": "Nothing to update"}

    set_clause = ", ".join([f"{k}=:{k}" for k in updates])
    updates["id"] = lead_id
    db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=NOW() WHERE id=:id"), updates)
    db.commit()
    changed = [k for k in updates if k != "id"]
    return {"message": "Contact updated", "updated": changed,
            "has_password": "password_hash" in changed}


_CALL_COLS_OK = False


@router.post("/{lead_id}/call")
def log_call(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    note = data.get("note","Called")
    # Notes are stored one-per-line (entries joined by \n) and the UI splits on \n to list them.
    # So a pasted MULTI-LINE note would be split into several rows (the 2nd+ losing its timestamp).
    # Collapse any newlines inside a single note into " / " so each note stays ONE entry (#162).
    import re
    note = re.sub(r'\s*[\r\n]+\s*', ' / ', str(note)).strip()
    # Format comment with agent name, timestamp, action
    from datetime import datetime
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    formatted_note = f"[{timestamp}] {current_user.full_name}: {note}"
    
    # last_call_by / last_call_at were referenced but MISSING → every note post 500'd.
    # Add them ONCE per process (catalog-check first — never take the ACCESS EXCLUSIVE lock on the
    # hot `leads` table on a no-op ALTER; that's the documented outage foot-gun).
    global _CALL_COLS_OK
    if not _CALL_COLS_OK:
        try:
            miss = db.execute(text("""SELECT 2 - COUNT(*) FROM information_schema.columns
                WHERE table_name='leads' AND column_name IN ('last_call_by','last_call_at')""")).scalar()
            if miss:
                db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_call_by INTEGER"))
                db.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_call_at TIMESTAMPTZ"))
                db.commit()
            _CALL_COLS_OK = True
        except Exception:
            db.rollback()
    db.execute(text("""
        UPDATE leads SET
            call_attempts = COALESCE(call_attempts, 0) + 1,
            last_call_at = NOW(),
            last_call_by = :uid,
            notes = CASE
                WHEN notes IS NULL OR notes = '' THEN :note
                ELSE notes || E'\n' || :note
            END,
            updated_at = NOW()
        WHERE id = :id
    """), {"uid": current_user.id, "note": formatted_note, "id": lead_id})
    db.commit()
    # #222: if someone OTHER than the lead's assigned agent adds a comment, email the assigned agent.
    try:
        import comment_notify
        comment_notify.notify_cross_agent_comment(db, "lead", lead_id, current_user, note)
    except Exception:
        pass
    # the desk working an archived lead = re-engagement -> bring it back to the active list
    try:
        import reactivation
        reactivation.reactivate_lead(db, lead_id, via="action")
    except Exception:
        db.rollback()
    return {"message": "Call logged", "note": formatted_note}


@router.post("/{lead_id}/send-verification-email")
def send_lead_verification_email(lead_id: int, db: Session = Depends(get_db),
                                 current_user: models.User = Depends(get_current_user)):
    """#294: send a lead a TNFX-branded 'confirm your email' request straight from the new CRM
    (the desk had to fall back to the old CRM for this). Mirrors the KYC console's verification
    email but keys off leads.email instead of a registration."""
    row = db.execute(text("SELECT full_name, email FROM leads WHERE id=:l"), {"l": lead_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    name, email = row[0], (row[1] or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "No email address on file for this lead."}
    import email_send
    if not email_send.configured():
        return {"ok": False, "error": "Email is not configured on the server yet."}
    ok = email_send.send(
        email, "Confirm your TNFX email address",
        "Please confirm your email address by logging in at https://my1.tnfx.co",
        body_html=email_send.verify_email_html(name, verify_url="https://my1.tnfx.co/portal/"))
    return {"ok": bool(ok), "sent_to": email}


# A lead note is editable/deletable by its AUTHOR for 60 minutes; then it freezes (#242 —
# parity with client comments). Lead notes are stored as "[YYYY-MM-DD HH:MM] Name: text" lines.
LEAD_NOTE_EDIT_WINDOW_MIN = 60
_NOTE_LINE_RE = None  # compiled lazily


@router.post("/{lead_id}/note-edit")
def edit_lead_note(lead_id: int, data: dict, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Edit or delete ONE of the caller's OWN note lines within 60 min of posting (#242).
    Body: {original: <the exact stored line>, note: <new text, or empty to DELETE>}."""
    import re
    original = str(data.get("original") or "").strip()
    new_text = re.sub(r'\s*[\r\n]+\s*', ' / ', str(data.get("note") or "")).strip()
    m = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*(.+?):\s(.*)$", original, re.S)
    if not m:
        raise HTTPException(status_code=400, detail="Note not found")
    ts_s, author = m.group(1), m.group(2).strip()
    if author != (current_user.full_name or "").strip():
        raise HTTPException(status_code=403, detail="You can only edit your own notes")
    try:
        ts = datetime.strptime(ts_s, "%Y-%m-%d %H:%M")     # stored in UTC (log_call uses utcnow)
    except ValueError:
        raise HTTPException(status_code=400, detail="Note not found")
    if (datetime.utcnow() - ts).total_seconds() > LEAD_NOTE_EDIT_WINDOW_MIN * 60:
        raise HTTPException(status_code=403, detail="This note can no longer be edited (60-minute window)")
    notes = db.execute(text("SELECT notes FROM leads WHERE id=:id"), {"id": lead_id}).scalar()
    lines = [ln for ln in str(notes or "").split("\n")]
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.strip() == original)
    except StopIteration:
        raise HTTPException(status_code=404, detail="Note not found")
    if new_text:
        lines[idx] = f"[{ts_s}] {author}: {new_text}"
        action = "edited"
    else:
        lines.pop(idx)
        action = "deleted"
    db.execute(text("UPDATE leads SET notes=:n, updated_at=NOW() WHERE id=:id"),
               {"n": "\n".join(lines), "id": lead_id})
    db.commit()
    return {"message": f"Note {action}", "notes": "\n".join(lines)}


@router.post("/{lead_id}/convert")
def convert_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    login = data.get("login")
    db.execute(text("""
        UPDATE leads SET status='converted', converted_login=:login,
        converted_at=NOW(), updated_at=NOW() WHERE id=:id
    """), {"login": login, "id": lead_id})
    db.commit()
    return {"message": "Lead converted"}


@router.get("/{lead_id}/trading-accounts")
def lead_trading_accounts(lead_id: int, db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Trading account(s) belonging to a VERIFIED/matched lead. READ-ONLY.

    A lead links to a client by matched_login (leads.matched_login -> clients.login) or,
    failing that, by phone. A person's accounts are the clients rows sharing the same phone
    (same aggregation the Clients list uses). Returns up to 10 accounts, richest first.
    Empty list when the lead has no match / no accounts.
    """
    import re as _re_ta
    accounts: list = []
    try:
        row = db.execute(text(
            "SELECT matched_login, converted_login, phone FROM leads WHERE id = :id"),
            {"id": lead_id}).fetchone()
        if not row:
            return {"trading_accounts": []}
        matched_login = row[0] or row[1]           # matched client login (may be None)
        phone = row[2] or ""
        p9 = _re_ta.sub(r"\D", "", phone)[-9:] if phone else ""
        if matched_login is None and not p9:
            return {"trading_accounts": []}

        rows = db.execute(text("""
            SELECT c.login, c.platform, c.group_name, c.balance
            FROM clients c
            WHERE (:ml IS NOT NULL AND c.login = :ml)
               OR (:p9 <> '' AND right(regexp_replace(COALESCE(c.phone,''),'[^0-9]','','g'),9) = :p9)
            ORDER BY c.balance DESC NULLS LAST
            LIMIT 10
        """), {"ml": matched_login, "p9": p9}).fetchall()
        accounts = [{
            "login": r[0],
            "platform": r[1] or "MT5",
            "group_name": r[2] or "",
            "balance": float(r[3]) if r[3] is not None else 0.0,
        } for r in rows]
    except Exception:
        db.rollback()
        return {"trading_accounts": []}
    return {"trading_accounts": accounts}


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Permanent delete — management only; everyone else archives (go-live hardening:
    # was only blocking sales_agent, letting any other role hard-delete leads).
    if (current_user.role or "").lower() not in ("super_admin", "admin", "director", "sales_manager"):
        raise HTTPException(status_code=403, detail="Only managers/admins can delete leads — archive instead.")
    db.execute(text("DELETE FROM leads WHERE id=:id"), {"id": lead_id})
    db.commit()
    return {"message": "Deleted"}


@router.post("/archive")
def archive_leads(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Bulk archive / unarchive leads (#57). Body: {ids:[...], archived:bool}."""
    ids = data.get("ids") or []
    archived = bool(data.get("archived", True))
    if not ids:
        return {"message": "Nothing to update", "count": 0}
    db.execute(text("UPDATE leads SET is_archived=:a, updated_at=NOW() WHERE id = ANY(:ids)"),
               {"a": archived, "ids": ids})
    db.commit()
    return {"message": "archived" if archived else "unarchived", "archived": archived, "count": len(ids)}


@router.post("/{lead_id}/archive")
def archive_lead(lead_id: int, data: dict | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Archive / unarchive a single lead (#57). Body: {archived:bool} (defaults True)."""
    archived = True if data is None else bool(data.get("archived", True))
    db.execute(text("UPDATE leads SET is_archived=:a, updated_at=NOW() WHERE id=:id"),
               {"a": archived, "id": lead_id})
    db.commit()
    return {"message": "archived" if archived else "unarchived", "archived": archived}


@router.post("/{lead_id}/unarchive")
def unarchive_lead(lead_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Convenience inverse of /{lead_id}/archive (#57) — moves a lead back to the active list."""
    return archive_lead(lead_id, {"archived": False}, db, current_user)


# Lead statuses that count as "not interested" for the bulk-archive convenience (#63).
# The Leads UI maps the 'Not Interested' call outcome to status='dead'.
_NOT_INTERESTED_STATUSES = ("dead", "not_interested", "lost")


@router.post("/archive-not-interested")
def archive_not_interested(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """#63 — bulk-archive every still-active lead marked 'not interested' (status dead/
    not_interested/lost) so the main Leads list stays clean. Respects role visibility:
    agents/managers only archive leads in their own scope. Returns how many moved."""
    where = ["COALESCE(is_archived, FALSE) = FALSE", "status = ANY(:st)"]
    params: dict = {"st": list(_NOT_INTERESTED_STATUSES)}
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where.append("assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where.append("FALSE")
    wc = " AND ".join(where)
    res = db.execute(text(
        f"UPDATE leads SET is_archived=TRUE, updated_at=NOW() WHERE {wc}"), params)
    db.commit()
    return {"message": "archived not-interested leads", "count": res.rowcount or 0}


# Meta webhook
@router.get("/webhook/meta")
def meta_webhook_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
):
    if hub_verify_token == "tnfx_leads_2025" and hub_mode == "subscribe":
        return int(hub_challenge)
    return {"error": "Invalid token"}


@router.post("/webhook/meta")
def meta_webhook_receive(data: dict, db: Session = Depends(get_db)):
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "leadgen":
                    value = change.get("value", {})
                    lead_id = value.get("leadgen_id")
                    form_id = value.get("form_id")
                    # Store raw lead - full data fetched separately
                    db.execute(text("""
                        INSERT INTO leads (meta_lead_id, form_id, source, platform, status, created_at, updated_at)
                        VALUES (:lid, :fid, 'Facebook', 'meta', 'new', NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """), {"lid": str(lead_id), "fid": str(form_id)})
        db.commit()
    except Exception as e:
        print(f"Meta webhook error: {e}")
    return {"status": "ok"}


# ── Verification endpoints ─────────────────────────────────────────────────

@router.post("/{lead_id}/verify")
def verify_lead(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Mark phone/email as verified."""
    updates = {}
    if "phone_verified" in data: updates["phone_verified"] = data["phone_verified"]
    if "email_verified" in data: updates["email_verified"] = data["email_verified"]
    if "is_verified"    in data: updates["is_verified"]    = data["is_verified"]
    if "verification_notes" in data: updates["verification_notes"] = data["verification_notes"]
    
    if updates:
        # Auto-set is_verified if both phone and email verified
        set_clause = ", ".join([f"{k}=:{k}" for k in updates])
        updates["id"] = lead_id
        db.execute(text(f"UPDATE leads SET {set_clause}, updated_at=NOW() WHERE id=:id"), updates)
        db.commit()
    return {"message": "Verification updated"}


@router.post("/{lead_id}/check-ip")
def check_ip(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Check IP address - how many leads/clients use same IP."""
    ip = data.get("ip_address","")
    if not ip:
        return {"error": "No IP provided"}
    
    # Count leads with same IP
    lead_count = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE ip_address=:ip AND id!=:id"
    ), {"ip": ip, "id": lead_id}).scalar() or 0
    
    # Count clients with same IP
    client_count = db.execute(text(
        "SELECT COUNT(*) FROM account_identifiers WHERE identifier_type='ip' AND identifier_value=:ip"
    ), {"ip": ip}).scalar() or 0
    
    total = lead_count + client_count
    
    # Update lead
    db.execute(text("""
        UPDATE leads SET ip_address=:ip, ip_count=:count, updated_at=NOW()
        WHERE id=:id
    """), {"ip": ip, "count": total, "id": lead_id})
    db.commit()
    
    return {
        "ip": ip,
        "lead_count": lead_count,
        "client_count": client_count,
        "total": total,
        "risk": "high" if total > 3 else "medium" if total > 1 else "new"
    }


@router.post("/{lead_id}/check-cid")
def check_cid(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Check CID - how many accounts use same device."""
    cid = data.get("cid","")
    if not cid:
        return {"error": "No CID provided"}
    
    # Count accounts with same CID
    cid_count = db.execute(text("""
        SELECT COUNT(DISTINCT login) FROM account_identifiers
        WHERE identifier_type='cid' AND identifier_value=:cid
    """), {"cid": cid}).scalar() or 0
    
    # Count leads with same CID
    lead_cid_count = db.execute(text(
        "SELECT COUNT(*) FROM leads WHERE cid=:cid AND id!=:id"
    ), {"cid": cid, "id": lead_id}).scalar() or 0
    
    total = cid_count + lead_cid_count
    
    db.execute(text("""
        UPDATE leads SET cid=:cid, cid_count=:count, updated_at=NOW()
        WHERE id=:id
    """), {"cid": cid, "count": total, "id": lead_id})
    db.commit()
    
    return {
        "cid": cid,
        "existing_accounts": cid_count,
        "other_leads": lead_cid_count,
        "total": total,
        "risk": "high" if total > 0 else "new"
    }


# ── Client Dashboard endpoints ─────────────────────────────────────────────

from fastapi import APIRouter as _AR
from fastapi import HTTPException as _HTTPException
from fastapi import Depends as _Depends
from auth import oauth2_scheme as _oauth2_scheme
from database import settings as _settings
from jose import jwt as _jwt, JWTError as _JWTError

client_router = _AR(prefix="/client-dashboard", tags=["Client Dashboard"])


def owns_login(login: int, token: str = _Depends(_oauth2_scheme)):
    """Authorize a /client-dashboard/{login} call. These endpoints were previously PUBLIC —
    any anonymous caller could pass any login and read that client's balance/deposits/PnL.
    Now: a valid token is required; a CLIENT token may only access its own login; a STAFF
    token may view any client. Raises 401 (bad/absent token) or 403 (not your account)."""
    _401 = _HTTPException(status_code=401, detail="Could not validate credentials",
                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = _jwt.decode(token, _settings.SECRET_KEY, algorithms=[_settings.ALGORITHM])
    except _JWTError:
        raise _401
    user_type = payload.get("user_type")
    if user_type == "staff":
        return True   # staff may view any client dashboard
    if user_type == "client":
        tok_login = payload.get("login")
        if tok_login is not None and int(tok_login) == int(login):
            return True
        raise _HTTPException(status_code=403, detail="That account is not yours.")
    raise _401


@client_router.get("/kpis/{login}")
def get_client_kpis(login: int, db: Session = Depends(get_db), _auth: bool = Depends(owns_login)):
    """Client-facing KPIs for their own dashboard."""
    client = db.execute(text("""
        SELECT login, name, balance, equity, total_deposits, total_withdrawals,
               credit, margin_level, group_name, reg_date
        FROM clients WHERE login=:l
    """), {"l": login}).fetchone()
    
    if not client:
        return {"error": "Not found"}
    
    # Open positions count
    open_pos = db.execute(text("""
        SELECT COUNT(*) FROM deals 
        WHERE login=:l AND deal_type='trade' AND entry=0
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
    """), {"l": login}).scalar() or 0
    
    # Recent trades
    recent_trades = db.execute(text("""
        SELECT COUNT(*), COALESCE(SUM(profit),0)
        FROM deals WHERE login=:l AND deal_type='trade' AND entry=1
        AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400*30
    """), {"l": login}).fetchone()
    
    return {
        "login": login,
        "name": client[1],
        "balance": float(client[2] or 0),
        "equity": float(client[3] or client[2] or 0),
        "total_deposits": float(client[4] or 0),
        "total_withdrawals": float(client[5] or 0),
        "credit": float(client[6] or 0),
        "margin_level": float(client[7] or 0),
        "group": client[8] or "",
        "open_positions": open_pos,
        "monthly_trades": recent_trades[0] or 0,
        "monthly_pnl": float(recent_trades[1] or 0),
        "reg_date": str(client[9] or ""),
    }


@client_router.post("/bonus-check/{login}")
def check_welcome_bonus(login: int, data: dict, db: Session = Depends(get_db),
                        _auth: bool = Depends(owns_login)):
    """Check if client is eligible for welcome bonus."""
    cid = data.get("cid","")
    ip  = data.get("ip","")
    
    # Get bonus rule
    rule = db.execute(text(
        "SELECT bonus_amount, max_per_cid, max_per_ip FROM welcome_bonus_rules WHERE active=TRUE LIMIT 1"
    )).fetchone()
    if not rule:
        return {"eligible": False, "reason": "No bonus program active"}
    
    bonus_amount, max_per_cid, max_per_ip = rule
    
    # Check if already claimed
    already = db.execute(text(
        "SELECT COUNT(*) FROM transactions WHERE login=:l AND tx_type='bonus_deposit'"
    ), {"l": login}).scalar() or 0
    if already > 0:
        return {"eligible": False, "reason": "Welcome bonus already claimed", "bonus_amount": 0}
    
    # Check CID uniqueness
    if cid:
        cid_count = db.execute(text("""
            SELECT COUNT(DISTINCT login) FROM account_identifiers
            WHERE identifier_type='cid' AND identifier_value=:cid AND login!=:l
        """), {"cid": cid, "l": login}).scalar() or 0
        if cid_count >= max_per_cid:
            return {
                "eligible": False,
                "reason": "This device has already been used to claim a welcome bonus. You can enjoy our deposit bonus instead!",
                "bonus_amount": 0,
                "show_deposit_bonus": True
            }
    
    # Check IP
    if ip:
        ip_count = db.execute(text("""
            SELECT COUNT(DISTINCT login) FROM account_identifiers
            WHERE identifier_type='ip' AND identifier_value=:ip AND login!=:l
        """), {"ip": ip, "l": login}).scalar() or 0
        if ip_count >= max_per_ip:
            return {
                "eligible": False,
                "reason": "Too many accounts from your network have claimed this bonus. You can enjoy our deposit bonus!",
                "bonus_amount": 0,
                "show_deposit_bonus": True
            }
    
    # Eligible!
    return {
        "eligible": True,
        "bonus_amount": bonus_amount,
        "reason": "You are eligible for the welcome bonus!",
        "next_step": "Login to your trading account to activate your bonus",
        "show_deposit_bonus": False
    }

@router.get("/verified")
def get_verified_accounts(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search:    str = Query(""),
    country:   str = Query(""),
    sort:      str = Query("date"),  # date | name | country | login
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Verified Accounts — KYC-approved accounts that have a trading-account number (#95, Nuha).

    Replaces the old "Approved & funded" tab. Lists trading accounts (clients) that are
    BOTH:
      (1) APPROVED / KYC-verified  ->  clients.kyc_status = 'verified'
      (2) ASSIGNED A TRADING ACCOUNT NUMBER (a login)  ->  clients.login IS NOT NULL
    REGARDLESS of whether they deposited (accounts that deposit move to the Clients list
    automatically, so a deposit filter is intentionally NOT applied). Joins back to a
    matched lead (leads.matched_login / converted_login) when one exists so the desk can
    see which lead the account came from.
    """
    where = ["c.kyc_status = 'verified'", "c.login IS NOT NULL"]
    params: dict = {}
    # go-live hardening: scope to the caller's book (agents were seeing the whole base)
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        where.append("c.assigned_agent_id = ANY(:rbac_ids)")
        params["rbac_ids"] = _scope or [-1]

    if search:
        where.append("(c.name ILIKE :s OR CAST(c.login AS TEXT) ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s)")
        params["s"] = f"%{search}%"
    if country:
        where.append("c.country = :country")
        params["country"] = country

    wc = " AND ".join(where)
    sort_map = {
        "date":    "c.reg_date DESC NULLS LAST",
        "name":    "c.name ASC",
        "country": "c.country ASC, c.reg_date DESC",
        "login":   "c.login ASC",
    }
    order = sort_map.get(sort, "c.reg_date DESC NULLS LAST")

    total = db.execute(text(f"SELECT COUNT(*) FROM clients c WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.country, c.platform, c.kyc_status, c.reg_date,
               l.id AS lead_id, l.full_name AS lead_name, l.match_badge, l.source,
               EXISTS (SELECT 1 FROM transactions t WHERE t.login = c.login AND t.tx_type='deposit') AS has_deposit
        FROM clients c
        LEFT JOIN leads l ON l.matched_login = c.login OR l.converted_login = c.login
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    return {
        "accounts": [{
            "login": r[0], "name": r[1] or "", "country": r[2] or "",
            "platform": r[3] or "MT5", "kyc_status": r[4] or "",
            "reg_date": str(r[5]) if r[5] else "",
            "lead_id": r[6], "lead_name": r[7] or "",
            "match_badge": r[8] or "", "source": r[9] or "",
            "has_deposit": bool(r[10]),
        } for r in rows],
        "total": total,
        "kpis": {
            "accounts": total,
        },
    }


@router.get("/funded")
def get_funded_accounts(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search:    str = Query(""),
    country:   str = Query(""),
    approved_only: str = Query("1"),   # '1' = require KYC-approved; '' = any deposited account
    sort:      str = Query("deposits"),  # deposits | name | country | date
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Approved & funded accounts — converted leads / funded clients (#95, Nuha).

    Lists trading accounts (clients) that have ACTUALLY DEPOSITED (a real deposit
    transaction in `transactions`, the deposit truth used across the CRM) and,
    when approved_only=1, are also KYC-APPROVED (clients.kyc_status='verified').
    Joins back to a matched lead (leads.matched_login / converted_login) when one
    exists so the desk can see which lead converted, but the row is the funded
    account itself. Aggregates the deposit total + first-deposit date per login.
    """
    where = ["EXISTS (SELECT 1 FROM transactions t WHERE t.login = c.login AND t.tx_type='deposit')"]
    params: dict = {}
    # go-live hardening: scope to the caller's book (agents were seeing the whole base)
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        where.append("c.assigned_agent_id = ANY(:rbac_ids)")
        params["rbac_ids"] = _scope or [-1]

    if approved_only == "1":
        where.append("c.kyc_status = 'verified'")
    if search:
        where.append("(c.name ILIKE :s OR CAST(c.login AS TEXT) ILIKE :s OR c.email ILIKE :s OR c.phone ILIKE :s)")
        params["s"] = f"%{search}%"
    if country:
        where.append("c.country = :country")
        params["country"] = country

    wc = " AND ".join(where)
    sort_map = {
        "deposits": "total_deposits DESC NULLS LAST",
        "name":     "c.name ASC",
        "country":  "c.country ASC, total_deposits DESC",
        "date":     "first_deposit DESC NULLS LAST",
    }
    order = sort_map.get(sort, "total_deposits DESC NULLS LAST")

    total = db.execute(text(f"SELECT COUNT(*) FROM clients c WHERE {wc}"), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT c.login, c.name, c.country, c.platform, c.kyc_status, c.reg_date,
               dep.total_deposits, dep.first_deposit, dep.deposit_count,
               l.id AS lead_id, l.full_name AS lead_name, l.match_badge, l.source
        FROM clients c
        JOIN LATERAL (
            SELECT COALESCE(SUM(t.amount),0) AS total_deposits,
                   MIN(t.tx_date)           AS first_deposit,
                   COUNT(*)                 AS deposit_count
            FROM transactions t
            WHERE t.login = c.login AND t.tx_type='deposit'
        ) dep ON TRUE
        LEFT JOIN leads l ON l.matched_login = c.login OR l.converted_login = c.login
        WHERE {wc}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page-1)*page_size}).fetchall()

    kpi = db.execute(text(f"""
        SELECT COUNT(*) AS accts,
               COALESCE(SUM(dep.total_deposits),0) AS total_dep
        FROM clients c
        JOIN LATERAL (
            SELECT COALESCE(SUM(t.amount),0) AS total_deposits
            FROM transactions t WHERE t.login=c.login AND t.tx_type='deposit'
        ) dep ON TRUE
        WHERE {wc}
    """), params).fetchone()

    return {
        "accounts": [{
            "login": r[0], "name": r[1] or "", "country": r[2] or "",
            "platform": r[3] or "MT5", "kyc_status": r[4] or "",
            "reg_date": str(r[5]) if r[5] else "",
            "total_deposits": float(r[6] or 0),
            "first_deposit": str(r[7]) if r[7] else "",
            "deposit_count": r[8] or 0,
            "lead_id": r[9], "lead_name": r[10] or "",
            "match_badge": r[11] or "", "source": r[12] or "",
        } for r in rows],
        "total": total,
        "kpis": {
            "accounts": kpi[0] or 0,
            "total_deposits": float(kpi[1] or 0),
        },
    }


@router.get("/logins-only")
def get_lead_logins(
    search: str = Query(""),
    sort:   str = Query("created_at"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fast endpoint — returns only lead IDs with phone for power dialer."""
    where_parts = ["l.phone IS NOT NULL", "l.phone != ''"]
    params: dict = {}
    if search:
        where_parts.append("(l.full_name ILIKE :s OR l.phone ILIKE :s OR l.email ILIKE :s)")
        params["s"] = f"%{search}%"
    # Role-based visibility: agent dials only their own leads; manager their team; admin all
    _scope = rbac.scope_agent_ids(db, current_user)
    if _scope is not None:
        if _scope:
            where_parts.append("l.assigned_agent_id = ANY(:rbac_agent_ids)")
            params["rbac_agent_ids"] = _scope
        else:
            where_parts.append("FALSE")
    sort_col = {"created_at":"l.created_at DESC","name":"l.full_name ASC",
                "status":"l.status ASC"}.get(sort, "l.created_at DESC")
    where = " AND ".join(where_parts)
    rows = db.execute(text(f"SELECT l.id FROM leads l WHERE {where} ORDER BY {sort_col}"), params).fetchall()
    return {"logins": [r[0] for r in rows], "total": len(rows)}

