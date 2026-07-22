import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    class Config:
        env_file = ".env"

settings = Settings()

# pool_pre_ping: detect & replace dead/poisoned connections before reuse (prevents the
# "idle in transaction" hang that took login down). Larger pool + recycle for headroom.
# Pool sizes are ENV-CONFIGURABLE so we can run MULTIPLE uvicorn instances (multi-worker via
# separate ports behind nginx, since uvicorn --workers is broken on this Windows box) without
# DB is S2 PostgreSQL 18, max_connections=200 (3 reserved). Single-instance default 20+20 (=40).
# The multi-instance launcher (start_core.ps1 / restart_backend.ps1) sets BROKER_POOL_SIZE=15 /
# BROKER_POOL_OVERFLOW=10 (=25 each) so the 6 instances cap at ~150, leaving ~47 for the bridge/
# workers/loops/scripts — well under 200. Raised from 6+4 (Jul 17) after a load test hit
# "QueuePool limit ... connection timed out" 500s under a burst of distinct users (each user's
# /dashboard/kpis etc. is cached per-token, so N cold users = N concurrent DB checkouts). The real
# fix for the 2-3k-concurrent target is PgBouncer transaction pooling (P0-48); this is the interim.
_POOL_SIZE     = int(os.getenv("BROKER_POOL_SIZE", "20"))
_POOL_OVERFLOW = int(os.getenv("BROKER_POOL_OVERFLOW", "20"))
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=_POOL_SIZE,
    max_overflow=_POOL_OVERFLOW,
    pool_recycle=1800,
    pool_timeout=10,           # fail fast instead of hanging the request if the pool is momentarily full
    connect_args={
        # SAFETY (Jul 15 2026): a request killed mid-transaction (e.g. a forced backend
        # restart, or a client that vanishes) left connections "idle in transaction" for
        # 14+ min, holding pool slots until every new /auth/me timed out and the whole CRM
        # showed "loading". These server-side timeouts make any stuck session self-clear:
        #   - idle_in_transaction_session_timeout: kill a txn left open with no work for 30s
        #   - statement_timeout: no single query may run > 60s (a runaway can't wedge the pool)
        # Plus TCP keepalives so a dead client is detected in ~1min, not hours.
        "options": "-c idle_in_transaction_session_timeout=30000 -c statement_timeout=180000",
        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3,
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()