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
        try:                               # fill new leads' email/phone from the FULL fx_leads
            import backfill_lead_contacts
            backfill_lead_contacts.run(db)
        except Exception as e:
            db.rollback(); log(f"lead-contacts backfill skipped: {e}")
        try:                               # add NEW IBs — IB-group accounts (MT5 IB\IB-*, MT4
            import backfill_new_ibs         # TNFX-IB-*) that build_ibs misses until they refer a
            _nib = backfill_new_ibs.run()   # client. Uses its own conn; won't poison `db`.
            if _nib:
                log(f"new IBs added: {_nib}")
        except Exception as e:
            db.rollback(); log(f"new-IB backfill skipped: {e}")
        try:                               # #233: MT-native accounts opened directly on the
            import heal_mt_native_customers as HMN   # trading server have no TradeSoft customer_no,
            _hm = HMN.heal(db)             # so no customer-master row -> invisible on the Clients
            if _hm.get("masters_created"): # page. Create the missing master rows so they show up.
                log(f"MT-native customers healed: +{_hm['masters_created']} master rows")
        except Exception as e:
            db.rollback(); log(f"MT-native heal skipped: {e}")
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
              COALESCE(NULLIF(t.currency,''),'USD'),
              COALESCE(NULLIF(NULLIF(t.payment_method,''),'0'),'TradeSoft'),
              -- TIMESTAMPS AT FACE VALUE (desk rule Jul 15 2026): keep TradeSoft's own stamp
              -- exactly as its UI shows it, like MT rows keep MT's stamp. The desk reconciles
              -- against those displays; do NOT shift clocks here (a -3h "normalization" was
              -- tried and REVERTED — see memory reporting-timezone-iraq).
              'approved', COALESCE(NULLIF(t.note,''),'TradeSoft import'), t.created_at, left(t.created_at,7),
              NULLIF(t.created_at,'')::timestamptz, NOW()
            FROM {L}.fx_transactions_view t
            WHERE t.deleted_at IS NULL AND t.status='completed' AND t.account_number ~ '^[0-9]+$'
              AND {A}>0 AND {A}<1000000
              -- method-0 deposits: usually system credits, EXCEPT small ones on clean Live accounts
              -- (not demo/NDA/contest) — real client money the gateway didn't record (scooter8exo
              -- $98 case, Jul 2026). Forensics showed larger/round method-0 amounts are mostly
              -- internal credits (repeated exact-$20k rows, no MT match), so only <=$1,000 auto-
              -- imports; anything larger needs desk review (see quarantine_ts_deposits.py tiers).
              AND ((t.type='deposit' AND COALESCE(t.payment_method,'')<>'0')
                   OR t.type IN ('withdrawal','transfer')
                   OR (t.type='deposit' AND COALESCE(t.payment_method,'')='0' AND {A}<=1000
                       AND EXISTS (SELECT 1 FROM {L}.fx_accounts_view av
                                   WHERE av.account_number=t.account_number AND av.account_type='Live'
                                     AND COALESCE(av.is_nda,'0')<>'1' AND av.contest_joined_date IS NULL)))
              AND NOT EXISTS (SELECT 1 FROM transactions e WHERE e.deal_id={off}+t.id::bigint)
            ON CONFLICT (deal_id) WHERE deal_id IS NOT NULL DO NOTHING
            RETURNING login)
          SELECT COALESCE(array_agg(DISTINCT login),'{{}}') FROM ins""")).scalar()
        db.commit()
        affected = list(rows) if rows else []
        log(f"new transactions for {len(affected)} logins")
        if affected:
            # #2 dedup: flag NEW legacy rows that duplicate an existing MT deposit/withdrawal/
            # internal transfer (same login+type+amount+day) so the same money isn't counted or
            # shown twice. Reversible (_dup). Transfers included since Jul 2026 (a TS 'transfer_from'
            # copy has NO counterparty, so it showed as a second blank from/to row in the profile).
            db.execute(text("""UPDATE transactions l SET tx_type=l.tx_type||'_dup'
                WHERE l.deal_id>=8000000000 AND l.tx_type IN ('deposit','withdrawal','internal_transfer') AND l.login=ANY(:lg)
                  AND EXISTS (SELECT 1 FROM transactions m WHERE m.deal_id<8000000000 AND m.tx_type=l.tx_type
                     AND m.login=l.login AND round(m.amount::numeric,2)=round(l.amount::numeric,2)
                     AND left(m.tx_date,10)=left(l.tx_date,10))"""), {"lg": affected})
            db.commit()
            db.execute(text(f"""WITH agg AS (SELECT login,
                ROUND(SUM(amount) FILTER (WHERE tx_type='deposit' AND amount<1000000
                  AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust')::numeric,2) dep,
                ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000 AND COALESCE(status,'')<>'rejected')::numeric,2) wd
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

            # capture the RECEIVING CARD (name_on_card + card number) from the TradeSoft extra_details
            # into transaction_wallet, so the Transactions details can show "Card receiver name" and the
            # back-office "Card holder name" (resolved from payment_cards). Idempotent (ON CONFLICT NOTHING).
            try:
                off = R.OFF if hasattr(R, "OFF") else 8_000_000_000
                cw = db.execute(text(f"""
                  INSERT INTO transaction_wallet (transaction_id, card_name, receiver_acct, method, source)
                  SELECT t.id,
                    (regexp_match(fx.extra_details,'name_on_card''?"\\s*:\\s*"([^"]+)'))[1],
                    (regexp_match(fx.extra_details,'wallet_id[^0-9]*([0-9]+)'))[1],
                    t.method, 'tradesoft_card'
                  FROM transactions t
                  JOIN {L}.fx_transactions_view fx ON fx.id = (t.deal_id - {off})::text
                  WHERE t.login = ANY(:lg) AND t.deal_id >= {off} AND t.deal_id < {off}+1000000000
                    AND t.tx_type IN ('deposit','deposit_dup')
                    AND fx.extra_details ~ 'wallet_id'
                    AND (regexp_match(fx.extra_details,'wallet_id[^0-9]*([0-9]+)'))[1] IS NOT NULL
                  ON CONFLICT (transaction_id) DO NOTHING
                """), {"lg": affected})
                db.commit()
                if cw.rowcount:
                    log(f"card-info captured for {cw.rowcount} TradeSoft deposit(s)")
            except Exception as e:
                db.rollback(); log(f"card-info capture skipped: {e}")

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
                ROUND(SUM(amount) FILTER (WHERE tx_type='withdrawal' AND amount<1000000 AND COALESCE(status,'')<>'rejected')::numeric,2) wd
                FROM transactions WHERE login = ANY(:lg) GROUP BY login)
              UPDATE clients c SET total_deposits=COALESCE(agg.dep,0), total_withdrawals=COALESCE(agg.wd,0)
              FROM agg WHERE agg.login=c.login"""), {"lg": deduped})
            db.execute(text("UPDATE client_tx_agg_meta SET refreshed_at='2000-01-01' WHERE id=1"))
            db.commit()

        # #2b-2 SELF-HEAL classifier leaks: the real-time mt5_deal_worker keeps a cached copy of the
        # classifier, so until it's restarted it can still insert reverting-withdraws / internal ops as
        # 'deposit'. Reclassify any recent ones each cycle so totals never drift. Idempotent + reversible.
        try:
            r1 = db.execute(text("""UPDATE transactions SET tx_type='withdrawal_revert', updated_at=NOW()
                WHERE tx_type IN ('deposit','deposit_dup') AND notes ~* 'revert.*withdraw'
                  AND tx_date > to_char(NOW() - INTERVAL '20 days','YYYY-MM-DD')""")).rowcount
            r2 = db.execute(text(r"""UPDATE transactions
                SET tx_type=CASE WHEN notes ~* 'negative\s*balance' THEN 'negative_cover' ELSE 'balance_fix' END, updated_at=NOW()
                WHERE tx_type IN ('deposit','deposit_dup') AND method='MT5'
                  AND notes ~* '(negative\s*balance|stop\s*out|deposit\s*fix|balance\s*fix|deposit\s*fee|cash\s*back|abus|\ysync\y)'
                  AND tx_date > to_char(NOW() - INTERVAL '20 days','YYYY-MM-DD')""")).rowcount
            # #2b-3 flag the ORIGINAL withdrawal of each recent revert as 'rejected' — a revert
            # means the money came back, so the withdrawal never really left; without this the
            # withdrawal totals over-count (July 2026 was ~$126k high). Greedy-all 1:1 matching,
            # idempotent — see revert_reject_engine docstring for why this pairing and not SQL.
            db.commit()
            import revert_reject_engine
            r3 = revert_reject_engine.run()
            if r1 or r2 or r3:
                log(f"classifier self-heal: {r1} revert(s) + {r2} internal reclassified out of deposits, "
                    f"{r3} reverted original withdrawal(s) flagged rejected")
                db.execute(text("UPDATE client_tx_agg_meta SET refreshed_at='2000-01-01' WHERE id=1")); db.commit()
        except Exception as e:
            db.rollback(); log(f"classifier self-heal skipped: {e}")

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
        # keep verbose ISO country names shortened for display (e.g. Syrian Arab Republic -> Syria)
        try:
            import normalize_countries
            normalize_countries.run()
        except Exception as e:
            db.rollback(); log(f"country normalize error: {e}")
        # FULL totals refresh EVERY cycle (bug fix Jul 2026): the incremental blocks above only
        # refresh logins touched by THIS cycle's TradeSoft import, so MT-sourced deposits (bridge /
        # MT4 journal) never refreshed their totals — 6,618 logins / $18.4M showed total_deposits=0.
        # The full agg is ~0.3s on the PG18 box, so just recompute everyone + customers rollup.
        try:
            from database import engine as _eng
            import update_client_totals as UCT
            with _eng.begin() as _conn:
                _ncl, _ncu = UCT.full_refresh(_conn)
            log(f"FULL totals refresh: {_ncl:,} client logins / {_ncu:,} customers with deposits")
        except Exception as e:
            db.rollback(); log(f"full totals refresh error: {e}")
        # normalize payment-method spelling variants -> canonical (Shamcash / Zaincash), so every
        # page shows ONE row per method. Idempotent (only touches non-canonical rows). Covers both
        # TradeSoft-imported and MT-comment-parsed methods.
        try:
            from database import engine as _eng2
            import normalize_methods as NM
            with _eng2.begin() as _conn:
                _res = NM.normalize(_conn)
            if any(_res.values()):
                log(f"method normalize: {_res}")
        except Exception as e:
            db.rollback(); log(f"method normalize error: {e}")
        # refresh deposit_documents + per-method pay tables (idempotent, additive) so NEW
        # deposits' receipts get picked up by the S3 nightly job (SFTP fetch -> Haiku
        # sender/receiver OCR -> transaction_wallet). Non-fatal.
        try:
            for scr in ("build_deposit_docs.py", "create_pay_method_tables.py"):
                r = subprocess.run([sys.executable, scr], cwd=BE,
                                   capture_output=True, text=True, timeout=900)
                tail = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
                log(f"{scr} exit={r.returncode} :: {tail}")
        except Exception as e:
            log(f"deposit-docs refresh error: {e}")
        log("=== sync done ===")
    except Exception as e:
        db.rollback(); log(f"reconcile ERROR: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
