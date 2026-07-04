"""
Copy-Trading seed — schema + ~50 diverse signal-provider profiles.

Creates the copy-trading data model and populates 50 demo providers with realistic,
DIVERSE behaviour: scalpers / intraday / swing, gold-only / FX-majors / EURUSD-only /
indices / multi-asset, winners AND losers, 1..150 days of daily equity history, a sample
of trades consistent with each style, and followers (synthetic + a few real portal clients).

SAFETY: pure demo data in NEW copy_* tables only. No live MT orders, no touch of
clients/deals/trading_accounts. Idempotent — truncates & reseeds the copy_* tables.
Run:  python seed_copy_trading.py
"""
import sys, random, math
from datetime import date, datetime, timedelta
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from sqlalchemy import text

random.seed(42)
TODAY = date(2026, 6, 18)
START_EQUITY = 10000.0

# ───────────────────────── SCHEMA ─────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS copy_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80), country VARCHAR(60), avatar VARCHAR(8),
    strategy VARCHAR(40), markets VARCHAR(80), risk_level INT,
    bio TEXT, fee_pct NUMERIC, min_investment NUMERIC,
    status VARCHAR(20) DEFAULT 'approved',          -- pending/approved/rejected
    client_id INT, login BIGINT,                    -- nullable links (real client / MT login)
    days_active INT, start_date DATE,
    return_pct NUMERIC, return_30d NUMERIC, win_rate NUMERIC,
    max_drawdown NUMERIC, profit_factor NUMERIC, total_trades INT,
    avg_hold_min NUMERIC, followers INT, aum NUMERIC, pnl_total NUMERIC,
    verified BOOLEAN DEFAULT TRUE, featured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS copy_provider_history (
    id SERIAL PRIMARY KEY, provider_id INT, day DATE,
    equity NUMERIC, return_pct NUMERIC, daily_pct NUMERIC
);
CREATE TABLE IF NOT EXISTS copy_provider_trades (
    id SERIAL PRIMARY KEY, provider_id INT, symbol VARCHAR(16), side VARCHAR(4),
    lots NUMERIC, open_time TIMESTAMP, close_time TIMESTAMP, hold_min INT,
    pnl NUMERIC, pips NUMERIC
);
CREATE TABLE IF NOT EXISTS copy_followers (
    id SERIAL PRIMARY KEY, provider_id INT, client_id INT, follower_name VARCHAR(80),
    allocation NUMERIC, multiplier NUMERIC DEFAULT 1.0,
    copy_mode VARCHAR(16) DEFAULT 'proportional',   -- proportional/fixed/mirror
    status VARCHAR(16) DEFAULT 'active', pnl NUMERIC DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_cph_provider ON copy_provider_history (provider_id, day);
CREATE INDEX IF NOT EXISTS ix_cpt_provider ON copy_provider_trades (provider_id, close_time);
CREATE INDEX IF NOT EXISTS ix_cf_provider ON copy_followers (provider_id);
CREATE INDEX IF NOT EXISTS ix_cf_client ON copy_followers (client_id);
"""

# ───────────────────────── ARCHETYPES (trading behaviour) ─────────────────────────
# drift = mean daily %, vol = daily stdev %, tpd = trades/day range, hold = minutes range
ARCH = [
    dict(strategy="Scalping",  markets="XAUUSD",            symbols=["XAUUSD"],
         drift=0.22, vol=1.9, tpd=(18,55), hold=(1,10),   win=0.69, risk=7),
    dict(strategy="Scalping",  markets="EURUSD",            symbols=["EURUSD"],
         drift=0.10, vol=0.7, tpd=(20,70), hold=(1,6),    win=0.66, risk=5),
    dict(strategy="Intraday",  markets="FX Majors",         symbols=["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD"],
         drift=0.14, vol=0.9, tpd=(3,11), hold=(25,200),  win=0.57, risk=4),
    dict(strategy="Intraday",  markets="EURUSD only",       symbols=["EURUSD"],
         drift=0.11, vol=0.6, tpd=(2,7),  hold=(30,240),  win=0.61, risk=3),
    dict(strategy="Swing",     markets="XAUUSD",            symbols=["XAUUSD"],
         drift=0.17, vol=2.3, tpd=(0.4,2),hold=(300,3000),win=0.52, risk=6),
    dict(strategy="News",      markets="Gold + FX",         symbols=["XAUUSD","EURUSD","GBPUSD"],
         drift=0.19, vol=3.1, tpd=(0.5,4),hold=(4,55),    win=0.48, risk=9),
    dict(strategy="Grid",      markets="EUR/GBP",           symbols=["EURUSD","GBPUSD"],
         drift=0.09, vol=2.7, tpd=(6,22), hold=(60,800),  win=0.80, risk=8),  # high win, deep DD
    dict(strategy="Conservative", markets="FX Majors",      symbols=["EURUSD","USDJPY"],
         drift=0.05, vol=0.35,tpd=(1,4),  hold=(120,600), win=0.63, risk=2),
    dict(strategy="Scalping",  markets="XAUUSD aggressive", symbols=["XAUUSD"],
         drift=0.28, vol=3.4, tpd=(10,32),hold=(2,25),    win=0.55, risk=10),
    dict(strategy="Intraday",  markets="US30 / NAS100",     symbols=["US30","NAS100"],
         drift=0.15, vol=2.0, tpd=(2,10), hold=(15,240),  win=0.56, risk=6),
    dict(strategy="Swing",     markets="FX / Metals / Indices", symbols=["XAUUSD","EURUSD","US30","GBPJPY"],
         drift=0.12, vol=1.3, tpd=(3,12), hold=(40,360),  win=0.58, risk=5),
    dict(strategy="Intraday",  markets="GBPJPY specialist", symbols=["GBPJPY"],
         drift=0.16, vol=1.7, tpd=(2,9),  hold=(20,180),  win=0.54, risk=7),
]

FIRST = ["Ahmed","Omar","Yousef","Khaled","Sami","Tariq","Fahad","Nasser","Hassan","Bilal",
         "Marco","Viktor","Dmitri","Lukas","Andre","Chen","Hiro","Raj","Diego","Sofia",
         "Layla","Nour","Mariam","Zaid","Faris","Idris","Salem","Rami","Adel","Jad"]
LAST = ["Al-Rashid","Haddad","Nasr","Kassab","Darwish","Ibrahim","Mansour","Saleh","Khalil","Aziz",
        "Rossi","Petrov","Volkov","Meyer","Dubois","Wang","Tanaka","Sharma","Costa","Ferraro",
        "Hamdan","Najjar","Sultan","Barakat","Fadel","Othman","Zahra","Karam","Rahman","Yousef"]
COUNTRIES = ["UAE","Saudi Arabia","Qatar","Kuwait","Iraq","Jordan","Egypt","Bahrain","Oman",
             "Lebanon","Italy","Germany","Russia","UK","Singapore","Japan","India"]
AVATARS = ["🦅","🐉","🦁","🐺","🦈","🐅","⚡","🔥","💎","🚀","🎯","📈","🏆","👑","🛡️","🌟","🦂","🐂"]

def gen_equity(days, drift, vol, loser):
    """Daily-compounded equity curve. Losers get negative drift + a worse path."""
    d = drift * (-1.0 if loser else 1.0) * (0.4 if loser else 1.0)
    eq = START_EQUITY
    out = []
    for i in range(days):
        r = random.gauss(d, vol)
        r = max(-12.0, min(12.0, r))           # clamp daily move
        eq *= (1 + r/100.0)
        eq = max(eq, 500.0)                    # never blow fully to zero
        out.append((eq, r))
    return out

def drawdown(equities):
    peak = -1e9; mdd = 0.0
    for e in equities:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e)/peak*100 if peak > 0 else 0)
    return round(mdd, 1)

def main():
    db = SessionLocal()
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            db.execute(text(stmt))
    db.commit()
    # idempotent reseed of the demo tables only
    db.execute(text("TRUNCATE copy_followers, copy_provider_trades, copy_provider_history, copy_providers RESTART IDENTITY"))
    db.commit()

    # real portal clients to wire as genuine followers (so 'My Following' is populated)
    real_clients = [r[0] for r in db.execute(text(
        "SELECT id FROM clients WHERE COALESCE(password_hash,'')<>'' ORDER BY id LIMIT 1"
    )).fetchall()]
    extra = [r[0] for r in db.execute(text(
        "SELECT id FROM clients WHERE login IS NOT NULL ORDER BY total_deposits DESC NULLS LAST LIMIT 40"
    )).fetchall()]
    real_clients = list(dict.fromkeys(real_clients + extra))

    N = 50
    # spread the active-history length: a few brand-new, most spread to 150 days
    day_lengths = [random.randint(1,7) for _ in range(6)] + \
                  [random.randint(8,45) for _ in range(14)] + \
                  [random.randint(46,150) for _ in range(N-20)]
    random.shuffle(day_lengths)
    loser_ids = set(random.sample(range(N), 9))   # ~9 net-losing providers

    used_names = set()
    for i in range(N):
        a = ARCH[i % len(ARCH)]
        # jitter the archetype so no two are identical
        drift = a["drift"] * random.uniform(0.6, 1.5)
        vol   = a["vol"]   * random.uniform(0.8, 1.3)
        win   = min(0.92, max(0.40, a["win"] + random.uniform(-0.06, 0.06)))
        risk  = max(1, min(10, a["risk"] + random.randint(-1,1)))
        days  = day_lengths[i]
        loser = i in loser_ids

        while True:
            nm = f"{random.choice(FIRST)} {random.choice(LAST)}"
            if nm not in used_names: used_names.add(nm); break
        start_date = TODAY - timedelta(days=days)

        curve = gen_equity(days, drift, vol, loser)
        equities = [e for e,_ in curve]
        final_eq = equities[-1]
        ret_pct = (final_eq/START_EQUITY - 1)*100
        # 30d return
        if days >= 31:
            ret_30 = (final_eq/equities[-31] - 1)*100
        else:
            ret_30 = ret_pct
        mdd = drawdown(equities)
        # trade count from trades/day
        avg_tpd = sum(a["tpd"])/2
        total_trades = max(1, int(avg_tpd * days * random.uniform(0.8,1.1)))
        avg_hold = int(sum(a["hold"])/2)
        pf = round(max(0.6, (win/(1-win)) * random.uniform(0.85,1.25)), 2)
        # followers scale with performance & track-record; losers/new get few
        score = max(0, ret_pct) * 0.8 + (days*0.6) - mdd*0.4
        followers = max(2, int(score * random.uniform(0.8,1.4)) + random.randint(0,15))
        if loser: followers = max(1, followers//4)
        avg_alloc = random.uniform(400, 6000)
        aum = round(followers * avg_alloc, 2)
        pnl_total = round(aum * ret_pct/100, 2)
        fee_pct = random.choice([10,15,20,20,25,30])
        min_inv = random.choice([100,200,250,500,1000])

        bio = f"{a['strategy']} trader focused on {a['markets']}. " + random.choice([
            "Disciplined risk management, capital preservation first.",
            "High-frequency setups with tight stops.",
            "Trend-following with strict daily loss limits.",
            "Momentum + news catalysts, selective entries.",
            "Mean-reversion on liquid pairs.",
        ])
        pid = db.execute(text("""
            INSERT INTO copy_providers
              (name,country,avatar,strategy,markets,risk_level,bio,fee_pct,min_investment,
               status,days_active,start_date,return_pct,return_30d,win_rate,max_drawdown,
               profit_factor,total_trades,avg_hold_min,followers,aum,pnl_total,featured)
            VALUES (:name,:country,:avatar,:strategy,:markets,:risk,:bio,:fee,:min,
               'approved',:days,:sd,:ret,:r30,:win,:mdd,:pf,:tt,:hold,:fol,:aum,:pnl,:feat)
            RETURNING id
        """), dict(name=nm, country=random.choice(COUNTRIES), avatar=random.choice(AVATARS),
                   strategy=a["strategy"], markets=a["markets"], risk=risk, bio=bio,
                   fee=fee_pct, min=min_inv, days=days, sd=start_date,
                   ret=round(ret_pct,2), r30=round(ret_30,2), win=round(win*100,1),
                   mdd=mdd, pf=pf, tt=total_trades, hold=avg_hold, fol=followers,
                   aum=aum, pnl=pnl_total, feat=(ret_pct>60 and mdd<30 and not loser))).scalar()

        # daily history
        for k,(e,r) in enumerate(curve):
            day = start_date + timedelta(days=k+1)
            db.execute(text("""INSERT INTO copy_provider_history (provider_id,day,equity,return_pct,daily_pct)
                               VALUES (:p,:d,:e,:rp,:dp)"""),
                       dict(p=pid, d=day, e=round(e,2), rp=round((e/START_EQUITY-1)*100,2), dp=round(r,3)))

        # sample of trades (cap rows; total_trades stat may be larger)
        n_sample = min(total_trades, 120)
        for _ in range(n_sample):
            sym = random.choice(a["symbols"])
            side = random.choice(["Buy","Sell"])
            offset_days = random.uniform(0, days)
            ot = datetime.combine(start_date + timedelta(days=offset_days), datetime.min.time()) \
                 + timedelta(minutes=random.randint(0,1439))
            hold = random.randint(a["hold"][0], a["hold"][1])
            ct = ot + timedelta(minutes=hold)
            winning = random.random() < win
            base = random.uniform(5, 400) * (risk/5.0)
            pnl = round(base if winning else -base*random.uniform(0.6,1.1), 2)
            lots = round(random.uniform(0.05, 2.0) * (risk/5.0), 2)
            pips = round((pnl/ max(lots,0.01))/10.0, 1)
            db.execute(text("""INSERT INTO copy_provider_trades
                  (provider_id,symbol,side,lots,open_time,close_time,hold_min,pnl,pips)
                  VALUES (:p,:s,:sd,:l,:ot,:ct,:h,:pnl,:pips)"""),
                  dict(p=pid, s=sym, sd=side, l=lots, ot=ot, ct=ct, h=hold, pnl=pnl, pips=pips))

        # follower sample rows (cap 50/provider; headline count stays in providers.followers)
        n_rows = min(followers, 50)
        for j in range(n_rows):
            cid = None
            fname = f"{random.choice(FIRST)} {random.choice(LAST)[0]}."
            # wire some REAL portal clients as followers of the better providers
            if real_clients and ret_pct > 20 and random.random() < 0.25:
                cid = random.choice(real_clients)
            alloc = round(random.uniform(min_inv, min_inv*30), 2)
            fpnl = round(alloc * ret_pct/100 * random.uniform(0.7,1.1), 2)
            db.execute(text("""INSERT INTO copy_followers
                  (provider_id,client_id,follower_name,allocation,multiplier,copy_mode,status,pnl,started_at)
                  VALUES (:p,:c,:n,:a,:m,:cm,'active',:pnl,:ts)"""),
                  dict(p=pid, c=cid, n=fname, a=alloc, m=random.choice([0.5,1.0,1.0,1.5,2.0]),
                       cm=random.choice(["proportional","proportional","fixed","mirror"]),
                       pnl=fpnl, ts=datetime.combine(start_date,datetime.min.time())+timedelta(days=random.uniform(0,max(1,days)))))
        if (i+1) % 10 == 0:
            print(f"  seeded {i+1}/{N} providers...")
    db.commit()

    # summary
    np = db.execute(text("SELECT COUNT(*) FROM copy_providers")).scalar()
    nh = db.execute(text("SELECT COUNT(*) FROM copy_provider_history")).scalar()
    nt = db.execute(text("SELECT COUNT(*) FROM copy_provider_trades")).scalar()
    nf = db.execute(text("SELECT COUNT(*) FROM copy_followers")).scalar()
    nrf = db.execute(text("SELECT COUNT(*) FROM copy_followers WHERE client_id IS NOT NULL")).scalar()
    print(f"\nDONE: {np} providers | {nh} history rows | {nt} trades | {nf} followers ({nrf} real-client)")
    print("\nTop 8 by return:")
    for r in db.execute(text("""SELECT name,strategy,markets,days_active,return_pct,win_rate,max_drawdown,followers
                                FROM copy_providers ORDER BY return_pct DESC LIMIT 8""")).fetchall():
        print(f"  {r[0]:22} {r[1]:12} {r[2]:18} {r[3]:3}d  ret {r[4]:7.1f}%  win {r[5]:4.0f}%  DD {r[6]:4.1f}%  {r[7]} followers")
    print("\nWorst 4 (losers):")
    for r in db.execute(text("""SELECT name,strategy,return_pct,max_drawdown,followers
                                FROM copy_providers ORDER BY return_pct ASC LIMIT 4""")).fetchall():
        print(f"  {r[0]:22} {r[1]:12} ret {r[2]:7.1f}%  DD {r[3]:4.1f}%  {r[4]} followers")
    db.close()

if __name__ == "__main__":
    main()
