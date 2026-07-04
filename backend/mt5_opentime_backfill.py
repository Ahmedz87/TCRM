"""
mt5_opentime_backfill.py
Adds position_id + open_time to deals and fills open_time for MT5 trades by
pairing each position's Entry=0 (open) and Entry=1 (close) deals via PositionID.

Run:  python mt5_opentime_backfill.py --days 30
"""
import argparse, time, sys
import db_config
import psycopg2
import bridge

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)


def ensure_columns():
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS position_id BIGINT")
    cur.execute("ALTER TABLE deals ADD COLUMN IF NOT EXISTS open_time BIGINT")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_deals_position_id ON deals(position_id)")
    conn.commit(); conn.close()
    print("Columns ready: position_id, open_time (+ index)")


def backfill(days):
    mgr = bridge.get_manager()
    if not mgr:
        print("No MT5 manager"); sys.exit(1)
    now = int(time.time()); ft = now - days*24*3600

    # Pull all MT5 logins from DB (trading_accounts platform MT5)
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("SELECT login FROM trading_accounts WHERE platform='MT5'")
    logins = [r[0] for r in cur.fetchall()]
    print(f"{len(logins)} MT5 logins to scan over last {days} days")

    BATCH = 200
    updated = 0
    for i in range(0, len(logins), BATCH):
        chunk = logins[i:i+BATCH]
        try:
            deals = mgr.DealRequestByLogins(chunk, ft, now) or []
        except Exception as e:
            print(f"  batch {i}: error {e}")
            continue

        # group deals by position_id; find entry (Entry=0) open time
        opens = {}   # position_id -> open_time
        closes = []  # (deal_id, position_id, close_time)
        for d in deals:
            act = getattr(d, "Action", -1)
            if act not in (0, 1):
                continue
            pos = getattr(d, "PositionID", 0)
            entry = getattr(d, "Entry", -1)
            t = getattr(d, "Time", 0)
            deal_id = getattr(d, "Deal", 0)
            if entry == 0:
                # earliest entry = open
                if pos not in opens or t < opens[pos]:
                    opens[pos] = t
            elif entry == 1:
                closes.append((deal_id, pos, t))

        # update each close deal's open_time + store position_id on all
        for deal_id, pos, ctime in closes:
            ot = opens.get(pos)
            if ot:
                cur.execute(
                    "UPDATE deals SET position_id=%s, open_time=%s WHERE deal_id=%s",
                    (pos, ot, deal_id))
                updated += cur.rowcount
        # also stamp position_id on the open deals we know
        conn.commit()
        print(f"  scanned {i+len(chunk)}/{len(logins)} logins, updated {updated} close deals so far")

    conn.close()
    print(f"DONE. open_time filled on {updated} MT5 deals.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    ensure_columns()
    backfill(args.days)
