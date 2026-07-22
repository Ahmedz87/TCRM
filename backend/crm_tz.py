"""crm_tz — the CRM's reporting calendar (Iraq, UTC+3, no DST).

DESK RULE (Jul 15 2026, the boss): report every transaction on the CALENDAR DAY ITS
SOURCE SYSTEM SHOWS — MT rows keep MT's server stamp, TradeSoft rows keep TradeSoft's
stamp, taken at face value. The desk reconciles CRM figures against MT statements and
TradeSoft exports, so the CRM must bucket by the same digits those systems display.
Do NOT shift stored times or day boundaries by clock offsets (a 21:00-UTC boundary
model + a -3h TradeSoft backfill were tried Jul 14 and REVERTED — they made the CRM
disagree with both reference systems; see memory reporting-timezone-iraq).

The one real timezone bug was "today": this box runs UTC, so date.today() flipped the
day 3 hours after Iraqi midnight ("today/yesterday" reports lagged). today_local()
fixes that — the day LABEL comes from Iraq's clock; the day CONTENT is face-value.

day_lo/day_hi return plain calendar-day bounds ('D 00:00:00' / 'D+1 00:00:00') for the
index-friendly string-range comparisons used across the routers.
"""
from datetime import datetime, date, timedelta, timezone

# Iraq abolished DST in 2007 — fixed UTC+3 year-round.
REPORT_UTC_OFFSET_H = 3


def now_local() -> datetime:
    """Current wall-clock time in Iraq (naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=REPORT_UTC_OFFSET_H)


def today_local() -> date:
    """Today's date in Iraq — use instead of date.today() in every period helper."""
    return now_local().date()


def _as_date(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def day_lo(d) -> str:
    """Inclusive lower bound of calendar day d (face-value digits)."""
    return f"{_as_date(d).isoformat()} 00:00:00"


def day_hi(d) -> str:
    """Exclusive upper bound for an INCLUSIVE end date d (start of day d+1)."""
    return f"{(_as_date(d) + timedelta(days=1)).isoformat()} 00:00:00"
