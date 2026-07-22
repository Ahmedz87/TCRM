"""Markup settings (per account type) + an IB-vs-markup cross-check.

- GET  /markups                 -> markup table grouped by account type (STD/CENT/ZERO/VIP/FIX)
- POST /markups/update          -> edit a single symbol's markup
- GET  /markups/crosscheck      -> realized check: per symbol/account-type, did we pay the IB
                                   MORE than the markup we earned? (we'd be losing money)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/markups", tags=["Markups"])

TYPES = ["STD", "VIP", "FIX", "ZERO", "CENT"]


@router.get("")
def get_markups(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT account_type, symbol, symbol_norm, category, bid_markup, ask_markup, total_markup,
               contract_size, digits, quote_currency
        FROM markup_config ORDER BY account_type,
          CASE category WHEN 'XAUUSD' THEN 0 WHEN 'FX' THEN 1 WHEN 'METAL' THEN 2 ELSE 3 END, symbol
    """)).fetchall()
    by_type = {t: [] for t in TYPES}
    for r in rows:
        by_type.setdefault(r[0], []).append({
            "symbol": r[1], "symbol_norm": r[2], "category": r[3],
            "bid": r[4], "ask": r[5], "total": r[6],
            "contract_size": float(r[7]) if r[7] is not None else None,
            "digits": r[8], "quote_currency": r[9],
        })
    return {"types": TYPES, "markups": by_type}


@router.get("/others")
def others(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Symbols that have been TRADED but are not in any markup sheet — so you can spot
    and configure the uncovered ones. Base symbol = part before the '.suffix'."""
    # PERF (Jul 2026): reads the precomputed deals_symbol_agg (~434 rows) instead of a full
    # 16.8M-row deals GROUP BY (~5s). Normalizes+re-groups the tiny rollup — instant.
    import markup_agg
    if markup_agg.is_stale(db):
        try: markup_agg.refresh()
        except Exception: db.rollback()
    rows = db.execute(text("""
        WITH traded AS (
            SELECT upper(regexp_replace(split_part(a.symbol,'.',1),'[^A-Za-z0-9]','','g')) AS sym_norm,
                   MIN(a.symbol) AS sample,
                   SUM(a.lots) AS lots,
                   SUM(a.markup_usd) AS markup_usd,
                   SUM(a.trades) AS trades
            FROM deals_symbol_agg a
            WHERE COALESCE(a.symbol,'') <> ''
            GROUP BY 1
        )
        SELECT sym_norm, sample, lots, markup_usd, trades
        FROM traded
        WHERE sym_norm <> '' AND sym_norm NOT IN (SELECT DISTINCT symbol_norm FROM markup_config)
        ORDER BY markup_usd DESC NULLS LAST
    """)).fetchall()
    return {"others": [{
        "symbol_norm": r[0], "sample": r[1], "lots": float(r[2] or 0),
        "markup_usd": float(r[3] or 0), "trades": r[4],
    } for r in rows]}


@router.post("/update")
def update_markup(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    at = (data.get("account_type") or "").upper()
    ns = (data.get("symbol_norm") or "").upper()
    bid = float(data.get("bid") or 0)
    ask = float(data.get("ask") or 0)
    total = abs(bid) + abs(ask)
    if not at or not ns:
        return {"ok": False, "error": "account_type and symbol_norm required"}
    db.execute(text("""
        INSERT INTO markup_config (account_type, symbol, symbol_norm, category, bid_markup, ask_markup, total_markup, updated_at)
        VALUES (:at, COALESCE((SELECT symbol FROM markup_config WHERE account_type=:at AND symbol_norm=:ns), :ns),
                :ns, COALESCE((SELECT category FROM markup_config WHERE account_type=:at AND symbol_norm=:ns),'OTHER'),
                :bid,:ask,:tot,NOW())
        ON CONFLICT (account_type, symbol_norm) DO UPDATE SET
            bid_markup=:bid, ask_markup=:ask, total_markup=:tot, updated_at=NOW()
    """), {"at": at, "ns": ns, "bid": bid, "ask": ask, "tot": total})
    db.commit()
    return {"ok": True, "account_type": at, "symbol_norm": ns, "total": total}


@router.get("/crosscheck")
def crosscheck(period: str = "all_time", db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """Realized: for every symbol, the markup we EARNED vs the IB commission we PAID.
    Flags rows where IB commission >= markup earned (we lose money on those trades)."""
    # PERF: reads the precomputed rollup, not a full deals GROUP BY (was ~1.5s uncached).
    import markup_agg
    if markup_agg.is_stale(db):
        try: markup_agg.refresh()
        except Exception: db.rollback()
    rows = db.execute(text("""
        WITH mk AS (
            SELECT a.symbol AS symbol, a.markup_usd AS markup_usd, a.lots AS lots
            FROM deals_symbol_agg a
        ),
        ibc AS (
            SELECT symbol, COALESCE(SUM(commission_usd),0) AS ib_usd
            FROM ib_commissions GROUP BY symbol
        )
        SELECT COALESCE(mk.symbol, ibc.symbol) AS symbol,
               COALESCE(mk.markup_usd,0) AS markup_usd,
               COALESCE(ibc.ib_usd,0)    AS ib_usd,
               COALESCE(mk.lots,0)       AS lots
        FROM mk FULL OUTER JOIN ibc ON ibc.symbol = mk.symbol
        WHERE COALESCE(mk.markup_usd,0) <> 0 OR COALESCE(ibc.ib_usd,0) <> 0
    """)).fetchall()
    out = []
    for sym, markup, ib, lots in rows:
        markup = float(markup or 0); ib = float(ib or 0)
        net = markup - ib
        out.append({
            "symbol": sym, "markup_usd": round(markup, 2), "ib_usd": round(ib, 2),
            "net_usd": round(net, 2), "lots": round(float(lots or 0), 2),
            "losing": ib > markup,   # paying the IB more than we earn
        })
    out.sort(key=lambda x: x["net_usd"])   # worst (most negative) first
    losing = [r for r in out if r["losing"]]
    return {
        "rows": out,
        "summary": {
            "symbols": len(out),
            "losing_symbols": len(losing),
            "total_markup": round(sum(r["markup_usd"] for r in out), 2),
            "total_ib": round(sum(r["ib_usd"] for r in out), 2),
            "total_net": round(sum(r["net_usd"] for r in out), 2),
            "loss_on_losing": round(sum(r["net_usd"] for r in losing), 2),
        },
    }
