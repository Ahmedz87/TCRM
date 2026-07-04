"""
build_sales_aliases.py — cross-match the legacy TradeSoft sales-agent NAME (legacy_sales_agent)
to our staff users.id and store it in the editable `sales_agent_aliases` table, then apply it to
clients/leads.assigned_agent_id. Auto entries (source='auto') are refreshed on each run; manual
entries the desk adds (source='manual') are preserved. Handles name variants (e.g. "Ahmad Nadem
Alkasem"->"Ahmad Nadem", "Shari Saddoon"->"Shari Sadoon Tawfiq") via token+fuzzy matching.
Re-run: python build_sales_aliases.py
The hourly enrich_tradesoft.py re-applies the alias table so new mappings flow automatically.
"""
# -*- coding: utf-8 -*-
# IMPORTANT: connect to the SAME DB the backend uses (.env DATABASE_URL), NOT hardcoded localhost.
# The live backend points at a REMOTE DB host (199.247.6.189); writing to localhost has NO effect
# on the site. Always derive the target from .env so this can't drift.
import psycopg2, re, sys, os
import db_config
sys.stdout.reconfigure(encoding='utf-8')
_url=None
for _l in open(os.path.join(os.path.dirname(__file__) or ".", ".env"), encoding="utf-8"):
    if _l.strip().startswith("DATABASE_URL"):
        _url=_l.split("=",1)[1].strip(); break
# Prefer .env DATABASE_URL; fall back to the central db_config (the REMOTE box), NEVER localhost
# (localhost is the frozen old DB — writing there has no effect on the live site).
c=psycopg2.connect(_url) if _url else db_config.connect()
print("DB:", re.sub(r':[^:@/]+@', ':****@', _url or 'localhost'))
cur=c.cursor()
def norm(s):
    s=(s or '').lower().strip().replace("'","").replace("`","").replace("-"," ")
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]',' ',s)).strip()
def toks(s): return [t for t in norm(s).split() if t]
def lev(a,b):
    if a==b: return 0
    if abs(len(a)-len(b))>2: return 9
    dp=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        prev=dp[0]; dp[0]=i
        for j,cb in enumerate(b,1):
            cu=dp[j]; dp[j]=min(dp[j]+1,dp[j-1]+1,prev+(ca!=cb)); prev=cu
    return dp[-1]
def tmatch(x,y):
    if x==y: return True
    if len(x)>=4 and len(y)>=4 and (x in y or y in x): return True
    return lev(x,y)<=1 and min(len(x),len(y))>=4
cur.execute("""SELECT id, full_name FROM users WHERE role IN ('sales_agent','sales_manager','director','customer_care')
  OR title ILIKE '%sales%' OR title ILIKE '%team leader%' OR full_name='Narmeen'""")
staff=[(r[0],r[1],toks(r[1])) for r in cur.fetchall()]
def best(name):
    nt=toks(name)
    if not nt: return None
    scored=[]
    for uid,fn,ut in staff:
        if not ut: continue
        used=set(); m=0
        for a in nt:
            for j,b in enumerate(ut):
                if j in used: continue
                if tmatch(a,b): used.add(j); m+=1; break
        first_ok=tmatch(nt[0],ut[0]); sc=m*10+(5 if first_ok else 0)-abs(len(nt)-len(ut))
        scored.append((sc,m,first_ok,uid,fn))
    scored.sort(reverse=True); top=scored[0]; gap=top[0]-(scored[1][0] if len(scored)>1 else 0)
    return top,gap
SYSTEM={'tnfx','developer admin developer','dev poovizhiraja','test dev','developer'}
cur.execute("""SELECT DISTINCT legacy_sales_agent FROM clients WHERE COALESCE(legacy_sales_agent,'') NOT IN ('','-')
   UNION SELECT DISTINCT legacy_sales_agent FROM leads WHERE COALESCE(legacy_sales_agent,'') NOT IN ('','-')""")
conf={}
for (name,) in cur.fetchall():
    if norm(name) in SYSTEM: continue
    r=best(name)
    if not r: continue
    (sc,m,first_ok,uid,fn),gap=r; nt=toks(name)
    if first_ok and m>=2 and m>=min(len(nt),2): conf[name]=(uid,fn)
    elif first_ok and len(nt)==1 and m==1 and gap>=10: conf[name]=(uid,fn)

# 1) editable alias table — single source of truth for legacy-name -> staff user
cur.execute("""CREATE TABLE IF NOT EXISTS sales_agent_aliases(
  legacy_name TEXT PRIMARY KEY, user_id INT REFERENCES users(id),
  source VARCHAR(16) DEFAULT 'auto', updated_at TIMESTAMPTZ DEFAULT NOW())""")
for name,(uid,fn) in conf.items():
    cur.execute("""INSERT INTO sales_agent_aliases(legacy_name,user_id,source) VALUES(%s,%s,'auto')
      ON CONFLICT (legacy_name) DO UPDATE SET user_id=EXCLUDED.user_id, updated_at=NOW()
      WHERE sales_agent_aliases.source='auto'""",(name,uid))
c.commit()
print(f"alias table: {len(conf)} confident entries upserted")

# 2) apply to clients + leads (only rows that differ -> minimal write)
for tbl in ("clients","leads"):
    cur.execute(f"""UPDATE {tbl} t SET assigned_agent_id=a.user_id
      FROM sales_agent_aliases a
      WHERE t.legacy_sales_agent=a.legacy_name
        AND t.assigned_agent_id IS DISTINCT FROM a.user_id""")
    print(f"{tbl}: {cur.rowcount:,} rows updated")
    c.commit()
c.close()
print("done")
