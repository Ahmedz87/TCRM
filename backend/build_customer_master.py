"""
build_customer_master.py — DRY-RUN planner for the TradeSoft reconciliation.
Read-only: computes exactly what the reconciliation WOULD do, no writes.

Rules (TradeSoft = source of truth):
  - CUS customer id per legacy user_id (the person); reused across all their accounts + lead/client.
  - match by login (accounts) / user_id (people) -> update, never duplicate.
  - classification follows TradeSoft: fx_clients_view -> clients, fx_leads_view -> leads.
  - trading account active if its login is on MT now (in our live `clients`), else -> archive.
"""
from sqlalchemy import text
from database import SessionLocal
L = "tradesoft_old"


def run():
    db = SessionLocal()
    try:
        # ---- PEOPLE: every legacy user gets a CUS ----
        users = db.execute(text(f"SELECT count(*) FROM {L}.fx_users_view WHERE id ~ '^[0-9]+$'")).scalar()
        clients_u = db.execute(text(f"SELECT count(DISTINCT user_id) FROM {L}.fx_clients_view WHERE deleted_at IS NULL")).scalar()
        leads_u = db.execute(text(f"""SELECT count(DISTINCT user_id) FROM {L}.fx_leads_view ll
            WHERE deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM {L}.fx_clients_view c
              WHERE c.user_id=ll.user_id AND c.deleted_at IS NULL)""")).scalar()
        print("PEOPLE -> CUS ids")
        print(f"   legacy persons (fx_users_view) ......... {users:,}")
        print(f"   classified CLIENT (in fx_clients_view) . {clients_u:,}")
        print(f"   classified LEAD   (leads, not client) .. {leads_u:,}")

        # ---- TRADING ACCOUNTS: active (on MT) vs archive ----
        db.execute(text(f"""CREATE TEMP TABLE ta AS
          SELECT DISTINCT a.account_number::bigint login, a.user_id
          FROM {L}.fx_accounts_view a
          WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$'
            AND COALESCE(a.account_group,'') NOT ILIKE '%demo%'"""))
        db.execute(text("CREATE INDEX ON ta(login)"))
        tot = db.execute(text("SELECT count(*) FROM ta")).scalar()
        active = db.execute(text("SELECT count(*) FROM ta WHERE EXISTS(SELECT 1 FROM clients c WHERE c.login=ta.login)")).scalar()
        print("\nTRADING ACCOUNTS (TradeSoft real, non-demo)")
        print(f"   total .................................. {tot:,}")
        print(f"   ON MT now (in live clients) -> active .. {active:,}")
        print(f"   NOT on MT -> ARCHIVE ................... {tot-active:,}")

        # ---- EXISTING live CRM rows: matched to a legacy person (get CUS) vs not ----
        live_clients = db.execute(text("SELECT count(*) FROM clients")).scalar()
        live_matched = db.execute(text(f"""SELECT count(*) FROM clients c
            WHERE EXISTS(SELECT 1 FROM {L}.fx_accounts_view a
              WHERE a.account_number ~ '^[0-9]+$' AND a.account_number::bigint=c.login)""")).scalar()
        print("\nEXISTING LIVE CRM (no duplication)")
        print(f"   live client accounts ................... {live_clients:,}")
        print(f"   found in TradeSoft (reconcile+CUS) ..... {live_matched:,}")
        print(f"   live-only, not in TradeSoft (new CUS) .. {live_clients-live_matched:,}")

        # ---- CONFLICTS to fix from TradeSoft (sample: IB/agent present in legacy) ----
        legacy_acct_with_agent = db.execute(text(f"""SELECT count(*) FROM {L}.fx_accounts_view a
            WHERE a.deleted_at IS NULL AND a.account_number ~ '^[0-9]+$' AND a.agent ~ '^[0-9]+$'
              AND EXISTS(SELECT 1 FROM clients c WHERE c.login=a.account_number::bigint)""")).scalar()
        print("\nRECONCILE (TradeSoft authoritative)")
        print(f"   live accounts whose IB/agent comes from TradeSoft: {legacy_acct_with_agent:,}")
        print("   (sales agent / IB / deposits / withdrawals overwritten from TradeSoft where they differ)")

        print("\n--- DRY RUN: nothing written. Review, then I commit in phases with a backup. ---")
    finally:
        db.close()


if __name__ == "__main__":
    run()
