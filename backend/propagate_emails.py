"""
propagate_emails.py — backfill missing emails across clients, trading_accounts and ibs by
LINKING the same person across their accounts and matched leads.

Most MT4 accounts carry an email; most MT5 accounts do not. The same person frequently holds
both (and/or exists as a lead, which always has an email). We key on the normalized phone
(last 9 digits — the SAME key auto_match uses) to copy a known email onto the person's
email-less accounts.

Email source priority per phone-key:
  1) another CLIENT account that already has an email  (covers MT4 -> MT5 same person)
  2) a matched LEAD email                              (leads are 100% emailed)

Then propagates the resulting client emails to:
  - trading_accounts  (by login)
  - ibs               (by the IB's own login = ibs.agent_id, then phone fallback)

ADDITIVE ONLY: never overwrites an existing non-empty email. Idempotent / re-runnable.
"""
import psycopg2
import db_config

PG_DSN = db_config.DSN

# normalized phone key = last 9 digits of the digits-only phone (NULL if too short)
def p9(col):
    return f"NULLIF(RIGHT(regexp_replace(COALESCE({col},''),'[^0-9]','','g'),9),'')"


def main():
    cn = psycopg2.connect(PG_DSN)
    cn.autocommit = False
    cur = cn.cursor()

    def scalar(sql):
        cur.execute(sql)
        return cur.fetchone()[0]

    HAS = "email IS NOT NULL AND email<>''"
    print("=== BEFORE ===")
    for tbl in ("clients", "trading_accounts", "ibs"):
        print(f"  {tbl:18s} {scalar(f'SELECT COUNT(*) FROM {tbl} WHERE {HAS}'):>7,} / "
              f"{scalar(f'SELECT COUNT(*) FROM {tbl}'):>7,}")

    # ── build phone-key -> email map (clients first, then leads for new keys) ──
    cur.execute(f"""
        CREATE TEMP TABLE email_map AS
        SELECT {p9('phone')} AS p9, MIN(email) AS email
        FROM clients
        WHERE {HAS} AND {p9('phone')} IS NOT NULL
        GROUP BY {p9('phone')}
    """)
    cur.execute(f"""
        INSERT INTO email_map (p9, email)
        SELECT lp9, MIN(email) FROM (
            SELECT {p9('phone')} AS lp9, email
            FROM leads WHERE {HAS}
        ) z
        WHERE lp9 IS NOT NULL AND lp9 NOT IN (SELECT p9 FROM email_map)
        GROUP BY lp9
    """)
    cur.execute("CREATE INDEX ix_email_map_p9 ON email_map(p9)")
    map_size = scalar("SELECT COUNT(*) FROM email_map")
    print(f"\nphone->email map keys: {map_size:,}")

    # ── 1) clients ──
    cur.execute(f"""
        UPDATE clients c SET email = m.email
        FROM email_map m
        WHERE (c.email IS NULL OR c.email='') AND {p9('c.phone')} = m.p9
    """)
    print(f"clients backfilled:          {cur.rowcount:,}")

    # ── 2) trading_accounts: from clients by login, then phone map ──
    cur.execute("""
        UPDATE trading_accounts ta SET email = c.email
        FROM clients c
        WHERE ta.login = c.login AND c.email IS NOT NULL AND c.email<>''
          AND (ta.email IS NULL OR ta.email='')
    """)
    n1 = cur.rowcount
    cur.execute(f"""
        UPDATE trading_accounts ta SET email = m.email
        FROM email_map m
        WHERE (ta.email IS NULL OR ta.email='') AND {p9('ta.phone')} = m.p9
    """)
    print(f"trading_accounts backfilled: {n1 + cur.rowcount:,}")

    # ── 3) ibs: IB's own client account (login = agent_id), then phone map ──
    cur.execute("""
        UPDATE ibs i SET email = c.email
        FROM clients c
        WHERE c.login = i.agent_id AND c.email IS NOT NULL AND c.email<>''
          AND (i.email IS NULL OR i.email='')
    """)
    n2 = cur.rowcount
    cur.execute(f"""
        UPDATE ibs i SET email = m.email
        FROM email_map m
        WHERE (i.email IS NULL OR i.email='') AND {p9('i.phone')} = m.p9
    """)
    print(f"ibs backfilled:              {n2 + cur.rowcount:,}")

    cn.commit()

    print("\n=== AFTER ===")
    for tbl in ("clients", "trading_accounts", "ibs"):
        print(f"  {tbl:18s} {scalar(f'SELECT COUNT(*) FROM {tbl} WHERE {HAS}'):>7,} / "
              f"{scalar(f'SELECT COUNT(*) FROM {tbl}'):>7,}")
    cn.close()
    print("\nDone (additive, no existing emails overwritten).")


if __name__ == "__main__":
    main()
