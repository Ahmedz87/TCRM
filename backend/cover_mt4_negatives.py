"""
cover_mt4_negatives.py — Negative Balance Protection for MT4 (REAL deposit via Manager API).

Covers a negative MT4 balance by DEPOSITING the deficit through the MT4 Manager API's
`TradeTransaction` call (the same primitive the old Trade Soft/SoftGate stack used). Verified
against the build-matched SDK (mtmanapi64.dll build 1473, MD5-identical to the SDK's DLL):

  vtable index 105 = TradeTransaction(TradeTransInfo *info)        [proven via SDK header]
  TradeTransInfo: type=TT_BR_BALANCE(83), cmd=OP_BALANCE(6), orderby=login, price=amount

MT4 allows only ONE manager connection at a time and there is no persistent MT4 bridge server,
so this runs as a short connect -> cover -> disconnect job (run BY mt4_loop or on demand). The
MT4 manager DLL only works in an INTERACTIVE desktop session (same as the fetchers).

Guardrails (mirror the MT5 auto-cover):
  - only clients.platform='MT4', balance < 0
  - skip clients.no_auto_cover = TRUE
  - skip accounts in an OPEN abuse case (status<>'dismissed')   [--all overrides]
  - flat-only: skip if it has open positions whose floating PnL >= $10
  - deposit |balance| so balance -> 0, audited in neg_cover_log. Re-reads live to PROVE balance>=0.

Modes:
  python cover_mt4_negatives.py --probe                 # connect, list eligible, DRY-RUN (no money)
  python cover_mt4_negatives.py --one <login> --live    # cover ONE account live (validation)
  python cover_mt4_negatives.py --live                  # sweep + cover ALL eligible
  python cover_mt4_negatives.py --live --all            # also cover abuse-flagged (override)
  python cover_mt4_negatives.py --live --limit N        # cap how many this run
"""
import sys, os, argparse
import db_config
sys.path.insert(0, r"C:\broker-crm\backend")
import psycopg2
from ctypes import (Structure, POINTER, byref, sizeof,
                    c_int, c_short, c_double, c_char, c_ubyte, c_byte)
import bridge_mt4 as B  # import does NOT start the Flask server / sync_loop (those are under __main__)
# allow overriding the manager login (same password for all managers) without changing the bridge default
if os.environ.get("MT4_MGR_LOGIN"):
    B.MT4_LOGIN = int(os.environ["MT4_MGR_LOGIN"])

PG = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# ── MT4 Manager API balance-operation binding (verified against build-1473 SDK) ──────────────
V_TRADE_TRANSACTION = 105       # CManagerInterface vtable slot for TradeTransaction
TT_BR_BALANCE       = 83        # trade transaction type: balance/credit
OP_BALANCE          = 6         # trade command: balance op
OP_CREDIT           = 7         # trade command: credit op (negative price = remove credit)
RET_OK              = 0


class TradeTransInfo(Structure):
    """MT4ManagerAPI.h TradeTransInfo, #pragma pack(1). Size must be 96 bytes."""
    _pack_ = 1
    _fields_ = [
        ("type",         c_ubyte),     # trade transaction type
        ("flags",        c_byte),      # flags
        ("cmd",          c_short),     # trade command
        ("order",        c_int),       # order
        ("orderby",      c_int),       # order by (the account login for a balance op)
        ("symbol",       c_char * 12), # trade symbol
        ("volume",       c_int),       # trade volume
        ("price",        c_double),    # trade price -> AMOUNT for a balance op
        ("sl",           c_double),
        ("tp",           c_double),
        ("ie_deviation", c_int),
        ("comment",      c_char * 32),
        ("expiration",   c_int),       # __time32_t
        ("crc",          c_int),
    ]


assert sizeof(TradeTransInfo) == 96, f"TradeTransInfo size {sizeof(TradeTransInfo)} != 96 (struct mismatch!)"


def _deposit(man, login, amount, comment):
    """Deposit `amount` (positive) into MT4 account `login` via TradeTransaction/TT_BR_BALANCE.
    Returns (rc, order). rc==RET_OK(0) on success; the new balance order ticket is in tti.order."""
    tti = TradeTransInfo()
    tti.type = TT_BR_BALANCE
    tti.cmd = OP_BALANCE
    tti.orderby = int(login)
    tti.price = float(amount)
    tti.comment = comment[:31].encode("ascii", "replace")
    rc = B.vcall(man, V_TRADE_TRANSACTION, c_int, [POINTER(TradeTransInfo)], byref(tti))
    return rc, tti.order


def _credit_out(man, login, amount, comment):
    """Remove `amount` (positive) of CREDIT from MT4 account `login` via TT_BR_BALANCE /
    OP_CREDIT with a NEGATIVE price (mirrors the MT5 'Credit Out' DealerBalance type 3).
    Returns (rc, order). rc==RET_OK(0) on success."""
    tti = TradeTransInfo()
    tti.type = TT_BR_BALANCE
    tti.cmd = OP_CREDIT
    tti.orderby = int(login)
    tti.price = -float(amount)          # negative => reduce credit
    tti.comment = comment[:31].encode("ascii", "replace")
    rc = B.vcall(man, V_TRADE_TRANSACTION, c_int, [POINTER(TradeTransInfo)], byref(tti))
    return rc, tti.order


def eligible_logins(include_abuse=False, limit=None):
    c = psycopg2.connect(**PG); cur = c.cursor()
    abuse = "" if include_abuse else (
        "AND login NOT IN ("
        "SELECT login_a FROM abuse_cases WHERE status<>'dismissed' "
        "UNION SELECT login_b FROM abuse_cases WHERE status<>'dismissed' AND login_b IS NOT NULL) ")
    cur.execute(f"""
        SELECT login FROM clients
        WHERE balance < 0 AND platform='MT4' AND COALESCE(no_auto_cover,FALSE)=FALSE {abuse}
        ORDER BY balance DESC      -- smallest deficit first
    """)
    rows = [r[0] for r in cur.fetchall()]; c.close()
    return rows[:limit] if limit else rows


def _log_cover(login, deficit, credit_taken, bal_before, cred_before, bal_after, cred_after, mode, order):
    """Audit one cover. cover_amount = credit actually reclaimed; before/after captured both fields."""
    try:
        c = psycopg2.connect(**PG); cur = c.cursor()
        cur.execute("""
            INSERT INTO neg_cover_log (login, platform, deficit, cover_amount,
                balance_before, credit_before, balance_after, credit_after, status, mode, created_at)
            VALUES (%s,'MT4',%s,%s,%s,%s,%s,%s,'covered',%s,NOW())
        """, (login, deficit, credit_taken, bal_before, cred_before, bal_after, cred_after, f"{mode}#{order}"))
        c.commit(); c.close()
    except Exception as e:
        print(f"  [warn] neg_cover_log write failed for #{login} (cover DID happen): {e}", flush=True)


def cover_login(login, urec, pos_list, live, mode):
    """Cover one account given its pre-fetched user record + open positions."""
    if not urec:
        return {"login": login, "status": "no_user"}
    bal, cred = float(urec["balance"]), float(urec["credit"])
    if bal >= 0:
        return {"login": login, "status": "not_negative", "balance": round(bal, 2)}
    floating = sum(float(t.get("profit", 0)) for t in (pos_list or []))
    if pos_list and floating >= 10:
        return {"login": login, "status": "has_positions_positive_pnl", "floating_pnl": round(floating, 2)}
    deficit = round(abs(bal), 2)
    # Mirror MT5: reclaim credit up to the deficit. credit>deficit -> take deficit (surplus stays);
    # credit<=deficit -> take all credit. Balance is always corrected to 0.
    credit_to_take = round(min(cred, deficit), 2) if cred > 0 else 0.0
    if not live:
        return {"login": login, "status": "dry_run", "deficit": deficit, "balance": round(bal, 2),
                "credit": round(cred, 2), "credit_to_take": credit_to_take}
    man = B.get_manager()
    rc, order = _deposit(man, login, deficit, "Negative balance cover")
    # re-read live to PROVE the deposit landed and the balance is no longer negative
    u2 = B._get_user_record(login)
    bal_after = float(u2["balance"]) if u2 else None
    if rc != RET_OK or bal_after is None or bal_after < -0.01:
        return {"login": login, "status": "cover_failed", "rc": rc, "order": order,
                "balance_before": round(bal, 2), "balance_after": bal_after}
    # Now take the credit out (only after the balance payoff is proven to have landed)
    credit_rc = RET_OK
    if credit_to_take > 0:
        credit_rc, _ = _credit_out(man, login, credit_to_take, "Credit Out")
        u2 = B._get_user_record(login)  # re-read to capture credit_after
        bal_after = float(u2["balance"]) if u2 else bal_after
    cred_after = float(u2["credit"]) if u2 else None
    _log_cover(login, deficit, credit_to_take, bal, cred, bal_after, cred_after, mode, order)
    return {"login": login, "status": "covered", "deficit": deficit,
            "credit_taken": credit_to_take, "credit_rc": credit_rc, "rc": rc, "order": order,
            "balance_before": round(bal, 2), "balance_after": round(bal_after, 2),
            "credit_before": round(cred, 2), "credit_after": round(cred_after, 2) if cred_after is not None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--one", type=int, default=0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--all", action="store_true", help="include abuse-flagged accounts")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    B.connect()  # establish the live MT4 manager session

    # fetch users + open positions ONCE (avoid AdmUsersRequest-per-login N+1)
    users = {u["login"]: u for u in B.get_all_users()}
    try:
        trades = B.get_open_trades()
    except Exception:
        trades = []
    pos_by_login = {}
    for t in trades:
        if t.get("cmd") in (0, 1):
            pos_by_login.setdefault(t.get("login"), []).append(t)

    if args.one:
        print(cover_login(args.one, users.get(args.one), pos_by_login.get(args.one),
                          live=args.live, mode="manual"), flush=True)
        return

    rows = eligible_logins(include_abuse=args.all, limit=(args.limit or None))
    print(f"MT4 eligible negatives (DB): {len(rows)} | users loaded from MT4: {len(users)} "
          f"(live={args.live}, include_abuse={args.all})", flush=True)
    if args.probe:
        shown = 0
        for login in rows:
            r = cover_login(login, users.get(login), pos_by_login.get(login), live=False, mode="manual")
            if r["status"] != "no_user":
                print("  ", r, flush=True); shown += 1
            if shown >= 15:
                break
        return

    covered = total = 0; failed = []
    for login in rows:
        r = cover_login(login, users.get(login), pos_by_login.get(login), live=args.live, mode="auto")
        if r.get("status") == "covered":
            covered += 1; total += float(r.get("deficit") or 0)
        elif r.get("status") in ("cover_failed", "error"):
            failed.append(r)
    print(f"Done. covered {covered}/{len(rows)} MT4 accounts, deposited ${total:,.2f} total.", flush=True)
    for f in failed[:10]:
        print("  FAILED:", f, flush=True)


if __name__ == "__main__":
    main()
