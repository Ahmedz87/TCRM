"""
run_hedge_scan.py — Run the hedge engine across MT5 accounts, store results.

Creates two tables:
  hedge_flagged_traders — one row per flagged account (ratio, reasons, etc.)
  hedge_trades          — the listed hedge matches (the abuse-trades list)

Usage:
  python run_hedge_scan.py --days 180 [--limit N] [--sample]
"""
import argparse, time
from sqlalchemy import text
from database import SessionLocal
import hedge_engine as HE


def ensure_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS hedge_flagged_traders (
            login BIGINT PRIMARY KEY,
            score INT,
            has_bonus BOOLEAN,
            credit DOUBLE PRECISION,
            total_positions INT,
            hedged_positions INT,
            hedged_ratio DOUBLE PRECISION,
            hedged_volume_ratio DOUBLE PRECISION,
            has_connected_hedge BOOLEAN,
            biggest_is_hedge BOOLEAN,
            connected_accounts TEXT,
            reasons TEXT,
            listed_count INT,
            scanned_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS hedge_trades (
            id SERIAL PRIMARY KEY,
            owner_login BIGINT,
            buy_login BIGINT, sell_login BIGINT,
            buy_sym VARCHAR, sell_sym VARCHAR, relation VARCHAR,
            buy_vol DOUBLE PRECISION, sell_vol DOUBLE PRECISION,
            overlap_sec BIGINT, cross_account BOOLEAN,
            buy_profit DOUBLE PRECISION, sell_profit DOUBLE PRECISION,
            open_time BIGINT
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_hedge_trades_owner ON hedge_trades(owner_login)"))
    db.commit()


def run(days, limit, sample):
    db = SessionLocal()
    ensure_tables(db)
    since = int(time.time()) - days*24*3600

    # candidate logins: MT5 accounts with positions having open_time
    q = """
        SELECT DISTINCT login FROM deals
        WHERE platform='MT5' AND entry=1 AND open_time IS NOT NULL
          AND deal_time >= :since
    """
    if sample:
        q += " LIMIT 200"
    elif limit:
        q += f" LIMIT {int(limit)}"
    logins = [r[0] for r in db.execute(text(q), {"since": since}).fetchall()]
    print(f"{len(logins)} MT5 accounts to scan (last {days} days)")

    # fresh results
    db.execute(text("DELETE FROM hedge_flagged_traders"))
    db.execute(text("DELETE FROM hedge_trades"))
    db.commit()

    flagged = 0; t0 = time.time()
    for n, login in enumerate(logins, 1):
        try:
            res = HE.scan_account(db, login, since)
        except Exception as e:
            db.rollback(); continue
        if res:
            flagged += 1
            db.execute(text("""
                INSERT INTO hedge_flagged_traders
                  (login, score, has_bonus, credit, total_positions, hedged_positions,
                   hedged_ratio, hedged_volume_ratio, has_connected_hedge, biggest_is_hedge,
                   connected_accounts, reasons, listed_count)
                VALUES (:l,:sc,:hb,:cr,:tp,:hp,:hr,:hvr,:hc,:bh,:ca,:rs,:lc)
                ON CONFLICT (login) DO UPDATE SET
                  score=:sc, has_bonus=:hb, credit=:cr,
                  total_positions=:tp, hedged_positions=:hp, hedged_ratio=:hr,
                  hedged_volume_ratio=:hvr, has_connected_hedge=:hc,
                  biggest_is_hedge=:bh, connected_accounts=:ca, reasons=:rs,
                  listed_count=:lc, scanned_at=NOW()
            """), {
                "l": login, "sc": res["score"], "hb": res["has_bonus"], "cr": res["credit"],
                "tp": res["total_positions"], "hp": res["hedged_positions"],
                "hr": res["hedged_ratio"], "hvr": res["hedged_volume_ratio"],
                "hc": res["has_connected_hedge"], "bh": res["biggest_is_hedge"],
                "ca": ",".join(str(x) for x in res["connected_accounts"][:20]),
                "rs": "; ".join(res["reasons"]), "lc": res["listed_count"],
            })
            for tr in res["listed_trades"]:
                db.execute(text("""
                    INSERT INTO hedge_trades
                      (owner_login, buy_login, sell_login, buy_sym, sell_sym, relation,
                       buy_vol, sell_vol, overlap_sec, cross_account, buy_profit, sell_profit, open_time)
                    VALUES (:o,:bl,:sl,:bs,:ss,:r,:bv,:sv,:ov,:cr,:bp,:sp,:ot)
                """), {
                    "o": login, "bl": tr["buy_login"], "sl": tr["sell_login"],
                    "bs": tr["buy_sym"], "ss": tr["sell_sym"], "r": tr["relation"],
                    "bv": tr["buy_vol"], "sv": tr["sell_vol"], "ov": tr["overlap_sec"],
                    "cr": tr["cross"], "bp": tr["buy_profit"], "sp": tr["sell_profit"],
                    "ot": tr["open"],
                })
            db.commit()
        if n % 200 == 0:
            el = time.time()-t0; rate = n/el; eta = (len(logins)-n)/rate/60
            print(f"  {n}/{len(logins)} scanned, {flagged} flagged, ETA {eta:.0f} min")

    print(f"\nDONE. {flagged} accounts flagged of {len(logins)} scanned.")
    # summary by score tier
    rows = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE score >= 75) as critical,
          COUNT(*) FILTER (WHERE score >= 60 AND score < 75) as high,
          COUNT(*) FILTER (WHERE score >= 45 AND score < 60) as medium,
          COUNT(*) FILTER (WHERE has_bonus) as with_bonus,
          COUNT(*) as total
        FROM hedge_flagged_traders
    """)).fetchone()
    print(f"  Critical(>=75): {rows[0]}   High(60-74): {rows[1]}   Medium(45-59): {rows[2]}")
    print(f"  With bonus credit: {rows[3]}   Total flagged: {rows[4]}")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    run(a.days, a.limit, a.sample)
