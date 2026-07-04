"""refresh.py — pull the latest TradeSoft data into the standalone tradesoft_crm DB.

Self-contained for this project: connects DIRECTLY to the legacy Workice/TradeSoft
MySQL views and reloads each into tradesoft_crm, then re-derives contact enrichment.
Does NOT depend on the main broker_crm mirror (broker_crm is only read, by the
enrichment step, to recover email/phone by MT login).

Availability-safe: each table is loaded into a `<t>__new` staging table, then swapped
in atomically (DROP old + RENAME) so the running CRM always sees a complete table —
never an empty/half-loaded one. Indexes are rebuilt right after each swap.

Usage:  python refresh.py            # one full refresh
Driven hourly by the TradeSoftCRM-Refresh scheduled task (see run_refresh.cmd).
"""
import sys, io, time, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pymysql
import pymysql.cursors
import psycopg2
from psycopg2.extras import execute_values

# ── secrets (gitignored _secrets.py) ────────────────────────────────────────
import _secrets

# ── SOURCE (legacy MySQL views) ─────────────────────────────────────────────
MY = dict(_secrets.MYSQL_SRC)

# ── DESTINATION (standalone Postgres copy) ──────────────────────────────────
PG_DSN = _secrets.PG_DSN

VIEWS = ["fx_users_view", "fx_clients_view", "fx_leads_view",
         "fx_accounts_view", "fx_transactions_view"]

# columns to index per table (stable names ix_<table>_<cols>, rebuilt after each swap)
INDEXES = {
    "fx_users_view":        [["id"], ["type"]],
    "fx_clients_view":      [["user_id"], ["owner"], ["deleted_at"]],
    "fx_leads_view":        [["user_id"], ["sales_rep"], ["deleted_at"]],
    "fx_accounts_view":     [["user_id"], ["account_number"], ["deleted_at"]],
    "fx_transactions_view": [["user_id"], ["account_number"], ["deleted_at"]],
}
BATCH = 2000


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def normalize(v):
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "replace")
        except Exception:
            return v.hex()
    return str(v)


def reload_table(my, pg, t):
    mc = my.cursor()
    # column order from the source view
    mc.execute("""SELECT column_name FROM information_schema.columns
                  WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position""",
               (MY["database"], t))
    cols = [r[0] for r in mc.fetchall()]
    if not cols:
        log(f"  ! {t}: no columns, skipped")
        return 0

    pc = pg.cursor()
    stg = f"{t}__new"
    pc.execute(f"DROP TABLE IF EXISTS {ident(stg)}")
    pc.execute(f"CREATE TABLE {ident(stg)} ({', '.join(ident(c)+' text' for c in cols)})")
    pg.commit()

    # stream rows (server-side cursor = constant memory)
    insert_sql = f"INSERT INTO {ident(stg)} ({', '.join(ident(c) for c in cols)}) VALUES %s"
    sc = my.cursor(pymysql.cursors.SSCursor)
    sc.execute(f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{t}`")
    loaded, buf = 0, []
    while True:
        row = sc.fetchone()
        if row is None:
            break
        buf.append(tuple(normalize(v) for v in row))
        if len(buf) >= BATCH:
            execute_values(pc, insert_sql, buf)
            loaded += len(buf); buf = []
    if buf:
        execute_values(pc, insert_sql, buf)
        loaded += len(buf)
    sc.close()
    pg.commit()

    # atomic swap: old table is replaced in one transaction
    pc.execute("BEGIN")
    pc.execute(f"DROP TABLE IF EXISTS {ident(t)}")
    pc.execute(f"ALTER TABLE {ident(stg)} RENAME TO {ident(t)}")
    pg.commit()

    # rebuild indexes (old ones dropped with the old table → names are free)
    for colset in INDEXES.get(t, []):
        ixname = "ix_" + t.replace("fx_", "").replace("_view", "") + "_" + "_".join(colset)
        pc.execute(f"CREATE INDEX {ident(ixname[:63])} ON {ident(t)} ({', '.join(ident(c) for c in colset)})")
    pg.commit()
    return loaded


def enrich_contacts(pg):
    """Recover email/phone from broker_crm.clients by MT login (account_number)."""
    try:
        bc = psycopg2.connect(_secrets.BROKER_LOCAL_DSN)
    except Exception as e:
        log(f"  enrichment skipped (broker_crm unreachable): {e}")
        return 0
    b, t = bc.cursor(), pg.cursor()
    b.execute("SELECT login::text, NULLIF(email,''), NULLIF(phone,'') FROM clients WHERE login IS NOT NULL")
    login2c = {str(lg).strip(): (em, ph) for lg, em, ph in b.fetchall()}
    t.execute("SELECT user_id, account_number FROM fx_accounts_view "
              "WHERE account_number IS NOT NULL AND account_number <> ''")
    ue, up = {}, {}
    for uid, acc in t.fetchall():
        c = login2c.get(str(acc).strip())
        if not c:
            continue
        if c[0] and uid not in ue:
            ue[uid] = c[0]
        if c[1] and uid not in up:
            up[uid] = c[1]
    uids = set(ue) | set(up)
    t.execute("""CREATE TABLE IF NOT EXISTS contact_enrichment (
                   user_id text PRIMARY KEY, email text, phone text,
                   source text DEFAULT 'broker_crm_login_match')""")
    # small table → in-txn truncate+insert is fine (atomic for readers)
    t.execute("BEGIN")
    t.execute("TRUNCATE contact_enrichment")
    execute_values(t, "INSERT INTO contact_enrichment (user_id, email, phone) VALUES %s",
                   [(u, ue.get(u), up.get(u)) for u in uids])
    pg.commit()
    bc.close()
    return len(uids)


def main():
    t0 = time.time()
    log("=== refresh start ===")
    my = pymysql.connect(**MY)
    pg = psycopg2.connect(PG_DSN)
    pg.autocommit = False
    total = 0
    for t in VIEWS:
        n = reload_table(my, pg, t)
        total += n
        log(f"  ✓ {t:24s} {n:>10,} rows")
    ec = enrich_contacts(pg)
    log(f"  ✓ contact_enrichment      {ec:>10,} people")
    my.close(); pg.close()
    log(f"=== refresh done: {total:,} rows in {time.time()-t0:.0f}s ===")


if __name__ == "__main__":
    main()
