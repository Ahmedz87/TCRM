"""Standalone DB access for the TradeSoft CRM copy.

Reads the mirrored legacy Workice/TradeSoft data from the dedicated `tradesoft_crm`
PostgreSQL database (a decoupled copy of the broker_crm.tradesoft_old schema).
Every source column is TEXT, so casts happen in SQL where numbers/dates are needed.
"""
import os
from contextlib import contextmanager
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor

# Use 127.0.0.1 (not "localhost"): under the SYSTEM account "localhost" can resolve to
# IPv6 ::1, which black-holes if Postgres only listens on IPv4 — that made the service
# hang on startup. Forcing IPv4 lets it run as a SYSTEM boot task.
try:
    import _secrets
    _default_url = _secrets.TRADESOFT_DATABASE_URL
except Exception:
    _default_url = "postgresql://postgres@127.0.0.1:5432/tradesoft_crm"  # no secret; set _secrets.py or TRADESOFT_DATABASE_URL
DATABASE_URL = os.getenv("TRADESOFT_DATABASE_URL", _default_url)

_pool = SimpleConnectionPool(1, 10, dsn=DATABASE_URL)


@contextmanager
def get_cursor():
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def query_all(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def query_one(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchone()
