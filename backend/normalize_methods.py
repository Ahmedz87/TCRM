# -*- coding: utf-8 -*-
"""
normalize_methods.py — collapse spelling variants of a payment method in transactions.method
into ONE canonical label, so every page (Reports, Transactions, Finance, per-method stats) shows
a single row per real method.

Desk request (Jul 2026): unify
  * sham_cash / Sham Cash / sham cash / shamcash / Shamcash USD …  -> "Shamcash"
  * ZC / ZC- USD / Zaincash / ZainCash / ZAIN CASH / Zain cash [jordan] / from #ZainCa … -> "Zaincash"

Matching is by pattern (case-insensitive `~*`) so it also catches MT-comment-parsed rows, NOT just
TradeSoft ones. NOTE: 'PayzCart' contains "zc" but is a DIFFERENT method — it is deliberately NOT
matched (the rules key on the word 'zain' or the exact 'ZC' tokens, never a bare 'zc' substring).

Idempotent: the WHERE excludes already-canonical rows, so re-runs touch nothing. Wired into
tradesoft_sync (hourly) AND runnable standalone: `python normalize_methods.py`.
"""
from sqlalchemy import text

# (canonical_label, WHERE predicate on `method`)
RULES = [
    ("Shamcash", "method ~* 'sham'"),
    ("Zaincash", "(method ~* 'zain' OR method IN ('ZC','ZC- USD','ZC-USD'))"),
]


def normalize(conn):
    """Run the canonical UPDATEs on a live SQLAlchemy connection/session. Returns {label: rows}."""
    out = {}
    for label, pred in RULES:
        res = conn.execute(text(
            f"UPDATE transactions SET method = :m WHERE {pred} AND method <> :m"), {"m": label})
        out[label] = res.rowcount or 0
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\broker-crm\backend")
    from database import engine
    with engine.begin() as conn:
        # preview the variants that will collapse (before)
        for label, pred in RULES:
            n = conn.execute(text(
                f"SELECT count(DISTINCT method) FROM transactions WHERE {pred}")).scalar()
            print(f"{label}: {n} distinct variant(s) before")
        res = normalize(conn)
        for label, pred in RULES:
            left = conn.execute(text(
                f"SELECT count(DISTINCT method) FROM transactions WHERE {pred}")).scalar()
            print(f"{label}: updated {res[label]:,} rows -> now {left} distinct label(s) (should be 1)")
    print("done")
