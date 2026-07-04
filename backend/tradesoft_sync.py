"""
tradesoft_sync.py — hourly TradeSoft -> CRM updater.

Each run:
  1) refresh the raw mirror from the legacy MySQL (fetch_tradesoft.py — drops & reloads the 5 fx_*_view)
  2) re-create the helper indexes on the mirror
  3) run the idempotent reconcile (reconcile_tradesoft phases) so ONLY new customers / accounts /
     leads / transactions get added; existing rows are untouched (NOT EXISTS / ON CONFLICT guards)
  4) recompute deposit/withdraw totals ONLY for the logins that got new transactions (incremental)

NOTE: the MySQL views do NOT carry email/phone (those came from the manual CSV export). New people
synced here arrive without contact until a fresh contact CSV is loaded.

Run: python tradesoft_sync.py   (scheduled hourly by Task Scheduler BrokerCRM-TradeSoftSync)
"""
import sys, subprocess, datetime, os, glob
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from sqlalchemy import text
from database import SessionLocal
import reconcile_tradesoft as R

BE = r"C:\Broker-crm\backend"
LOG = r"C:\Broker-crm\backend\logs\tradesoft_sync.log"
L = "tradesoft_old"


def log(m):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {m}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def reindex(db):
    for t, col in [("fx_users_view", "id"), ("fx_clients_view", "user_id"), ("fx_leads_view", "user_id"),
                   ("fx_accounts_view", "user_id"), ("fx_accounts_view", "account_number"),
                   ("fx_transactions_view", "account_number")]:
        try:
            db.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t}_{col} ON {L}.{t}({col})")); db.commit()
        except Exception:
            db.rollback()


def maybe_load_contacts():
    """If a NEWER contact CSV was dropped in the folder (old CRM sends one ~every 3 days), load it."""
    folder = r"C:\Broker-crm\data Email + Phone"
    marker = r"C:\Broker-crm\backend\logs\.contacts_mtime"
    try:
        files = glob.glob(os.path.join(folder, "*.csv"))
        if not files:
            log("contacts: no CSV in folder"); return
        newest = max(os.path.getmtime(f) for f in files)
        last = 0.0
        try:
            last = float(open(marker).read().strip())
        except Exception:
            pass
        if newest > last + 1:
            log("contacts: newer CSV found -> loading email/phone")
            import load_contacts
            n = load_contacts.main()
            open(marker, "w").write(str(newest))
            log(f"contacts: loaded ({n} rows enriched)")
        else:
            log("contacts: no new CSV since last load")
    except Exception as e:
        log(f"contacts: load error: {e}")


def main():
    log("=== sync start ===")
    # 1) refresh mirror
    try:
        r = subprocess.run([sys.executable, "fetch_tradesoft.py"], cwd=BE,
                           capture_output=True, text=True, timeout=1800)
        tail = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
        log(f"mirror refresh exit={r.returncode} :: {tail}")
        if r.returncode != 0:
            log(f"mirror STDERR: {(r.stderr or '')[-300:]}")
            return
    except Exception as e:
        log(f"mirror refresh FAILED: {e}")
        return

    db = SessionLocal()
    try:
        reindex(db); log("indexes ensured")
        R.schema(db)
        R.phase1(db)                       # new customers + CUS + classify
        R.phase2(db)                       # new accounts -> active/archive
        R.phase3(db)                       # new leads
        # incremental transactions: import new, capture affected logins, update only those totals
        off = R.OFF if hasattr(R, "OFF") else 8_000_000_000
        A = "NULLIF(regexp_replace(t.amount,'[^0-9.\\-]','','g'),'')::numeric"
        TYPE = """CASE WHEN t.type='withdrawal' THEN 'withdrawal' WHEN t.type='transfer' THEN 'internal_transfer'
            WHEN COALESCE(t.note,'') ~* 'negativ|cover' THEN 'negative_cover'
            WHEN COALESCE(t.note,'') ~* 'fix' THEN 'balance_fix' ELSE 'deposit' END"""
        rows = db.execute(text(f"""
          WITH ins AS (
            INSERT INTO transactions (deal_id, login, tx_type, amount, currency, method, status, notes,
                                      tx_date, tx_month, created_at, updated_at)
            SELECT {off}+t.id::bigint, t.account_number::bigint, {TYPE}, {A},
              COALESCE(NULLIF(t.currency,''),'USD'), COALESCE(NULLIF(t.payment_method,''),'TradeSoft'),
              'approved', COALESCE(NULLIF(t.note,''),'TradeSoft import'), t.created_at, left(t.created_at,7),
              NULLIF(t.created_at,'')::timestamptz, NOW()
            FROM {L}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
              AND {A}>0 AND {A}<1000000
              AND ((t.type='deposit' AND COALESCE(t.payment_method,'')<>'0') OR t.type IN ('withdrawal','transfer'))
              AND NOT EXISTS (SELECT 1 FROM transactions e WHERE e.deal_id={off}+t.id::bigint)
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
            RETURNING login)
          SELECT COALESCE(array_agg(DISTINCT login),'{{}}') FROM ins""")).scalar()
        db.commit()
        affected = list(rows) if rows else []
        log(f"new transactions for {len(affected)} logins")
        if affected:
            # #2 dedup: flag NEW legacy rows that duplicate an existing MT deposit/withdrawal
            # (same login+type+amount+day) so the same money isn't counted twice. Reversible (_dup).
            db.execute(text("""UPDATE transactions l SET tx_type=l.tx_type||'_dup'
                WHERE l.deal_id>=8000000000 AND l.tx_type IN ('deposit','withdrawal') AND l.login=ANY(:lg)
                  AND EXISTS (SELECT 1 FROM transactions m WHERE m.deal_id<8000000000 AND m.tx_type=l.tx_type
                     AND m.login=l.login AND round(m.amount::numeric,2)=round(l.amount::numeric,2)
                     AND left(m.tx_date,10)=left(l.tx_date,10))"""), {"lg": affected})
            db.commit()
            db.execute(text(f"""WITH agg AS (SELECT login,
                ROUND(SUM(amount) FILTER (WHERE tx_type='deposit' AND amount<1000000
                  AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust')::numeric,2) dep,
                ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000)::numeric,2) wd
                FROM transactions WHERE login = ANY(:lg) GROUP BY login)
              UPDATE clients c SET total_deposits=COALESCE(agg.dep,0), total_withdrawals=COALESCE(agg.wd,0)
              FROM agg WHERE agg.login=c.login"""), {"lg": affected})
            db.commit()
            db.execute(text("""WITH ct AS (SELECT customer_no, sum(total_deposits) dep, sum(total_withdrawals) wd
                FROM clients WHERE customer_no IN (SELECT DISTINCT customer_no FROM clients WHERE login = ANY(:lg))
                GROUP BY customer_no)
              UPDATE customers cu SET total_deposits=ROUND(COALESCE(ct.dep,0)::numeric,2),
                total_withdrawals=ROUND(COALESCE(ct.wd,0)::numeric,2),
                kind=CASE WHEN COALESCE(ct.dep,0)>0 THEN 'client' ELSE cu.kind END,
                kyc_status=CASE WHEN COALESCE(ct.dep,0)>0 THEN 'verified' ELSE cu.kyc_status END
              FROM ct WHERE ct.customer_no=cu.customer_no"""), {"lg": affected})
            db.commit()
            log("totals updated for affected customers")

        # #2b RACE DEDUP (runs EVERY cycle, not just on new imports): a gateway deposit/withdrawal
        # can land as BOTH a TradeSoft-import row (8e9+) AND an MT deal. The MT deal often arrives
        # AFTER the TS import and on a DIFFERENT calendar day, so the import-time dedup above (same-day
        # string match, only for that cycle's logins) misses it. Re-check RECENT rows on the PARSED
        # timestamp (±1 day) and flag the TS row *_dup (reversible) — keep the MT deal.
        # NOTE: match BOTH MT5 (deal_id<4e9) AND MT4 (4e9-8e9), i.e. deal_id<8e9. The MT4 case was the
        # gap that left ~840 Sham-Cash/Qi/Wallet duplicates double-counted (fixed Jun 30 2026); MT4
        # deposits come from the journal and routinely arrive a day late, so they need this pass too.
        # 30-day lookback so a late MT4 journal pull still gets deduped.
        dre = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}"
        deduped = []
        for _k in ("deposit", "withdrawal"):
            r2 = db.execute(text(f"""
              WITH d AS (
                UPDATE transactions ts SET tx_type=ts.tx_type||'_dup'
                WHERE ts.deal_id>=8000000000 AND ts.deal_id<9000000000 AND ts.tx_type='{_k}'
                  AND ts.tx_date > to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD') AND ts.tx_date ~ :re
                  AND EXISTS (SELECT 1 FROM transactions mt WHERE mt.deal_id<8000000000 AND mt.tx_type='{_k}'
                     AND mt.login=ts.login AND mt.tx_date ~ :re
                     AND round(mt.amount::numeric,2)=round(ts.amount::numeric,2)
                     AND abs(EXTRACT(EPOCH FROM (mt.tx_date::timestamp - ts.tx_date::timestamp))) < 86400)
                RETURNING login)
              SELECT COALESCE(array_agg(DISTINCT login),'{{}}') FROM d"""), {"re": dre}).scalar()
            deduped += list(r2) if r2 else []
            db.commit()
        deduped = list(set(deduped))
        if deduped:
            log(f"race-dedup: flagged late MT/TS duplicates for {len(deduped)} logins")
            db.execute(text("""WITH agg AS (SELECT login,
                ROUND(SUM(amount) FILTER (WHERE tx_type='deposit' AND amount<1000000
                  AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust')::numeric,2) dep,
                ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000)::numeric,2) wd
                FROM transactions WHERE login = ANY(:lg) GROUP BY login)
              UPDATE clients c SET total_deposits=COALESCE(agg.dep,0), total_withdrawals=COALESCE(agg.wd,0)
              FROM agg WHERE agg.login=c.login"""), {"lg": deduped})
            db.execute(text("UPDATE client_tx_agg_meta SET refreshed_at='2000-01-01' WHERE id=1"))
            db.commit()

        # #2c ONE-TO-ONE re-dedup: the ±1-day match above misses slow-settling crypto (MT credit lands
        # days after the TS row) and can over-flag genuine same-amount repeats. redup_engine re-pairs
        # each TS row to the NEAREST unused MT deal within ±7 days, one-to-one — fixing both. Idempotent.
        try:
            import redup_engine
            rd, ru = redup_engine.run()
            if rd or ru:
                log(f"one-to-one re-dedup: +{rd} dup / -{ru} un-dup")
                db.execute(text("UPDATE client_tx_agg_meta SET refreshed_at='2000-01-01' WHERE id=1")); db.commit()
        except Exception as e:
            log(f"redup_engine error: {e}")

        # CLIENT RULE: a real depositor is a client (kept above). Also ensure every TradeSoft
        # client is marked client. PROMOTE-ONLY — never demote a depositor back to lead.
        db.execute(text(f"""UPDATE customers cu SET kind='client'
            WHERE kind<>'client' AND legacy_user_id IN (SELECT user_id FROM {L}.fx_clients_view WHERE deleted_at IS NULL)"""))
        db.commit()
        log("kind: TradeSoft clients + depositors marked client")
        # #3/#4/#5: enrich new leads (campaign/city/sales/IB/date) + client sales agent + IB + notes
        try:
            import enrich_tradesoft
            enrich_tradesoft.enrich(db)
            log("enriched leads + client sales/IB")
        except Exception as e:
            db.rollback(); log(f"enrich error: {e}")
        # Mirror agent reassignments made in TradeSoft (sales→retention when a lead deposits &
        # becomes a client): update our agent + comment the client + log from→to (source=TradeSoft).
        try:
            import sync_agent_from_tradesoft as SAT
            res = SAT.sync_agent_changes(db)
            log(f"agent sync from TradeSoft: {res.get('changed',0)} client(s) reassigned")
        except Exception as e:
            db.rollback(); log(f"agent sync error: {e}")
        # Document the sales→retention handover on deposit for newly-converted clients whose current
        # (retention) agent already matches but has no timeline comment — reconstructs the OLD sales
        # agent from the matched lead. Comment + log only; never changes the agent assignment.
        try:
            import backfill_lead_retention_handover as BLRH
            hres = BLRH.backfill(db)
            log(f"lead→retention handover documented: {hres.get('documented',0)} client(s)")
        except Exception as e:
            db.rollback(); log(f"handover doc error: {e}")
        maybe_load_contacts()
        log("=== sync done ===")
    except Exception as e:
        db.rollback(); log(f"reconcile ERROR: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
