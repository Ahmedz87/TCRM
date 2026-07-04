"""Template for ts_mysql_config.py (gitignored). Copy to ts_mysql_config.py and fill in."""
import os
MYSQL_SRC = dict(
    host=os.getenv("TS_MYSQL_HOST", "YOUR_MYSQL_HOST"),
    port=int(os.getenv("TS_MYSQL_PORT", "3306")),
    user=os.getenv("TS_MYSQL_USER", "YOUR_MYSQL_USER"),
    password=os.getenv("TS_MYSQL_PASSWORD", "YOUR_MYSQL_PASSWORD"),
    database=os.getenv("TS_MYSQL_DB", "YOUR_MYSQL_DB"),
    connect_timeout=15, read_timeout=900, charset="utf8mb4", use_unicode=True,
)
