import os, glob
print("=== All bridge.py files ===")
for f in glob.glob(r"C:\broker-crm\**\bridge.py", recursive=True):
    s = open(f, encoding="utf-8", errors="ignore").read()
    has_model4 = "has_positions_positive_pnl" in s
    has_old = '"status": "has_positions"})' in s and "positive_pnl" not in s
    size = os.path.getsize(f)
    print(f"  {f}")
    print(f"     size={size}, Model4={has_model4}, old_has_positions={'has_positions\"})' in s}")

print("\n=== Which file has the OLD 'has_positions' string? ===")
for f in glob.glob(r"C:\broker-crm\**\bridge.py", recursive=True):
    s = open(f, encoding="utf-8", errors="ignore").read()
    # count occurrences of the bare has_positions return
    import re
    bare = len(re.findall(r'"status":\s*"has_positions"\)', s))
    print(f"  {f}: bare 'has_positions' returns = {bare}")
