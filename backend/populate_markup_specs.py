"""
Add + fill markup_config spec columns: contract_size, digits, quote_currency.

Source of truth = mt5_symbol_specs (the real TNFX MT5 server specs):
  - quote_currency  <- currency_profit  (for FX XXXYYY this is YYY; for GER30 it's EUR, etc.)
  - digits          <- digits
  - contract_size   <- contract_size

Matching: prefer an EXACT mt5 symbol == markup symbol_norm; else the canonical base
(shortest symbol for that base); a few aliases cover oddly-normalised index rows
(DE40->GER40, JPN225->JP225) and trailing XX/YY duplicate tags are stripped.
Fallbacks when no spec row exists: FX/metal/crypto quote = last 3 letters; sensible
class defaults for digits/contract.
"""
import re
from database import SessionLocal
from sqlalchemy import text

ALIAS = {"DE40": "GER40", "JPN225": "JP225"}
CCY = {"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","HKD","SGD","SEK","NOK","PLN",
       "MXN","TRY","ZAR","CNH","RUB"}

# index/commodity quote fallback (only used if no spec row matched)
INDEX_CCY = {"AUS200":"AUD","GER30":"EUR","GER40":"EUR","DE40":"EUR","DJ30":"USD","EU50":"EUR",
             "FRA40":"EUR","HK50":"HKD","JPN225":"JPY","JP225":"JPY","NETH25":"EUR","NGAS":"USD",
             "SPAIN35":"EUR","SWI20":"CHF","UK100":"GBP","UKOIL":"USD","US500":"USD","USOIL":"USD",
             "USTEC":"USD"}


def base_of(sym: str) -> str:
    return re.sub(r"(XX|YY)$", "", sym.split(".")[0].upper())


def main():
    db = SessionLocal()
    # 1) columns
    db.execute(text("""
        ALTER TABLE markup_config
          ADD COLUMN IF NOT EXISTS contract_size  NUMERIC,
          ADD COLUMN IF NOT EXISTS digits          INTEGER,
          ADD COLUMN IF NOT EXISTS quote_currency  VARCHAR(8)
    """))
    db.commit()

    # 2) load specs -> by exact symbol and by base (canonical = shortest symbol for that base)
    specs_exact, specs_base = {}, {}
    for sym, digits, contract, ccy in db.execute(text(
        "SELECT symbol, digits, contract_size, currency_profit FROM mt5_symbol_specs WHERE symbol IS NOT NULL"
    )).fetchall():
        u = sym.upper()
        rec = {"digits": digits, "contract": float(contract) if contract is not None else None,
               "ccy": (ccy or "").upper() or None}
        specs_exact[u] = rec
        b = u.split(".")[0]
        cur = specs_base.get(b)
        # prefer the exact base name (sym == base), else the shortest symbol string
        if cur is None or (u == b) or (len(u) < cur["_len"] and cur["_sym"] != b):
            specs_base[b] = {**rec, "_len": len(u), "_sym": u}

    def lookup(symnorm: str):
        u = symnorm.upper()
        b = base_of(u)
        b = ALIAS.get(b, b)
        return specs_exact.get(u) or specs_base.get(b) or specs_base.get(ALIAS.get(u, u))

    def quote_for(symnorm: str, spec):
        if spec and spec.get("ccy"):
            return spec["ccy"]
        u = symnorm.upper()
        # 6-letter pair (FX / metal / crypto) -> last 3 if it's a currency
        if len(u) == 6 and u[3:] in CCY:
            return u[3:]
        return INDEX_CCY.get(base_of(u))

    def defaults(symnorm, category):
        # used only when no spec row matched
        u = symnorm.upper()
        if category in ("FX",) and len(u) == 6:
            return (3 if u.endswith("JPY") else 5), 100000.0
        if category in ("METAL", "XAUUSD"):
            if u.startswith("XAG"): return 3, 5000.0
            return 2, 100.0
        return 2, 1.0  # index / cfd / crypto default

    # 3) distinct symbols in markup_config
    rows = db.execute(text(
        "SELECT DISTINCT symbol_norm, category FROM markup_config WHERE symbol_norm IS NOT NULL"
    )).fetchall()

    updated, unmatched = 0, []
    for symnorm, category in rows:
        spec = lookup(symnorm)
        q = quote_for(symnorm, spec)
        if spec and spec.get("digits") is not None:
            digits, contract = spec["digits"], spec["contract"]
        else:
            digits, contract = defaults(symnorm, category)
            if not spec:
                unmatched.append(symnorm)
        db.execute(text("""
            UPDATE markup_config
               SET quote_currency=:q, digits=:d, contract_size=:c, updated_at=NOW()
             WHERE symbol_norm=:s
        """), {"q": q, "d": digits, "c": contract, "s": symnorm})
        updated += 1
    db.commit()

    total = db.execute(text("SELECT COUNT(*) FROM markup_config")).scalar()
    filled = db.execute(text("SELECT COUNT(*) FROM markup_config WHERE quote_currency IS NOT NULL")).scalar()
    print(f"Updated {updated} symbols across {total} rows; {filled} rows now have quote_currency.")
    if unmatched:
        print("No MT5 spec match (used class defaults):", ", ".join(sorted(unmatched)))
    db.close()


if __name__ == "__main__":
    main()
