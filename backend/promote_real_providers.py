"""
Promote REAL top traders into copy-trade providers.

READ-ONLY on deals/clients/transactions. Ranks real accounts by genuine performance and
creates `copy_providers` rows LINKED to the real MT login (copy_providers.login), with the
equity curve (copy_provider_history) and recent trades (copy_provider_trades) computed from
the account's ACTUAL deal history. Marks them status='approved', verified, is_real=TRUE so
they appear on the leaderboard as real, verified traders.

Idempotent: clears prior is_real providers (and their history/trades) and rebuilds. Synthetic
seeded providers (is_real=FALSE) are left untouched.

  python promote_real_providers.py [--target 30] [--min-trades 40] [--dry-run]
"""
import sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from sqlalchemy import text

START_BASE_FLOOR = 1000.0      # floor for the return% denominator
AVATARS = ["📈","💹","🦅","🐂","🎯","🔥","💎","🚀","🏆","👑","🛡️","🌟","⚡","🦁","🐉","🦈"]

def infer_strategy(trades_per_day):
    if trades_per_day >= 20: return "Scalping", 10
    if trades_per_day >= 5:  return "Intraday", 90
    return "Swing", 720

def infer_markets(symbols):
    # symbols: list of (symbol, count) desc
    if not symbols: return "FX Majors"
    top = symbols[0][0].upper()
    names = [s.upper() for s, _ in symbols]
    gold = sum(c for s, c in symbols if "XAU" in s.upper())
    total = sum(c for _, c in symbols) or 1
    if gold / total > 0.7: return "XAUUSD"
    if len(symbols) == 1: return top
    fx = sum(c for s, c in symbols if any(p in s.upper() for p in ["EUR","GBP","USD","JPY","AUD","CHF","CAD","NZD"]) and "XAU" not in s.upper())
    if fx / total > 0.7: return "FX Majors"
    return "Multi-asset"

def max_drawdown(equity):
    peak = -1e18; mdd = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0: mdd = max(mdd, (peak - e) / peak * 100)
    return round(mdd, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=30)
    ap.add_argument("--min-trades", type=int, default=40)
    ap.add_argument("--min-days", type=int, default=5)
    ap.add_argument("--shortlist", type=int, default=160)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()

    db.execute(text("ALTER TABLE copy_providers ADD COLUMN IF NOT EXISTS is_real BOOLEAN DEFAULT FALSE"))
    db.commit()

    print("Stage 1: ranking real accounts by performance (closed trades)…")
    cand = db.execute(text("""
        SELECT d.login,
               COUNT(*) AS n,
               SUM(CASE WHEN d.profit>0 THEN 1 ELSE 0 END) AS wins,
               SUM(d.profit) AS net,
               SUM(CASE WHEN d.profit>0 THEN d.profit ELSE 0 END) AS gp,
               SUM(CASE WHEN d.profit<0 THEN -d.profit ELSE 0 END) AS gl,
               SUM(d.volume)/10000.0 AS lots,
               MIN(d.deal_time) AS first_t, MAX(d.deal_time) AS last_t
        FROM deals d
        WHERE d.entry=1 AND d.action IN (0,1)
        GROUP BY d.login
        HAVING COUNT(*) >= :mt AND SUM(d.profit) > 0
        ORDER BY SUM(d.profit) DESC
        LIMIT :sl
    """), {"mt": a.min_trades, "sl": a.shortlist}).fetchall()
    print(f"  {len(cand)} candidates with >= {a.min_trades} closed trades and net profit > 0")

    # only accounts we can name (real clients), with their deposits (deposit-truth = deals action=2, profit>0)
    scored = []
    for c in cand:
        login = c[0]
        cl = db.execute(text("SELECT name, country, platform FROM clients WHERE login=:l LIMIT 1"), {"l": login}).fetchone()
        if not cl or not (cl[0] or "").strip():
            continue
        n, wins, net = int(c[1]), int(c[2]), float(c[3])
        gp, gl, lots = float(c[4]), float(c[5]), float(c[6])
        first_t, last_t = int(c[7]), int(c[8])
        days = max(1, round((last_t - first_t) / 86400))
        if days < a.min_days:
            continue
        win_rate = wins / n * 100
        if win_rate >= 99 or win_rate < 30:   # exclude implausible / weak
            continue
        pf = (gp / gl) if gl > 0 else 99.0
        if pf < 1.1:
            continue
        deposits = db.execute(text(
            "SELECT COALESCE(SUM(profit),0) FROM deals WHERE login=:l AND action=2 AND profit>0"
        ), {"l": login}).scalar() or 0
        base = max(float(deposits), START_BASE_FLOOR)
        ret = net / base * 100
        tpd = n / days
        strategy, hold = infer_strategy(tpd)
        syms = db.execute(text("""
            SELECT symbol, COUNT(*) FROM deals WHERE login=:l AND entry=1 AND action IN (0,1)
            GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 6
        """), {"l": login}).fetchall()
        markets = infer_markets([(s[0] or "", s[1]) for s in syms])
        scored.append({
            "login": login, "name": cl[0].strip(), "country": cl[1] or "", "platform": cl[2] or "MT5",
            "n": n, "win_rate": round(win_rate, 1), "net": round(net, 2), "pf": round(pf, 2),
            "lots": round(lots, 2), "days": days, "base": base, "ret": round(ret, 2),
            "strategy": strategy, "markets": markets, "hold": hold, "tpd": tpd,
        })
    # composite rank: reward return + profit factor + track record, penalise nothing here (DD added later)
    scored.sort(key=lambda x: (x["ret"] * 0.5 + min(x["pf"], 5) * 10 + min(x["days"], 180) * 0.3), reverse=True)
    picks = scored[:a.target]
    print(f"Stage 2: {len(picks)} real providers selected. Building equity curves + trades…")

    if a.dry_run:
        for p in picks[:15]:
            print(f"  {p['name'][:22]:22} login {p['login']:>9} {p['strategy']:9} {p['markets']:11} "
                  f"{p['days']:4}d  ret {p['ret']:8.1f}%  win {p['win_rate']:4.0f}%  PF {p['pf']:.2f}  net ${p['net']:,.0f}")
        db.close(); return

    # rebuild: clear prior real providers + their history/trades
    old = [r[0] for r in db.execute(text("SELECT id FROM copy_providers WHERE is_real=TRUE")).fetchall()]
    if old:
        db.execute(text("DELETE FROM copy_provider_history WHERE provider_id = ANY(:ids)"), {"ids": old})
        db.execute(text("DELETE FROM copy_provider_trades  WHERE provider_id = ANY(:ids)"), {"ids": old})
        db.execute(text("DELETE FROM copy_followers        WHERE provider_id = ANY(:ids)"), {"ids": old})
        db.execute(text("DELETE FROM copy_providers WHERE id = ANY(:ids)"), {"ids": old})
        db.commit()

    created = 0
    for i, p in enumerate(picks):
        # full ordered closed-trade pnl for the equity curve + drawdown (cap recent 6000)
        rows = db.execute(text("""
            SELECT deal_time, profit FROM deals
            WHERE login=:l AND entry=1 AND action IN (0,1)
            ORDER BY deal_time DESC LIMIT 6000
        """), {"l": p["login"]}).fetchall()
        rows = list(reversed(rows))
        cums = []; cum = 0.0
        for _, prof in rows:
            cum += float(prof or 0); cums.append(cum)
        # effective base: never let the equity curve dip below the floor, so return%/DD% stay realistic
        min_cum = min(cums) if cums else 0.0
        eff_base = max(p["base"], START_BASE_FLOOR + max(0.0, -min_cum))
        eq = [eff_base + c for c in cums]
        mdd = min(95.0, max_drawdown(eq)) if eq else 0.0
        ret_eff = round(p["net"] / eff_base * 100, 2)
        # return over last 30 days
        import time as _t
        cut = int(_t.time()) - 30 * 86400
        net30 = db.execute(text("""
            SELECT COALESCE(SUM(profit),0) FROM deals
            WHERE login=:l AND entry=1 AND action IN (0,1) AND deal_time>=:c
        """), {"l": p["login"], "c": cut}).scalar() or 0
        ret30 = round(float(net30) / eff_base * 100, 2)

        bio = f"Real {p['strategy'].lower()} trader on {p['markets']} — verified {p['days']}-day track record, " \
              f"{p['n']:,} trades, {p['win_rate']:.0f}% win rate. Live results from this account."
        pid = db.execute(text("""
            INSERT INTO copy_providers
              (name,country,avatar,strategy,markets,risk_level,bio,fee_pct,min_investment,
               status,client_id,login,days_active,start_date,return_pct,return_30d,win_rate,
               max_drawdown,profit_factor,total_trades,avg_hold_min,followers,aum,pnl_total,
               verified,featured,is_real)
            VALUES (:n,:co,:av,:st,:mk,:rk,:bio,:fee,:min,'approved',NULL,:lg,:days,
               CURRENT_DATE - (:days || ' days')::interval, :ret,:r30,:win,:mdd,:pf,:tt,:hold,
               0,0,:net,TRUE,:feat,TRUE)
            RETURNING id
        """), {
            "n": p["name"], "co": p["country"], "av": AVATARS[i % len(AVATARS)],
            "st": p["strategy"], "mk": p["markets"],
            "rk": 9 if mdd > 35 else 6 if mdd > 18 else 3,
            "bio": bio, "fee": 25, "min": 250, "lg": p["login"], "days": p["days"],
            "ret": ret_eff, "r30": ret30, "win": p["win_rate"], "mdd": mdd, "pf": min(p["pf"], 99),
            "tt": p["n"], "hold": p["hold"], "net": p["net"], "feat": (ret_eff > 30 and mdd < 35),
        }).scalar()

        # equity curve -> downsample to ~120 points into copy_provider_history
        if eq:
            from datetime import date, timedelta
            step = max(1, len(eq) // 120)
            start_day = date.today() - timedelta(days=p["days"])
            pts = eq[::step]
            for k, e in enumerate(pts):
                day = start_day + timedelta(days=int((k / max(1, len(pts) - 1)) * p["days"]))
                db.execute(text("""INSERT INTO copy_provider_history (provider_id,day,equity,return_pct,daily_pct)
                                   VALUES (:p,:d,:e,:rp,0)"""),
                           {"p": pid, "d": day, "e": round(e, 2), "rp": round((e / eff_base - 1) * 100, 2)})
        # recent real trades -> copy_provider_trades
        tr = db.execute(text("""
            SELECT symbol, action, volume, profit, deal_time FROM deals
            WHERE login=:l AND entry=1 AND action IN (0,1)
            ORDER BY deal_time DESC LIMIT 40
        """), {"l": p["login"]}).fetchall()
        from datetime import datetime, timedelta as td
        for t in tr:
            ct = datetime.utcfromtimestamp(int(t[4])) if t[4] else None
            ot = (ct - td(minutes=p["hold"])) if ct else None
            db.execute(text("""INSERT INTO copy_provider_trades
                  (provider_id,symbol,side,lots,open_time,close_time,hold_min,pnl,pips)
                  VALUES (:p,:s,:sd,:l,:ot,:ct,:h,:pnl,0)"""),
                  {"p": pid, "s": t[0] or "", "sd": "Buy" if int(t[1]) == 0 else "Sell",
                   "l": round(float(t[2] or 0) / 10000.0, 2), "ot": ot, "ct": ct,
                   "h": p["hold"], "pnl": round(float(t[3] or 0), 2)})
        created += 1
        if created % 10 == 0:
            db.commit(); print(f"  built {created}/{len(picks)}…")
    db.commit()

    nreal = db.execute(text("SELECT COUNT(*) FROM copy_providers WHERE is_real=TRUE")).scalar()
    nsyn = db.execute(text("SELECT COUNT(*) FROM copy_providers WHERE COALESCE(is_real,FALSE)=FALSE")).scalar()
    print(f"\nDONE: created {created} REAL providers (linked to live MT logins). "
          f"Leaderboard now: {nreal} real + {nsyn} demo.")
    print("\nTop 10 real providers:")
    for r in db.execute(text("""SELECT name, login, strategy, markets, days_active, return_pct, win_rate,
                                       max_drawdown, profit_factor, total_trades
                                FROM copy_providers WHERE is_real=TRUE ORDER BY return_pct DESC LIMIT 10""")).fetchall():
        print(f"  {r[0][:22]:22} #{r[1]:>9} {r[2]:9} {r[3]:11} {r[4]:4}d  ret {r[5]:8.1f}%  "
              f"win {r[6]:4.0f}%  DD {r[7]:4.1f}%  PF {r[8]:.2f}  {r[9]:,} trades")
    db.close()

if __name__ == "__main__":
    main()
