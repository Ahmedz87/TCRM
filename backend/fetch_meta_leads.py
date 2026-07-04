"""
fetch_meta_leads.py  —  Pull Meta (Facebook) Lead Ads leads into the broker_crm `leads` table.

WHAT IT DOES (multi-form)
  1. Validates the access token (a System User token, scopes incl. leads_retrieval).
  2. Derives a PAGE ACCESS TOKEN from it — page-level endpoints (/leadgen_forms)
     REQUIRE a page token; the raw system-user token gets "(#190) This method must
     be called with a Page Access Token".
  3. Lists EVERY lead form on the page (paginated) and fetches the leads from each
     form that actually has leads.
  4. Maps Meta field_data -> full_name / email / phone (robust to form field naming).
  5. Tags each lead with its form: campaign_name = the form's readable name,
     source = a "meta_<slug>" tag (so the CRM can filter by campaign), plus the
     raw meta_form_id / meta_form_name for traceability.
  6. Upserts into `leads`, de-duped on the Meta lead id. Re-runs never create
     duplicates AND they backfill the campaign_name / source tags onto rows that
     were imported by the old single-form version of this script.

RUN IT
  # See every form + how many leads each would import, WITHOUT touching the DB:
  python fetch_meta_leads.py --dry-run
  # Actually import (all forms):
  python fetch_meta_leads.py
  # Only one form:
  python fetch_meta_leads.py --form 1795851617749555

  Schedule it (meta_loop.py runs it every 5 min) to keep polling.

CREDENTIALS
  Read from environment if set, otherwise the hard-coded fallbacks below are used.
  Prefer env vars so secrets stay out of the file:
    setx META_ACCESS_TOKEN "EAA..."   (PowerShell, then reopen the terminal)
"""

import os
import db_config
import meta_config
import re
import sys
import json
import requests

# Console may be cp1252 (esp. when run headless by meta_poller) — Arabic lead names in
# the diagnostic prints would otherwise raise UnicodeEncodeError and KILL the whole
# fetch before any leads are inserted. Force UTF-8 with replacement so prints never crash.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import psycopg2
from psycopg2.extras import execute_values

# --- Meta config -------------------------------------------------------------
# Graph API version. v19.0 is alive as of 2026; bump to the latest at
# https://developers.facebook.com/docs/graph-api/changelog if Meta sunsets it.
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v19.0")
PAGE_ID       = os.getenv("META_PAGE_ID",      meta_config.META_PAGE_ID)
ACCESS_TOKEN  = os.getenv("META_ACCESS_TOKEN", meta_config.META_ACCESS_TOKEN)

GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Meta's per-lead `platform` field -> the channel value the CRM/UI understands
# (SourceLogo renders facebook/instagram/messenger/audience_network/whatsapp icons).
PLATFORM_MAP = {
    "fb": "facebook", "facebook": "facebook",
    "ig": "instagram", "instagram": "instagram",
    "msg": "messenger", "messenger": "messenger",
    "an": "audience_network", "audience_network": "audience_network",
    "wa": "whatsapp", "whatsapp": "whatsapp",
}

# --- DB config (matches the Session 9 handoff) -------------------------------
DB = dict(
    host     = os.getenv("PGHOST", db_config.DB_HOST),
    port     = os.getenv("PGPORT", db_config.DB_PORT),
    dbname   = os.getenv("PGDATABASE", db_config.DB_NAME),
    user     = os.getenv("PGUSER", db_config.DB_USER),
    password = os.getenv("PGPASSWORD", db_config.DB_PASSWORD),
)


def validate_token():
    """Confirm the token works and report who it belongs to + its scopes."""
    r = requests.get(f"{GRAPH}/debug_token",
                     params={"input_token": ACCESS_TOKEN, "access_token": ACCESS_TOKEN},
                     timeout=15)
    data = r.json().get("data", {})
    if not data.get("is_valid"):
        print("TOKEN INVALID:", json.dumps(r.json(), indent=2))
        print("\nFix: generate a fresh token with the `leads_retrieval` permission, "
              "ideally a long-lived Page token or a System User token (those don't expire).")
        sys.exit(1)
    scopes = data.get("scopes", [])
    print(f"Token OK. type={data.get('type')}  expires={data.get('expires_at')}  scopes={scopes}")
    if "leads_retrieval" not in scopes:
        print("WARNING: token is missing the `leads_retrieval` scope — the lead pull will likely fail.")
    return data


def get_page_token():
    """Exchange the (system-user) token for a PAGE access token.

    The /{page}/leadgen_forms endpoint must be called with a page token, otherwise
    Meta returns: (#190) This method must be called with a Page Access Token.
    A system-user token assigned to the page can read the page token directly.
    """
    r = requests.get(f"{GRAPH}/{PAGE_ID}",
                     params={"fields": "access_token,name", "access_token": ACCESS_TOKEN},
                     timeout=15)
    body = r.json()
    if "access_token" not in body:
        print("Could not get a page access token. Response:")
        print(json.dumps(body, indent=2))
        print("\nThe token must be a System User / Page token assigned to the page "
              "with pages_show_list + leads_retrieval. Falling back to the raw token "
              "(page-level form listing will likely fail).")
        return ACCESS_TOKEN
    print(f"Page token acquired for page '{body.get('name')}' ({PAGE_ID}).")
    return body["access_token"]


def list_forms(page_token):
    """Return [{id, name, leads_count, status}, ...] for every form on the page."""
    forms, url = [], f"{GRAPH}/{PAGE_ID}/leadgen_forms"
    params = {"fields": "id,name,leads_count,status", "limit": 100, "access_token": page_token}
    while url:
        body = requests.get(url, params=params, timeout=30).json()
        if "error" in body:
            print("GRAPH API ERROR (listing forms):", json.dumps(body["error"], indent=2))
            sys.exit(1)
        forms.extend(body.get("data", []))
        url = body.get("paging", {}).get("next")
        params = {}
    return forms


def fetch_leads_for_form(form_id, page_token):
    """Pull every lead from one form, following pagination."""
    leads, url = [], f"{GRAPH}/{form_id}/leads"
    # include ad-level attribution so reporting can go ad/adset/campaign-level (ticket: ad ROI)
    params = {"fields": "id,created_time,platform,field_data,ad_id,adset_id,campaign_id,ad_name,adset_name,campaign_name",
              "limit": 200, "access_token": page_token}
    while url:
        body = requests.get(url, params=params, timeout=30).json()
        if "error" in body:
            print(f"  GRAPH API ERROR (form {form_id}):", json.dumps(body["error"], indent=2))
            break
        leads.extend(body.get("data", []))
        url = body.get("paging", {}).get("next")   # full URL with cursor baked in
        params = {}                                 # don't re-send params on the next page
    return leads


def parse_lead(lead):
    """Map Meta's field_data array -> (full_name, email, phone, raw).
    Field names vary per form, so we match by keyword instead of assuming exact keys."""
    fields = {}
    for f in lead.get("field_data", []):
        vals = f.get("values") or [""]
        fields[f["name"].lower()] = vals[0]

    def first_match(*keywords):
        for k, v in fields.items():
            if any(kw in k for kw in keywords):
                return v
        return ""

    email = first_match("email")
    phone = first_match("phone", "mobile", "number", "whatsapp")
    name  = fields.get("full_name") or fields.get("name")
    if not name:
        first = first_match("first_name", "first name")
        last  = first_match("last_name", "last name")
        name  = (f"{first} {last}").strip()
    if not name:
        # last resort: any field that isn't the email or phone we already grabbed
        name = next((v for k, v in fields.items()
                     if v not in (email, phone) and v), "")

    return name.strip(), email.strip(), phone.strip(), fields


def lead_channel(lead):
    """Map Meta's per-lead `platform` (fb/ig/msg/an/wa) -> CRM channel value.
    These are Facebook lead forms, so an unknown/missing platform defaults to facebook."""
    plat = (lead.get("platform") or "").lower()
    return PLATFORM_MAP.get(plat, "facebook"), plat


def ensure_schema(conn):
    """Add the tracking columns + unique key if they aren't there yet (idempotent)."""
    with conn.cursor() as cur:
        # Steady-state skip: once the last column exists the migration has run, so don't grab an
        # ACCESS EXCLUSIVE lock on the hot `leads` table every 5-min cycle (caused restart-time
        # lock pileups). Only run the DDL the first time (fresh column), preserving old behavior.
        cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='adset_name'")
        if cur.fetchone():
            return
        cur.execute("""
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_lead_id   TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_created   TIMESTAMPTZ;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_raw        JSONB;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_form_id    TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_form_name  TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_platform   VARCHAR;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_name   VARCHAR;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_id           TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS adset_id        TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_id     TEXT;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_name         VARCHAR;
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS adset_name      VARCHAR;
            CREATE UNIQUE INDEX IF NOT EXISTS leads_meta_lead_id_uq
                ON leads (meta_lead_id) WHERE meta_lead_id IS NOT NULL;
        """)
    conn.commit()


def upsert(conn, rows):
    """rows: (full_name, email, phone, source, campaign_name,
             meta_lead_id, meta_created, meta_form_id, meta_form_name, meta_platform, meta_raw).

    source   = the publisher channel (facebook/instagram/messenger/...) per lead.
    campaign = the form name.
    On conflict we DO UPDATE the tagging columns so old rows get back-tagged — but we
    deliberately leave full_name / email / phone / status untouched (no CRM-edit clobber)."""
    _SQL = """
            INSERT INTO leads (full_name, email, phone, status, source, campaign_name,
                               meta_lead_id, meta_created, meta_form_id, meta_form_name,
                               meta_platform, meta_raw, score,
                               ad_id, adset_id, campaign_id, ad_name, adset_name)
            VALUES %s
            ON CONFLICT (meta_lead_id) WHERE meta_lead_id IS NOT NULL DO UPDATE SET
                source         = EXCLUDED.source,
                campaign_name  = EXCLUDED.campaign_name,
                meta_form_id   = EXCLUDED.meta_form_id,
                meta_form_name = EXCLUDED.meta_form_name,
                meta_platform  = EXCLUDED.meta_platform,
                meta_created   = COALESCE(leads.meta_created, EXCLUDED.meta_created),
                meta_raw       = COALESCE(EXCLUDED.meta_raw, leads.meta_raw),
                ad_id          = COALESCE(EXCLUDED.ad_id, leads.ad_id),
                adset_id       = COALESCE(EXCLUDED.adset_id, leads.adset_id),
                campaign_id    = COALESCE(EXCLUDED.campaign_id, leads.campaign_id),
                ad_name        = COALESCE(EXCLUDED.ad_name, leads.ad_name),
                adset_name     = COALESCE(EXCLUDED.adset_name, leads.adset_name),
                -- RE-CAPTURE FROM ARCHIVE: an archived lead that re-submits the Meta form comes
                -- back to the active list with ♻ recapture + 📦 archive badges and +50 score.
                is_archived              = FALSE,
                status                   = CASE WHEN COALESCE(leads.is_archived,FALSE) THEN 'new' ELSE leads.status END,
                reactivated_from_archive = CASE WHEN COALESCE(leads.is_archived,FALSE) THEN TRUE ELSE COALESCE(leads.reactivated_from_archive,FALSE) END,
                reactivated_at           = CASE WHEN COALESCE(leads.is_archived,FALSE) THEN NOW() ELSE leads.reactivated_at END,
                match_badge              = CASE WHEN COALESCE(leads.is_archived,FALSE) AND COALESCE(leads.match_badge,'') <> 'converted' THEN 'recapture_archive' ELSE leads.match_badge END,
                score                    = CASE WHEN COALESCE(leads.is_archived,FALSE) THEN LEAST(100, COALESCE(leads.score,0)+50) ELSE leads.score END
                -- score is NOT otherwise overwritten on conflict (auto_match owns it for existing leads)
            RETURNING id, (xmax = 0) AS inserted
        """
    _TMPL = "(%s,%s,%s,'new',%s,%s,%s,%s,%s,%s,%s,%s,30,%s,%s,%s,%s,%s)"
    # IMPORTANT: fetch=True makes execute_values send EVERY row in ONE statement (it can't page),
    # which for a big form (e.g. 11k Syria leads) builds a multi-MB statement that drops the DB
    # connection ("server closed the connection unexpectedly") and aborts the whole fetch -> no
    # leads insert. So we chunk the rows ourselves and run each chunk as its own small statement.
    affected, new_ids = 0, []
    CHUNK = 400
    with conn.cursor() as cur:
        for i in range(0, len(rows), CHUNK):
            batch = rows[i:i + CHUNK]
            returned = execute_values(cur, _SQL, batch, template=_TMPL, fetch=True)
            affected += cur.rowcount
            new_ids += [r[0] for r in (returned or []) if r[1]]
            conn.commit()
    return affected, new_ids


def _fill_blank_countries():
    """Fill leads.country (and clients via the same code if blank) from the phone's calling code,
    for any row still missing a country. Reuses country_for() from fill_lead_country (single source
    of truth for the code->country map). Idempotent — only touches blank rows."""
    import psycopg2
    from fill_lead_country import country_for
    conn = db_config.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, phone FROM leads WHERE COALESCE(country,'')='' AND COALESCE(phone,'')<>''")
        n = 0
        for lid, phone in cur.fetchall():
            c = country_for(phone)
            if c:
                cur.execute("UPDATE leads SET country=%s WHERE id=%s", (c, lid))
                n += 1
        conn.commit()
        if n:
            print(f"[country] filled {n} lead(s) from phone calling code.")
    finally:
        conn.close()


def auto_assign_new(new_ids):
    """Route freshly-inserted leads through the assignment rules. GUARDED — a routing error
    must NEVER break the lead fetch (same defensive stance as the UTF-8 console fix)."""
    if not new_ids:
        return
    try:
        from database import SessionLocal
        import lead_routing
        db = SessionLocal()
        try:
            lead_routing.ensure_schema(db)
            if not lead_routing.get_config(db).get("auto_assign_enabled"):
                return
            assigned = 0
            for lid in new_ids:
                try:
                    if lead_routing.assign_lead(db, lid, commit=False).get("ok"):
                        assigned += 1
                except Exception:
                    db.rollback()
            db.commit()
            print(f"  routing: assigned {assigned}/{len(new_ids)} new lead(s) via rules.")
        finally:
            db.close()
    except Exception as e:
        print(f"  routing skipped ({type(e).__name__}: {str(e)[:120]})")


def _reactivate_archived_meta(new_ids):
    """Re-capture ARCHIVED leads whose phone/email matches a brand-NEW Meta submission
    (new_ids = the freshly-inserted lead rows). ♻+📦 badge, +50 score. Excludes the new rows
    themselves so we only flip the older archived duplicates."""
    if not new_ids:
        return
    conn = db_config.connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            WITH fresh AS (
                SELECT DISTINCT NULLIF(phone,'') AS phone, LOWER(NULLIF(email,'')) AS email
                FROM leads WHERE id = ANY(%s)
            )
            UPDATE leads l SET
                is_archived = FALSE,
                status = 'new',
                reactivated_from_archive = TRUE,
                reactivated_at = NOW(),
                match_badge = CASE WHEN COALESCE(l.match_badge,'') <> 'converted' THEN 'recapture_archive' ELSE l.match_badge END,
                score = LEAST(100, COALESCE(l.score,0) + 50),
                updated_at = NOW()
            WHERE COALESCE(l.is_archived, FALSE) = TRUE
              AND l.id <> ALL(%s)
              AND EXISTS (SELECT 1 FROM fresh f
                          WHERE (f.phone IS NOT NULL AND f.phone = l.phone)
                             OR (f.email IS NOT NULL AND f.email = LOWER(l.email)))
        """, (list(new_ids), list(new_ids)))
        n = cur.rowcount
        conn.commit()
        if n:
            print(f"  archive re-capture: reactivated {n} archived lead(s) that re-submitted a Meta form.")
        # an archived CLIENT (person-level) who fills our ads form also comes back to the Clients page
        cur.execute("""
            WITH fresh AS (
                SELECT DISTINCT NULLIF(phone,'') AS phone, LOWER(NULLIF(email,'')) AS email
                FROM leads WHERE id = ANY(%s)
            ), back AS (
                SELECT DISTINCT COALESCE(c.customer_no,'L'||c.login) AS gk
                FROM clients c WHERE COALESCE(c.user_archived,FALSE)=TRUE
                  AND EXISTS (SELECT 1 FROM fresh f
                              WHERE (f.phone IS NOT NULL AND f.phone=c.phone)
                                 OR (f.email IS NOT NULL AND f.email=LOWER(c.email)))
            )
            UPDATE clients c SET user_archived=FALSE, reactivated_from_archive=TRUE, reactivated_at=NOW(),
                   call_score=LEAST(100, COALESCE(call_score,0)+50), lead_badge='reactivated', updated_at=NOW()
            WHERE COALESCE(c.customer_no,'L'||c.login) IN (SELECT gk FROM back)
        """, (list(new_ids),))
        nc = cur.rowcount
        conn.commit()
        if nc:
            print(f"  archive re-capture: brought back {nc} archived client row(s) that filled a Meta form.")
    finally:
        conn.close()


def main():
    dry  = "--dry-run" in sys.argv
    only = None
    if "--form" in sys.argv:
        only = sys.argv[sys.argv.index("--form") + 1]

    if ACCESS_TOKEN in ("", "PASTE_TOKEN_HERE"):
        print("Set META_ACCESS_TOKEN (env var) or edit ACCESS_TOKEN in the file first.")
        sys.exit(1)

    validate_token()
    page_token = get_page_token()

    forms = list_forms(page_token)
    if only:
        forms = [f for f in forms if str(f.get("id")) == str(only)]
        if not forms:
            # form not in the listing (e.g. archived) — fetch it anyway as a bare id
            forms = [{"id": only, "name": only, "leads_count": None}]

    # Only bother hitting forms that report leads (or unknown count).
    todo = [f for f in forms
            if f.get("leads_count") is None or (isinstance(f["leads_count"], int) and f["leads_count"] > 0)]
    skipped = len(forms) - len(todo)
    print(f"\n{len(forms)} form(s) on page; {len(todo)} with leads to fetch, "
          f"{skipped} empty form(s) skipped.\n")

    conn = None
    if not dry:
        conn = psycopg2.connect(**DB)
        # This is a batch job that holds its connection while slowly pulling thousands of leads
        # from Meta over the network. The DB has idle_in_transaction_session_timeout=1min (a lock-
        # convoy mitigation) which would KILL this connection mid-pull -> "server closed the
        # connection unexpectedly" -> no leads insert. autocommit means we never sit idle-in-
        # transaction (and never hold locks during the slow Meta fetches); also exempt this
        # session from the timeout and cap lock waits so ensure_schema can't hang on a lock.
        conn.autocommit = True
        with conn.cursor() as _cur:
            _cur.execute("SET idle_in_transaction_session_timeout = 0")
            _cur.execute("SET lock_timeout = '8s'")
        ensure_schema(conn)

    grand_fetched = grand_affected = 0
    new_lead_ids = []
    try:
        for f in sorted(todo, key=lambda x: -(x.get("leads_count") or 0)):
            fid, fname = str(f["id"]), (f.get("name") or str(f["id"]))
            leads = fetch_leads_for_form(fid, page_token)
            grand_fetched += len(leads)
            chans = {}
            for lead in leads:
                ch, _ = lead_channel(lead)
                chans[ch] = chans.get(ch, 0) + 1
            mix = ", ".join(f"{k}={v}" for k, v in sorted(chans.items(), key=lambda x: -x[1]))
            print(f"  form {fid:>18}  fetched={len(leads):>6}  [{mix}]  ({fname})")

            if dry:
                for lead in leads[:3]:
                    name, email, phone, _ = parse_lead(lead)
                    ch, plat = lead_channel(lead)
                    print(f"      sample: name={name!r} email={email!r} phone={phone!r} platform={plat!r} -> {ch}")
                continue

            db_rows = []
            for lead in leads:
                name, email, phone, raw = parse_lead(lead)
                channel, plat = lead_channel(lead)
                db_rows.append((name, email, phone, channel, fname,
                                lead["id"], lead.get("created_time"),
                                fid, fname, plat, json.dumps(raw),
                                lead.get("ad_id"), lead.get("adset_id"), lead.get("campaign_id"),
                                lead.get("ad_name"), lead.get("adset_name")))
            if db_rows:
                aff, nids = upsert(conn, db_rows)
                grand_affected += aff
                new_lead_ids.extend(nids)
    finally:
        if conn:
            conn.close()

    if not dry and new_lead_ids:
        auto_assign_new(new_lead_ids)

    # ARCHIVE RE-CAPTURE: a brand-NEW Meta submission (new_lead_ids = freshly-inserted leads, i.e.
    # new meta_lead_ids) whose phone/email matches an ARCHIVED lead brings that archived lead back to
    # the active list with ♻+📦 badges and +50 score. We gate on NEW submissions only (not the whole
    # form history) so we don't churn-reactivate archived leads that merely overlap old Meta leads.
    if not dry and new_lead_ids:
        try:
            _reactivate_archived_meta(new_lead_ids)
        except Exception as e:
            print(f"  archive re-capture skipped ({type(e).__name__}: {str(e)[:120]})")

    # Derive country from the phone's calling code for any lead still missing it. Meta forms don't
    # capture country, but the phone carries it (+963 Syria, +964 Iraq, +90 Turkey, +20 Egypt …).
    # Runs every poll cycle so new leads always show a country on the Leads page. GUARDED — a
    # backfill error must never break the fetch.
    if not dry:
        try:
            _fill_blank_countries()
        except Exception as e:
            print(f"[country] backfill skipped: {e}")

    print()
    if dry:
        print(f"--dry-run: nothing written. Would fetch {grand_fetched} lead(s) "
              f"across {len(todo)} form(s). Run without --dry-run to import.")
    else:
        print(f"Done. Fetched {grand_fetched} lead(s) across {len(todo)} form(s); "
              f"{grand_affected} row(s) inserted-or-tagged (duplicates de-duped on meta_lead_id).")


if __name__ == "__main__":
    main()
