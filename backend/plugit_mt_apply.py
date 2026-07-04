"""Apply IB-account MT group level fixes via the bridge. SAFE BY DEFAULT.
  python plugit_mt_apply.py                 -> DRY-RUN (echo only, no changes)
  python plugit_mt_apply.py --test 335000693  -> LIVE change ONE MT5 account, verify
  python plugit_mt_apply.py --live           -> LIVE batch (MT5 only; MT4 flagged/skipped)
MT4 accounts are reported but NOT changed (needs a validated MT4 manager UsersUpdate path).
"""
import sys, requests, psycopg2
BRIDGE = "http://127.0.0.1:5000"
import db_config

def load_changes():
    conn = db_config.connect(); cur = conn.cursor()
    cur.execute("""
      WITH ib_person AS (
        SELECT i.id ib_id, i.ib_level, i.agent_id, oc.customer_no
        FROM ibs i LEFT JOIN clients oc ON oc.login=i.agent_id
        WHERE i.plugit_status='synced' AND i.ib_level IS NOT NULL
      )
      SELECT DISTINCT c.login, COALESCE(c.platform,'MT5') platform, c.group_name, p.ib_level
      FROM ib_person p
      JOIN clients c ON (p.customer_no IS NOT NULL AND c.customer_no=p.customer_no) OR c.login=p.agent_id
      WHERE c.group_name ILIKE '%IB-%'
    """)
    out = []
    for login, platform, grp, lvl in cur.fetchall():
        mt4 = str(platform).upper().startswith('MT4')
        tgt = f"TNFX-IB-{lvl}" if mt4 else f"IB\IB-{lvl}"
        if (grp or '') != tgt:
            out.append({"login": login, "mt4": mt4, "old": grp, "new": tgt})
    cur.close(); conn.close()
    return out

def set_group(login, group, dry):
    r = requests.post(f"{BRIDGE}/provision/group/{login}", json={"group": group, "dry": dry}, timeout=20)
    return r.json()

def main():
    args = sys.argv[1:]
    changes = load_changes()
    mt5 = [c for c in changes if not c["mt4"]]
    mt4 = [c for c in changes if c["mt4"]]
    print(f"pending: {len(changes)} ({len(mt5)} MT5, {len(mt4)} MT4 [not changed here])")
    if "--test" in args:
        login = int(args[args.index("--test")+1])
        c = next((x for x in mt5 if x["login"]==login), None)
        if not c: print("login not in MT5 pending set"); return
        print("LIVE test:", c); print("result:", set_group(login, c["new"], dry=False))
        return
    live = "--live" in args
    done = fail = 0
    for c in mt5:
        res = set_group(c["login"], c["new"], dry=not live)
        if res.get("ok"): done += 1
        else: fail += 1; print("FAIL", c["login"], res)
    print(f"MT5 {'APPLIED' if live else 'DRY-RUN'}: ok={done} fail={fail}")
    if mt4: print(f"MT4: {len(mt4)} accounts need TNFX-IB-N groups — NOT changed (separate validated path required)")

if __name__ == "__main__":
    main()
