"""
archive_accounts.py — weekly MT4/MT5 account-archival sync for the CRM.

WHAT MT DOES: each Sunday MT4/MT5 archives accounts that have no login/trading activity AND
balance < $1. Those accounts then DISAPPEAR from the live MT user list.

HOW WE DETECT IT (cross-check, per the desk's chosen approach): the bridge (MT5) and the MT4
sync stamp `clients.mt_last_seen = NOW()` for every account they see in each MT pull. An account
that is NO LONGER in MT stops getting stamped, so its mt_last_seen goes stale. OUR rule:
    a real CRM trading account is archived IFF it is GONE from MT (mt_last_seen stale/NULL).
We do NOT re-check balance — the balance<$1 is MT's OWN criterion for deciding what to archive;
we just mirror the result (absence). Mock/demo groups (retail/demo) are excluded.

SAFETY: if the MT sync looks unhealthy (too few accounts seen recently — e.g. the bridge is down)
we ABORT rather than mass-archive. Dry-run by default; pass --commit to actually archive.

Archiving is ADDITIVE — it only sets clients.archived_at/archive_reason. All history (deposits,
withdrawals, IB & sales commission, loyalty, trades) stays. The portal blocks NEW deposits and
internal transfers for archived accounts; everything else is read-only-visible.

Usage:
    python archive_accounts.py            # DRY RUN — report what would be archived
    python archive_accounts.py --commit   # actually archive
    python archive_accounts.py --unarchive <login>   # manual un-archive (e.g. account came back)
"""
import sys
from sqlalchemy import text
from database import SessionLocal

STALE_DAYS = 2          # not seen in MT for this long => candidate (full MT pulls run every ~5 min)
MIN_SEEN_HEALTHY = 8000 # require at least this many accounts seen in the last day, else ABORT
ARCHIVE_REASON = "mt_weekly_archive"


def ensure_schema(db):
    """Add archive + last-seen columns. Guarded (check first, short lock_timeout) per the
    ops lesson: never run an unconditional ALTER on the hot `clients` table at boot."""
    have = {r[0] for r in db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='clients'")).fetchall()}
    db.execute(text("SET lock_timeout='4s'"))
    if "archived_at" not in have:
        db.execute(text("ALTER TABLE clients ADD COLUMN archived_at TIMESTAMPTZ"))
    if "archive_reason" not in have:
        db.execute(text("ALTER TABLE clients ADD COLUMN archive_reason TEXT"))
    if "mt_last_seen" not in have:
        db.execute(text("ALTER TABLE clients ADD COLUMN mt_last_seen TIMESTAMPTZ"))
    db.execute(text("RESET lock_timeout"))
    db.execute(text("CREATE INDEX IF NOT EXISTS clients_archived_idx ON clients(archived_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS clients_mt_seen_idx ON clients(mt_last_seen)"))
    db.commit()


def _candidates_sql():
    # Our rule (per the desk): archive a CRM trading account IFF it is GONE from MT4/5 — i.e.
    # the MT sync stopped seeing it. The balance<$1 condition is MT's OWN criterion for deciding
    # what to archive; we don't re-apply it, we just mirror MT's result (absence). Real accounts
    # only (positive login). NULL mt_last_seen counts as "not seen"; the health guard below makes
    # sure a full MT sync actually ran first, and STALE_DAYS protects against a single missed sync.
    return f"""
        FROM clients c
        WHERE c.login > 0
          AND COALESCE(c.group_name,'') NOT ILIKE '%retail%'
          AND COALESCE(c.group_name,'') NOT ILIKE '%demo%'
          AND c.archived_at IS NULL
          AND (c.mt_last_seen IS NULL OR c.mt_last_seen < NOW() - INTERVAL '{STALE_DAYS} days')
    """


def run(commit=False):
    db = SessionLocal()
    try:
        ensure_schema(db)

        # ── health guard: how many accounts did MT stamp in the last day? ──
        seen_recent = db.execute(text(
            "SELECT count(*) FROM clients WHERE mt_last_seen > NOW() - INTERVAL '1 day'")).scalar() or 0
        print(f"accounts seen in MT in last 24h: {seen_recent:,}")
        if seen_recent < MIN_SEEN_HEALTHY:
            print(f"ABORT: only {seen_recent:,} accounts seen recently (< {MIN_SEEN_HEALTHY:,}). "
                  "The MT sync (bridge / mt4_loop) looks unhealthy or mt_last_seen hasn't populated "
                  "yet — refusing to archive so we don't mass-archive live accounts.")
            return {"aborted": True, "seen_recent": seen_recent}

        n = db.execute(text("SELECT count(*) " + _candidates_sql())).scalar() or 0
        by_plat = db.execute(text(
            "SELECT CASE WHEN COALESCE(platform,'MT5')='MT4' THEN 'MT4' ELSE 'MT5' END, count(*) "
            + _candidates_sql() + " GROUP BY 1")).fetchall()
        print(f"\nWould archive {n:,} account(s):")
        for plat, cnt in by_plat:
            print(f"   {plat}: {cnt:,}")
        # Sanity check: how many have a real balance? MT only archives <$1, so candidates with a
        # balance are worth eyeballing — they can be a partial-sync miss rather than a real archive.
        with_bal = db.execute(text(
            "SELECT count(*), COALESCE(SUM(COALESCE(balance,0)),0) "
            + _candidates_sql() + " AND COALESCE(c.balance,0) >= 1")).fetchone()
        print(f"   ...of which {with_bal[0]:,} have balance >= $1 (total ${float(with_bal[1]):,.2f}) — review these")
        sample = db.execute(text(
            "SELECT c.login, c.name, COALESCE(c.balance,0), c.mt_last_seen, COALESCE(c.platform,'MT5') "
            + _candidates_sql() + " ORDER BY c.mt_last_seen NULLS FIRST LIMIT 10")).fetchall()
        print("\nsample:")
        for r in sample:
            print(f"   #{r[0]} {r[1]!s:24.24} bal=${float(r[2]):.2f} last_seen={r[3]} {r[4]}")

        if not commit:
            print("\nDRY RUN — nothing archived. Re-run with --commit to apply.")
            return {"would_archive": n, "by_platform": dict(by_plat), "committed": False}

        res = db.execute(text(
            "UPDATE clients c SET archived_at=NOW(), archive_reason=:r "
            "WHERE c.login IN (SELECT c.login " + _candidates_sql() + ")"),
            {"r": ARCHIVE_REASON})
        db.commit()
        print(f"\nARCHIVED {res.rowcount:,} account(s).")
        return {"archived": res.rowcount, "committed": True}
    finally:
        db.close()


def unarchive(login):
    db = SessionLocal()
    try:
        res = db.execute(text(
            "UPDATE clients SET archived_at=NULL, archive_reason=NULL WHERE login=:l"), {"l": int(login)})
        db.commit()
        print(f"un-archived {res.rowcount} row(s) for login {login}")
    finally:
        db.close()


if __name__ == "__main__":
    if "--unarchive" in sys.argv:
        unarchive(sys.argv[sys.argv.index("--unarchive") + 1])
    else:
        run(commit="--commit" in sys.argv)
