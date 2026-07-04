import time, subprocess, sys
from datetime import datetime
import db_config
import psycopg2

INTERVAL = 60  # seconds

def sync_mt4_to_trading_accounts():
    """Insert any MT4 clients not yet in trading_accounts (keeps accounts page current)."""
    try:
        c = db_config.connect()
        cur = c.cursor()
        cur.execute("""
            INSERT INTO trading_accounts
                (login, name, email, phone, group_name, balance, credit, equity,
                 leverage, country, city, last_ip, cid, mqid, agent, reg_date,
                 is_active, platform, total_deposits, total_withdrawals, net_deposit,
                 kyc_status, risk_score, account_type)
            SELECT c.login, c.name, c.email, c.phone, c.group_name, c.balance, c.credit, c.equity,
                 c.leverage, c.country, c.city, c.last_ip, c.cid, c.mqid, c.agent, c.reg_date,
                 c.is_active, 'MT4', c.total_deposits, c.total_withdrawals, c.net_deposit,
                 c.kyc_status, c.risk_score, c.group_name
            FROM clients c
            WHERE c.platform='MT4'
              AND NOT EXISTS (SELECT 1 FROM trading_accounts ta WHERE ta.login=c.login)
        """)
        n = cur.rowcount
        c.commit(); c.close()
        if n: print(f"  +{n} new MT4 accounts synced to trading_accounts", flush=True)
    except Exception as e:
        print("  sync_mt4 error:", e, flush=True)

print(f"=== MT4 auto-fetch loop (recent, every {INTERVAL}s). Ctrl+C to stop. ===", flush=True)
cycle = 0
while True:
    print(f"\n[{datetime.now():%H:%M:%S}] MT4 recent fetch...", flush=True)
    try:
        subprocess.run([sys.executable, "fetch_mt4_recent.py"], check=False)
        sync_mt4_to_trading_accounts()
        cycle += 1
        # MT4 deposits/withdrawals are now pulled by the dedicated MT4-B (login 1026) worker
        # (mt4_journal_worker.py) on its own connection — so this loop (login 1025) only does
        # the account list and never blocks / needs stopping for journal pulls.
        # Negative-balance auto-cover every 5 cycles (~5 min). Runs as a subprocess on login 1025,
        # SERIALLY after the fetch (so there is never a second concurrent 1025 connection). The
        # cover re-checks each account's LIVE balance and only deposits flat negatives -> $0
        # (guardrails: skip no_auto_cover, skip open abuse cases, skip winning open positions).
        if cycle % 5 == 0:
            print(f"[{datetime.now():%H:%M:%S}] MT4 neg-balance auto-cover sweep...", flush=True)
            subprocess.run([sys.executable, "cover_mt4_negatives.py", "--live"], check=False)
    except Exception as e:
        print("MT4 loop error:", e, flush=True)
    print(f"[{datetime.now():%H:%M:%S}] done, sleeping {INTERVAL}s", flush=True)
    time.sleep(INTERVAL)
