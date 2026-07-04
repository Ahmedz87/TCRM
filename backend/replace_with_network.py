p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

old = """<td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                  {l.ip_address ? (
                    <div style={{ fontSize:10 }}>
                      <div title={l.ip_address} style={{ fontFamily:'monospace', color:'#888', marginBottom:2 }}>{l.ip_address}</div>
                      <span style={{ color: l.ip_count>3?'#ff4d4d':l.ip_count>1?'#ffaa00':'#00e5a0' }}>
                        {l.ip_count>0?`⚠️ ×${l.ip_count+1} accounts`:'✅ New IP'}
                      </span>
                    </div>
                  ) : <span style={{ color:'#555', fontSize:10 }}>—</span>}
                </td>
                {/* CID */}
                <td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                  {l.cid ? (
                    <div style={{ fontSize:10 }}>
                      <div title={l.cid} style={{ fontFamily:'monospace', color:'#888', marginBottom:2 }}>{l.cid.substring(0,10)}...</div>
                      <span style={{ color: l.cid_count>0?'#ff4d4d':'#00e5a0' }}>
                        {l.cid_count>0?`⚠️ ×${l.cid_count+1} devices`:'✅ New device'}
                      </span>
                    </div>
                  ) : <span style={{ color:'#555', fontSize:10 }}>—</span>}
                </td>"""

new = """<td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                  <div style={{ position:'relative', display:'inline-block' }}
                    onMouseEnter={()=>setNetworkHover(l.id)} onMouseLeave={()=>setNetworkHover(null)}>
                    {(() => {
                      const raw = l.network_score || 0;
                      const score = Math.min(10, Math.round(raw/10));
                      const color = score>=7?'#ff4d4d':score>=4?'#ffaa00':'#00e5a0';
                      return <span style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'3px 9px', borderRadius:99, cursor:'pointer', border:`1px solid ${color}`, color, fontSize:11, fontWeight:600 }}>🔗 {score}/10</span>;
                    })()}
                    {networkHover === l.id && (
                      <div style={{ position:'absolute', bottom:'110%', left:'50%', transform:'translateX(-50%)', background:'#1a1d24', border:'1px solid #333', borderRadius:10, padding:12, width:230, zIndex:999, pointerEvents:'none', textAlign:'left' }}>
                        <div style={{ fontSize:12, fontWeight:600, marginBottom:8 }}>Network connections</div>
                        {[
                          ['📱 Same device (CID)', l.cid_count>0 ? `×${l.cid_count+1}` : '—', l.cid_count>0],
                          ['🌐 Same IP', l.ip_count>0 ? `×${l.ip_count+1}` : '—', l.ip_count>0],
                          ['👨‍👩‍👧 Family (same name)', l.family_count>0 ? `×${l.family_count}` : '—', l.family_count>0],
                          ['🏙️ Same city', l.city || '—', !!l.city],
                          ['🤝 Same IB', l.ib_name || '—', !!l.ib_name],
                        ].map(([label,val,active]:any) => (
                          <div key={label} style={{ display:'flex', justifyContent:'space-between', fontSize:10, padding:'3px 0', borderBottom:'1px solid #222', color: active?'#e0e0e0':'#555' }}>
                            <span>{label}</span>
                            <span style={{ color: active?'#ff8800':'#555' }}>{val}</span>
                          </div>
                        ))}
                        {l.cid && <div style={{ fontSize:9, color:'#444', marginTop:6, fontFamily:'monospace' }} title={l.cid}>CID: {l.cid.substring(0,16)}...</div>}
                        {l.ip_address && <div style={{ fontSize:9, color:'#444', fontFamily:'monospace' }}>IP: {l.ip_address}</div>}
                      </div>
                    )}
                  </div>
                </td>"""

if old in s:
    s = s.replace(old, new)
    print("IP+CID cells replaced with Network hover cell")
else:
    print("Pattern not matched - check whitespace")

open(p, "w", encoding="utf-8").write(s)
print("Network cell present:", "Network connections" in s)
