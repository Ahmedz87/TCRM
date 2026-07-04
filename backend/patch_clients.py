import re

# ---- Fix clients_router.py ----
p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

# 1. Fix score sort to use call_score + pin recapture to top
s = s.replace(
    'elif sort == "score":      sort_col = "balance DESC"',
    'elif sort == "score":      sort_col = "COALESCE(call_score,0) DESC, balance DESC"'
)
if "lead_badge=\x27recapture\x27 THEN 0" not in s:
    s = s.replace(
        '    elif sort == "city":       sort_col = "city ASC"',
        '    elif sort == "city":       sort_col = "city ASC"\n'
        '    sort_col = "CASE WHEN lead_badge=\x27recapture\x27 THEN 0 ELSE 1 END ASC, " + sort_col'
    )

# 2. Add lead_badge to SELECT
if "MAX(c.lead_badge)" not in s:
    s = s.replace(
        "            CASE\n                WHEN c.phone IS NOT NULL AND c.phone != \x27\x27 AND c.phone != \x270\x27\n                THEN c.phone ELSE CAST(c.login AS TEXT)\n            END as ck",
        "            MAX(c.lead_badge)         as lead_badge,\n            MAX(c.matched_lead_id)    as matched_lead_id,\n            CASE\n                WHEN c.phone IS NOT NULL AND c.phone != \x27\x27 AND c.phone != \x270\x27\n                THEN c.phone ELSE CAST(c.login AS TEXT)\n            END as ck"
    )

# 3. Map lead_badge + boost recapture in calc
if '"lead_badge":          r[27]' not in s:
    s = s.replace(
        '            "all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],\n            "source":              "none",\n        }\n        mapped["call_score"] = calc_priority_score(mapped, settings)',
        '            "all_logins":          list(r[26]) if len(r)>26 and r[26] else [r[0]],\n            "lead_badge":          r[27] if len(r)>27 else None,\n            "matched_lead_id":     r[28] if len(r)>28 else None,\n            "source":              "none",\n        }\n        mapped["call_score"] = calc_priority_score(mapped, settings)\n        if mapped.get("lead_badge") == "recapture":\n            mapped["call_score"] += 50'
    )

open(p, "w", encoding="utf-8").write(s)
print("clients_router.py patched:", "MAX(c.lead_badge)" in s and "call_score,0) DESC" in s)

# ---- Fix Clients.tsx ----
p2 = r"C:\broker-crm\frontend\src\Clients.tsx"
t = open(p2, encoding="utf-8").read()
if "RECAPTURE" not in t:
    flag = "{c.is_flagged && <span style={{ fontSize:9, padding:\x271px 6px\x27, borderRadius:99, background:\x27rgba(255,77,77,0.15)\x27, color:\x27#ff4d4d\x27, border:\x271px solid rgba(255,77,77,0.3)\x27, whiteSpace:\x27nowrap\x27 }}>\U0001F6A8 FLAGGED</span>}"
    add = flag + "\n                    {c.lead_badge === \x27recapture\x27 && <span title={`Was a client, filled the ad form again`} style={{ fontSize:9, fontWeight:700, padding:\x271px 6px\x27, borderRadius:99, background:\x27rgba(255,77,77,0.15)\x27, color:\x27#ff4d4d\x27, border:\x271px solid #ff4d4d\x27, whiteSpace:\x27nowrap\x27 }}>\u267B RECAPTURE</span>}\n                    {c.lead_badge === \x27from_lead\x27 && <span title={`Came from a Meta lead`} style={{ fontSize:9, fontWeight:700, padding:\x271px 6px\x27, borderRadius:99, background:\x27rgba(0,170,255,0.12)\x27, color:\x27#00aaff\x27, border:\x271px solid #00aaff\x27, whiteSpace:\x27nowrap\x27 }}>\U0001F4E5 FROM LEAD</span>}"
    t = t.replace(flag, add)
    open(p2, "w", encoding="utf-8").write(t)
    print("Clients.tsx patched:", "RECAPTURE" in t)
else:
    print("Clients.tsx already has badges")
