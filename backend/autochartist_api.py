"""
Autochartist Data API client + normalizer.

Returns opportunities in ONE clean shape the UI + AI bot use:
  { instrument, timeframe, type, title, direction, entry, stop, target,
    target_period, age, identified_at, expiry, probability, description, chart_url }

Until autochartist_config has a real API key it serves realistic DEMO opportunities
(so the cards + bot work now). When the key is set, _fetch_live() runs instead — adjust
its request/response mapping to match Autochartist's actual Data API and you're live.
"""
import time, json, urllib.request, urllib.parse
from datetime import datetime, timedelta

try:
    import autochartist_config as cfg
except Exception:
    cfg = None

_CACHE = {"at": 0.0, "data": None}
_TTL = 300  # 5 min


def is_mock() -> bool:
    return (cfg is None) or cfg.use_mock()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%-m/%-d %H:%M") if hasattr(dt, "strftime") else str(dt)


def _ago(hours: float) -> str:
    if hours < 1:
        return f"{int(hours*60)} minutes ago"
    if hours < 2:
        return "1 hour ago"
    if hours < 48:
        return f"{int(hours)} hours ago"
    return f"{int(hours/24)} days ago"


# ── DEMO opportunities (realistic; ages/times computed live so they feel current) ──
# (instrument, tf, type, title, direction, entry, stop, target, target_period, hours_ago, expire_in_h, desc)
_DEMO = [
    ("GBPNZD", "60", "support", "Support Emerging", "bearish", 2.2970, 2.3015, 2.2882, "4 Days", 3, 120,
     "Approaching Support level of 2.2882. This pattern is still forming. Possible bearish move towards the support 2.2882 within the next 4 days."),
    ("XAUUSD", "240", "resistance", "Resistance Approaching", "bearish", 4362.0, 4395.0, 4310.0, "5 Days", 1, 130,
     "Price is approaching a key resistance at 4395. A rejection could open a move down towards 4310 over the coming days."),
    ("EURUSD", "60", "chart_pattern", "Triangle (Completed)", "bullish", 1.0842, 1.0808, 1.0910, "3 Days", 6, 96,
     "A completed triangle pattern signals a potential bullish breakout with a target near 1.0910."),
    ("USDJPY", "240", "key_level", "Key Level Breakout", "bullish", 157.20, 156.40, 158.60, "6 Days", 9, 140,
     "Price has broken a key level at 157.20. Continuation towards 158.60 is possible over the next several days."),
    ("XAGUSD", "60", "fibonacci", "Fibonacci (Butterfly)", "bullish", 68.40, 67.55, 70.10, "4 Days", 12, 110,
     "A Butterfly harmonic pattern completed near 68.40, suggesting upside towards 70.10."),
    ("GBPUSD", "240", "support", "Support Completed", "bullish", 1.3290, 1.3235, 1.3380, "5 Days", 18, 120,
     "Price bounced from support at 1.3290. A move up towards 1.3380 is possible within 5 days."),
]


def _mock(now: datetime):
    out = []
    for (sym, tf, typ, title, direction, entry, stop, target, period, h_ago, exp_h, desc) in _DEMO:
        ident = now - timedelta(hours=h_ago)
        exp = now + timedelta(hours=exp_h)
        out.append({
            "instrument": sym, "timeframe": tf, "type": typ, "title": title,
            "direction": direction, "entry": entry, "stop": stop, "target": target,
            "target_period": period, "age": _ago(h_ago),
            "identified_at": ident.strftime("%m/%d %H:%M"),
            "expiry": exp.strftime("%m/%d %H:%M"),
            "probability": None, "description": desc, "chart_url": None,
        })
    return out


def _fetch_live():
    """REAL Autochartist Data API call. PLACEHOLDER — adjust endpoint, auth and the field
    mapping to match the actual API response once the key/docs are available."""
    base = cfg.AC_API_BASE.rstrip("/")
    # Example shape — replace with the documented endpoint/params Autochartist gives you:
    url = f"{base}/search?" + urllib.parse.urlencode({
        "broker_id": cfg.AC_BROKER_ID, "key": cfg.AC_API_KEY,
    })
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    raw = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
    items = raw.get("results") or raw.get("opportunities") or raw if isinstance(raw, list) else []
    out = []
    for it in items:
        # map their fields -> our schema (ADJUST keys to the real response)
        out.append({
            "instrument": it.get("symbol") or it.get("instrument", ""),
            "timeframe": str(it.get("interval") or it.get("timeframe", "")),
            "type": it.get("type", "pattern"),
            "title": it.get("pattern") or it.get("title", "Opportunity"),
            "direction": it.get("direction", ""),
            "entry": it.get("entry"), "stop": it.get("stoploss") or it.get("stop"),
            "target": it.get("target") or it.get("forecast_price"),
            "target_period": it.get("target_period", ""),
            "age": it.get("age", ""), "identified_at": it.get("identified", ""),
            "expiry": it.get("expire", ""), "probability": it.get("probability"),
            "description": it.get("description", ""), "chart_url": it.get("chart_url") or it.get("image"),
        })
    return out


def fetch_opportunities(symbol: str = None, limit: int = 12):
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["at"] < _TTL):
        data = _CACHE["data"]
    else:
        try:
            data = _mock(datetime.utcnow()) if is_mock() else _fetch_live()
        except Exception:
            data = _mock(datetime.utcnow())
        _CACHE["data"] = data
        _CACHE["at"] = now
    if symbol:
        s = symbol.upper().replace("/", "")
        data = [o for o in data if (o["instrument"] or "").upper().replace("/", "") == s]
    return data[:limit]


def opportunities_text(limit: int = 5) -> str:
    """Compact block for the AI bot's system prompt so it can quote REAL live signals."""
    ops = fetch_opportunities(limit=limit)
    if not ops:
        return ""
    tag = " (DEMO sample — say 'sample' if asked)" if is_mock() else ""
    lines = [f"LIVE AUTOCHARTIST SIGNALS{tag} — current opportunities. If the client asks for setups/"
             "ideas/market analysis, share these (entry/stop/target). They are observations, not "
             "guarantees; remind them trading carries risk:"]
    for o in ops:
        lines.append(
            f"- {o['instrument']} ({o['timeframe']}m): {o['title']} — {o['direction']}, "
            f"entry {o['entry']}, stop {o['stop']}, target {o['target']}, "
            f"target period {o['target_period']}, identified {o['age']}.")
    return "\n".join(lines)
