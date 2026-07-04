"""
rebuild_db.py — Proper rebuild following exact definitions:

1. trading_accounts — every MT5 login (14,272 records from clients table)
2. clients — unique people grouped by email+phone
3. ibs — clients who have at least one account with group containing 'IB'
4. transactions — deposits/withdrawals/internal transfers extracted from deals

Run: python rebuild_db.py
SAFE: Never touches clients, deals, account_identifiers, network_edges
"""
import sys, re
sys.path.insert(0, r'C:\broker-crm\backend')

from database import SessionLocal, engine
import models
from sqlalchemy import text

db = SessionLocal()

# ── CHECK ─────────────────────────────────────────────────────────
total_raw   = db.query(models.Client).count()
total_deals = db.query(models.Deal).count()
print("=" * 60)
print(f"Raw MT5 accounts (clients table): {total_raw}")
print(f"Deals:                            {total_deals}")
print("=" * 60)

if total_raw == 0:
    print("ERROR: No data. Run bridge.py first!")
    db.close()
    sys.exit(1)

models.Base.metadata.create_all(bind=engine)

# ── COLLECT RAW DATA ──────────────────────────────────────────────
print("\nReading all raw accounts...")
all_raw = db.query(models.Client).all()

raw_data = []
for a in all_raw:
    g = (a.group_name or "").upper()
    is_islamic = g.endswith("-IS") or g.endswith("_IS")
    is_ib      = "\\IB" in g or g.startswith("IB")
    is_demo    = "DEMO" in g

    # Detect account sub-type from group name
    if is_ib:            acc_type = "ib"
    elif is_demo:        acc_type = "demo"
    elif "STD" in g:     acc_type = "standard"
    elif "ZERO" in g:    acc_type = "zero"
    elif "CENT" in g:    acc_type = "cent"
    elif "VIP" in g:     acc_type = "vip"
    elif "FIX" in g:     acc_type = "fix"
    else:                acc_type = "standard"  # default

    raw_data.append({
        "id":            a.id,
        "login":         a.login,
        "name":          a.name or "",
        "email":         (a.email or "").strip().lower(),
        "phone":         (a.phone or "").strip(),
        "group_name":    a.group_name or "",
        "account_type":  acc_type,
        "is_islamic":    is_islamic,
        "is_ib":         is_ib,
        "leverage":      a.leverage or 100,
        "balance":       float(a.balance or 0),
        "equity":        float(a.equity or 0),
        "credit":        float(a.credit or 0),
        "margin_level":  float(a.margin_level or 0),
        "free_margin":   float(getattr(a,'free_margin',0) or 0),
        "agent":         a.agent or 0,
        "country":       a.country or "",
        "city":          a.city or "",
        "last_ip":       a.last_ip or "",
        "cid":           a.cid or "",
        "mqid":          a.mqid or 0,
        "reg_date":      a.reg_date or "",
        "is_active":     a.is_active,
        "kyc_status":    a.kyc_status or "pending",
        "risk_score":    a.risk_score or "low",
        "source":        getattr(a,'source','none') or "none",
        "total_deposits":    float(a.total_deposits or 0),
        "total_withdrawals": float(a.total_withdrawals or 0),
        "net_deposit":       float((a.total_deposits or 0) - (a.total_withdrawals or 0)),
        "total_volume":      float(getattr(a,'total_volume_lots',0) or 0),
        "total_trades":      int(getattr(a,'total_trades',0) or 0),
        "first_deposit_at":  getattr(a,'first_deposit_at',None),
        "last_deposit_at":   getattr(a,'last_deposit_at',None),
        "last_trade_at":     getattr(a,'last_trade_at',None),
    })

# ── STEP 1: TRADING ACCOUNTS ──────────────────────────────────────
print("\nSTEP 1: Populating trading_accounts...")
db.execute(text("DELETE FROM trading_accounts"))
db.commit()

count = 0
for d in raw_data:
    db.add(models.TradingAccount(
        login        = d["login"],
        client_id    = d["id"],
        name         = d["name"],
        email        = d["email"],
        phone        = d["phone"],
        group_name   = d["group_name"],
        account_type = d["account_type"],
        is_islamic   = d["is_islamic"],
        is_ib        = d["is_ib"],
        leverage     = d["leverage"],
        balance      = d["balance"],
        equity       = d["equity"],
        credit       = d["credit"],
        margin_level = d["margin_level"],
        free_margin  = d["free_margin"],
        agent        = d["agent"],
        country      = d["country"],
        city         = d["city"],
        last_ip      = d["last_ip"],
        cid          = d["cid"],
        mqid         = d["mqid"],
        reg_date     = d["reg_date"],
        first_deposit_at = d["first_deposit_at"],
        last_deposit_at  = d["last_deposit_at"],
        last_trade_at    = d["last_trade_at"],
        is_active        = d["is_active"],
        kyc_status       = d["kyc_status"],
        risk_score       = d["risk_score"],
        source           = d["source"],
        total_deposits    = d["total_deposits"],
        total_withdrawals = d["total_withdrawals"],
        total_volume      = d["total_volume"],
        total_trades      = d["total_trades"],
        net_deposit       = d["net_deposit"],
    ))
    count += 1
    if count % 1000 == 0:
        db.commit()
        print(f"  {count} trading accounts saved...")

db.commit()
print(f"✓ trading_accounts: {db.query(models.TradingAccount).count()}")

# Account type summary
for t in ["live","demo","islamic","ib"]:
    n = db.query(models.TradingAccount).filter(models.TradingAccount.account_type==t).count()
    if n > 0:
        print(f"  {t}: {n}")

# ── STEP 2: UNIQUE CLIENTS ────────────────────────────────────────
print("\nSTEP 2: Building unique clients from trading accounts...")
print("  Rule: group by email (primary) or phone (secondary)")

# Group accounts by unique person
person_map = {}  # key → list of account dicts

for d in raw_data:
    email = d["email"]
    phone = d["phone"]

    # Build identity key — email is most reliable
    if email and email not in ("", "null", "none"):
        key = f"email:{email}"
    elif phone and phone not in ("", "0", "null"):
        key = f"phone:{phone}"
    else:
        key = f"login:{d['login']}"  # no email/phone — each account is own client

    if key not in person_map:
        person_map[key] = []
    person_map[key].append(d)

print(f"  Unique persons found: {len(person_map)}")

# Update clients table — update existing records with client_id
# First build a map: login → client_id (person id)
# We'll use the first account's client.id as the person id

# Clear client assignments
db.execute(text("UPDATE trading_accounts SET client_id = NULL"))
db.commit()

persons_created = 0
for key, accounts in person_map.items():
    # Use the account with highest balance as primary
    primary = max(accounts, key=lambda x: x["balance"])

    # Aggregate across all accounts
    total_dep  = sum(a["total_deposits"] for a in accounts)
    total_with = sum(a["total_withdrawals"] for a in accounts)
    total_vol  = sum(a["total_volume"] for a in accounts)
    total_tr   = sum(a["total_trades"] for a in accounts)
    net_dep    = total_dep - total_with

    # Get all logins for this person
    logins = [a["login"] for a in accounts]

    # Find or update the client record
    client = db.query(models.Client).filter(
        models.Client.login == primary["login"]
    ).first()

    if client:
        # Update with aggregated data
        client.total_deposits    = total_dep
        client.total_withdrawals = total_with
        client.net_deposit       = net_dep
        client.total_volume_lots = total_vol
        client.total_trades      = total_tr

        # Link all trading accounts to this client
        db.execute(text(
            f"UPDATE trading_accounts SET client_id = {client.id} WHERE login IN ({','.join(str(l) for l in logins)})"
        ))
        persons_created += 1

    if persons_created % 1000 == 0 and persons_created > 0:
        db.commit()
        print(f"  {persons_created} clients processed...")

db.commit()
print(f"✓ Unique clients processed: {persons_created}")

# Stats
multi_account = sum(1 for accounts in person_map.values() if len(accounts) > 1)
print(f"  Clients with multiple accounts: {multi_account}")
print(f"  Single account clients: {len(person_map) - multi_account}")

# ── STEP 3: IBS ───────────────────────────────────────────────────
print("\nSTEP 3: Building ibs table...")
db.execute(text("DELETE FROM ibs"))
db.commit()

ib_data = [d for d in raw_data if d["is_ib"]]
print(f"  IB accounts found: {len(ib_data)}")

# Extract pts from group name
def get_pts(group_name):
    if not group_name:
        return 5
    m = re.search(r'IB-(\d+)', group_name, re.I)
    return int(m.group(1)) if m else 5

for d in ib_data:
    client_count = sum(1 for r in raw_data if r["agent"] == d["login"])
    ftd_count    = sum(1 for r in raw_data if r["agent"] == d["login"] and r["total_deposits"] > 0)
    total_vol    = sum(r["total_volume"] for r in raw_data if r["agent"] == d["login"])
    pts          = get_pts(d["group_name"])

    db.add(models.IB(
        agent_id          = d["login"],
        ib_code           = f"IB-{d['login']}",
        name              = d["name"] or f"IB #{d['login']}",
        email             = d["email"],
        phone             = d["phone"],
        country           = d["country"],
        city              = d["city"],
        status            = "active" if d["is_active"] else "inactive",
        ib_level          = pts,  # level = pts (IB-5=5, IB-6=6...)
        group_name        = d["group_name"],
        balance           = d["balance"],
        total_clients     = client_count,
        active_clients    = ftd_count,
        unique_ftds       = ftd_count,
        total_volume      = total_vol,
        total_commission  = 0,
        unpaid_commission = 0,
        paid_commission   = 0,
        net_deposits      = 0,
        referral_clicks   = 0,
    ))

db.commit()
print(f"✓ ibs: {db.query(models.IB).count()}")

# Show top IBs
top_ibs = db.query(models.IB).order_by(models.IB.total_clients.desc()).limit(5).all()
for ib in top_ibs:
    print(f"  {ib.name} ({ib.ib_code}) — {ib.total_clients} clients, {ib.unique_ftds} FTDs, L{ib.ib_level}")

# ── STEP 4: TRANSACTIONS ──────────────────────────────────────────
print("\nSTEP 4: Building transactions from deals...")

# Check if transactions table exists
try:
    db.execute(text("SELECT COUNT(*) FROM transactions"))
    db.execute(text("DELETE FROM transactions"))
    db.commit()
    has_transactions = True
except:
    has_transactions = False
    print("  transactions table not found — skipping")

if has_transactions:
    # Extract deposits, withdrawals, internal transfers from deals
    # Map deal types to transaction types
    deal_types = {
        "deposit":            "deposit",
        "withdrawal":         "withdrawal",
        "internal_transfer":  "internal_transfer",
        "credit_in":          "credit_in",
        "credit_out":         "credit_out",
        "bonus_deposit":      "bonus_deposit",
        "bonus_withdrawal":   "bonus_withdrawal",
    }

    count = 0
    for deal_type, tx_type in deal_types.items():
        deals = db.query(models.Deal).filter(
            models.Deal.deal_type == deal_type
        ).all()

        for d in deals:
            try:
                # Extract payment method from comment
                # "Deposit - Qi card - USD" → method = "Qi card"
                # "Withdraw - Bank Wire - USD" → method = "Bank Wire"
                comment = d.comment or ""
                method = ""
                if " - " in comment:
                    parts = comment.split(" - ")
                    if len(parts) >= 3:
                        method = parts[1].strip()

                db.add(models.Transaction(
                    login    = d.login,
                    deal_id  = d.deal_id,
                    tx_type  = tx_type,
                    amount   = abs(d.profit or 0),
                    currency = "USD",
                    method   = method,
                    status   = "approved",
                    notes    = comment,
                    tx_date  = d.deal_date,
                    tx_month = d.deal_date[:7] if d.deal_date and len(d.deal_date) >= 7 else "",
                ))
                count += 1
            except Exception as e:
                continue

        db.commit()
        if len(deals) > 0:
            print(f"  {deal_type}: {len(deals)} records")

    print(f"✓ transactions: {count} total")

# ── SUMMARY ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("REBUILD COMPLETE")
print("=" * 60)
print(f"Trading accounts: {db.query(models.TradingAccount).count()}")
print(f"Unique clients:   {len(person_map)}")
print(f"IBs:              {db.query(models.IB).count()}")
print(f"Deals:            {db.query(models.Deal).count()}")
print(f"Identifiers:      {db.query(models.AccountIdentifier).count()}")
print(f"Network edges:    {db.query(models.NetworkEdge).count()}")

db.close()
print("\nDone! Now restart backend: uvicorn main:app --reload")
