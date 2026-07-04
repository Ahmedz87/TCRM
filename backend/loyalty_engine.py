"""
loyalty_engine.py — TN Point Program (loyalty) core engine.

Reads CLOSED, ELIGIBLE trades (FX majors/minors + XAUUSD) and:
  - awards points = lots * tier_rate  (Bronze4/Silver5/Gold6/Plat7)
  - tracks per-client streak of consecutive TRADING days (weekends skipped)
  - promotes at 30 / 30 / 40-day streaks
  - demotes after 30 days inactivity (Bronze is floor)
Points roll up PER CLIENT across all their logins.
"""
import datetime
from sqlalchemy import text

TIER_RATE = {"bronze": 4, "silver": 5, "gold": 6, "platinum": 7}
TIER_ORDER = ["bronze", "silver", "gold", "platinum"]
# Consecutive STRICT trading-day streak required to promote FROM each tier (resets on promotion):
#   Bronze->Silver 30, Silver->Gold 30, Gold->Platinum 60. Weekends don't count as gaps, but any
#   MISSED trading day breaks the streak — there are no "pass" days (removed Jun 2026 per desk).
PROMO_STREAK = {"bronze": 30, "silver": 30, "gold": 60}   # days to promote FROM this tier
DEMOTE_INACTIVE_DAYS = 30

# eligible: 6-letter FX pairs OR XAUUSD (after stripping suffixes). Excludes indices/oil/crypto/other metals.
ELIGIBLE_SQL = r"""
    ( regexp_replace(upper(symbol),'\.(C|R|M|V|PRO)?$','') ~ '^[A-Z]{6}$'
      OR regexp_replace(upper(symbol),'\.(C|R|M|V|PRO)?$','') = 'XAUUSD' )
"""
# but exclude non-FX 6-letter junk: keep only if quote or base is a real currency, plus XAUUSD.
# Simpler robust filter: base/quote must be in known currency set, OR symbol is XAUUSD.
CURRENCIES = {'USD','EUR','GBP','JPY','CHF','CAD','AUD','NZD','CNH','SGD','XAU'}


def normalize_symbol(sym):
    s = (sym or "").upper()
    for suf in ('.C', '.R', '.M', '.V', '.PRO', '.'):
        if s.endswith(suf):
            s = s[:-len(suf)]
    return s


def is_eligible(sym):
    s = normalize_symbol(sym)
    if s == 'XAUUSD':
        return True
    if len(s) == 6 and s.isalpha():
        base, quote = s[:3], s[3:]
        # FX majors/minors: both must be currencies, and exclude metals other than gold
        if base in CURRENCIES and quote in CURRENCIES and 'XAG' not in s:
            return True
    return False


def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loyalty_accounts (
            client_id     INT PRIMARY KEY,
            tier          VARCHAR(12) DEFAULT 'bronze',
            best_tier     VARCHAR(12) DEFAULT 'bronze',
            points_balance DOUBLE PRECISION DEFAULT 0,
            lifetime_points DOUBLE PRECISION DEFAULT 0,
            current_streak INT DEFAULT 0,
            best_streak    INT DEFAULT 0,
            pass_tokens    INT DEFAULT 0,
            pass_days_used INT DEFAULT 0,
            last_trade_date DATE,
            referral_code  VARCHAR(16),
            referred_by    INT,
            created_at     TIMESTAMP DEFAULT NOW(),
            updated_at     TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loyalty_ledger (
            id          SERIAL PRIMARY KEY,
            client_id   INT,
            kind        VARCHAR(20),       -- 'trade','referral','redemption','adjust'
            points      DOUBLE PRECISION,  -- +earn / -redeem
            lots        DOUBLE PRECISION,
            tier        VARCHAR(12),
            symbol      VARCHAR(32),
            ref         VARCHAR(64),       -- trade id / reward id
            trade_date  DATE,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_loy_ledger_client ON loyalty_ledger(client_id)"))
    db.execute(text("ALTER TABLE loyalty_accounts ADD COLUMN IF NOT EXISTS best_tier VARCHAR(12) DEFAULT 'bronze'"))
    db.execute(text("ALTER TABLE loyalty_accounts ADD COLUMN IF NOT EXISTS pass_tokens INT DEFAULT 0"))
    db.execute(text("ALTER TABLE loyalty_accounts ADD COLUMN IF NOT EXISTS pass_days_used INT DEFAULT 0"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loyalty_rewards (
            id SERIAL PRIMARY KEY,
            name VARCHAR(80),
            cost_points DOUBLE PRECISION,
            category VARCHAR(30),
            description TEXT,
            active BOOLEAN DEFAULT TRUE,
            sort_order INT DEFAULT 0
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loyalty_redemptions (
            id SERIAL PRIMARY KEY,
            client_id INT,
            reward_id INT,
            reward_name VARCHAR(80),
            cost_points DOUBLE PRECISION,
            status VARCHAR(20) DEFAULT 'pending',  -- pending/approved/fulfilled/rejected
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loyalty_referrals (
            id SERIAL PRIMARY KEY,
            referrer_client_id INT,
            referred_client_id INT,
            referred_login BIGINT,
            bonus_points DOUBLE PRECISION DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',  -- pending/qualified
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.commit()
    _seed_rewards(db)


def _seed_rewards(db):
    n = db.execute(text("SELECT COUNT(*) FROM loyalty_rewards")).scalar()
    if n and n > 0:
        return
    rewards = [
        ("Trading Bonus $50", 50, "bonus", "Redeem 50 points for a $50 trading bonus (1 point = $1).", 1),
        ("Trading Bonus $100", 100, "bonus", "Redeem 100 points for a $100 trading bonus.", 2),
        ("Cashback", 120, "cashback", "Cash back to your wallet (points / 12).", 3),
        ("Branded Merchandise", 2000, "merch", "TN-branded premium merchandise pack.", 4),
        ("iPhone 17", 12000, "gadget", "Latest iPhone 17.", 5),
        ("Dubai Trip", 20000, "travel", "All-expenses Dubai trip.", 6),
        ("Luxury Car", 75000, "grand", "Luxury car grand prize.", 7),
    ]
    for name, cost, cat, desc, order in rewards:
        db.execute(text("""
            INSERT INTO loyalty_rewards (name, cost_points, category, description, sort_order)
            VALUES (:n,:c,:cat,:d,:o)
        """), {"n": name, "c": cost, "cat": cat, "d": desc, "o": order})
    db.commit()


def _tier_rate(tier):
    return TIER_RATE.get(tier, 4)


def rebuild_from_trades(db, start_date, end_date):
    """
    Full rebuild over a date window. Processes each client's eligible closed
    trades in time order, awarding points at the tier in effect at that time,
    updating streak and tier as it goes. Idempotent: clears loyalty data first.
    """
    print("Resetting loyalty data...")
    # DELETE (children first for FK) in the SAME transaction as the re-insert below — no commit
    # here — so a reader during a live refresh never sees an empty loyalty table (MVCC keeps the
    # old rows visible until the single final commit). (TRUNCATE would commit immediately and
    # leave loyalty blank for the whole ~50s rebuild.)
    db.execute(text("DELETE FROM loyalty_ledger"))
    db.execute(text("DELETE FROM loyalty_redemptions"))
    db.execute(text("DELETE FROM loyalty_accounts"))

    start_ts = int(datetime.datetime.combine(start_date, datetime.time()).timestamp())
    end_ts   = int(datetime.datetime.combine(end_date,   datetime.time()).timestamp())

    # pull all eligible closed trades in window, joined to client_id, ordered by client+time
    print("Loading eligible trades...")
    rows = db.execute(text(f"""
        SELECT COALESCE(ta.client_id, c.id) AS client_id, d.login, d.symbol, d.volume, d.deal_time,
               COALESCE(ta.group_name, c.group_name, '') AS group_name
        FROM deals d
        LEFT JOIN trading_accounts ta ON ta.login = d.login
        LEFT JOIN clients c ON c.login = d.login
        WHERE d.entry=1 AND d.action IN (0,1)
          AND d.deal_time >= :s AND d.deal_time < :e
          AND COALESCE(ta.client_id, c.id) IS NOT NULL
        ORDER BY COALESCE(ta.client_id, c.id), d.deal_time
    """), {"s": start_ts, "e": end_ts}).fetchall()
    print(f"  {len(rows):,} closed trades to process")

    from collections import defaultdict
    # group by client
    by_client = defaultdict(list)
    for client_id, login, symbol, volume, deal_time, group_name in rows:
        # MT5 volume: 1.00 standard lot = 10,000 (min 0.01 lot = volume 100)
        lots = float(volume or 0) / 10000.0
        if group_name and 'cent' in group_name.lower():
            lots = lots / 10.0
        eligible = is_eligible(symbol)   # only FX + Gold earn POINTS
        by_client[client_id].append((deal_time, symbol, lots, eligible))

    print(f"  {len(by_client):,} clients with eligible trades")

    account_rows = []   # accumulate then bulk-insert (DB is remote — per-row INSERT is too slow)
    all_ledger = []
    for client_id, trades in by_client.items():
        tier = "bronze"
        best_tier_idx = 0
        balance = 0.0
        lifetime = 0.0
        streak = 0
        best = 0
        pass_tokens = 0      # banked pass days (earned by consistent trading)
        pass_days_used = 0   # lifetime off-days bridged by passes
        last_date = None
        ledger_rows = []

        for deal_time, symbol, lots, eligible in trades:
            tdate = datetime.date.fromtimestamp(deal_time)
            new_day = (last_date is None) or (tdate != last_date)
            # streak update on first trade of a NEW day
            if last_date is None:
                streak = 1
            elif tdate == last_date:
                pass  # same day, streak unchanged
            else:
                gap = _trading_day_gap(last_date, tdate)
                if gap == 0:
                    pass  # weekend-adjacent date (e.g. Sun/Sat trade after Fri) -> not a new trading day
                elif gap == 1:
                    streak += 1
                else:
                    streak = 1        # STRICT: any missed trading day breaks the streak (passes removed)
                # promotion check on streak increase
                promo = PROMO_STREAK.get(tier)
                if promo and streak >= promo and tier != "platinum":
                    idx = TIER_ORDER.index(tier)
                    tier = TIER_ORDER[idx+1]
                    best_tier_idx = max(best_tier_idx, idx+1)
                    streak = 0  # reset streak after promotion
            if new_day:
                best = max(best, streak)
            last_date = tdate

            if eligible:
                pts = lots * _tier_rate(tier)
                balance += pts
                lifetime += pts
                ledger_rows.append((client_id, 'trade', pts, lots, tier, symbol, tdate))

        best_tier = TIER_ORDER[best_tier_idx]
        account_rows.append((client_id, tier, best_tier, balance, lifetime, streak, best,
                             pass_tokens, pass_days_used, last_date, f"TN{client_id:06d}"))
        all_ledger.extend(ledger_rows[:500])   # cap stored detail to keep it light

    # Bulk-write in batched multi-row INSERTs. The DB is REMOTE now, so the old per-row INSERT
    # loop (~955k network round-trips) took 15-25 min; execute_values does it in seconds.
    # loyalty tables were TRUNCATEd above, so these are plain inserts (no conflicts).
    from psycopg2.extras import execute_values
    raw = db.connection().connection
    cur = raw.cursor()
    execute_values(cur,
        "INSERT INTO loyalty_accounts (client_id,tier,best_tier,points_balance,lifetime_points,"
        "current_streak,best_streak,pass_tokens,pass_days_used,last_trade_date,referral_code) VALUES %s",
        account_rows, page_size=1000)
    if all_ledger:
        execute_values(cur,
            "INSERT INTO loyalty_ledger (client_id,kind,points,lots,tier,symbol,trade_date) VALUES %s",
            all_ledger, page_size=1000)
    db.commit()
    print(f"Loyalty rebuild complete. accounts={len(account_rows)} ledger={len(all_ledger)}")


def _trading_day_gap(d1, d2):
    """
    Number of TRADING days between d1 and d2 (weekends don't count as gaps).
    Returns 1 if d2 is the next trading day after d1 (Fri->Mon = 1).
    """
    if d2 <= d1:
        return 0
    days = 0
    cur = d1
    while cur < d2:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5:   # Mon-Fri are trading days
            days += 1
    return days
