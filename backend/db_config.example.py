"""
db_config.example.py — template for db_config.py (which is gitignored, holds the real password).

Copy this to db_config.py and fill in the real values, OR (preferred) leave db_config.py
using os.getenv() and set the BROKER_DB_* environment variables on each machine. All raw
psycopg2 scripts/loops connect via db_config.connect() (or DSN / SQLALCHEMY_URL) instead of
hardcoding host/password, so a host move or password rotation is a single edit / env change.
"""
import os
import psycopg2

DB_HOST     = os.getenv("BROKER_DB_HOST",     "YOUR_DB_HOST")   # e.g. the S2 database box IP
DB_PORT     = os.getenv("BROKER_DB_PORT",     "5432")
DB_NAME     = os.getenv("BROKER_DB_NAME",     "broker_crm")
DB_USER     = os.getenv("BROKER_DB_USER",     "postgres")
DB_PASSWORD = os.getenv("BROKER_DB_PASSWORD", "YOUR_DB_PASSWORD")

DSN = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}"
SQLALCHEMY_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def connect(**kwargs):
    params = dict(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    params.update(kwargs)
    return psycopg2.connect(**params)
