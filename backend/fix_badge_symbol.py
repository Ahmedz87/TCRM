p = r"C:\broker-crm\frontend\src\Clients.tsx"
s = open(p, encoding="utf-8").read()

# Replace the badge text with just symbols, make them compact circular badges
s = s.replace(
    ">\u267B RECAPTURE</span>}",
    ">\u267B</span>}"
)
s = s.replace(
    ">\U0001F4E5 FROM LEAD</span>}",
    ">\U0001F4E5</span>}"
)

# Also tighten padding so it's a small badge
s = s.replace(
    "fontSize:9, fontWeight:700, padding:'1px 6px', borderRadius:99, background:'rgba(255,77,77,0.15)', color:'#ff4d4d', border:'1px solid #ff4d4d', whiteSpace:'nowrap' }}>\u267B</span>}",
    "fontSize:12, padding:'1px 5px', borderRadius:99, background:'rgba(255,77,77,0.15)', border:'1px solid #ff4d4d', whiteSpace:'nowrap' }}>\u267B</span>}"
)
s = s.replace(
    "fontSize:9, fontWeight:700, padding:'1px 6px', borderRadius:99, background:'rgba(0,170,255,0.12)', color:'#00aaff', border:'1px solid #00aaff', whiteSpace:'nowrap' }}>\U0001F4E5</span>}",
    "fontSize:12, padding:'1px 5px', borderRadius:99, background:'rgba(0,170,255,0.12)', border:'1px solid #00aaff', whiteSpace:'nowrap' }}>\U0001F4E5</span>}"
)

open(p, "w", encoding="utf-8").write(s)
print("Done. RECAPTURE text removed:", "RECAPTURE" not in s)
print("FROM LEAD text removed:", "FROM LEAD" not in s)
