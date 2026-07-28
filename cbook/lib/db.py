"""
cbook.lib.db — SELECT-only database access for the C-Book project.

SAFETY: this helper CANNOT write. Every query runs inside a transaction forced to
`READ ONLY`, and a guard rejects any statement that is not a single SELECT/WITH. The
C-Book project never modifies client data, accounts, balances or transactions.

Connection settings come from backend/db_config.py (the live remote PG18 box, per CLAUDE.md).
This module only runs on the CRM server, where that box is reachable — not from a sandbox.
"""
import os
import sys
import re

# Reuse the CRM's own DB config (creds live in gitignored backend/db_config.py).
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_WRITE_RE = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|copy|merge|"
    r"vacuum|comment|reindex|refresh)\b",
    re.I,
)


def _connect():
    import psycopg2
    import db_config  # from backend/
    return psycopg2.connect(
        host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME,
        user=db_config.DB_USER, password=db_config.DB_PASSWORD,
    )


def _assert_read_only(sql: str):
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise ValueError("Only a single statement is allowed (no ';' chaining).")
    head = stripped.lstrip().split(None, 1)[0].lower() if stripped else ""
    if head not in ("select", "with"):
        raise ValueError(f"Read-only: statement must start with SELECT/WITH, got {head!r}.")
    if _WRITE_RE.search(stripped):
        raise ValueError("Read-only: write/DDL keyword detected — refused.")


def fetch(sql: str, params=None):
    """Run a single read-only SELECT/WITH and return a list of dict rows."""
    _assert_read_only(sql)
    conn = _connect()
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '600s'")
            cur.execute(sql, params or {})
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.rollback()
        return rows
    finally:
        conn.close()


def fetch_sql_file(path: str, params=None):
    """Run a .sql file (must be a single read-only statement) and return dict rows."""
    with open(path, "r", encoding="utf-8") as fh:
        # strip line comments so the single-statement / read-only guard sees clean SQL
        body = "\n".join(l for l in fh.read().splitlines() if not l.lstrip().startswith("--"))
    return fetch(body, params)
