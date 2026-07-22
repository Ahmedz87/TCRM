"""
heal_mt_native_customers.py — make MT-native client accounts visible on the Clients page.

WHY (ticket #233, Jul 2026): the Clients list is driven FROM the customer master
(`customers`, keyed by customer_no) LEFT JOIN clients. A brand-new trading account opened
directly on MT (not through TradeSoft) lands in `clients` with customer_no = NULL and has NO
`customers` master row, so it is structurally invisible on the Clients page even though it is a
real, live account — sales had to chase these in the old system. tradesoft_sync only *updates*
existing master rows to kind='client' (on deposit); it never *creates* a master for an
MT-native account. This closes that gap.

WHAT: for every real (non-retail/demo) client account that has a login but no matching customer
master, synthesize a customer_no ('MT'+login) when it has none, then INSERT a customers master
row (kind='client', source='mt_native'). Idempotent + additive (ON CONFLICT DO NOTHING; only
fills NULL customer_no). Safe to run every sync cycle.

Run standalone:  python heal_mt_native_customers.py
Wired into tradesoft_sync (phase 3) so new MT-native accounts appear within one cycle.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text

# a client account we should surface: has a login, and is not a retail/demo group
_REAL = ("c.login IS NOT NULL"
         " AND (c.group_name IS NULL OR (c.group_name NOT ILIKE '%retail%'"
         "      AND c.group_name NOT ILIKE '%demo%'))")


def heal(db) -> dict:
    """Create missing customer-master rows for MT-native client accounts. Returns counts."""
    # A. give a synthetic customer_no to accounts that have none yet
    synth = db.execute(text(f"""
        UPDATE clients c SET customer_no = 'MT'||c.login::text
        WHERE (c.customer_no IS NULL OR c.customer_no='') AND {_REAL}
          AND NOT EXISTS (SELECT 1 FROM customers cu WHERE cu.customer_no = c.customer_no)
    """)).rowcount
    # B. create the master rows (one per person = customer_no)
    created = db.execute(text(f"""
        INSERT INTO customers (customer_no, name, email, phone, country, kind, kyc_status,
                               source, n_accounts, total_deposits, total_withdrawals, created_at)
        SELECT c.customer_no, MIN(c.name), MIN(c.email), MIN(c.phone), MIN(c.country),
               'client', COALESCE(MIN(c.kyc_status),'pending'), 'mt_native', count(*),
               COALESCE(SUM(c.total_deposits),0), COALESCE(SUM(c.total_withdrawals),0), NOW()
        FROM clients c
        WHERE c.customer_no IS NOT NULL AND c.customer_no<>'' AND {_REAL}
          AND NOT EXISTS (SELECT 1 FROM customers cu WHERE cu.customer_no = c.customer_no)
        GROUP BY c.customer_no
        ON CONFLICT (customer_no) DO NOTHING
    """)).rowcount
    db.commit()
    return {"synthetic_customer_no": synth, "masters_created": created}


if __name__ == "__main__":
    import db_config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(db_config.SQLALCHEMY_URL, pool_pre_ping=True)
    db = sessionmaker(bind=eng)()
    try:
        res = heal(db)
        print(f"[heal_mt_native] synthetic customer_no set: {res['synthetic_customer_no']}, "
              f"masters created: {res['masters_created']}")
    finally:
        db.close()
