"""
calculate_ib_commissions.py

Calculates IB commissions for all trades with these rules:
1. Client balance > 0 at time of trade open
2. Trade duration >= 5 minutes
3. Commission = volume × pts_per_lot (based on IB group: IB-5=5, IB-6=6, etc.)
4. Quote currency commission converted to USD

Run after bridge.py finishes:
    python calculate_ib_commissions.py
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')

from database import SessionLocal
import models
from sqlalchemy import text
from datetime import datetime

db = SessionLocal()

print("=" * 60)
print("IB COMMISSION CALCULATOR")
print("=" * 60)

# ── Build IB map: login → pts_per_lot ─────────────────────────────
print("\nBuilding IB map...")
ibs = db.query(models.IB).all()
ib_map = {}  # agent_id → {pts, name, ib_code}
for ib in ibs:
    # Extract pts from group name: IB\IB-5 → 5
    pts = 5  # default
    if ib.group_name:
        import re
        m = re.search(r'IB-(\d+)', ib.group_name, re.I)
        if m:
            pts = int(m.group(1))
    ib_map[ib.agent_id] = {
        'pts':      pts,
        'name':     ib.name,
        'ib_code':  ib.ib_code,
        'ib_id':    ib.id,
    }
print(f"  IBs loaded: {len(ib_map)}")

# ── Build client→IB map ───────────────────────────────────────────
print("Building client→IB map...")
# login → agent (IB login)
client_ib = {}
accounts = db.query(models.TradingAccount).filter(
    models.TradingAccount.agent != None,
    models.TradingAccount.agent != 0
).all()
for acc in accounts:
    if acc.agent in ib_map:
        client_ib[acc.login] = acc.agent
print(f"  Clients with IB: {len(client_ib)}")

# ── FX rates (approximate — update daily in production) ──────────
FX_RATES = {
    'USD': 1.0,
    'EUR': 1.08,
    'GBP': 1.27,
    'JPY': 0.0065,
    'CAD': 0.73,
    'CHF': 1.12,
    'AUD': 0.65,
    'NZD': 0.60,
    'SGD': 0.74,
    'HKD': 0.13,
    'NOK': 0.09,
    'SEK': 0.09,
    'DKK': 0.14,
    'MXN': 0.058,
    'ZAR': 0.054,
    'TRY': 0.031,
    'XAU': 2300.0,  # Gold per oz → per point (adjust as needed)
    'XAG': 28.0,
}

def get_quote_currency(symbol: str) -> str:
    """Extract quote currency from symbol name."""
    symbol = symbol.upper().strip()
    # Standard forex: EURUSD → USD, GBPJPY → JPY
    if len(symbol) == 6 and symbol.isalpha():
        return symbol[3:]
    # Gold/Silver
    if symbol.startswith('XAU'):
        return symbol[3:] or 'USD'
    if symbol.startswith('XAG'):
        return symbol[3:] or 'USD'
    # Indices, crypto → USD by default
    return 'USD'

def to_usd(amount: float, currency: str) -> float:
    rate = FX_RATES.get(currency.upper(), 1.0)
    return round(amount * rate, 4)

# ── Clear existing commissions ────────────────────────────────────
print("\nClearing existing IB commissions...")
db.execute(text("DELETE FROM ib_commissions"))
db.commit()

# ── Process trades ────────────────────────────────────────────────
print("Processing trades...")

# Get all closed trades (entry=1) for clients who have an IB
# Process in batches of 10,000
batch_size = 10000
offset = 0
total_processed = 0
total_paid = 0
total_skipped_balance = 0
total_skipped_duration = 0
total_commission_usd = 0

while True:
    # Get closed trade deals for clients with IB
    trades = db.query(models.Deal).filter(
        models.Deal.deal_type == 'trade',
        models.Deal.entry == 1,  # closing deal
        models.Deal.login.in_(list(client_ib.keys()))
    ).order_by(models.Deal.deal_time.asc()).offset(offset).limit(batch_size).all()

    if not trades:
        break

    commissions_batch = []

    for close_deal in trades:
        login = close_deal.login
        ib_login = client_ib.get(login)
        if not ib_login:
            continue

        ib_info = ib_map.get(ib_login)
        if not ib_info:
            continue

        # Find matching open deal (entry=0, same login, earlier time)
        open_deal = db.query(models.Deal).filter(
            models.Deal.login == login,
            models.Deal.deal_type == 'trade',
            models.Deal.entry == 0,
            models.Deal.symbol == close_deal.symbol,
            models.Deal.deal_time < close_deal.deal_time,
        ).order_by(models.Deal.deal_time.desc()).first()

        # Rule 1: Trade duration >= 5 minutes (300 seconds)
        if open_deal and close_deal.deal_time and open_deal.deal_time:
            duration = close_deal.deal_time - open_deal.deal_time
            if duration < 300:
                total_skipped_duration += 1
                continue
        
        # Rule 2: Balance > 0 at time of trade open
        # Use balance_after of the deal just before the open deal
        if open_deal:
            balance_before = open_deal.balance_after or 0
        else:
            # Fallback: use balance_after of last deposit/withdrawal before this trade
            prev_deal = db.query(models.Deal).filter(
                models.Deal.login == login,
                models.Deal.deal_type.in_(['deposit','withdrawal']),
                models.Deal.deal_time < close_deal.deal_time,
            ).order_by(models.Deal.deal_time.desc()).first()
            balance_before = prev_deal.balance_after if prev_deal else 0

        if balance_before <= 0:
            total_skipped_balance += 1
            continue

        # Calculate commission
        pts          = ib_info['pts']
        volume       = close_deal.volume or 0
        symbol       = close_deal.symbol or ''
        quote_ccy    = get_quote_currency(symbol)
        comm_native  = round(volume * pts, 4)
        comm_usd     = to_usd(comm_native, quote_ccy)

        commissions_batch.append(models.IBCommission(
            ib_id            = ib_info['ib_id'],
            ib_login         = ib_login,
            client_login     = login,
            deal_id          = close_deal.deal_id,
            symbol           = symbol,
            volume           = volume,
            pts_per_lot      = pts,
            quote_currency   = quote_ccy,
            commission_native= comm_native,
            fx_rate          = FX_RATES.get(quote_ccy.upper(), 1.0),
            commission_usd   = comm_usd,
            trade_date       = close_deal.deal_date,
            status           = 'unpaid',
            commission_type  = 'direct',
        ))

        total_commission_usd += comm_usd
        total_paid += 1

    # Save batch
    if commissions_batch:
        for c in commissions_batch:
            db.add(c)
        db.commit()
        print(f"  Processed {offset + len(trades)} trades, {total_paid} commissions so far...")

    total_processed += len(trades)
    if len(trades) < batch_size:
        break
    offset += batch_size

# ── Sub-IB override (10%) ─────────────────────────────────────────
print("\nCalculating sub-IB overrides (10%)...")

# Find master IBs (those who have sub-IBs under them)
# Sub-IB: an IB whose parent_ib_id is set
sub_ibs = db.query(models.IB).filter(
    models.IB.parent_ib_id != None
).all()

override_count = 0
for sub_ib in sub_ibs:
    master = db.query(models.IB).filter(
        models.IB.id == sub_ib.parent_ib_id
    ).first()
    if not master:
        continue

    # Get all direct commissions for this sub-IB
    sub_comms = db.query(models.IBCommission).filter(
        models.IBCommission.ib_login == sub_ib.agent_id,
        models.IBCommission.commission_type == 'direct'
    ).all()

    for sc in sub_comms:
        override_usd = round(sc.commission_usd * 0.10, 4)
        db.add(models.IBCommission(
            ib_id             = master.id,
            ib_login          = master.agent_id,
            client_login      = sc.client_login,
            deal_id           = sc.deal_id,
            symbol            = sc.symbol,
            volume            = sc.volume,
            pts_per_lot       = sc.pts_per_lot,
            quote_currency    = sc.quote_currency,
            commission_native = round(sc.commission_native * 0.10, 4),
            fx_rate           = sc.fx_rate,
            commission_usd    = override_usd,
            trade_date        = sc.trade_date,
            status            = 'unpaid',
            commission_type   = 'override',
            override_from_ib  = sub_ib.agent_id,
        ))
        override_count += 1

    if override_count % 1000 == 0 and override_count > 0:
        db.commit()

db.commit()
print(f"  Override commissions: {override_count}")

# ── Update IB totals ──────────────────────────────────────────────
print("\nUpdating IB totals...")
for ib in ibs:
    total = db.query(models.IBCommission).filter(
        models.IBCommission.ib_login == ib.agent_id
    ).with_entities(
        models.IBCommission.commission_usd
    ).all()
    total_usd = sum(r[0] for r in total)
    db.query(models.IB).filter(models.IB.id == ib.id).update({
        'total_commission':   total_usd,
        'unpaid_commission':  total_usd,
    })
db.commit()

# ── SUMMARY ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("COMMISSION CALCULATION COMPLETE")
print("=" * 60)
print(f"Total trades processed:       {total_processed:,}")
print(f"Commissions paid:             {total_paid:,}")
print(f"Skipped (balance = 0):        {total_skipped_balance:,}")
print(f"Skipped (duration < 5 min):   {total_skipped_duration:,}")
print(f"Override commissions:         {override_count:,}")
print(f"Total IB commission (USD):    ${total_commission_usd:,.2f}")
print(f"Total in DB:                  {db.query(models.IBCommission).count():,}")

# Top IBs
print("\nTop 5 IBs by commission:")
top = db.query(models.IB).order_by(models.IB.total_commission.desc()).limit(5).all()
for ib in top:
    print(f"  {ib.name} ({ib.ib_code}): ${ib.total_commission:,.2f}")

db.close()
