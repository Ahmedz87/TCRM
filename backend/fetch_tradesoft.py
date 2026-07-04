"""
fetch_tradesoft.py — full mirror of the legacy "Trade Soft - tnFX" MySQL CRM into a
separate `tradesoft_old` schema inside the live PostgreSQL broker_crm database.

WHY a raw/text mirror:
  Old MySQL CRMs routinely hold values that are illegal in Postgres typed columns
  (e.g. '0000-00-00 00:00:00' datetimes, out-of-range numbers, mixed encodings).
  To fetch EVERYTHING losslessly we land every column as TEXT and record the original
  MySQL types/DDL in metadata tables. Casting/cleaning happens later, once the desk
  decides how each table maps into the new CRM. This keeps the first pull bulletproof.

Creates in schema tradesoft_old:
  _tables   (table_name, src_rows, loaded_rows, status, error)
  _columns  (table_name, ordinal, column_name, mysql_type, nullable, col_key)
  _ddl      (table_name, create_sql)        -- exact SHOW CREATE TABLE
  <table>   one per source table, all columns TEXT, faithful values

Idempotent: each data table is dropped & reloaded. Re-runnable.
Usage:
  python fetch_tradesoft.py                 # full mirror, all tables
  python fetch_tradesoft.py --tables a,b    # only these source tables
  python fetch_tradesoft.py --skip a,b      # all except these
  python fetch_tradesoft.py --probe         # connect + list tables/counts, load nothing
"""
import sys
import db_config
import argparse
# headless cp1252 consoles can't encode ✓/Arabic — force UTF-8 so the mirror never dies on a print
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pymysql
import pymysql.cursors
import psycopg2
from psycopg2.extras import execute_values

# ── SOURCE (legacy MySQL) ──────────────────────────────────────────────────
import ts_mysql_config
_MY = ts_mysql_config.MYSQL_SRC
MY_HOST = _MY["host"]
MY_PORT = _MY["port"]
MY_USER = _MY["user"]
MY_PASS = _MY["password"]
MY_DB   = _MY["database"]   # read-only views DB the old-CRM team granted us (5 fx_*_view tables)

# ── DESTINATION (live Postgres) ────────────────────────────────────────────
PG_DSN    = db_config.DSN
PG_SCHEMA = "tradesoft_old"

BATCH = 2000   # rows per INSERT


def pg_ident(name: str) -> str:
    """Postgres-safe quoted identifier (preserves original name, truncates to 63 bytes)."""
    n = name[:63]
    return '"' + n.replace('"', '""') + '"'


def connect_mysql():
    return pymysql.connect(
        host=MY_HOST, port=int(MY_PORT), user=MY_USER, password=MY_PASS,
        database=MY_DB, connect_timeout=15, read_timeout=600,
        charset="utf8mb4", use_unicode=True,
    )


def normalize(v):
    """Coerce any MySQL value to a text-storable form (or None)."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "replace")
        except Exception:
            return v.hex()
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="", help="comma list of source tables to include")
    ap.add_argument("--skip", default="", help="comma list of source tables to skip")
    ap.add_argument("--probe", action="store_true", help="list tables + counts only, load nothing")
    args = ap.parse_args()
    only = {t.strip() for t in args.tables.split(",") if t.strip()}
    skip = {t.strip() for t in args.skip.split(",") if t.strip()}

    print(f"Connecting to MySQL {MY_HOST}:{MY_PORT}/{MY_DB} ...", flush=True)
    my = connect_mysql()
    print("  ✓ MySQL connected", flush=True)
    mc = my.cursor()
    mc.execute("SHOW TABLES")
    all_tables = [r[0] for r in mc.fetchall()]
    print(f"  {len(all_tables)} tables in source\n", flush=True)

    # source row counts
    counts = {}
    for t in all_tables:
        try:
            mc.execute(f"SELECT COUNT(*) FROM `{t}`")
            counts[t] = mc.fetchone()[0]
        except Exception as e:
            counts[t] = -1
        print(f"  {t:45s} {counts[t]:>12,} rows" if counts[t] >= 0
              else f"  {t:45s}   (count error)", flush=True)

    if args.probe:
        print("\n--probe: no data loaded.")
        my.close()
        return

    tables = [t for t in all_tables
              if (not only or t in only) and t not in skip]
    print(f"\nLoading {len(tables)} tables into Postgres schema {PG_SCHEMA}\n", flush=True)

    pg = psycopg2.connect(PG_DSN)
    pg.autocommit = False
    pc = pg.cursor()
    pc.execute(f"CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA}")
    pc.execute(f'CREATE TABLE IF NOT EXISTS {PG_SCHEMA}."_tables" '
               '(table_name text PRIMARY KEY, src_rows bigint, loaded_rows bigint, status text, error text)')
    pc.execute(f'CREATE TABLE IF NOT EXISTS {PG_SCHEMA}."_columns" '
               '(table_name text, ordinal int, column_name text, mysql_type text, nullable text, col_key text)')
    pc.execute(f'CREATE TABLE IF NOT EXISTS {PG_SCHEMA}."_ddl" '
               '(table_name text PRIMARY KEY, create_sql text)')
    pg.commit()

    grand = 0
    for t in tables:
        try:
            # column metadata
            mc.execute("""SELECT ordinal_position, column_name, column_type, is_nullable, column_key
                          FROM information_schema.columns
                          WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position""",
                       (MY_DB, t))
            cols_meta = mc.fetchall()
            col_names = [c[1] for c in cols_meta]

            # exact source DDL
            try:
                mc.execute(f"SHOW CREATE TABLE `{t}`")
                ddl = mc.fetchone()[1]
            except Exception:
                ddl = None

            # (re)create the landing table — all TEXT
            qt = f'{PG_SCHEMA}.{pg_ident(t)}'
            pc.execute(f"DROP TABLE IF EXISTS {qt}")
            cols_sql = ", ".join(f"{pg_ident(c)} text" for c in col_names) or '"_empty" text'
            pc.execute(f"CREATE TABLE {qt} ({cols_sql})")

            # record metadata
            pc.execute(f'DELETE FROM {PG_SCHEMA}."_columns" WHERE table_name=%s', (t,))
            execute_values(pc,
                f'INSERT INTO {PG_SCHEMA}."_columns" (table_name, ordinal, column_name, mysql_type, nullable, col_key) VALUES %s',
                [(t, c[0], c[1], c[2], c[3], c[4]) for c in cols_meta])
            pc.execute(f'INSERT INTO {PG_SCHEMA}."_ddl" (table_name, create_sql) VALUES (%s,%s) '
                       'ON CONFLICT (table_name) DO UPDATE SET create_sql=EXCLUDED.create_sql', (t, ddl))
            pg.commit()

            # stream rows from MySQL (server-side cursor = constant memory)
            loaded = 0
            if col_names:
                insert_sql = f'INSERT INTO {qt} ({", ".join(pg_ident(c) for c in col_names)}) VALUES %s'
                sc = my.cursor(pymysql.cursors.SSCursor)
                sc.execute(f"SELECT {', '.join('`'+c+'`' for c in col_names)} FROM `{t}`")
                buf = []
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

            pc.execute(f'INSERT INTO {PG_SCHEMA}."_tables" (table_name, src_rows, loaded_rows, status, error) '
                       "VALUES (%s,%s,%s,'ok',NULL) ON CONFLICT (table_name) DO UPDATE SET "
                       "src_rows=EXCLUDED.src_rows, loaded_rows=EXCLUDED.loaded_rows, status='ok', error=NULL",
                       (t, counts.get(t, -1), loaded))
            pg.commit()
            grand += loaded
            print(f"  ✓ {t:45s} {loaded:>12,} rows", flush=True)
        except Exception as e:
            pg.rollback()
            try:
                pc.execute(f'INSERT INTO {PG_SCHEMA}."_tables" (table_name, src_rows, loaded_rows, status, error) '
                           "VALUES (%s,%s,0,'error',%s) ON CONFLICT (table_name) DO UPDATE SET "
                           "status='error', error=EXCLUDED.error",
                           (t, counts.get(t, -1), str(e)[:500]))
                pg.commit()
            except Exception:
                pg.rollback()
            print(f"  ✗ {t:45s} ERROR: {e}", flush=True)

    my.close()
    pg.close()
    print(f"\nDone. {grand:,} rows mirrored into {PG_SCHEMA}.", flush=True)


if __name__ == "__main__":
    main()
