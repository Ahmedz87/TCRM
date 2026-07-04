"""
apply_contact_updates.py — push UPDATED email/phone from the legacy TradeSoft exports
(C:\\Broker-crm\\data Email + Phone\\*.xlsx) into the live CRM leads + clients.

Matching: the exports are keyed by the legacy person id (users file `id`, leads file `user_id`),
which equals customers.legacy_user_id. So we resolve  legacy_id -> customers.customer_no -> the
clients/leads rows that carry that customer_no, and refresh their email/phone.

Safety:
  • Only writes a value that is non-empty AND actually different from what's already stored
    (never blanks a good value, never a no-op churn).
  • Email must look like an email; phone must have >= 8 digits. For leads we prefer the
    international `mobile` over the local `phone`.
  • Every overwritten (table,id,old_email,old_phone) is saved to `contact_update_backup` first,
    so the change is fully reversible (`--revert`).

Run:  python apply_contact_updates.py --dry-run   (report only, no writes)
      python apply_contact_updates.py             (apply)
      python apply_contact_updates.py --revert     (restore from backup)
"""
import sys, os, re
import psycopg2
from psycopg2.extras import execute_values
import openpyxl

BASE = r"C:/Broker-crm/data Email + Phone"
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def _dsn():
    for ln in open(os.path.join(os.path.dirname(__file__) or ".", ".env"), encoding="utf-8"):
        if ln.strip().startswith("DATABASE_URL"):
            return ln.split("=", 1)[1].strip()
    raise SystemExit("no DATABASE_URL")

def _clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.upper() == "NULL" else s

def _email(v):
    s = _clean(v).lower()
    return s if EMAIL_RE.match(s) else ""

def _phone(*cands):
    """Pick the best phone among candidates: prefer one starting with '+', need >=8 digits."""
    best = ""
    for v in cands:
        s = _clean(v).replace(" ", "").replace("-", "")
        digits = re.sub(r"\D", "", s)
        if len(digits) < 8:
            continue
        if s.startswith("+"):
            return s                      # international form wins outright
        if not best:
            best = s
    return best

def parse(fname, id_col, email_col, phone_cols):
    """Return dict legacy_id -> (email, phone). Last non-empty wins on duplicate ids."""
    wb = openpyxl.load_workbook(os.path.join(BASE, fname), read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    header = [_clean(h) for h in next(it)]
    idx = {h: i for i, h in enumerate(header)}
    iI = idx[id_col]; iE = idx[email_col]; iP = [idx[c] for c in phone_cols]
    out = {}
    for r in it:
        if iI >= len(r):
            continue
        lid = _clean(r[iI])
        if not lid:
            continue
        email = _email(r[iE]) if iE < len(r) else ""
        phone = _phone(*[r[i] for i in iP if i < len(r)])
        if not email and not phone:
            continue
        prev = out.get(lid, ("", ""))
        out[lid] = (email or prev[0], phone or prev[1])
    wb.close()
    return out

def stage(cur, name, data):
    # NOTE: no ON COMMIT DROP — we commit between the clients and leads applies, which would
    # otherwise drop the staging tables mid-run. Temp tables vanish at session end regardless.
    cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS {name}(legacy_id text PRIMARY KEY, email text, phone text)")
    cur.execute(f"TRUNCATE {name}")
    execute_values(cur, f"INSERT INTO {name}(legacy_id,email,phone) VALUES %s ON CONFLICT (legacy_id) DO NOTHING",
                   [(k, v[0], v[1]) for k, v in data.items()], page_size=5000)

def main():
    dry = "--dry-run" in sys.argv
    revert = "--revert" in sys.argv
    c = psycopg2.connect(_dsn()); cur = c.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS contact_update_backup(
        tbl text, row_id bigint, old_email text, old_phone text, new_email text, new_phone text,
        applied_at timestamp DEFAULT NOW())""")
    c.commit()

    if revert:
        for tbl in ("clients", "leads"):
            cur.execute(f"""UPDATE {tbl} t SET email=b.old_email, phone=b.old_phone, updated_at=NOW()
                FROM contact_update_backup b WHERE b.tbl=%s AND b.row_id=t.id""", (tbl,))
            print(f"reverted {tbl}: {cur.rowcount}")
        c.commit(); return

    users = parse("tnfx_users_export.xlsx", "id", "email", ["phone"])
    leads = parse("tnfx_leads_export.xlsx", "user_id", "email", ["mobile", "phone"])
    print(f"parsed: users file -> {len(users)} legacy ids with contact, leads file -> {len(leads)}")

    stage(cur, "stg_users", users)
    stage(cur, "stg_leads", leads)

    # CLIENTS get contact from the USERS export (a person = a legacy user id).
    # LEADS get contact from the LEADS export. Both join via customers.legacy_user_id.
    plans = [
        ("clients", "stg_users"),
        ("leads",   "stg_leads"),
    ]
    for tbl, stg in plans:
        # candidate updates: row joined to its legacy id, where the staged value is non-empty AND differs
        cur.execute(f"""
            SELECT t.id,
                   NULLIF(s.email,'') , NULLIF(s.phone,''),
                   t.email, t.phone
            FROM {tbl} t
            JOIN customers cu ON cu.customer_no = t.customer_no
            JOIN {stg} s ON s.legacy_id = cu.legacy_user_id
            WHERE ( NULLIF(s.email,'') IS NOT NULL AND LOWER(COALESCE(s.email,'')) <> LOWER(COALESCE(t.email,'')) )
               OR ( NULLIF(s.phone,'') IS NOT NULL AND COALESCE(s.phone,'') <> COALESCE(t.phone,'') )
        """)
        rows = cur.fetchall()
        n_email = sum(1 for r in rows if r[1] and (r[1] or '').lower() != (r[3] or '').lower())
        n_phone = sum(1 for r in rows if r[2] and (r[2] or '') != (r[4] or ''))
        print(f"\n{tbl}: {len(rows)} rows would change  (email:{n_email}, phone:{n_phone})")
        for r in rows[:4]:
            print(f"   id={r[0]}  email {r[3]!r}->{r[1]!r}   phone {r[4]!r}->{r[2]!r}")
        if dry:
            continue
        # only write the field that GENUINELY changed (case-insensitive for email)
        upd = []
        for r in rows:
            ne = r[1] if (r[1] and (r[1] or '').lower() != (r[3] or '').lower()) else ''
            np = r[2] if (r[2] and (r[2] or '') != (r[4] or '')) else ''
            upd.append((r[0], ne, np, r[3], r[4]))
        # backup old values first (reversible), then apply
        execute_values(cur, """INSERT INTO contact_update_backup(tbl,row_id,old_email,old_phone,new_email,new_phone)
                               VALUES %s""",
                       [(tbl, u[0], u[3], u[4], u[1], u[2]) for u in upd], page_size=5000)
        execute_values(cur, f"""
            UPDATE {tbl} t SET
                email = COALESCE(NULLIF(v.new_email,''), t.email),
                phone = COALESCE(NULLIF(v.new_phone,''), t.phone),
                updated_at = NOW()
            FROM (VALUES %s) AS v(id, new_email, new_phone)
            WHERE t.id = v.id
        """, [(u[0], u[1], u[2]) for u in upd], template="(%s,%s,%s)", page_size=5000)
        c.commit()
        print(f"   applied {len(upd)} updates to {tbl}.")

    if dry:
        print("\n(dry-run — nothing written)")

if __name__ == "__main__":
    main()
