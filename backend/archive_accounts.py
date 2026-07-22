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
    # Our rule (per the desk): archive a CRM trading account IFF it was ACTIVE on MT4/5 and then
    # DISAPPEARED — i.e. MT's weekly archival dropped it from the user list, so the sync stopped
    # seeing an account it USED to see. The balance<$1 is MT's OWN criterion for what to archive;
    # we just mirror the result (disappearance).
    #   KEY: we require mt_last_seen IS NOT NULL — the account must have been seen on MT at least
    #   once. A NULL mt_last_seen means "never seen on MT" (a brand-new account, or one on an MT
    #   server/group this bridge doesn't cover, e.g. ECN) — that is NOT a disappearance, so we must
    #   NOT archive it. (The old rule archived NULLs too, which wrongly hid every new ECN account.)
    # Real accounts only (positive login). STALE_DAYS protects against a single missed sync.
    return f"""
        FROM clients c
        WHERE c.login > 0
          AND COALESCE(c.group_name,'') NOT ILIKE '%retail%'
          AND COALESCE(c.group_name,'') NOT ILIKE '%demo%'
          AND c.archived_at IS NULL
          AND c.mt_last_seen IS NOT NULL
          AND c.mt_last_seen < NOW() - INTERVAL '{STALE_DAYS} days'
    """


def reactivate_on_mt(db, commit=False):
    """Reverse side of the cross-check: an account that is BACK on MT (fresh mt_last_seen) must NOT
    stay archived. This catches (a) accounts MT un-archived, and (b) the big one — NEW accounts
    imported from TradeSoft that default to archive_reason='tradesoft_not_on_mt' but are actually
    live on MT (the bridge's full user-list pull stamps their mt_last_seen). Un-archive them and mark
    their trading_accounts active. Inherently safe: requires FRESH mt_last_seen, so a dead bridge
    (nothing fresh) un-archives nothing."""
    sql_where = f"archived_at IS NOT NULL AND mt_last_seen > NOW() - INTERVAL '{STALE_DAYS} days'"
    n = db.execute(text(f"SELECT count(*) FROM clients WHERE {sql_where}")).scalar() or 0
    by_reason = db.execute(text(
        f"SELECT COALESCE(archive_reason,'?'), count(*) FROM clients WHERE {sql_where} GROUP BY 1")).fetchall()
    print(f"\nOn MT again but still archived: {n:,}")
    for reason, cnt in by_reason:
        print(f"   {reason}: {cnt:,}")
    if not commit:
        print("   (dry run — pass --commit to re-activate)")
        return {"would_reactivate": n}
    logins = [r[0] for r in db.execute(text(f"SELECT login FROM clients WHERE {sql_where}")).fetchall()]
    r1 = db.execute(text(
        f"UPDATE clients SET archived_at=NULL, archive_reason=NULL WHERE {sql_where}"))
    if logins:
        db.execute(text("UPDATE trading_accounts SET is_active=TRUE WHERE login = ANY(:l)"), {"l": logins})
    db.commit()
    print(f"   RE-ACTIVATED {r1.rowcount:,} account(s).")
    return {"reactivated": r1.rowcount}


def run(commit=False):
    db = SessionLocal()
    try:
        ensure_schema(db)
        # bidirectional cross-check: FIRST bring back accounts that are live on MT again, THEN
        # archive the ones that have gone stale/absent.
        reactivate_on_mt(db, commit=commit)

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
    elif "--reactivate-only" in sys.argv:
        # only the reverse pass: bring back accounts that are live on MT again (no archiving)
        _db = SessionLocal()
        try:
            ensure_schema(_db)
            reactivate_on_mt(_db, commit="--commit" in sys.argv)
        finally:
            _db.close()
    else:
        run(commit="--commit" in sys.argv)
