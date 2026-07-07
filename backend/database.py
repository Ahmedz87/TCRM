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
# exceeding Postgres max_connections=100. Single-instance default stays 20+20 (=40); the
# multi-instance launcher sets BROKER_POOL_SIZE=8 / BROKER_POOL_OVERFLOW=6 (=14 each) so
# 4 instances = 56, leaving headroom for the loops/bridges/scripts.
_POOL_SIZE     = int(os.getenv("BROKER_POOL_SIZE", "20"))
_POOL_OVERFLOW = int(os.getenv("BROKER_POOL_OVERFLOW", "20"))
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=_POOL_SIZE,
    max_overflow=_POOL_OVERFLOW,
    pool_recycle=1800,
    pool_timeout=10,           # fail fast instead of hanging the request if the pool is momentarily full
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()