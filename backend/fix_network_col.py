p = r"C:\broker-crm\backend\routers\neg_cover_router.py"
s = open(p, encoding="utf-8").read()

# Replace the network_score source: instead of clients.network_score (always 0),
# compute from network_edges count. Add an edge-count lookup in scan.
# Find where we read network_score from the row and build the item
old = '''    # Build abuse lookup with type + reason per login'''
new = '''    # Build edge-count lookup (real network connections) for the negative accounts
    edge_counts = {}
    try:
        ec = db.execute(text("""
            SELECT lg, COUNT(*) FROM (
                SELECT login_a AS lg FROM network_edges
                UNION ALL
                SELECT login_b AS lg FROM network_edges
            ) t GROUP BY lg
        """)).fetchall()
        edge_counts = {r[0]: r[1] for r in ec}
    except Exception:
        pass

    # Build abuse lookup with type + reason per login'''

if old in s and "edge_counts" not in s:
    s = s.replace(old, new)
    print("Added edge-count lookup")

# Now set network_score from edge count (capped to a 0-100 scale: edges*3 capped 100, shown as /10)
old2 = '''        net_score, flagged = int(r[4] or 0), bool(r[5])'''
new2 = '''        net_score = min(100, edge_counts.get(login, 0) * 3)  # from real network edges
        flagged = bool(r[5])'''
if old2 in s:
    s = s.replace(old2, new2)
    print("network_score now computed from edge count")

open(p, "w", encoding="utf-8").write(s)
import py_compile
py_compile.compile(p, doraise=True)
print("SYNTAX OK")
