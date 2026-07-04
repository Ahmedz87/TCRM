p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
c = []

# 1. schema: add best_tier column after tier
if "best_tier     VARCHAR" not in s:
    s = s.replace(
        "            tier          VARCHAR(12) DEFAULT \x27bronze\x27,",
        "            tier          VARCHAR(12) DEFAULT \x27bronze\x27,\n            best_tier     VARCHAR(12) DEFAULT \x27bronze\x27,")
    c.append("schema")

# 2. ensure_schema migration ALTER
if "ADD COLUMN IF NOT EXISTS best_tier" not in s:
    s = s.replace(
        "CREATE INDEX IF NOT EXISTS ix_loy_ledger_client ON loyalty_ledger(client_id)\"))",
        "CREATE INDEX IF NOT EXISTS ix_loy_ledger_client ON loyalty_ledger(client_id)\"))\n    db.execute(text(\"ALTER TABLE loyalty_accounts ADD COLUMN IF NOT EXISTS best_tier VARCHAR(12) DEFAULT \x27bronze\x27\"))")
    c.append("migration")

# 3. loop: init best_tier_idx after 'tier = "bronze"'
if "best_tier_idx = 0" not in s:
    s = s.replace(
        "        tier = \"bronze\"\n",
        "        tier = \"bronze\"\n        best_tier_idx = 0\n", 1)
    c.append("init-idx")

# 3b. update best_tier_idx on promotion (after tier = TIER_ORDER[idx+1])
if "best_tier_idx = max(best_tier_idx, idx+1)" not in s:
    s = s.replace(
        "                        tier = TIER_ORDER[idx+1]\n                        streak = 0",
        "                        tier = TIER_ORDER[idx+1]\n                        best_tier_idx = max(best_tier_idx, idx+1)\n                        streak = 0")
    c.append("update-idx")

# 4. account write: add best_tier. Compute it + add to INSERT
if "best_tier = TIER_ORDER[best_tier_idx]" not in s:
    s = s.replace(
        "        # write account\n        db.execute(text(\"\"\"\n            INSERT INTO loyalty_accounts\n              (client_id, tier, points_balance, lifetime_points, current_streak, best_streak, last_trade_date, referral_code)\n            VALUES (:cid,:t,:bal,:life,:streak,:best,:ld,:rc)\n            ON CONFLICT (client_id) DO UPDATE SET\n              tier=:t, points_balance=:bal, lifetime_points=:life,",
        "        best_tier = TIER_ORDER[best_tier_idx]\n        # write account\n        db.execute(text(\"\"\"\n            INSERT INTO loyalty_accounts\n              (client_id, tier, best_tier, points_balance, lifetime_points, current_streak, best_streak, last_trade_date, referral_code)\n            VALUES (:cid,:t,:bt,:bal,:life,:streak,:best,:ld,:rc)\n            ON CONFLICT (client_id) DO UPDATE SET\n              tier=:t, best_tier=:bt, points_balance=:bal, lifetime_points=:life,")
    s = s.replace(
        "        \"\"\"), {\"cid\": client_id, \"t\": tier, \"bal\": balance, \"life\": lifetime,",
        "        \"\"\"), {\"cid\": client_id, \"t\": tier, \"bt\": best_tier, \"bal\": balance, \"life\": lifetime,")
    c.append("account-write")

open(p,"w",encoding="utf-8").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("best_tier patches:", c)
print("verify: idx-init", "best_tier_idx = 0" in s, "| write", ":bt,:bal" in s, "| compiles OK")
