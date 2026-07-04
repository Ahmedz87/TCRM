p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# 1. Add 'Score' to header before 'Actions'
s = s.replace(
    "'KYC','IP','CID','Actions'",
    "'KYC','IP','CID','Score','Actions'"
)

# 2. Insert Score cell before the Actions cell (the LeadActions td)
old = """</td>
                <td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                  <LeadActions lead={l} onUpdate={load} onView={()=>setSelected(l)} showView={false} />
                </td>"""
new = """</td>
                <td style={{ padding:'8px 10px', textAlign:'center' }}>
                  <div style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:32, height:32, borderRadius:'50%', border:`2px solid ${(l.score||0)>=50?'#ff4d4d':(l.score||0)>=25?'#ff8800':'#555'}`, color:(l.score||0)>=50?'#ff4d4d':(l.score||0)>=25?'#ff8800':'#888', fontWeight:700, fontSize:12 }} title={l.match_badge==='recapture'?'Recapture +50':l.match_badge==='registered_no_deposit'?'No deposit +50':'Priority score'}>
                    {l.score||0}
                  </div>
                </td>
                <td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                  <LeadActions lead={l} onUpdate={load} onView={()=>setSelected(l)} showView={false} />
                </td>"""

if old in s:
    s = s.replace(old, new)
    print("Score cell added before Actions")
else:
    print("Actions cell pattern not found")

open(p, "w", encoding="utf-8").write(s)
print("Header has Score:", "'CID','Score','Actions'" in s)
