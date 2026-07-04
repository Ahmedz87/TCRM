import os, glob, re
print("=== All bridge.py files ===")
for f in glob.glob(r"C:\broker-crm\**\bridge.py", recursive=True):
    s = open(f, encoding="utf-8", errors="ignore").read()
    has_model4 = "has_positions_positive_pnl" in s
    bare = len(re.findall(r'has_positions"\)', s))
    size = os.path.getsize(f)
    print(f"  {f}")
    print(f"     size={size}  Model4={has_model4}  bare_has_positions_returns={bare}")
