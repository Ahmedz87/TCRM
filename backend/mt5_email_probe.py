"""
mt5_email_probe.py — READ-ONLY. Connects to the MT5 manager and inspects the user records
to find (a) the exact email attribute name and (b) whether the server actually holds emails.

Why: the bridge reads getattr(u,"Email","") off the bulk UserGetByGroup() and logs "0 emails"
forever. The MT5Manager attribute may be "EMail" (capital M) and/or the bulk call may return a
light record without it. This probe dumps the real fields and tries the full per-user request.

No DB writes, no user modification. Frees nothing — RUN ONLY WHILE bridge.py IS STOPPED
(one manager connection per login 1025).
"""
import sys
import db_config
import psycopg2
import MT5Manager as m

SERVER = "192.109.15.62:443"
LOGIN  = 1025
PASS   = "ZjFb!vA0"


def sample_logins():
    cn = db_config.connect()
    cur = cn.cursor()
    # a few MT5 (blank platform) accounts with NO email, plus a few that DO have one
    cur.execute("""
        (SELECT login FROM clients WHERE COALESCE(platform,'')='' AND (email IS NULL OR email='')
           AND login>10 ORDER BY login LIMIT 8)
        UNION
        (SELECT login FROM clients WHERE COALESCE(platform,'')='' AND email<>'' LIMIT 4)
    """)
    out = [r[0] for r in cur.fetchall()]
    cn.close()
    return out


def main():
    print("Connecting to MT5", SERVER, "...", flush=True)
    mgr = m.ManagerAPI()
    if not mgr.Connect(SERVER, LOGIN, PASS):
        print("CONNECT FAILED:", m.LastError() if hasattr(m, "LastError") else "?")
        return
    print("  connected\n", flush=True)

    logins = sample_logins()
    print("sample logins:", logins, "\n", flush=True)

    # ── dump the full field set of one user record ──
    first = None
    for lg in logins:
        u = mgr.UserRequest(lg)
        if u:
            first = u
            break
    if first is not None:
        attrs = [a for a in dir(first) if not a.startswith("_")]
        print("UserRequest object attributes:")
        print("  ", attrs, "\n")
        mail_attrs = [a for a in attrs if "mail" in a.lower()]
        print("attributes containing 'mail':", mail_attrs, "\n")
    else:
        print("UserRequest returned nothing for all sample logins\n")

    # ── per-login: show every mail-ish field + name/phone ──
    print(f"{'login':>12} {'name':28.28} {'EMail':30.30} {'Email':20.20} {'phone'}")
    for lg in logins:
        u = mgr.UserRequest(lg)
        if not u:
            print(f"{lg:>12}  <no record>")
            continue
        em1 = getattr(u, "EMail", "") or ""
        em2 = getattr(u, "Email", "") or ""
        nm  = getattr(u, "Name", "") or ""
        ph  = getattr(u, "Phone", "") or ""
        print(f"{lg:>12} {nm:28.28} {em1:30.30} {em2:20.20} {ph}")

    # ── bulk scan: how many of ALL users carry an email (try both attrs) ──
    print("\nScanning all users via UserGetByGroup('*') ...", flush=True)
    users = mgr.UserGetByGroup("*") or []
    n = len(users)
    c_email = sum(1 for u in users if (getattr(u, "EMail", "") or "").strip())
    c_email2 = sum(1 for u in users if (getattr(u, "Email", "") or "").strip())
    print(f"  total users: {n:,}")
    print(f"  with EMail (capital M): {c_email:,}")
    print(f"  with Email:             {c_email2:,}")
    # show a few real examples
    shown = 0
    for u in users:
        e = (getattr(u, "EMail", "") or getattr(u, "Email", "") or "").strip()
        if e:
            print(f"    e.g. login {getattr(u,'Login','?')}: {e}")
            shown += 1
            if shown >= 5:
                break

    mgr.Disconnect()
    print("\ndone (read-only).")


if __name__ == "__main__":
    main()
