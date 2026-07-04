"""Create markup_config from OZ Markups.xlsx — the company's per-symbol, per-account-type
markup (in points). Sheets: Plain Standard->STD, Cent->CENT, Zero->ZERO, VIP->VIP.
Also seeds an empty FIX set (no data in the Excel). Idempotent."""
import openpyxl, re
from sqlalchemy import text
from database import SessionLocal

SHEET_TYPE = {"Plain Standard": "STD", "Cent": "CENT", "Zero": "ZERO", "VIP": "VIP"}

def norm(sym):
    return re.sub(r"[^A-Z0-9]", "", (sym or "").upper())

def run():
    db = SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS markup_config (
                id SERIAL PRIMARY KEY,
                account_type VARCHAR NOT NULL,     -- STD/CENT/ZERO/VIP/FIX
                symbol       VARCHAR NOT NULL,      -- display, e.g. EUR/USD
                symbol_norm  VARCHAR NOT NULL,      -- EURUSD (matches deals.symbol)
                category     VARCHAR,               -- FX / XAUUSD / METAL / CRYPTO / OTHER
                bid_markup   DOUBLE PRECISION DEFAULT 0,
                ask_markup   DOUBLE PRECISION DEFAULT 0,
                total_markup DOUBLE PRECISION DEFAULT 0,  -- points (abs bid + abs ask)
                updated_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(account_type, symbol_norm)
            )
        """))
        db.commit()

        wb = openpyxl.load_workbook("../OZ Markups.xlsx", data_only=True)
        ins = 0
        for sheet, atype in SHEET_TYPE.items():
            if sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                sym = str(row[0]).strip()
                bid = float(row[3] or 0) if len(row) > 3 and row[3] is not None else 0.0
                ask = float(row[4] or 0) if len(row) > 4 and row[4] is not None else 0.0
                total = abs(bid) + abs(ask)
                nsym = norm(sym)
                # category
                if nsym in ("XAUUSD",):
                    cat = "XAUUSD"
                elif nsym.startswith(("XAU", "XAG", "XPT", "XPD")):
                    cat = "METAL"
                elif re.fullmatch(r"[A-Z]{6}", nsym):
                    cat = "FX"
                elif nsym.endswith("USD") and len(nsym) <= 7:
                    cat = "CRYPTO"
                else:
                    cat = "OTHER"
                db.execute(text("""
                    INSERT INTO markup_config (account_type, symbol, symbol_norm, category,
                        bid_markup, ask_markup, total_markup, updated_at)
                    VALUES (:at,:sym,:ns,:cat,:bid,:ask,:tot,NOW())
                    ON CONFLICT (account_type, symbol_norm) DO UPDATE SET
                        symbol=EXCLUDED.symbol, category=EXCLUDED.category,
                        bid_markup=EXCLUDED.bid_markup, ask_markup=EXCLUDED.ask_markup,
                        total_markup=EXCLUDED.total_markup, updated_at=NOW()
                """), {"at": atype, "sym": sym, "ns": nsym, "cat": cat,
                       "bid": bid, "ask": ask, "tot": total})
                ins += 1
        db.commit()
        print(f"upserted {ins} markup rows")
        for at, n in db.execute(text("SELECT account_type, COUNT(*) FROM markup_config GROUP BY 1 ORDER BY 1")):
            print(f"  {at}: {n}")
    finally:
        db.close()

if __name__ == "__main__":
    run()
