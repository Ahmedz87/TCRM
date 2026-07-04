"""
sql_hedge_scan.py — FAST hedge detection done in SQL (seconds, not an hour).

Step 1: build mt5_positions (one row per position: open+close time, dir, sym, base/quote)
Step 2: SQL self-join finds overlapping opposite positions (same symbol/base/quote)
Step 3: aggregate per account -> hedge ratio -> score -> store flagged top tier
"""
import time
from sqlalchemy import text
from database import SessionLocal

SINCE_DAYS = 180
SCORE_THRESHOLD = 45


def build_positions(db):
    print("Building mt5_positions table...")
    since = int(time.time()) - SINCE_DAYS*24*3600
    db.execute(text("DROP TABLE IF EXISTS mt5_positions"))
    db.execute(text("""
        CREATE TABLE mt5_positions AS
        SELECT
            e.login,
            e.position_id,
            CASE WHEN e.action=0 THEN 'buy' ELSE 'sell' END AS direction,
            e.deal_time AS open_time,
            x.deal_time AS close_time,
            COALESCE(x.volume, e.volume) AS volume,
            x.profit AS profit,
            UPPER(regexp_replace(COALESCE(x.symbol,e.symbol), '\\.(c|r|m|pro)?$', '', 'i')) AS sym
        FROM deals e
        JOIN deals x ON e.position_id = x.position_id AND e.login = x.login
        WHERE e.entry=0 AND x.entry=1 AND e.platform='MT5'
          AND e.action IN (0,1) AND e.open_time IS NOT NULL
          AND e.deal_time >= :since
    """), {"since": since})
    # base / quote columns
    db.execute(text("ALTER TABLE mt5_positions ADD COLUMN base TEXT, ADD COLUMN quote TEXT"))
    db.execute(text("""
        UPDATE mt5_positions SET
          base = CASE
            WHEN sym IN ('USOIL','UKOIL','BRENT','WTI','XBRUSD','XTIUSD') THEN 'OIL'
            WHEN length(sym)=6 AND sym ~ '^[A-Z]{6}$' THEN left(sym,3)
            WHEN right(sym,3)='USD' AND length(sym)>3 THEN left(sym, length(sym)-3)
            ELSE sym END,
          quote = CASE
            WHEN sym IN ('USOIL','UKOIL','BRENT','WTI','XBRUSD','XTIUSD') THEN 'USD'
            WHEN length(sym)=6 AND sym ~ '^[A-Z]{6}$' THEN right(sym,3)
            WHEN right(sym,3)='USD' AND length(sym)>3 THEN 'USD'
            ELSE NULL END
    """))
    db.execute(text("CREATE INDEX ix_mp_login ON mt5_positions(login)"))
    db.execute(text("CREATE INDEX ix_mp_sym ON mt5_positions(sym)"))
    db.execute(text("CREATE INDEX ix_mp_times ON mt5_positions(open_time, close_time)"))
    db.commit()
    n = db.execute(text("SELECT COUNT(*) FROM mt5_positions")).scalar()
    print(f"  {n:,} positions built")


def find_hedged(db):
    """
    Mark hedged positions via overlap self-join. A position is 'hedged' if an
    opposite-direction position on a related symbol (same sym, base, or quote)
    overlapped in time, within the SAME account.
    """
    print("Detecting hedges (SQL self-join)...")
    db.execute(text("DROP TABLE IF EXISTS mt5_hedged_pos"))
    db.execute(text("""
        CREATE TABLE mt5_hedged_pos AS
        SELECT DISTINCT a.login, a.position_id
        FROM mt5_positions a
        JOIN mt5_positions b
          ON a.login = b.login
         AND a.position_id <> b.position_id
         AND a.direction <> b.direction
         AND a.open_time <= b.close_time
         AND b.open_time <= a.close_time
         AND (
              a.sym = b.sym
           OR a.base = b.base
           OR (a.quote IS NOT NULL AND a.quote = b.quote)
         )
    """))
    db.execute(text("CREATE INDEX ix_mhp ON mt5_hedged_pos(login, position_id)"))
    db.commit()
    n = db.execute(text("SELECT COUNT(*) FROM mt5_hedged_pos")).scalar()
    print(f"  {n:,} hedged positions")


def score_and_store(db):
    print("Scoring accounts...")
    # per-account totals + hedged counts
    db.execute(text("DROP TABLE IF EXISTS hedge_flagged_traders"))
    db.execute(text("""
        CREATE TABLE hedge_flagged_traders AS
        WITH tot AS (
            SELECT login, COUNT(*) AS total_pos, SUM(volume) AS total_vol
            FROM mt5_positions GROUP BY login
        ),
        hed AS (
            SELECT login, COUNT(*) AS hedged_pos
            FROM mt5_hedged_pos GROUP BY login
        )
        SELECT
            t.login,
            t.total_pos AS total_positions,
            COALESCE(h.hedged_pos,0) AS hedged_positions,
            COALESCE(h.hedged_pos,0)::float / NULLIF(t.total_pos,0) AS hedged_ratio,
            COALESCE(ta.credit,0) AS credit,
            (COALESCE(ta.credit,0) > 0) AS has_bonus,
            COALESCE(ta.balance,0) AS balance,
            COALESCE(ta.total_deposits,0) AS deposits,
            0::int AS score,
            ''::text AS reasons,
            NOW() AS scanned_at
        FROM tot t
        LEFT JOIN hed h ON h.login=t.login
        LEFT JOIN trading_accounts ta ON ta.login=t.login
        WHERE t.total_pos >= 5
    """))
    db.commit()

    # strong link: shares ip/cid/mqid with another flagged hedger
    db.execute(text("""
        ALTER TABLE hedge_flagged_traders
        ADD COLUMN IF NOT EXISTS strong_link BOOLEAN DEFAULT FALSE
    """))
    db.execute(text("""
        UPDATE hedge_flagged_traders f SET strong_link = TRUE
        WHERE EXISTS (
            SELECT 1 FROM network_edges ne
            JOIN hedge_flagged_traders f2
              ON (f2.login = CASE WHEN ne.login_a=f.login THEN ne.login_b ELSE ne.login_a END)
            WHERE (ne.login_a=f.login OR ne.login_b=f.login)
              AND ne.reason IN ('ip','cid','mqid')
              AND f2.hedged_ratio >= 0.4
        )
    """))
    db.commit()

    # compute score
    db.execute(text("""
        UPDATE hedge_flagged_traders SET score = LEAST(100, ROUND(
            100 * (
                0.45 * GREATEST(0, (hedged_ratio - 0.4) / 0.6) +
                0.25 * CASE WHEN has_bonus THEN LEAST(1.0, credit/(deposits+1)) ELSE 0 END +
                0.20 * CASE WHEN strong_link THEN 1 ELSE 0 END +
                0.10 * CASE WHEN has_bonus AND balance < credit*0.1 THEN 1 ELSE 0 END
            )
            + CASE WHEN has_bonus AND hedged_ratio >= 0.6 THEN 8 ELSE 0 END
        ))
    """))
    # build reasons text
    db.execute(text("""
        UPDATE hedge_flagged_traders SET reasons =
            ROUND(hedged_ratio*100) || '% hedged'
            || CASE WHEN has_bonus THEN '; bonus $' || ROUND(credit) ELSE '' END
            || CASE WHEN strong_link THEN '; strong link to hedger' ELSE '' END
    """))
    db.commit()

    # keep only top tier
    db.execute(text(f"DELETE FROM hedge_flagged_traders WHERE score < {SCORE_THRESHOLD}"))
    db.commit()

    r = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE score>=75),
          COUNT(*) FILTER (WHERE score>=60 AND score<75),
          COUNT(*) FILTER (WHERE score>=45 AND score<60),
          COUNT(*) FILTER (WHERE has_bonus),
          COUNT(*)
        FROM hedge_flagged_traders
    """)).fetchone()
    print(f"\nDONE. Critical(>=75): {r[0]}  High(60-74): {r[1]}  Medium(45-59): {r[2]}")
    print(f"      With bonus: {r[3]}   Total flagged: {r[4]}")


if __name__ == "__main__":
    db = SessionLocal()
    t0 = time.time()
    build_positions(db)
    find_hedged(db)
    score_and_store(db)
    print(f"\nTotal time: {time.time()-t0:.0f}s")
    db.close()
