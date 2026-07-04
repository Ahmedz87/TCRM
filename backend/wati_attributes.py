"""
wati_attributes.py — keep Wati contact ATTRIBUTES in sync with the CRM.

The most important attribute is **acd** = the contact's CURRENT owning agent. In the CRM the current
owner is clients.assigned_agent_id (it flips sales→retention when a client deposits — see the TradeSoft
agent sync), so acd must follow it. We also fill the other Wati custom attributes that already exist on
the tenant (sales_agent, agent_team, type, email, country, city, language, deposits, last_login,
created_at, lead_stage) so segmentation/personalisation in Wati is correct — and so a BRAND-NEW contact
(one we message for the first time) is created fully populated, not blank.

Wati endpoint: POST /api/v1/addContact/{whatsappNumber}  body {name, customParams:[{name,value}...]}
  — upserts: creates the contact if new, updates attributes if it already exists.

Runs as a throttled BACKGROUND job (per-contact API calls; a segment can be large). Progress in _STATE.
"""
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from database import SessionLocal
from marketing_router import SEG_BY_KEY, _base

WATI_TIMEOUT = 25
WORKERS = 8                      # gentle concurrency so we don't trip Wati rate limits

_STATE = {"running": False, "segment": None, "total": 0, "done": 0,
          "ok": 0, "failed": 0, "started": None, "finished": None, "last_error": ""}
_LOCK = threading.Lock()


def _norm_phone(p):
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    return d if len(d) >= 8 else None


def _ymd(dt):
    try:
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


def _stage(total_dep, first_dep):
    if total_dep and float(total_dep) > 0:
        return "Depositor"
    if first_dep:
        return "Registered"
    return "Registered"


# one authoritative row per PHONE (a person has multiple logins → take the funded/most-relevant one)
# NB: clients.agent is an INTEGER (the MT agent login), NOT a name — the agent NAME is users.full_name
# via clients.assigned_agent_id (the current owner: sales pre-deposit, retention after).
_ATTR_SQL = """
    SELECT DISTINCT ON (regexp_replace(c.phone,'[^0-9]','','g'))
        c.phone, c.name, c.full_name_en, c.email, c.country, c.city,
        c.total_deposits, c.total_withdrawals, c.last_login_at, c.reg_date, c.first_deposit_at,
        u.full_name AS agent_full, u.team_type,
        COALESCE(NULLIF(c.legacy_sales_agent,''), u.full_name) AS sales_agent
    FROM clients c
    LEFT JOIN users u ON u.id = c.assigned_agent_id
    WHERE {where} AND COALESCE(c.phone,'') <> ''
    ORDER BY regexp_replace(c.phone,'[^0-9]','','g'), c.total_deposits DESC NULLS LAST
"""


def _rows_for_segment(db, seg):
    # segment 'where' is written against the clients alias c / bare columns; clients segments use c.*
    where = seg["where"] if seg["audience"] == "clients" else "TRUE"
    frm, _a, _em, _ph = _base(seg["audience"])
    if seg["audience"] != "clients":
        return []          # attributes are a client concept; lead segments have no agent/deposits
    return db.execute(text(_ATTR_SQL.format(where=where))).fetchall()


def build_attrs(row):
    """Map a CRM client row -> Wati customParams list + display name. acd = CURRENT agent."""
    (phone, name, name_en, email, country, city, tot_dep, tot_wd, last_login, reg_date,
     first_dep, agent_full, team_type, sales_agent) = row
    acd = (agent_full or "").strip()                          # current owner (retention/sales)
    disp = (name or name_en or "").strip()
    attrs = {
        "acd": acd,
        "agent_team": (team_type or "").strip(),             # sales | retention (extra context)
        "sales_agent": (sales_agent or "").strip(),
        "type": "Client",
        "email": (email or "").strip(),
        "country": (country or "").strip(),
        "city": (city or "").strip(),
        "language": "Arabic",
        "total_deposit_amount": str(int(tot_dep)) if tot_dep is not None else "0",
        "total_withdrawal_amount": str(int(tot_wd)) if tot_wd is not None else "0",
        "last_login": _ymd(last_login),
        "created_at": _ymd(reg_date),
        "lead_stage": _stage(tot_dep, first_dep),
        "allowbroadcast": "TRUE",
    }
    params = [{"name": k, "value": v} for k, v in attrs.items() if v != ""]
    return disp, params


def push_contact(ep, tok, phone, name, params):
    """Upsert one Wati contact's attributes (creates it if new). Returns (ok, detail). No message sent."""
    hdr = {"Authorization": tok if tok.lower().startswith("bearer") else f"Bearer {tok}",
           "Content-Type": "application/json"}
    body = {"name": name or phone, "customParams": params}
    try:
        r = requests.post(f"{ep}/api/v1/addContact/{phone}", headers=hdr, json=body, timeout=WATI_TIMEOUT)
        ok = r.status_code < 300 and (r.json().get("result") is not False if r.text else True)
        return ok, ("" if ok else r.text[:160])
    except Exception as e:
        return False, str(e)[:160]


def preview_segment(db, seg, n=3):
    rows = _rows_for_segment(db, seg)[:n]
    out = []
    for row in rows:
        disp, params = build_attrs(row)
        out.append({"phone": _norm_phone(row[0]), "name": disp,
                    "attrs": {p["name"]: p["value"] for p in params}})
    return out


def run_sync(segment_key):
    """Background worker: upsert attributes for every reachable contact in a segment."""
    seg = SEG_BY_KEY.get(segment_key)
    if not seg:
        return
    with _LOCK:
        if _STATE["running"]:
            return
        _STATE.update({"running": True, "segment": segment_key, "total": 0, "done": 0,
                       "ok": 0, "failed": 0, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "finished": None, "last_error": ""})

    def worker():
        db = SessionLocal()
        try:
            ep_tok = db.execute(text("SELECT api_endpoint, api_token FROM wati_config WHERE id=1")).fetchone()
            ep = (ep_tok[0] or "").rstrip("/"); tok = ep_tok[1] or ""
            rows = _rows_for_segment(db, seg)
            # dedup by normalized phone
            seen, jobs = set(), []
            for row in rows:
                ph = _norm_phone(row[0])
                if ph and ph not in seen:
                    seen.add(ph); jobs.append(row)
            _STATE["total"] = len(jobs)

            def do(row):
                ph = _norm_phone(row[0])
                disp, params = build_attrs(row)
                ok, detail = push_contact(ep, tok, ph, disp, params)
                with _LOCK:
                    _STATE["done"] += 1
                    if ok:
                        _STATE["ok"] += 1
                    else:
                        _STATE["failed"] += 1; _STATE["last_error"] = detail
                time.sleep(0.05)   # be gentle on the rate limit

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                list(ex.map(do, jobs))
        except Exception as e:
            _STATE["last_error"] = str(e)[:200]
        finally:
            db.close()
            with _LOCK:
                _STATE["running"] = False
                _STATE["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=worker, daemon=True).start()


def status():
    return dict(_STATE)
