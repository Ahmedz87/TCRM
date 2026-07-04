"""
import_mt4_remaining.py — imports the 318 remaining MT4 accounts not yet
in trading_accounts, with precise skip rules based on manual inspection.

Run: python import_mt4_remaining.py --dry-run
     python import_mt4_remaining.py
"""
import sys, os, re
import db_config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DRY_RUN = "--dry-run" in sys.argv

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from bridge_mt4 import load_dll, connect, get_all_users

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# ── Skip lists (confirmed service/test/internal accounts) ──────────────────
# Login numbers to skip entirely (confirmed service/system on BOTH platforms)
SKIP_LOGINS = {
    # Service accounts confirmed from inspection
    1025, 4004, 4005, 4006, 4008, 4009, 4018, 4019, 4020, 4021,
    10099, 100100, 1994312, 100100100, 2100050658, 2100051583,
    334161763, 2100052951, 2100051476,
    # MT5 managers group accounts (internal system)
    4, 4003, 4023, 4026, 4027, 4028, 4029, 4030, 4031,
    4500, 4501, 4502, 44444,
    # Test/dev accounts
    77777, 99000, 31054, 31055, 31059, 31060, 31061, 31053, 31056, 31063,
    25041, 25065, 45823,
}

# MT5 side is a system account but MT4 side is a REAL CLIENT
# -> create new clients row without login field (avoids login collision)
MT4_REAL_CLIENT_LOGINS = {518, 5000, 4022, 4025, 10149, 10857, 10865}

# Name keywords that mark a service/system/test account
SKIP_NAME_KW = [
    "datacenter","dc bkp","dc fra","dc uk","dc bah","dc ger","dc cai",
    "dc kl","dc tur","dc saf","report server","watchdog","feeder",
    "manual dealer","trading operations","lost & found","demo feeder",
    "do not delete","oz report","bridge dealer","failover",
    "plugit","itradesoft","stp dealing","bo stp","fsa reporting",
    "test raw","gbe","centroid risk","pamm","manager - rtca",
    "autochart","crm nully","weekly test","ahmed test","dev test",
    "forex iq","martin win","admin chart","jwan falih",
]

def is_skip(u):
    if u["login"] in MT4_REAL_CLIENT_LOGINS: return False  # always process these
    if u["login"] in SKIP_LOGINS: return True
    if u["login"] <= 10: return True
    name = u["name"].lower()
    if any(kw in name for kw in SKIP_NAME_KW): return True
    group = u["group"].lower()
    if "managers\\" in group or "managers/" in group: return True
    if not u["phone"] and u["login"] < 200: return True
    return False

def norm(p):
    if not p: return ""
    p = re.sub(r"[\s\-\(\)]", "", p.strip())
    return ("+" + p) if p and not p.startswith("+") else p

def acct_type(group):
    g = group.upper()
    if "VIP"  in g: return "vip"
    if "ZERO" in g: return "zero"
    if "CENT" in g: return "cent"
    if "FIX"  in g: return "fix"
    if "IB"   in g: return "ib"
    return "standard"

def main():
    print("=" * 60)
    print("MT4 REMAINING IMPORT" + (" [DRY RUN]" if DRY_RUN else " [LIVE]"))
    print("=" * 60)

    load_dll(); connect()
    all_users = get_all_users()

    conn = psycopg2.connect(**DB, cursor_factory=RealDictCursor)
    cur  = conn.cursor()

    cur.execute("SELECT login FROM trading_accounts WHERE platform='MT4'")
    in_ta = {r["login"] for r in cur.fetchall()}

    cur.execute("SELECT id,login,name,phone,platform FROM clients ORDER BY id")
    db_clients = {r["login"]: r for r in cur.fetchall()}

    # Build phone -> client_id map
    phone_map = {}
    for r in cur.fetchall() if False else []:
        pass
    cur.execute("SELECT id,login,phone,platform FROM clients WHERE phone IS NOT NULL AND phone!=''")
    for r in cur.fetchall():
        p = norm(r["phone"])
        if p and p not in phone_map: phone_map[p] = r
        elif p and r["platform"] == "MT5": phone_map[p] = r

    # Filter to only accounts not yet imported
    users = [u for u in all_users
             if u["login"] not in in_ta and not is_skip(u)]

    print(f"MT4 server total:      {len(all_users)}")
    print(f"Already in TA:         {len(in_ta)}")
    print(f"To process:            {len(users)}")

    skipped = new_client = linked_login = linked_phone = 0
    plan = []

    for u in users:
        phone = norm(u["phone"])
        ex_by_login = db_clients.get(u["login"])
        ex_by_phone = phone_map.get(phone) if phone else None

        # MT5 side is system, MT4 side is real — new client row, no login field
        if u["login"] in MT4_REAL_CLIENT_LOGINS:
            plan.append(("collision", None, u))
            new_client += 1
        elif ex_by_login:
            plan.append(("link_login", ex_by_login["id"], u))
            linked_login += 1
        elif ex_by_phone:
            plan.append(("link_phone", ex_by_phone["id"], u))
            linked_phone += 1
        else:
            plan.append(("new", None, u))
            new_client += 1

    print(f"\nPlan:")
    print(f"  Link by login (in_db=YES): {linked_login}")
    print(f"  Link by phone:             {linked_phone}")
    print(f"  New MT4-only clients:      {new_client}")

    if DRY_RUN:
        print("\n--- Collision logins (MT5=system, MT4=real client) ---")
        for _, _, u in [x for x in plan if x[0]=="collision"]:
            print(f"  login={u['login']:8d} {u['name']:<35} {u['phone']}")
        print("\n--- Sample new clients (first 10) ---")
        for _, _, u in [x for x in plan if x[0]=="new"][:10]:
            print(f"  login={u['login']:8d} {u['name']:<35} {u['phone']}")
        print("\nDRY RUN done.")
        conn.close()
        return

    inserted = 0; errors = 0
    for action, client_id, u in plan:
        try:
            phone   = norm(u["phone"])
            reg     = datetime.fromtimestamp(u["regdate"]).strftime("%Y-%m-%d") if u["regdate"] else None
            at      = acct_type(u["group"])
            is_ib   = "IB" in u["group"].upper()

            if action == "collision":
                # MT5 login is taken by a system account — create new client
                # Use negative login as placeholder (real MT4 login is in trading_accounts)
                placeholder_login = -u["login"]
                cur.execute("""
                    INSERT INTO clients (login,name,email,phone,country,city,
                        balance,credit,leverage,group_name,agent,mqid,
                        reg_date,platform,account_type,is_ib,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',%s,%s,NOW())
                    ON CONFLICT DO NOTHING RETURNING id
                """, (placeholder_login,u["name"],u["email"],phone,
                      u["country"],u["city"],u["balance"],u["credit"],
                      u["leverage"],u["group"],u["agent"],u["mqid"] or None,
                      reg,at,is_ib))
                row = cur.fetchone()
                if not row:
                    # Already inserted (re-run) — look up by negative login
                    cur.execute("SELECT id FROM clients WHERE login=%s",(placeholder_login,))
                    row = cur.fetchone()
                client_id = row["id"] if row else None
                if not client_id: continue

            elif action == "new":
                cur.execute("""
                    INSERT INTO clients (login,name,email,phone,country,city,
                        balance,credit,leverage,group_name,agent,mqid,
                        reg_date,platform,account_type,is_ib,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',%s,%s,NOW())
                    ON CONFLICT DO NOTHING RETURNING id
                """, (u["login"],u["name"],u["email"],phone,
                      u["country"],u["city"],u["balance"],u["credit"],
                      u["leverage"],u["group"],u["agent"],u["mqid"] or None,
                      reg,at,is_ib))
                row = cur.fetchone()
                if row:
                    client_id = row["id"]
                else:
                    # Login collision — check if it's the same person or different
                    cur.execute("SELECT id,name,phone,platform FROM clients WHERE login=%s",(u["login"],))
                    existing = cur.fetchone()
                    if existing:
                        ex_p = (existing["phone"] or "").replace(" ","").replace("+","")
                        mt4_p = phone.replace("+","")
                        ex_n = existing["name"].strip().lower()
                        mt4_n = u["name"].strip().lower()
                        same = bool((ex_p and mt4_p and ex_p==mt4_p) or ex_n==mt4_n)
                        if same:
                            # Same person — just link to existing client
                            client_id = existing["id"]
                        else:
                            # Different person — create new row WITHOUT login field
                            print(f"  RUNTIME COLLISION login={u['login']}: "
                                  f"DB={existing['name']!r} vs MT4={u['name']!r} "
                                  f"-> creating separate MT4 client row")
                            cur.execute("""
                                INSERT INTO clients (login,name,email,phone,country,city,
                                    balance,credit,leverage,group_name,agent,mqid,
                                    reg_date,platform,account_type,is_ib,created_at)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',%s,%s,NOW())
                                ON CONFLICT DO NOTHING RETURNING id
                            """, (-u["login"],u["name"],u["email"],phone,
                                  u["country"],u["city"],u["balance"],u["credit"],
                                  u["leverage"],u["group"],u["agent"],u["mqid"] or None,
                                  reg,at,is_ib))
                            row = cur.fetchone()
                            client_id = row["id"] if row else None
                    else:
                        continue
                    if not client_id: continue

            elif action in ("link_login","link_phone"):
                # Update existing client platform
                cur.execute("""
                    UPDATE clients SET platform='MT4/MT5', updated_at=NOW()
                    WHERE id=%s AND platform='MT5'
                """, (client_id,))

            # Insert trading_account row
            cur.execute("""
                INSERT INTO trading_accounts (
                    login,client_id,name,email,group_name,account_type,
                    leverage,balance,credit,agent,reg_date,phone,
                    is_ib,platform,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',NOW())
                ON CONFLICT (login) DO UPDATE SET
                    client_id=EXCLUDED.client_id,
                    platform='MT4',
                    balance=EXCLUDED.balance,
                    updated_at=NOW()
            """, (u["login"],client_id,u["name"],u["email"],
                  u["group"],at,u["leverage"],u["balance"],u["credit"],
                  u["agent"],reg,phone,is_ib))

            inserted += 1
            if inserted % 500 == 0:
                conn.commit()
                print(f"  {inserted} processed...")

        except Exception as e:
            conn.rollback()
            errors += 1
            if errors <= 5:
                print(f"  ERROR login={u['login']}: {e}")

    conn.commit()

    cur.execute("SELECT COUNT(*) as n FROM trading_accounts WHERE platform='MT4'")
    ta_mt4 = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) as n FROM clients WHERE platform='MT4'")
    mt4_only = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) as n FROM clients WHERE platform='MT4/MT5'")
    both = cur.fetchone()["n"]

    print(f"\nDone.")
    print(f"  Accounts inserted/updated: {inserted}")
    print(f"  Errors:                    {errors}")
    print(f"\nFinal DB state:")
    print(f"  trading_accounts MT4:      {ta_mt4}")
    print(f"  clients MT4:               {mt4_only}")
    print(f"  clients MT4/MT5:           {both}")
    conn.close()

if __name__ == "__main__":
    main()
