"""
ib_commission.py — IB commission profile engine.

Model (per the IB-5 "0.5 pips Markup" profile, MT5):
  • A PROFILE belongs to an IB level (5..10) on a platform (MT5).
  • A profile holds a flat list of RULES: { priority, symbols(patterns), distribution, value }.
  • On a closed trade: among the rules whose symbol pattern matches the trade symbol, the
    LOWEST priority number wins (most specific). `*` (priority 20) is the STD catch-all.
  • Payout = lots × value          when distribution = 'usd_per_lot'
            = lots × value × pip$  when distribution = 'pips'  (pip$ = money value of one
              "pip" for that symbol per lot, derived from MT5 symbol specs — see pip_value_usd).

Pattern matching (case-insensitive):
  '*'      -> matches every symbol           (STD)
  '*.x'    -> symbol ends with '.x'          (.c Cent, .x FIX, .v VIP, .z Zero)
  'EURUSD' -> exact symbol match
"""
import psycopg2
import db_config
from psycopg2.extras import RealDictCursor

PG_DSN = db_config.DSN

# ── IB-5 "0.5 pips Markup" profile, MT5 — 16 rules (lowest priority number wins) ──
IB5_RULES = [
    # priority, name,                 symbols(comma patterns),                                   distribution,   value
    (1,  "0.5 $ USOIL, UKOIL",  "USOIL,UKOIL,NGAS",                                               "pips",        0.5),
    (2,  "DJ30 0.5$",           "DJ30,USTEC,US500,SPAIN35,SWI20,AUS200,EU50,FRA40,GER30,HK50,NETH25,UK100,JP225", "pips", 50),
    (3,  "TRPUSD",              "TRPUSD",                                                          "pips",        10),
    (6,  "Silver VIP",          "XAGUSD.v,XAGEUR.v",                                               "pips",        0.3),
    (7,  "Silver Lvl 5",        "XAGUSD,XAGEUR,XAGUSD.x,XAGEUR.x",                                  "pips",        1.6),
    (8,  "Equities",            "Adidas,AIG.N,AirFrance,ALIBABA,Allianz,Amazon,Apple,At&T,AXP.N,BAC.N,Banco-SAN,BMW,BNP-Paribas,Boeing,Chevron,Cisco.sys,Citigroup,Coca-Cola,Commerzbank,Danone,Deutsche-BK,Deutsche-Po,DT-Lufthans,Ebay,Exxon,Facebook,Fedex,Ferrari,Ford,General-Ele,General.Mo,GoldMan,Google,Hilton-Worl,HP,IBM,Illumina,Intel,J&J,JP-Morgan,L.V.M.H.,Mastercard,Mcdonalds,Microsoft,Netflix,NIO,NVIDIA,Oracle,Pfizer,Procter&Gam,Qualcomm,Siemens,SOGN.PA,Telefonica,Tesla,Total,Twitter,Uber,Visa,Volkswagen", "pips", 2),  # full Equities US+EU basket
    (9,  "1 X Crepto",          "BTCUSD,BTCEUR,BNBUSD,LTCUSD,ETHBTC,ETHUSD",                        "pips",        50),
    (10, "10 X Crypto",         "BCHBTC,LTCBTC,BSVUSD,AVEUSD,DSHUSD,DOTUSD,LNKUSD,XRPUSD,XRPEUR,VETUSD", "pips",   5),
    (11, "100 x Crypto",        "XMRUSD,THTUSD,UNIUSD,XTZUSD,XEMUSD,ADAUSD,XLMUSD,EOSUSD,TRXUSD",   "pips",        0.5),
    (12, "1000 x Crypto",       "DOGUSD",                                                          "pips",        0.05),
    (13, "VIP LVL 5",           "*.v",                                                             "pips",        1.5),
    (14, "Silver Cent",         "XAGUSD.c,XAGEUR.c",                                               "pips",        0.15),
    (15, "Zero",                "*.",                                                              "pips",        2),    # Zero acct symbols end with a literal '.'
    (17, "FIX LVL5",            "*.x",                                                             "pips",        5),
    (18, "Cent account LVL5",   "*.c",                                                             "pips",        5),
    (20, "0.5 pips Markup",     "*",                                                               "pips",        5),
]

# ── Markup-tier profiles (named library) ──
# Profiles are MARKUP TIERS derived from the base IB-5 ruleset. Each tier = IB-5 with ONLY the
# FX + XAUUSD rules (Zero 15, FIX 17, Cent 18, Markup 20) scaled by (markup_value / 5); all other
# rules (oil/indices/crypto/silver/equities/TRPUSD) identical. ib_level is an optional label.
DERIVED_RAISE = {15, 17, 18, 20}
BASE_MARKUP = 5

# (markup_value, ib_level_label)   ib_level=None -> a tier not tied to an IB 5-10 level
PROFILES = [
    (5, 5), (7, 6), (7.5, 7), (8, 8), (9, 9), (10, 10),         # the IB-5..IB-10 ladder
    (6, None), (15, None), (20, None), (30, None), (40, None),  # extra markup tiers
]

# priority-15 (Zero) is set explicitly per level, NOT scaled by the markup multiplier.
# (pending confirmation with the IB manager — shown highlighted in the UI)
ZERO_BY_LEVEL = {5: 2, 6: 2, 7: 2.5, 8: 2.5, 9: 3, 10: 3}

def build_profile(markup_value, level=None):
    """Return (profile_name, rules) for a markup tier derived from IB-5."""
    mult = markup_value / BASE_MARKUP
    pname = f"{markup_value/10:g} pips Markup"
    def rn(n):
        if level:
            n = n.replace("LVL5", f"LVL{level}").replace("LVL 5", f"LVL {level}").replace("Lvl 5", f"Lvl {level}")
        return n.replace("0.5 pips Markup", pname)
    rules = []
    for (pr, name, syms, dist, val) in IB5_RULES:
        v = round(val * mult, 4) if pr in DERIVED_RAISE else val
        if pr == 15 and level in ZERO_BY_LEVEL:
            v = ZERO_BY_LEVEL[level]      # explicit per-level Zero value
        rules.append((pr, rn(name), syms, dist, v))
    return pname, rules


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS commission_profiles (
            id        SERIAL PRIMARY KEY,
            name      TEXT,
            ib_level  INT,
            platform  TEXT DEFAULT 'MT5',
            UNIQUE (ib_level, platform)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS commission_rules (
            id           SERIAL PRIMARY KEY,
            profile_id   INT REFERENCES commission_profiles(id) ON DELETE CASCADE,
            name         TEXT,
            priority     INT,
            symbols      TEXT,
            distribution TEXT,           -- 'pips' | 'usd_per_lot'
            value        DOUBLE PRECISION,
            entry        TEXT DEFAULT 'out'
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_comm_rules_profile ON commission_rules(profile_id, priority)")
    # profiles are a named library (markup tiers), no longer 1-per-ib_level
    cur.execute("ALTER TABLE commission_profiles DROP CONSTRAINT IF EXISTS commission_profiles_ib_level_platform_key")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_comm_profile_name ON commission_profiles(name, platform)")


def seed_profile(cur, name, ib_level, rules, platform="MT5"):
    cur.execute("""INSERT INTO commission_profiles (name, ib_level, platform)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (name, platform) DO UPDATE SET ib_level=EXCLUDED.ib_level
                   RETURNING id""", (name, ib_level, platform))
    pid = cur.fetchone()[0]
    cur.execute("DELETE FROM commission_rules WHERE profile_id=%s", (pid,))
    for pr, rname, syms, dist, val in rules:
        cur.execute("""INSERT INTO commission_rules (profile_id, name, priority, symbols, distribution, value)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (pid, rname, pr, syms, dist, val))
    return pid


# ── matching ──
def _pattern_matches(pattern, symbol):
    p = pattern.strip().lower()
    s = symbol.strip().lower()
    if not p:
        return False
    if p == "*":
        return True
    if p.startswith("*."):
        return s.endswith(p[1:])      # '*.c' -> endswith '.c'
    return s == p                      # exact


def match_rule(rules, symbol):
    """rules: list of dicts (priority, symbols, distribution, value, name).
    Returns the lowest-priority rule whose pattern list matches `symbol`, else None."""
    best = None
    for r in rules:
        if any(_pattern_matches(pat, symbol) for pat in r["symbols"].split(",")):
            if best is None or r["priority"] < best["priority"]:
                best = r
    return best


def load_profile_rules(cur, ib_level=5, platform="MT5"):
    cur.execute("""SELECT r.name, r.priority, r.symbols, r.distribution, r.value
                   FROM commission_rules r JOIN commission_profiles p ON p.id=r.profile_id
                   WHERE p.ib_level=%s AND p.platform=%s ORDER BY r.priority""",
                (ib_level, platform))
    return [dict(name=x[0], priority=x[1], symbols=x[2], distribution=x[3], value=x[4])
            for x in cur.fetchall()]


def load_rules_by_profile(cur, profile_id):
    cur.execute("""SELECT name, priority, symbols, distribution, value
                   FROM commission_rules WHERE profile_id=%s ORDER BY priority""", (profile_id,))
    return [dict(name=x[0], priority=x[1], symbols=x[2], distribution=x[3], value=x[4])
            for x in cur.fetchall()]


# Approximate USD value per 1 unit of each profit currency. USD is exact; the rest are used
# only for cross/EUR-denominated symbols and should be refreshed from a live feed periodically.
CCY_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0067, "CHF": 1.12, "CAD": 0.73,
    "AUD": 0.66, "NZD": 0.61, "CNH": 0.138, "SGD": 0.74, "HKD": 0.128, "SEK": 0.095,
    "NOK": 0.094, "PLN": 0.25, "MXN": 0.058, "ZAR": 0.054, "TRY": 0.031, "RUB": 0.011,
}


def pip_value_usd(symbol, cur=None):
    """USD value of ONE point per 1.00 lot for `symbol`, from mt5_symbol_specs.
    point_value_profit = contract_size * point (in the symbol's profit currency); convert to USD.
    Returns None if the symbol isn't in the spec table."""
    own = False
    if cur is None:
        own = True
        _cn = psycopg2.connect(PG_DSN); cur = _cn.cursor()
    try:
        cur.execute("SELECT point_value_profit, currency_profit FROM mt5_symbol_specs WHERE symbol=%s", (symbol,))
        row = cur.fetchone()
        if not row:
            return None
        pvp, ccy = float(row[0] or 0), (row[1] or "USD")
        return pvp * CCY_USD.get(ccy, 1.0)
    finally:
        if own:
            _cn.close()


def commission_for(rule, lots, symbol):
    """Commission to the IB for a closed trade of `lots` on `symbol`, given the matched rule."""
    if rule is None:
        return 0.0
    if rule["distribution"] == "usd_per_lot":
        return lots * rule["value"]
    # pips
    pip = pip_value_usd(symbol)
    if pip is None:
        return None  # pips→money factor not yet calibrated
    return lots * rule["value"] * pip


if __name__ == "__main__":
    cn = psycopg2.connect(PG_DSN); cn.autocommit = False; cur = cn.cursor()
    ensure_schema(cur)
    cur.execute("TRUNCATE commission_rules, commission_profiles RESTART IDENTITY CASCADE")
    for mv, lvl in PROFILES:
        pname, rules = build_profile(mv, lvl)
        seed_profile(cur, pname, lvl, rules)
    cn.commit()
    print(f"Seeded {len(PROFILES)} profiles (markup20 / Zero15):")
    for mv, lvl in PROFILES:
        pname, rules = build_profile(mv, lvl)
        mk = next(v for pr, n, s, d, v in rules if pr == 20)
        z = next(v for pr, n, s, d, v in rules if pr == 15)
        print(f"  {pname:18} level={str(lvl):4}  markup={mk:<5} Zero={z}")
    print()

    rules = load_profile_rules(cur)
    tests = ["EURUSD", "EURUSD.c", "EURUSD.x", "EURUSD.v", "EURUSD.",
             "XAGUSD", "XAGUSD.x", "XAGUSD.v", "XAGUSD.c",
             "USOIL", "DJ30", "BTCUSD", "DOGUSD", "XAUUSD", "Tesla", "TRPUSD"]
    LOTS = 1.0
    print(f"IB commission for {LOTS} lot:")
    print(f"  {'symbol':12} {'rule':20} {'pri':>3} {'dist':11} {'value':>6} {'pip$':>8} {'-> comm$':>10}")
    for s in tests:
        r = match_rule(rules, s)
        if not r:
            print(f"  {s:12} (no match)"); continue
        comm = commission_for(r, LOTS, s)
        pip = pip_value_usd(s, cur)
        comm_str = "n/a (no spec)" if comm is None else f"${comm:.4f}"
        pip_str = "-" if pip is None else f"${pip:.4f}"
        print(f"  {s:12} {r['name']:20} {r['priority']:>3} {r['distribution']:11} {r['value']:>6} {pip_str:>8} {comm_str:>10}")
    cn.close()
