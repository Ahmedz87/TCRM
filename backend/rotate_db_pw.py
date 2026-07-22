# -*- coding: utf-8 -*-
"""Rotate the broker_crm `postgres` DB password (P0-7 companion). Generates a strong new password
at RUNTIME (never a literal in source/command), changes it on PostgreSQL via a parameterized ALTER,
updates the two gitignored config files, and records it. It does NOT restart processes or touch
PgBouncer's userlist — the caller does those next (see the session runbook). Idempotent-safe:
verifies the new password before writing any config; on any failure it stops before config edits.

  python rotate_db_pw.py        # do it
"""
import sys, io, os, time, secrets
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Broker-crm\backend")
import db_config
import psycopg2
from psycopg2 import sql

OLD = db_config.DB_PASSWORD               # read at runtime — no literal in this file
NEW = secrets.token_urlsafe(18)           # URL-safe (A-Za-z0-9_-): safe inside DATABASE_URL + a Python string
BE = r"C:\Broker-crm\backend"
ENV = os.path.join(BE, ".env")
CFG = os.path.join(BE, "db_config.py")
PWF = os.path.join(BE, "db_password.NEW.txt")
stamp = time.strftime("%Y%m%d-%H%M%S")

def _conn(pw):
    return psycopg2.connect(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME,
                            user=db_config.DB_USER, password=pw, connect_timeout=10)

# 0) sanity: current password works
try:
    c = _conn(OLD); c.close()
except Exception as e:
    print(f"ABORT: current password does not connect ({e}); nothing changed."); sys.exit(1)

# 1) back up the two config files (*.bak-* is gitignored)
for f in (ENV, CFG):
    with open(f, "r", encoding="utf-8") as r:
        open(f + f".bak-prerotate-{stamp}", "w", encoding="utf-8").write(r.read())
print(f"backed up .env + db_config.py (suffix .bak-prerotate-{stamp})")

# 2) change the password on PostgreSQL (parameterized; role name via safe identifier)
c = _conn(OLD); c.autocommit = True
c.cursor().execute(sql.SQL("ALTER USER {} WITH PASSWORD %s").format(sql.Identifier(db_config.DB_USER)), (NEW,))
c.close()

# 3) verify the NEW password connects direct to PG before touching any config
try:
    t = _conn(NEW); tc = t.cursor(); tc.execute("SELECT 1"); assert tc.fetchone()[0] == 1; t.close()
except Exception as e:
    print(f"ABORT: new password failed to connect ({e}). PG password WAS changed — rollback: "
          f"ALTER USER postgres WITH PASSWORD <old> from a working session."); sys.exit(1)
print("PostgreSQL password changed + verified (direct :5432)")

# 4) update the gitignored config files (targeted replace of the old value — no literal here)
env = open(ENV, encoding="utf-8").read()
env2 = env.replace(":" + OLD + "@", ":" + NEW + "@")
open(ENV, "w", encoding="utf-8", newline="").write(env2)
print("  .env DATABASE_URL updated" if env2 != env else "  WARN: .env password token not found")

cfg = open(CFG, encoding="utf-8").read()
cfg2 = cfg.replace('"' + OLD + '"', '"' + NEW + '"')
open(CFG, "w", encoding="utf-8", newline="").write(cfg2)
print("  db_config.py DB_PASSWORD updated" if cfg2 != cfg else "  WARN: db_config password token not found")

# 5) record the new password for the operator (gitignored)
open(PWF, "w", encoding="utf-8").write(
    f"broker_crm postgres password rotated {stamp}. Store in your password manager, then delete this file.\n"
    f"password: {NEW}\n")
print(f"new password saved to {PWF} (gitignored). masked: {NEW[:3]}***{NEW[-2:]}  len={len(NEW)}")
print("NEXT: regenerate PgBouncer userlist (new verifier) + reload; then restart web tier, loops, bridges.")
