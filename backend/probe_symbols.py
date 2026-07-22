"""
probe_symbols.py — discover how YOUR installed MT5Manager exposes symbols.
Run once:  python probe_symbols.py
Paste the entire output back.
"""
import MT5Manager

from mt_secrets import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD

m = MT5Manager.ManagerAPI()
if not m.Connect(MT5_SERVER, MT5_LOGIN, MT5_PASSWORD):
    print("CONNECT FAILED"); raise SystemExit

print("\n== symbol-related methods on the manager ==")
print([x for x in dir(m) if "ymbol" in x])

# Try the most likely enumeration methods; show whatever works.
def try_call(label, fn):
    try:
        r = fn()
        print(f"\n[OK] {label} ->", type(r), "| value:", (r if not isinstance(r, (list, tuple)) else f"{len(r)} items"))
        return r
    except Exception as e:
        print(f"\n[--] {label} failed: {e}")
        return None

total = try_call("SymbolGetTotal()", lambda: m.SymbolGetTotal())
if total is None:
    total = try_call("SymbolTotal()", lambda: m.SymbolTotal())

# Try to grab ONE symbol config object via several possible APIs
sample = None
for label, fn in [
    ("SymbolNext(0)",        lambda: m.SymbolNext(0)),
    ("SymbolGetByIndex(0)",  lambda: m.SymbolGetByIndex(0)),
    ("SymbolGet('XAUUSD')",  lambda: m.SymbolGet("XAUUSD")),
    ("SymbolGetByGroup('*')",lambda: m.SymbolGetByGroup("*")),
]:
    r = try_call(label, fn)
    if r is not None and sample is None:
        sample = r[0] if isinstance(r, (list, tuple)) and r else r

if sample is not None and not isinstance(sample, (str, int, float)):
    print("\n== attributes on a symbol config object ==")
    attrs = [a for a in dir(sample) if not a.startswith("_")]
    print(attrs)
    print("\n== sample values (the ones we likely need) ==")
    for a in ["Symbol", "Path", "Description", "CurrencyBase", "CurrencyProfit",
              "CurrencyMargin", "Digits", "ContractSize", "CategoryName"]:
        try:
            v = getattr(sample, a)
            print(f"  {a} =", v() if callable(v) else v)
        except Exception as e:
            print(f"  {a} -- n/a ({e})")
else:
    print("\nsample symbol value:", sample)
