"""One-shot MT4 fetch: connect, pull users + closed trades ONCE, save, exit. No loop."""
import sys, logging, traceback
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mt4_once")

import bridge_mt4 as b

DAYS = 1 / 24  # 1-hour window: the loop runs every 60s so a 1h window is 60x overlap (plenty),
               # and the MT4 journal is so dense (~293k records/hour) that a wider window blows past
               # the ~288k server record cap (which silently truncated recent trades -> MT4
               # commission froze Jul 15). Fetched in 30-min cap-safe chunks. Any brief truncation
               # of the very newest minutes self-heals on the next cycle as the window slides.

def main():
    # 1. connect + login (sets up the global manager inside bridge_mt4)
    log.info("Connecting to MT4...")
    b.load_dll()
    b.get_manager()
    b.connect()

    # 2. users -> clients + trading_accounts (THE missing piece)
    log.info("Fetching all users...")
    users = b.get_all_users()
    log.info("Got %d users, saving to clients/trading_accounts...", len(users))
    b.save_mt4_clients(users)
    log.info("save_mt4_clients done")

    # 3. closed trades -> deals (journal method = the working one per the code)
    log.info("Fetching closed trade history (last %.1fh)...", DAYS*24)
    try:
        trades = b.sync_trade_journal(days=DAYS)
        log.info("Got %d closed trades, saving to deals...", len(trades) if trades else 0)
        if trades:
            b.save_journal_deals(trades)
        log.info("save_journal_deals done")
    except Exception as e:
        log.error("trade history step failed: %s", e)
        traceback.print_exc()

    log.info("=== ONE-SHOT FETCH COMPLETE ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error("FATAL: %s", e)
        traceback.print_exc()
        sys.exit(1)
