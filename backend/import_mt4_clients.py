"""
import_mt4_clients.py — One-time MT4 client import into broker_crm DB.

Strategy:
  - Match MT4 user to existing client by PHONE NUMBER
  - If matched  -> link MT4 trading_account to existing client_id
                   update client platform to 'MT4/MT5'
  - If no match -> insert new clients row (platform='MT4')
                   then insert trading_account linked to new client
  - Skip logins <= 10 (manager/admin/system accounts)
  - All inserts are idempotent (safe to re-run)

Run: python import_mt4_clients.py --dry-run   (preview, no DB changes)
     python import_mt4_clients.py              (actual import)
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

def normalize_phone(p: str) -> str:
    """Strip spaces/dashes, ensure + prefix."""
    if not p:
        return ""
    p = re.sub(r"[\s\-\(\)]", "", p.strip())
    if p and not p.startswith("+"):
        p = "+" + p
    return p

def account_type_from_group(group: str) -> str:
    g = group.upper()
    if "VIP"   in g: return "vip"
    if "ZERO"  in g: return "zero"
    if "CENT"  in g: return "cent"
    if "FIX"   in g: return "fix"
    if "IB"    in g: return "ib"
    if "DEMO"  in g: return "demo"
    return "standard"

def is_ib_group(group: str) -> bool:
    return "IB" in group.upper()

def main():
    print("=" * 60)
    print("MT4 CLIENT IMPORT" + (" [DRY RUN]" if DRY_RUN else " [LIVE]"))
    print("=" * 60)

    # 1. Fetch MT4 users
    load_dll()
    connect()
    users = get_all_users()
    # Skip manager/system accounts (login <= 10)
    users = [u for u in users if u["login"] > 10]
    print(f"MT4 users to process: {len(users)}")

    # 2. Build phone -> client_id map from existing clients
    conn = psycopg2.connect(**DB, cursor_factory=RealDictCursor)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, login, phone, platform, name
        FROM clients
        WHERE phone IS NOT NULL AND phone != ''
        ORDER BY id
    """)
    existing = cur.fetchall()
    # phone -> list of (id, login, platform, name)
    phone_map: dict = {}
    for row in existing:
        p = normalize_phone(row["phone"])
        if p:
            if p not in phone_map:
                phone_map[p] = []
            phone_map[p].append(row)
    print(f"Existing clients with phone: {len(existing)} ({len(phone_map)} unique phones)")

    # 3. Check which MT4 logins already exist in trading_accounts
    cur.execute("SELECT login FROM trading_accounts WHERE platform='MT4'")
    existing_mt4_logins = {r["login"] for r in cur.fetchall()}
    print(f"MT4 logins already in trading_accounts: {len(existing_mt4_logins)}")

    # 4. Process each MT4 user
    stats = {"matched": 0, "new_client": 0, "skipped_dup": 0,
             "already_imported": 0, "multi_match": 0}
    to_insert = []  # list of (action, client_id_or_none, user_dict)

    for u in users:
        if u["login"] in existing_mt4_logins:
            stats["already_imported"] += 1
            continue

        phone = normalize_phone(u["phone"])
        matches = phone_map.get(phone, []) if phone else []

        if len(matches) == 1:
            # Clean match — link to this client
            client_id = matches[0]["id"]
            stats["matched"] += 1
            to_insert.append(("link", client_id, u))
        elif len(matches) > 1:
            # Multiple existing clients with same phone — pick the MT5 one
            mt5_matches = [m for m in matches if m["platform"] == "MT5"]
            if mt5_matches:
                client_id = mt5_matches[0]["id"]
            else:
                client_id = matches[0]["id"]
            stats["multi_match"] += 1
            to_insert.append(("link_multi", client_id, u))
        else:
            # No match — new client
            stats["new_client"] += 1
            to_insert.append(("new", None, u))

    print(f"\nPlan:")
    print(f"  Already imported (skip):     {stats['already_imported']}")
    print(f"  Link to existing client:     {stats['matched']}")
    print(f"  Link (multi-match, best):    {stats['multi_match']}")
    print(f"  Create new client:           {stats['new_client']}")
    print(f"  Total to process:            {len(to_insert)}")

    if DRY_RUN:
        # Show sample of each type
        print("\n--- Sample matches (first 5) ---")
        for action, cid, u in to_insert[:5]:
            print(f"  [{action}] login={u['login']} name={u['name']!r} phone={normalize_phone(u['phone'])!r} -> client_id={cid}")
        print("\n--- Sample new clients (first 5) ---")
        new_samples = [(a,c,u) for a,c,u in to_insert if a == "new"][:5]
        for action, cid, u in new_samples:
            print(f"  [new] login={u['login']} name={u['name']!r} phone={normalize_phone(u['phone'])!r}")
        print("\nDRY RUN complete. Run without --dry-run to import.")
        conn.close()
        return

    # 5. Execute
    imported = 0
    new_clients = 0
    for action, client_id, u in to_insert:
        try:
            # Create new client if needed
            if action == "new":
                reg = datetime.fromtimestamp(u["regdate"]).strftime("%Y-%m-%d") if u["regdate"] else None
                # If this login already exists in clients (same number used on both platforms),
                # link to that existing client instead of creating a duplicate
                cur.execute("SELECT id, platform FROM clients WHERE login=%s", (u["login"],))
                existing_row = cur.fetchone()
                if existing_row:
                    client_id = existing_row["id"]
                    # Update platform to MT4/MT5
                    cur.execute("""
                        UPDATE clients SET platform='MT4/MT5', updated_at=NOW()
                        WHERE id=%s
                    """, (client_id,))
                else:
                    cur.execute("""
                        INSERT INTO clients (login, name, email, phone, country, city,
                            balance, credit, leverage, group_name, agent, mqid,
                            reg_date, platform, account_type, is_ib, created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',%s,%s,NOW())
                        RETURNING id
                    """, (
                        u["login"], u["name"], u["email"], normalize_phone(u["phone"]),
                        u["country"], u["city"], u["balance"], u["credit"],
                        u["leverage"], u["group"], u["agent"], u["mqid"] or None,
                        reg, account_type_from_group(u["group"]),
                        is_ib_group(u["group"]),
                    ))
                    client_id = cur.fetchone()["id"]
                    new_clients += 1
            else:
                # Update existing client to show MT4/MT5
                cur.execute("""
                    UPDATE clients SET platform='MT4/MT5',
                        updated_at=NOW()
                    WHERE id=%s AND platform='MT5'
                """, (client_id,))

            # Insert trading_account for this MT4 login
            reg = datetime.fromtimestamp(u["regdate"]).strftime("%Y-%m-%d") if u["regdate"] else None
            cur.execute("""
                INSERT INTO trading_accounts (
                    login, client_id, name, email, group_name, account_type,
                    leverage, balance, credit, agent, reg_date,
                    is_ib, platform, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MT4',NOW())
                ON CONFLICT (login) DO UPDATE SET
                    client_id=EXCLUDED.client_id,
                    platform='MT4',
                    updated_at=NOW()
            """, (
                u["login"], client_id, u["name"], u["email"],
                u["group"], account_type_from_group(u["group"]),
                u["leverage"], u["balance"], u["credit"],
                u["agent"], reg,
                is_ib_group(u["group"]),
            ))

            imported += 1
            if imported % 500 == 0:
                conn.commit()
                print(f"  {imported} processed...")

        except Exception as e:
            conn.rollback()
            print(f"  ERROR login={u['login']}: {e}")
            continue

    conn.commit()
    print(f"\nDone.")
    print(f"  New clients created:         {new_clients}")
    print(f"  Trading accounts imported:   {imported}")

    # Final counts
    cur.execute("SELECT COUNT(*) FROM clients WHERE platform='MT4'")
    mt4_only = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM clients WHERE platform='MT4/MT5'")
    both = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM trading_accounts WHERE platform='MT4'")
    ta_mt4 = cur.fetchone()["count"]
    print(f"\nDB state after import:")
    print(f"  clients platform=MT4:        {mt4_only}")
    print(f"  clients platform=MT4/MT5:    {both}")
    print(f"  trading_accounts MT4:        {ta_mt4}")
    conn.close()

if __name__ == "__main__":
    main()
