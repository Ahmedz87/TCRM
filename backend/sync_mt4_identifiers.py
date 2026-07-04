"""
sync_mt4_identifiers.py — Pull MT4 login history (IP + CID) from the
MT4 journal and sync into account_identifiers + network_edges tables.

Run:  python sync_mt4_identifiers.py              (default: all history)
      python sync_mt4_identifiers.py --days=30    (last 30 days only)
      python sync_mt4_identifiers.py --cross-platform  (add MT4<->MT5 edges)
"""
import sys, os, re, time
import db_config
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DAYS_BACK      = 3650
CROSS_PLATFORM = "--cross-platform" in sys.argv
for arg in sys.argv:
    if arg.startswith("--days="):
        DAYS_BACK = int(arg.split("=")[1])

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# Vtable slots
V_JOURNAL_REQUEST = 96
V_MEM_FREE        = 3
LOG_TYPE_LOGINS   = 1

# ServerLog struct layout: int(4) + char time[24] + char ip[256] + char message[512]
SERVERLOG_SIZE = 796
OFFSET_IP      = 28
OFFSET_MSG     = 284

# Parse: '12271': login (1470, iphone, dc: 3, cid: 098884edbf..., ping: 75ms, port: 35822)
RE_LOGIN = re.compile(r"'(\d+)':\s*login")
RE_CID   = re.compile(r"\bcid:\s*([0-9a-fA-F]{16,})")

def parse_record(base, i):
    off = base + i * SERVERLOG_SIZE
    ip  = string_at(off + OFFSET_IP,  256).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    msg = string_at(off + OFFSET_MSG, 512).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    return ip, msg

def main():
    from bridge_mt4 import load_dll, connect, get_manager, vcall

    print("=" * 60)
    print(f"MT4 IDENTIFIER SYNC  (last {DAYS_BACK} days)")
    print(f"Cross-platform edges: {CROSS_PLATFORM}")
    print("=" * 60)

    load_dll()
    connect()
    man = get_manager()

    from_time = int(time.time()) - DAYS_BACK * 86400
    to_time   = int(time.time())
    print(f"Journal range: {datetime.fromtimestamp(from_time).date()} → today")

    total = c_int(0)
    ptr   = vcall(man, V_JOURNAL_REQUEST, c_void_p,
                  [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                  LOG_TYPE_LOGINS, from_time, to_time, b"", byref(total))

    if not ptr or total.value <= 0:
        print("No journal records returned.")
        return

    print(f"Journal records fetched: {total.value:,}")

    # login -> {ip: count}, login -> {cid: count}
    login_ips  = {}
    login_cids = {}
    skipped    = 0

    for i in range(total.value):
        try:
            ip, msg = parse_record(ptr, i)
            m = RE_LOGIN.search(msg)
            if not m:
                skipped += 1
                continue
            login = int(m.group(1))
            if login <= 0:
                continue
            if ip:
                login_ips.setdefault(login, {})
                login_ips[login][ip] = login_ips[login].get(ip, 0) + 1
            mc = RE_CID.search(msg)
            if mc:
                cid = mc.group(1).lower()
                login_cids.setdefault(login, {})
                login_cids[login][cid] = login_cids[login].get(cid, 0) + 1
        except Exception:
            skipped += 1

    vcall(man, V_MEM_FREE, None, [c_void_p], ptr)

    print(f"Logins with IP history:  {len(login_ips):,}")
    print(f"Logins with CID history: {len(login_cids):,}")
    if skipped:
        print(f"Skipped records:         {skipped:,}")

    now = datetime.now(timezone.utc)
    conn_db = psycopg2.connect(**DB)
    cur     = conn_db.cursor()

    # ── account_identifiers upsert ────────────────────────────────────────────
    print("Upserting account_identifiers...")

    # Build rows: (login, type, value, first_seen, last_seen, count)
    rows = []
    for login, ip_counts in login_ips.items():
        for ip, cnt in ip_counts.items():
            rows.append((login, "ip", ip, now, now, cnt))
    for login, cid_counts in login_cids.items():
        for cid, cnt in cid_counts.items():
            rows.append((login, "cid", cid, now, now, cnt))

    if rows:
        execute_values(cur, """
            INSERT INTO account_identifiers
                (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
            VALUES %s
            ON CONFLICT (login, identifier_type, identifier_value)
            DO UPDATE SET
                last_seen  = GREATEST(account_identifiers.last_seen, EXCLUDED.last_seen),
                seen_count = account_identifiers.seen_count + EXCLUDED.seen_count
        """, rows, template="(%s,%s,%s,%s,%s,%s)", page_size=1000)
        print(f"  Rows upserted: {len(rows):,}")

    conn_db.commit()

    # ── network_edges: MT4 <-> MT4 ────────────────────────────────────────────
    print("Building MT4-MT4 network edges...")

    edges = set()

    # IP edges
    ip_to_logins = {}
    for login, ip_counts in login_ips.items():
        for ip in ip_counts:
            ip_to_logins.setdefault(ip, set()).add(login)
    for ip, logins in ip_to_logins.items():
        logins = sorted(logins)
        for i in range(len(logins)):
            for j in range(i+1, len(logins)):
                edges.add((logins[i], logins[j], "ip", ip))

    # CID edges
    cid_to_logins = {}
    for login, cid_counts in login_cids.items():
        for cid in cid_counts:
            cid_to_logins.setdefault(cid, set()).add(login)
    for cid, logins in cid_to_logins.items():
        logins = sorted(logins)
        for i in range(len(logins)):
            for j in range(i+1, len(logins)):
                edges.add((logins[i], logins[j], "cid", cid))

    # ── network_edges: MT4 <-> MT5 (cross-platform) ───────────────────────────
    if CROSS_PLATFORM:
        print("Building MT4-MT5 cross-platform edges...")
        cur.execute("""
            SELECT login, identifier_type, identifier_value
            FROM account_identifiers
            WHERE login NOT IN (
                SELECT login FROM trading_accounts WHERE platform='MT4'
            )
        """)
        mt5_ids = {}
        for row in cur.fetchall():
            mt5_ids.setdefault((row[1], row[2]), set()).add(row[0])

        for login_mt4, ip_counts in login_ips.items():
            for ip in ip_counts:
                for login_mt5 in mt5_ids.get(("ip", ip), set()):
                    a, b = min(login_mt4, login_mt5), max(login_mt4, login_mt5)
                    edges.add((a, b, "ip", ip))

        for login_mt4, cid_counts in login_cids.items():
            for cid in cid_counts:
                for login_mt5 in mt5_ids.get(("cid", cid), set()):
                    a, b = min(login_mt4, login_mt5), max(login_mt4, login_mt5)
                    edges.add((a, b, "cid", cid))

    edge_list = list(edges)
    if edge_list:
        execute_values(cur, """
            INSERT INTO network_edges (login_a, login_b, reason, value, weight, created_at)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, [(a, b, r, v, 3, now) for a,b,r,v in edge_list],
        template="(%s,%s,%s,%s,%s,%s)", page_size=1000)
        print(f"  Network edges added: {len(edge_list):,}")

    conn_db.commit()

    # Summary
    cur.execute("SELECT COUNT(*) FROM account_identifiers WHERE identifier_type='ip' AND login IN (SELECT login FROM trading_accounts WHERE platform='MT4')")
    n_ip = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM account_identifiers WHERE identifier_type='cid' AND login IN (SELECT login FROM trading_accounts WHERE platform='MT4')")
    n_cid = cur.fetchone()[0]

    print(f"\nDone.")
    print(f"  MT4 IP identifiers:   {n_ip:,}")
    print(f"  MT4 CID identifiers:  {n_cid:,}")
    print(f"  Network edges added:  {len(edge_list):,}")
    conn_db.close()

if __name__ == "__main__":
    main()
