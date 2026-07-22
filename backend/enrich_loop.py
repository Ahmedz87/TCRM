"""
enrich_loop.py — makes TradeSoft-created leads COMPLETE within ~1 min, regardless of what
creates them (even an old-machine sync running pre-fix code).

Every 60s:
  * backfill_lead_contacts.py — pulls email/phone/campaign for any contactless lead straight
    from the FULL MySQL fx_leads (so it never depends on the redacted view / the mirror).
  * fills customer email/phone from the full fx_leads mirror.
Every 5th cycle (~5 min):
  * reclassify_sources.py --apply  (meta / google / MQL5 / sales_agent from the mirror)
  * sync_lead_verification.py       (phone/email/KYC upgrade from fx_users_view)

Idempotent; each pass only touches rows still missing data, so it stays cheap after catch-up.
Run: python enrich_loop.py   (started at boot alongside meta_poller — see start_core.ps1)
"""
import time, subprocess, sys, os
from datetime import datetime

# Own our stdout/stderr via a file WE open. A detached launch (Start-Process from a short-lived
# launcher) closes the inherited stdout handle when the launcher exits, so the next print() raised
# "I/O operation on closed file" and killed the loop — repeatedly taking down the notification
# generator (#274/#302). Holding this file open ourselves for the process's lifetime is crash-proof.
_LOGF = None
try:
    _LOGF = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "enrich_loop.log"),
                 "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = _LOGF
    sys.stderr = _LOGF
except Exception:
    pass

BE = r"C:\Broker-crm\backend"
PY = sys.executable
INTERVAL = 60


def run(script, *args):
    try:
        # send the child's output to OUR owned log file (or DEVNULL) — never let a child inherit the
        # closed stdout handle and crash on its own print (that's how notify_engine stopped firing).
        subprocess.run([PY, script, *args], cwd=BE, check=False, timeout=600,
                       stdout=(_LOGF or subprocess.DEVNULL), stderr=subprocess.STDOUT,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except Exception as e:
        try: print(f"  {script} error: {e}", flush=True)
        except Exception: pass


def fill_contacts_fast():
    """LIGHT 60s pass: fill ONLY email/phone that's actually missing, from the full fx_leads
    mirror. Touches just the still-blank rows (near-zero after catch-up) — never the campaign
    field, so it doesn't churn the ~46k leads whose source has no campaign."""
    try:
        import db_config
        c = db_config.connect(); c.autocommit = True; cur = c.cursor()
        # customers first (leads inherit from them)
        cur.execute("""
          UPDATE customers cu SET
            email = COALESCE(NULLIF(TRIM(cu.email),''), fl.email),
            phone = COALESCE(NULLIF(TRIM(cu.phone),''), fl.phone)
          FROM (SELECT DISTINCT ON(user_id) user_id, NULLIF(TRIM(email),'') email,
                  COALESCE(NULLIF(TRIM(phone),''), NULLIF(TRIM(mobile),'')) phone
                FROM tradesoft_old.fx_leads WHERE deleted_at IS NULL ORDER BY user_id) fl
          WHERE fl.user_id = cu.legacy_user_id
            AND ((COALESCE(TRIM(cu.email),'')='' AND fl.email IS NOT NULL)
                 OR (COALESCE(TRIM(cu.phone),'')='' AND fl.phone IS NOT NULL))""")
        nc = cur.rowcount
        # then leads from customers
        cur.execute("""
          UPDATE leads l SET email=COALESCE(NULLIF(TRIM(l.email),''),cu.email),
                             phone=COALESCE(NULLIF(TRIM(l.phone),''),cu.phone)
          FROM customers cu WHERE cu.customer_no=l.customer_no
            AND ((COALESCE(TRIM(l.email),'')='' AND cu.email IS NOT NULL)
                 OR (COALESCE(TRIM(l.phone),'')='' AND cu.phone IS NOT NULL))""")
        nl = cur.rowcount
        c.close()
        if nc or nl:
            print(f"  filled contacts: {nc} customers, {nl} leads", flush=True)
    except Exception as e:
        print(f"  contacts error: {e}", flush=True)


def resolve_agent_ids():
    """The old-machine sync inserts leads with legacy_sales_agent = a TradeSoft STAFF USER ID
    (e.g. 296017) instead of the name. Resolve numeric ids -> staff names via fx_users_view;
    blank the meaningless '0' and ids TradeSoft no longer knows (deleted staff).
    Guarded against the mirror mid-reload (view empty => skip the blanking)."""
    try:
        import db_config
        c = db_config.connect(); c.autocommit = True; cur = c.cursor()
        cur.execute("""UPDATE leads l SET legacy_sales_agent = s.nm
          FROM (SELECT id, NULLIF(TRIM(COALESCE(name,'')||' '||COALESCE(surname,'')),'') nm
                FROM tradesoft_old.fx_users_view) s
          WHERE l.legacy_sales_agent ~ '^[0-9]+$' AND s.id = l.legacy_sales_agent AND s.nm IS NOT NULL""")
        n = cur.rowcount
        cur.execute("SELECT count(*) FROM tradesoft_old.fx_users_view")
        if (cur.fetchone()[0] or 0) > 1000:   # mirror is loaded -> safe to blank unresolvable
            cur.execute("""UPDATE leads SET legacy_sales_agent = NULL
              WHERE legacy_sales_agent ~ '^[0-9]+$'
                AND NOT EXISTS (SELECT 1 FROM tradesoft_old.fx_users_view u
                                WHERE u.id = leads.legacy_sales_agent)""")
            n += cur.rowcount
        c.close()
        if n:
            print(f"  agent ids resolved/cleaned: {n}", flush=True)
    except Exception as e:
        print(f"  agent-id resolve error: {e}", flush=True)


def dedup_transactions():
    """Flag TradeSoft deposit/withdrawal rows that duplicate an MT deal as *_dup — one-to-one —
    so a gateway payment recorded as BOTH a TradeSoft-import row (8e9+) AND an MT deal isn't
    counted twice (ticket #182: a $54.84 deposit shown twice). The full dedup lives in
    tradesoft_sync, but that runs MANUALLY only, so intra-day deposits double-counted until the
    next hand-run — the TS row often lands minutes BEFORE the MT deal, so import-time same-day
    matching misses it. Run the authoritative redup engine every cycle (idempotent + reversible;
    ~1-2s, scoped to recent rows) and, only when it actually changed something, recompute totals
    via the guard-aware full refresh. Keeps deposits deduped within ~1 min."""
    try:
        import redup_engine
        d, u = redup_engine.run()
        if d or u:
            from database import engine
            import update_client_totals
            with engine.begin() as conn:
                update_client_totals.full_refresh(conn)
            print(f"  tx dedup: +{d} dup / -{u} un-dup (totals refreshed)", flush=True)
    except Exception as e:
        print(f"  tx dedup error: {e}", flush=True)


print(f"enrich_loop started — every {INTERVAL}s: contacts+agent-ids+tx-dedup; every 15 min: campaign+source+verification", flush=True)
cycle = 0
while True:
    print(f"[{datetime.now():%H:%M:%S}] enriching…", flush=True)
    fill_contacts_fast()
    resolve_agent_ids()
    # dedupe gateway deposits/withdrawals that landed as both a TradeSoft row and an MT deal, so
    # they are never counted twice (ticket #182). Cheap + idempotent; the money-critical pass.
    dedup_transactions()
    # kill Meta dupes fast: a tradesoft/'meta' lead that matches a Meta-DIRECT fb/ig lead by email
    # is a duplicate (we already have it split fb/ig) -> merge + delete, BEFORE reclassify labels it 'meta'.
    run("dedup_meta_direct.py")
    # the notification bell: new leads -> sales, client transfers -> retention, money requests ->
    # backoffice, tickets/abuse/call-QA -> owners. Idempotent (dedupe keys), ~1s.
    run("notify_engine.py")
    cycle += 1
    if cycle % 15 == 0:   # ~15 min — heavier mirror-dependent passes
        run("backfill_lead_contacts.py")      # campaign + any contact the mirror missed (from MySQL)
        run("reclassify_sources.py", "--apply")
        run("sync_lead_verification.py")
        run("meta_auto_feed.py")              # auto lead-quality feedback to Meta CAPI (stage/verify/deposit driven)
        # keep the Markup page's per-symbol rollup fresh (15-min cadence < 20-min stale
        # threshold) so the page always reads the tiny table, never a 16.8M-row live scan
        try:
            import markup_agg
            markup_agg.refresh()
        except Exception as e:
            print(f"  markup_agg refresh error: {e}", flush=True)
        # lead priority scores: compute_score used to live only in run_meta_sync_service (not
        # scheduled) so most verified leads sat at score NULL (#246). Write-guarded; cheap.
        try:
            from database import SessionLocal as _SL
            import auto_match as _am
            _sdb = _SL()
            try:
                _am.compute_score(_sdb)
            finally:
                _sdb.close()
            print("  lead scores refreshed", flush=True)
        except Exception as e:
            print(f"  lead score refresh error: {e}", flush=True)
        # AML/sanctions lists: re-download once a day (staleness-gated, so a restart won't re-fetch).
        try:
            import aml_load
            aml_load.refresh_if_stale(hours=20)
        except Exception as e:
            print(f"  AML list refresh error: {e}", flush=True)
        # un-archive any account that shows REAL life (deposit/withdraw/trade in 30d) but is
        # still flagged archived by the bulk import / rogue sync ('tradesoft_not_on_mt' or no reason).
        try:
            import db_config
            c2 = db_config.connect(); c2.autocommit = True; cur2 = c2.cursor()
            cur2.execute("SET lock_timeout='10s'")
            cur2.execute("""UPDATE clients c SET is_archived=FALSE, archive_reason=NULL, is_active=TRUE
              WHERE COALESCE(c.is_archived,false)
                AND (c.archive_reason='tradesoft_not_on_mt' OR c.archive_reason IS NULL)
                AND (EXISTS (SELECT 1 FROM transactions t WHERE t.login=c.login AND t.tx_type IN ('deposit','withdrawal')
                             AND left(t.tx_date,10) >= to_char(now()-interval '30 days','YYYY-MM-DD'))
                     OR EXISTS (SELECT 1 FROM deals d WHERE d.login=c.login AND d.action IN (0,1)
                             AND d.deal_date >= to_char(now()-interval '30 days','YYYY-MM-DD')))""")
            if cur2.rowcount:
                print(f"  reactivated wrongly-archived active accounts: {cur2.rowcount}", flush=True)
            # PERSON-level archive sync from TradeSoft (client archive ~150 people; lead archive):
            # the desk's archives made in the OLD CRM must reflect here too. Upgrade-only.
            cur2.execute("""UPDATE clients cl SET user_archived=TRUE,
                  user_archived_at=COALESCE(cl.user_archived_at, NOW())
              FROM customers cu
              WHERE cl.customer_no=cu.customer_no AND NOT COALESCE(cl.user_archived,false)
                AND EXISTS (SELECT 1 FROM tradesoft_old.fx_clients_view v
                            WHERE v.user_id=cu.legacy_user_id AND v.deleted_at IS NULL
                              AND v.archived_at IS NOT NULL AND COALESCE(TRIM(v.archived_at),'') NOT IN ('','NULL')
                              AND v.archived_at NOT ILIKE '%0000%')""")
            if cur2.rowcount:
                print(f"  client-archive synced from TradeSoft: {cur2.rowcount}", flush=True)
            cur2.execute("""UPDATE leads l SET is_archived=TRUE
              FROM customers cu
              WHERE l.customer_no=cu.customer_no AND NOT COALESCE(l.is_archived,false)
                AND EXISTS (SELECT 1 FROM tradesoft_old.fx_leads fl
                            WHERE fl.user_id::text=cu.legacy_user_id AND fl.deleted_at IS NULL
                              AND fl.archived_at IS NOT NULL AND COALESCE(TRIM(fl.archived_at),'') NOT IN ('','NULL')
                              AND fl.archived_at NOT ILIKE '%0000%')""")
            if cur2.rowcount:
                print(f"  lead-archive synced from TradeSoft: {cur2.rowcount}", flush=True)
            # first_deposit_at must follow the transaction truth — an empty field made the
            # "New clients" KPI under-count vs the back office's NDA sheet (Jul 10 case).
            cur2.execute("""UPDATE clients c SET first_deposit_at = s.fd
              FROM (SELECT t.login, MIN(t.tx_date) fd FROM transactions t
                    WHERE t.tx_type='deposit' GROUP BY t.login) s
              WHERE s.login = c.login AND COALESCE(c.first_deposit_at,'') = ''""")
            if cur2.rowcount:
                print(f"  first_deposit_at backfilled: {cur2.rowcount}", flush=True)
            c2.close()
        except Exception as e:
            print(f"  reactivate error: {e}", flush=True)
    time.sleep(INTERVAL)
