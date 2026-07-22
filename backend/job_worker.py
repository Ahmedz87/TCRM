# -*- coding: utf-8 -*-
"""Durable job worker (P0-3, Jul 16 2026). Drains the `jobs` table, runs the handler for each,
retries failures with backoff. DB-backed (no Redis). Money-affecting async work (bonus MT credits)
now survives restarts and never silently vanishes.

  python job_worker.py --loop [--interval 3]   # daemon (autostart via start_core.ps1)
  python job_worker.py --once                   # drain everything due, then exit
  python job_worker.py --status                 # counts by status
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from sqlalchemy import text
from database import SessionLocal
import job_queue as Q
import job_handlers as H


def _run_one():
    """Claim + run one job in its OWN session. Returns True if a job ran."""
    db = SessionLocal()
    try:
        Q.ensure_schema(db)
        job = Q.claim_one(db)
        if not job:
            return False
        jid, kind, payload, attempts, max_attempts = job
        handler = H.HANDLERS.get(kind)
        if handler is None:
            Q.mark_retry_or_fail(db, jid, max_attempts, max_attempts, f"no handler for kind '{kind}'")
            return True
        try:
            res = handler(db, payload or {})
            Q.mark_done(db, jid, res)
            print(f"[jobs] #{jid} {kind} done: {res}", flush=True)
        except Exception as e:
            db.rollback()
            Q.mark_retry_or_fail(db, jid, attempts, max_attempts, str(e))
            print(f"[jobs] #{jid} {kind} attempt {attempts}/{max_attempts} failed: {str(e)[:120]}", flush=True)
        return True
    finally:
        db.close()


def status():
    db = SessionLocal()
    try:
        Q.ensure_schema(db)
        for r in db.execute(text("SELECT status, count(*) FROM jobs GROUP BY 1 ORDER BY 2 DESC")).fetchall():
            print(f"  {r[0]:10} {r[1]}")
    finally:
        db.close()


def main():
    if "--status" in sys.argv:
        status(); return
    once = "--once" in sys.argv
    interval = 3
    if "--interval" in sys.argv:
        try: interval = int(sys.argv[sys.argv.index("--interval") + 1])
        except Exception: pass
    print(f"job_worker started ({'once' if once else 'loop'})", flush=True)
    idle = 0
    while True:
        ran = _run_one()
        if ran:
            idle = 0
            continue
        if once:
            break
        idle += 1
        time.sleep(interval)


if __name__ == "__main__":
    main()
