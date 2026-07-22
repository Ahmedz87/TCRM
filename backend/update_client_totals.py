# -*- coding: utf-8 -*-
"""
update_client_totals.py — FULL refresh of clients.total_deposits / total_withdrawals /
net_deposit from the transactions truth, then roll up to customers.

WHY (bug found Jul 2026): tradesoft_sync only refreshed totals for logins touched by THAT
cycle's TradeSoft import — deposits arriving via the MT5 bridge / MT4 journal never refreshed
their login's totals. Result: 6,618 logins ($18.4M of real deposits) showed total_deposits=0,
which under-counted depositors everywhere (Clients page, Sales report, Wati attributes,
customer 'client' kind). This script recomputes EVERY login (full agg is ~0.3s on the PG18 box)
and is also called at the end of every tradesoft_sync cycle so it can't go stale again.

CANONICAL FORMULA (keep all three places in sync: here, tradesoft_sync incremental blocks,
transactions_router NOT_INTERNAL_SQL):
  deposits    = SUM(amount)  tx_type='deposit'    AND amount<1e6
                AND notes !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'
  withdrawals = SUM(amount)  tx_type='withdrawal' AND amount<1e6 AND status<>'rejected'
(_dup / balance_fix / negative_cover / withdrawal_revert rows are already excluded by tx_type.)

Run:  python update_client_totals.py
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text

DEP_FILTER = ("tx_type='deposit' AND amount<1000000 "
              "AND COALESCE(notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'")
WD_FILTER = "tx_type='withdrawal' AND amount<1000000 AND COALESCE(status,'')<>'rejected'"


def full_refresh(conn):
    """Recompute totals for ALL logins + roll up to customers. Returns (clients>0, customers>0)."""
    # identify as the authoritative totals writer: the clients_totals_guard DB trigger blocks
    # every OTHER connection from LOWERING total_deposits/total_withdrawals (defends against the
    # ghost writer that kept zeroing totals — see memory note). Only this app name may correct down.
    conn.execute(text("SET application_name = 'totals_refresh'"))
    conn.execute(text(f"""
        UPDATE clients c SET
            total_deposits    = COALESCE(sub.dep, 0),
            total_withdrawals = COALESCE(sub.wd, 0),
            net_deposit       = COALESCE(sub.dep, 0) - COALESCE(sub.wd, 0)
        FROM (
            SELECT login,
                   ROUND(SUM(amount) FILTER (WHERE {DEP_FILTER})::numeric, 2) dep,
                   ROUND(SUM(amount) FILTER (WHERE {WD_FILTER})::numeric, 2) wd
            FROM transactions GROUP BY login
        ) sub
        WHERE c.login = sub.login
          AND (c.total_deposits    IS DISTINCT FROM COALESCE(sub.dep,0)
            OR c.total_withdrawals IS DISTINCT FROM COALESCE(sub.wd,0))
    """))
    # customers rollup (person grain) — same promotion rules tradesoft_sync uses
    conn.execute(text("""
        WITH ct AS (SELECT customer_no, SUM(total_deposits) dep, SUM(total_withdrawals) wd
                    FROM clients WHERE customer_no IS NOT NULL GROUP BY customer_no)
        UPDATE customers cu SET
            total_deposits    = ROUND(COALESCE(ct.dep,0)::numeric, 2),
            total_withdrawals = ROUND(COALESCE(ct.wd,0)::numeric, 2),
            kind       = CASE WHEN COALESCE(ct.dep,0) > 0 THEN 'client'  ELSE cu.kind       END,
            kyc_status = CASE WHEN COALESCE(ct.dep,0) > 0 THEN 'verified' ELSE cu.kyc_status END
        FROM ct WHERE ct.customer_no = cu.customer_no
          AND (cu.total_deposits    IS DISTINCT FROM ROUND(COALESCE(ct.dep,0)::numeric,2)
            OR cu.total_withdrawals IS DISTINCT FROM ROUND(COALESCE(ct.wd,0)::numeric,2))
    """))
    # the Clients-list precompute reads client_tx_agg — mark it stale so it rebuilds
    try:
        conn.execute(text("UPDATE client_tx_agg_meta SET refreshed_at='2000-01-01' WHERE id=1"))
    except Exception:
        pass
    ncl = conn.execute(text("SELECT COUNT(*) FROM clients WHERE total_deposits > 0")).scalar()
    ncu = conn.execute(text("SELECT COUNT(*) FROM customers WHERE COALESCE(total_deposits,0) > 0")).scalar()
    return ncl, ncu


if __name__ == "__main__":
    import time
    # the live MT5 bridge bulk-updates clients concurrently — retry through deadlocks
    for attempt in range(1, 6):
        try:
            with engine.begin() as conn:
                before_cl = conn.execute(text("SELECT COUNT(*) FROM clients WHERE COALESCE(total_deposits,0) > 0")).scalar()
                before_cu = conn.execute(text("SELECT COUNT(*) FROM customers WHERE COALESCE(total_deposits,0) > 0")).scalar()
                ncl, ncu = full_refresh(conn)
                print(f"client logins with deposits: {before_cl:,} -> {ncl:,}")
                print(f"customers with deposits:     {before_cu:,} -> {ncu:,}")
            print("Full totals refresh done.")
            break
        except Exception as e:
            if "deadlock" in str(e).lower() and attempt < 5:
                print(f"deadlock with live sync (attempt {attempt}) — retrying in 30s")
                time.sleep(30)
            else:
                raise
