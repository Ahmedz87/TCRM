# -*- coding: utf-8 -*-
"""Durable, idempotent job queue for money-affecting async work (P0-3/9/10, Jul 16 2026).

Before this, real MT credits (welcome/birthday/deposit bonuses) ran as fire-and-forget FastAPI
BackgroundTasks: if the worker restarted between the response and the task, the money silently
never reached MT — no persistence, no retry. This is a DB-backed queue (no Redis dependency —
"super light"): claims are persisted, retried with backoff, and de-duplicated by an idempotency
key so a job never runs twice.

  enqueue(db, kind, payload, key)  -> insert a job (ON CONFLICT key DO NOTHING = idempotent)
  claim_one(db)                    -> atomically take the next due job (FOR UPDATE SKIP LOCKED)
  run(job)                         -> dispatch to HANDLERS[kind]; mark done/failed w/ backoff

The worker loop lives in job_worker.py. Handlers live in job_handlers.py.
"""
import json
import db_config
from sqlalchemy import text

MAX_ATTEMPTS = 6
# exponential backoff seconds by attempt #: ~10s, 30s, 2m, 10m, 30m, 2h
BACKOFF = [10, 30, 120, 600, 1800, 7200]


def ensure_schema(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS jobs (
        id BIGSERIAL PRIMARY KEY,
        kind TEXT NOT NULL,
        payload JSONB,
        idempotency_key TEXT,
        status TEXT NOT NULL DEFAULT 'queued',   -- queued | running | done | failed
        attempts INT NOT NULL DEFAULT 0,
        max_attempts INT NOT NULL DEFAULT 6,
        run_after TIMESTAMPTZ DEFAULT NOW(),
        last_error TEXT,
        result JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_idem ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_due ON jobs(status, run_after)"))
    db.commit()


def enqueue(db, kind, payload, key=None, max_attempts=MAX_ATTEMPTS):
    """Insert a job. If `key` is given and already exists, this is a no-op (idempotent enqueue).
    Commits its own row. Returns the job id (or the existing one)."""
    try:
        ensure_schema(db)
        row = db.execute(text("""
            INSERT INTO jobs (kind, payload, idempotency_key, max_attempts)
            VALUES (:k, CAST(:p AS jsonb), :key, :ma)
            ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
            RETURNING id
        """), {"k": kind, "p": json.dumps(payload or {}), "key": key, "ma": max_attempts}).fetchone()
        db.commit()
        if row:
            return row[0]
        r = db.execute(text("SELECT id FROM jobs WHERE idempotency_key=:key"), {"key": key}).fetchone()
        return r[0] if r else None
    except Exception as e:
        db.rollback()
        print(f"[jobs] enqueue error: {e}", flush=True)
        return None


def enqueue_tx(db, kind, payload, key=None, max_attempts=MAX_ATTEMPTS):
    """Enqueue INSIDE the caller's open transaction (does NOT commit). Use this to enqueue a job
    in the SAME transaction as the state change it depends on — the transactional-outbox pattern:
    the job and the business row commit atomically, so the job can't be lost after a partial write.
    The `jobs` table must already exist (ensure_schema runs at app + worker startup). Caller commits."""
    db.execute(text("""
        INSERT INTO jobs (kind, payload, idempotency_key, max_attempts)
        VALUES (:k, CAST(:p AS jsonb), :key, :ma)
        ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
    """), {"k": kind, "p": json.dumps(payload or {}), "key": key, "ma": max_attempts})


def claim_one(db):
    """Atomically take the next due job. Returns (id, kind, payload, attempts) or None.
    FOR UPDATE SKIP LOCKED lets many workers run without stepping on each other."""
    row = db.execute(text("""
        WITH nxt AS (
            SELECT id FROM jobs
            WHERE status='queued' AND run_after <= NOW()
            ORDER BY run_after
            FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE jobs j SET status='running', attempts=attempts+1, updated_at=NOW()
        FROM nxt WHERE j.id=nxt.id
        RETURNING j.id, j.kind, j.payload, j.attempts, j.max_attempts
    """)).fetchone()
    db.commit()
    return row


def mark_done(db, job_id, result=None):
    db.execute(text("UPDATE jobs SET status='done', result=CAST(:r AS jsonb), updated_at=NOW() WHERE id=:i"),
               {"r": json.dumps(result or {}), "i": job_id})
    db.commit()


def mark_retry_or_fail(db, job_id, attempts, max_attempts, err):
    if attempts >= max_attempts:
        db.execute(text("UPDATE jobs SET status='failed', last_error=:e, updated_at=NOW() WHERE id=:i"),
                   {"e": str(err)[:2000], "i": job_id})
    else:
        delay = BACKOFF[min(attempts - 1, len(BACKOFF) - 1)]
        db.execute(text("""UPDATE jobs SET status='queued', last_error=:e,
                           run_after=NOW() + make_interval(secs => :d), updated_at=NOW() WHERE id=:i"""),
                   {"e": str(err)[:2000], "d": delay, "i": job_id})
    db.commit()
