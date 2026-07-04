"""
ONE-ACCOUNT copy-trade live test — the supervised gate before broad live copying.

Validates the FULL execution path for a single master->follower pair:
  master opens -> size follower lots -> bridge /trade/open -> ... -> master closes -> bridge /trade/close
DRY by default (no real orders). Real execution requires ALL of:
  • --live flag, AND
  • env COPY_LIVE_ENABLED=1 (engine gate), AND
  • the bridge running with env COPY_BRIDGE_TRADING=1 (bridge gate), AND
  • the bridge restarted so /trade/* routes exist.

Usage (DRY, safe, run anytime):
  python copy_live_test.py --follower-login 1829 --symbol XAUUSD --side buy --lots 0.01
Usage (LIVE one account — only when supervised & authorised):
  set COPY_LIVE_ENABLED=1
  python copy_live_test.py --follower-login <test> --symbol XAUUSD --side buy --lots 0.01 --live
"""
import sys, argparse, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import copy_engine as ce

BRIDGE = ce.BRIDGE_URL

def bridge_reachable():
    try:
        requests.get(BRIDGE + "/", timeout=3); return True
    except Exception:
        return False

def dry_open(login, symbol, side, lots):
    r = requests.post(BRIDGE + "/trade/open", timeout=10,
                      json={"login": login, "symbol": symbol, "side": side, "lots": lots, "dry": True})
    return r.json()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--follower-login", type=int, required=True)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--side", default="buy", choices=["buy", "sell"])
    ap.add_argument("--lots", type=float, default=0.01)
    ap.add_argument("--master-lots", type=float, default=0.10, help="master trade size to size against")
    ap.add_argument("--allocation", type=float, default=1000.0)
    ap.add_argument("--mode", default="proportional", choices=["proportional", "mirror", "fixed"])
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    print("══ COPY-TRADE ONE-ACCOUNT TEST ══")
    print(f"engine gate  COPY_LIVE_ENABLED = {ce.COPY_LIVE_ENABLED}")
    reach = bridge_reachable()
    print(f"bridge :5000 reachable          = {reach}")

    # 1. sizing
    flots = ce.compute_follower_lots(a.master_lots, a.mode, 1.0, a.allocation)
    print(f"\n1) SIZING  master {a.master_lots} lot · {a.mode} · ${a.allocation:,.0f} alloc "
          f"-> follower {flots} lot ({a.symbol} {a.side})")

    # 2. bridge dry echo (proves route + params + bridge gate state)
    if reach:
        try:
            echo = dry_open(a.follower_login, a.symbol, a.side, flots)
            print(f"2) BRIDGE /trade/open (dry)     -> {echo}")
            if "trading_enabled" in echo:
                print(f"   bridge COPY_BRIDGE_TRADING    = {echo['trading_enabled']}")
            if echo.get("error") and "404" not in str(echo):
                print("   NOTE: bridge responded but with an error — check params.")
        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                print("2) BRIDGE /trade/open           -> route NOT present yet")
                print("   → restart the bridge so the new /trade/* routes load (see CLAUDE.md).")
            else:
                print(f"2) BRIDGE /trade/open           -> {msg}")
    else:
        print("2) BRIDGE                        -> not reachable; dry validation of sizing only.")

    # 3. live execution — only if every gate is open
    print("\n3) LIVE EXECUTION")
    if not a.live:
        print("   --live not passed → DRY. Nothing placed. (This is the safe default.)")
    elif not ce.COPY_LIVE_ENABLED:
        print("   BLOCKED: --live given but COPY_LIVE_ENABLED=0. Set env COPY_LIVE_ENABLED=1 first.")
    elif not reach:
        print("   BLOCKED: bridge not reachable.")
    else:
        print(f"   Placing REAL order: {a.side} {flots} {a.symbol} on follower {a.follower_login} …")
        try:
            res = ce.place_order_via_bridge(a.follower_login, a.symbol, a.side, flots, dry=False)
            print(f"   OPEN result: {res}")
            input("   Position should be OPEN on the account. Press Enter to CLOSE it… ")
            cres = ce.close_order_via_bridge(a.follower_login, a.symbol, dry=False)
            print(f"   CLOSE result: {cres}")
            print("   ✓ One-account round-trip complete. Verify on the MT terminal.")
        except Exception as e:
            print(f"   ERROR (expected if bridge route still needs validation): {e}")

    print("\nDone. No broad copying runs until this one-account round-trip is verified and "
          "COPY_LIVE_ENABLED is set for the daemon.")

if __name__ == "__main__":
    main()
