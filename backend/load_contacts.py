"""
load_contacts.py — load email/phone from the TradeSoft contact export CSV(s) and enrich the CRM.

Scans `C:\\Broker-crm\\data Email + Phone\\*.csv` (the old-CRM email/phone export, sent ~every 3 days),
parses them defensively (malformed/quoting-broken), keys by user_id (= CUS), enriches `customers`,
then propagates email/phone down to clients / leads / trading_accounts. Idempotent: only FILLS
missing values (never overwrites an existing email/phone). Batched so it coexists with live sync.

Run standalone:  python load_contacts.py
Called automatically by tradesoft_sync.py when a newer CSV is dropped in the folder.
"""
import csv, re, sys, os, glob, time, psycopg2
import db_config
from psycopg2.extras import execute_values
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
csv.field_size_limit(10**8)

FOLDER = r"C:\Broker-crm\data Email + Phone"
PG = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)
PH = re.compile(r"^\+?\d[\d\-]{7,}$")


def _clean(x):
    x = (x or "").strip().strip('"')
    return "" if x.upper() == "NULL" else x


def _isem(x):
    return x and "@" in x and " " not in x


def parse_file(path):
    rows = {}
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rd = csv.reader(f, quoting=csv.QUOTE_NONE)
        header = next(rd, None) or []
        hl = [h.strip().strip('"').lower() for h in header]
        key = hl.index("user_id") if "user_id" in hl else (hl.index("id") if "id" in hl else 0)
        for r in rd:
            if len(r) <= key or not r[key].strip().isdigit():
                continue
            uid = r[key].strip()
            email = next((_clean(v) for v in r if _isem(_clean(v))), "")
            phone = next((_clean(v) for v in r if PH.match(_clean(v).replace(" ", ""))), "")
            ce, cp = rows.get(uid, ("", ""))
            rows[uid] = (email or ce, phone or cp)
    return rows


def main():
    files = sorted(glob.glob(os.path.join(FOLDER, "*.csv")))
    if not files:
        print("no contact CSVs found in", FOLDER); return 0
    merged = {}
    for p in files:
        for uid, (e, ph) in parse_file(p).items():
            ce, cp = merged.get(uid, ("", ""))
            merged[uid] = (ce or e, cp or ph)
    print(f"parsed {len(merged):,} contacts from {len(files)} file(s)")

    c = psycopg2.connect(**PG); cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS ts_contact")
    cur.execute("CREATE TABLE ts_contact(user_id text PRIMARY KEY, email text, phone text)")
    execute_values(cur, "INSERT INTO ts_contact(user_id,email,phone) VALUES %s ON CONFLICT(user_id) DO NOTHING",
                   [(k, e, p) for k, (e, p) in merged.items()], page_size=5000)
    cur.execute("CREATE INDEX ON ts_contact(user_id)"); c.commit()

    cur.execute("""UPDATE customers cu SET email=COALESCE(NULLIF(cu.email,''),NULLIF(t.email,'')),
        phone=COALESCE(NULLIF(cu.phone,''),NULLIF(t.phone,''))
        FROM ts_contact t WHERE t.user_id=cu.legacy_user_id
          AND (COALESCE(cu.email,'')='' OR COALESCE(cu.phone,'')='')""")
    print("customers enriched:", cur.rowcount); c.commit()

    total = 0
    for table, idcol in [("clients", "login"), ("leads", "id"), ("trading_accounts", "login")]:
        cur.execute(f"""SELECT x.{idcol} FROM {table} x JOIN customers cu ON cu.customer_no=x.customer_no
            WHERE x.customer_no IS NOT NULL AND (COALESCE(x.email,'')='' OR COALESCE(x.phone,'')='')
              AND (COALESCE(cu.email,'')<>'' OR COALESCE(cu.phone,'')<>'')""")
        ids = [r[0] for r in cur.fetchall()]
        sql = f"""UPDATE {table} x SET email=COALESCE(NULLIF(x.email,''),cu.email),
                  phone=COALESCE(NULLIF(x.phone,''),cu.phone)
                  FROM customers cu WHERE cu.customer_no=x.customer_no AND x.{idcol}=ANY(%s)"""
        done = 0
        for i in range(0, len(ids), 3000):
            b = ids[i:i+3000]
            for a in range(8):
                try:
                    cur.execute("SET lock_timeout='4s'"); cur.execute(sql, (b,)); done += cur.rowcount; c.commit(); break
                except Exception:
                    c.rollback()
                    if a == 7: raise
                    time.sleep(1.3 * (a + 1))
        total += done
        print(f"{table}: filled {done:,}")
    c.close()
    print(f"DONE — {total:,} rows enriched")
    return total


if __name__ == "__main__":
    main()
