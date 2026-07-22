# -*- coding: utf-8 -*-
"""
backfill_closed_ts_accounts.py — create ARCHIVED client rows for closed TradeSoft accounts
that have deposit/withdrawal history in `transactions` but no `clients` row (they closed before
our MT import window, so the account importer never saw them). Without a clients row their
money can't roll up to `customers`, under-counting depositors by ~7.4k customers / ~$30M.

Rows are created is_archived=TRUE / is_active=FALSE with a clear archive_reason, linked to the
right person via tradesoft_old.fx_accounts_view.account_number -> user_id -> customers.legacy_user_id.
Totals are then filled by update_client_totals.full_refresh(). Idempotent (ON CONFLICT login).
"""
import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import engine
from sqlalchemy import text
import update_client_totals as UCT

with engine.begin() as conn:
    n = conn.execute(text("""
        WITH missing AS (              -- tx logins with NO clients row
            SELECT DISTINCT t.login FROM transactions t
            LEFT JOIN clients c ON c.login = t.login
            WHERE c.login IS NULL AND t.login IS NOT NULL AND t.login <= 2147483647
        ),
        mapped AS (                    -- one TS account row per login -> its customer
            SELECT DISTINCT ON (m.login) m.login, cu.customer_no, cu.name, cu.email, cu.phone, cu.country
            FROM missing m
            JOIN tradesoft_old.fx_accounts_view av ON av.account_number = m.login::text
            JOIN customers cu ON cu.legacy_user_id = av.user_id
            ORDER BY m.login, av.id
        ),
        ins AS (
            INSERT INTO clients (login, customer_no, name, email, phone, country, source,
                                 is_active, is_archived, archived_at, archive_reason, created_at, updated_at)
            SELECT login, customer_no, name, email, phone, country, 'tradesoft',
                   FALSE, TRUE, NOW(),
                   'closed TradeSoft account — created for deposit-history rollup (Jul 2026)',
                   NOW(), NOW()
            FROM mapped
            ON CONFLICT (login) DO NOTHING
            RETURNING 1)
        SELECT count(*) FROM ins""")).scalar()
    print(f"archived client rows created: {n:,}")
    ncl, ncu = UCT.full_refresh(conn)
    print(f"after refresh: {ncl:,} client logins with deposits | {ncu:,} customers with deposits")
