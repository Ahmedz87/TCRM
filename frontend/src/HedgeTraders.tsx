import React, { useState, useEffect } from 'react';
import { apiGet } from './api';

const fmt = (n:number) => n>=1e6?'$'+(n/1e6).toFixed(2)+'M':n>=1e3?'$'+(n/1e3).toFixed(1)+'K':'$'+Math.round(n);
const tval = (t:number) => t ? new Date(t*1000).toISOString().slice(5,16).replace('T',' ') : '';

const SEV_COLOR:any = { critical:'#ff5d6c', high:'#ffaa00', medium:'#ffd666' };

export default function HedgeTraders() {
  const [stats, setStats] = useState<any>(null);
  const [traders, setTraders] = useState<any[]>([]);
  const [sev, setSev] = useState('all');
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiGet('/hedge/stats').then(setStats).catch(()=>{});
  }, []);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ severity: sev, search });
    apiGet(`/hedge/traders?${p}`).then((d:any)=>setTraders(d?.traders||[])).catch(()=>setTraders([])).finally(()=>setLoading(false));
  }, [sev, search]);

  const openDetail = (login:number) => {
    setDetail({ loading:true });
    apiGet(`/hedge/trader/${login}`).then(setDetail).catch(()=>setDetail(null));
  };

  const TABS = [
    ['all','All'], ['critical','🔴 Critical'], ['high','🟠 High'],
    ['medium','🟡 Medium'], ['bonus','🎁 Bonus'], ['linked','🔗 Linked'],
  ];

  return (
    <div style={{ color:'#e8e8e8' }}>
      {/* Stats strip */}
      {stats && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:10, marginBottom:16 }}>
          {[
            ['Flagged', stats.total, '#fff'],
            ['Critical', stats.critical, '#ff5d6c'],
            ['High', stats.high, '#ffaa00'],
            ['Medium', stats.medium, '#ffd666'],
            ['With bonus', stats.with_bonus, '#00e5a0'],
            ['Linked', stats.linked, '#00aaff'],
          ].map(([label,val,color]:any)=>(
            <div key={label} style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'12px 14px' }}>
              <div style={{ fontSize:11, color:'#888', marginBottom:4 }}>{label}</div>
              <div style={{ fontSize:22, fontWeight:600, color }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filter tabs */}
      <div style={{ display:'flex', gap:8, marginBottom:12, flexWrap:'wrap' }}>
        {TABS.map(([k,label])=>(
          <button key={k} onClick={()=>setSev(k)}
            style={{ padding:'6px 14px', borderRadius:8, fontSize:12, cursor:'pointer',
              background: sev===k?'rgba(0,170,255,0.15)':'transparent',
              border:`1px solid ${sev===k?'#00aaff':'#626d80'}`,
              color: sev===k?'#00aaff':'#aaa' }}>{label}</button>
        ))}
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search login..."
          style={{ marginLeft:'auto', padding:'6px 12px', borderRadius:8, background:'var(--bg-input,#373f4d)', border:'1px solid #626d80', color:'#fff', fontSize:12 }} />
      </div>

      {/* Traders table */}
      <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, overflow:'hidden' }}>
        <div style={{ display:'grid', gridTemplateColumns:'70px 1fr 90px 90px 90px 100px 1fr', gap:8, padding:'10px 14px', fontSize:10, color:'#666', textTransform:'uppercase', borderBottom:'1px solid #4f596b' }}>
          <span>Score</span><span>Account</span><span style={{textAlign:'right'}}>Hedge%</span>
          <span style={{textAlign:'right'}}>Positions</span><span style={{textAlign:'right'}}>Bonus</span>
          <span style={{textAlign:'right'}}>Balance</span><span>Reasons</span>
        </div>
        {loading && <div style={{ padding:20, color:'#666', fontSize:13 }}>Loading…</div>}
        {!loading && traders.length===0 && <div style={{ padding:20, color:'#666', fontSize:13 }}>No flagged traders.</div>}
        <div style={{ maxHeight:560, overflowY:'auto' }}>
          {traders.map(t=>(
            <div key={t.login} onClick={()=>openDetail(t.login)}
              style={{ display:'grid', gridTemplateColumns:'70px 1fr 90px 90px 90px 100px 1fr', gap:8, padding:'11px 14px', fontSize:12.5, borderBottom:'1px solid #373f4d', cursor:'pointer', alignItems:'center' }}
              onMouseEnter={e=>(e.currentTarget.style.background='#161922')}
              onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
              <span><span style={{ display:'inline-block', minWidth:34, textAlign:'center', padding:'3px 0', borderRadius:6, fontWeight:700, fontSize:12, background:SEV_COLOR[t.severity]+'22', color:SEV_COLOR[t.severity] }}>{t.score}</span></span>
              <span><span style={{ color:'#fff' }}>{t.name}</span><span style={{ color:'#666', fontSize:10 }}> #{t.login} · {t.country}</span></span>
              <span style={{ textAlign:'right', color: t.hedged_ratio>=0.8?'#ff5d6c':'#ffaa00', fontWeight:600 }}>{Math.round(t.hedged_ratio*100)}%</span>
              <span style={{ textAlign:'right', color:'#aaa' }}>{t.hedged_positions}/{t.total_positions}</span>
              <span style={{ textAlign:'right', color: t.has_bonus?'#00e5a0':'#555' }}>{t.has_bonus?fmt(t.credit):'—'}</span>
              <span style={{ textAlign:'right', color:'#ccc' }}>{fmt(t.balance)}</span>
              <span style={{ fontSize:10.5, color:'#888', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{t.reasons}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Detail drawer */}
      {detail && (
        <div onClick={()=>setDetail(null)} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.6)', zIndex:100, display:'flex', justifyContent:'flex-end' }}>
          <div onClick={e=>e.stopPropagation()} style={{ width:680, maxWidth:'94vw', height:'100%', overflowY:'auto', background:'#262c36', borderLeft:'1px solid #4f596b', padding:24 }}>
            {detail.loading ? <div style={{ color:'#888' }}>Loading…</div> : detail.error ? <div style={{ color:'#ff5d6c' }}>Not found</div> : (<>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16 }}>
                <div>
                  <span style={{ padding:'3px 10px', borderRadius:6, fontSize:11, fontWeight:700, background:SEV_COLOR[detail.severity]+'22', color:SEV_COLOR[detail.severity], textTransform:'uppercase' }}>{detail.severity}</span>
                  <div style={{ fontSize:20, fontWeight:600, marginTop:8 }}>{detail.name}</div>
                  <div style={{ fontSize:12, color:'#888' }}>#{detail.login} · {detail.country}</div>
                </div>
                <button onClick={()=>setDetail(null)} style={{ background:'none', border:'none', color:'#888', fontSize:22, cursor:'pointer' }}>×</button>
              </div>

              <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:16 }}>
                {[['Score',detail.score,'/100'],['Hedged',Math.round(detail.hedged_ratio*100)+'%',`${detail.hedged_positions}/${detail.total_positions}`],['Bonus',detail.has_bonus?fmt(detail.credit):'none','']].map(([l,v,s]:any)=>(
                  <div key={l} style={{ background:'#373f4d', borderRadius:8, padding:'12px 14px' }}>
                    <div style={{ fontSize:10, color:'#666', textTransform:'uppercase' }}>{l}</div>
                    <div style={{ fontSize:20, fontWeight:600, marginTop:2 }}>{v}</div>
                    <div style={{ fontSize:10, color:'#666' }}>{s}</div>
                  </div>
                ))}
              </div>

              <div style={{ marginBottom:16 }}>
                <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:6 }}>Recommended action</div>
                <div style={{ background:'rgba(255,170,0,0.08)', border:'1px solid rgba(255,170,0,0.3)', borderRadius:8, padding:'10px 12px', color:'#ffaa00', fontWeight:600, fontSize:13 }}>{detail.recommendation}</div>
              </div>

              {/* Hedge trades evidence */}
              {detail.hedge_trades?.length>0 && (
                <div style={{ marginBottom:16 }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:6 }}>Hedge trades — overlapping opposite positions ({detail.hedge_trades.length})</div>
                  <div style={{ background:'#373f4d', borderRadius:8, overflow:'hidden' }}>
                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 80px', gap:6, padding:'7px 10px', fontSize:9, color:'#666', textTransform:'uppercase', borderBottom:'1px solid #4f596b' }}>
                      <span>Leg A</span><span>Leg B (opposite)</span><span style={{textAlign:'right'}}>Overlap</span>
                    </div>
                    <div style={{ maxHeight:300, overflowY:'auto' }}>
                      {detail.hedge_trades.map((h:any,i:number)=>(
                        <div key={i} style={{ display:'grid', gridTemplateColumns:'1fr 1fr 80px', gap:6, padding:'8px 10px', fontSize:11, borderBottom:'1px solid #373f4d', alignItems:'center' }}>
                          <span>
                            <span style={{ color: h.a_dir==='buy'?'#00e5a0':'#ff5d6c', fontWeight:600 }}>{h.a_dir.toUpperCase()}</span>
                            <span style={{ color:'#ccc' }}> {h.a_sym} {h.a_vol.toFixed(2)}</span>
                            <span style={{ color: h.a_profit>=0?'#00e5a0':'#ff5d6c', fontSize:10 }}> {fmt(h.a_profit)}</span>
                          </span>
                          <span>
                            <span style={{ color: h.b_dir==='buy'?'#00e5a0':'#ff5d6c', fontWeight:600 }}>{h.b_dir.toUpperCase()}</span>
                            <span style={{ color:'#ccc' }}> {h.b_sym} {h.b_vol.toFixed(2)}</span>
                            <span style={{ color: h.b_profit>=0?'#00e5a0':'#ff5d6c', fontSize:10 }}> {fmt(h.b_profit)}</span>
                            {h.relation!=='same_symbol' && <span style={{ fontSize:8, color:'#888', padding:'1px 4px', background:'#4f596b', borderRadius:3, marginLeft:4 }}>{h.relation}</span>}
                          </span>
                          <span style={{ textAlign:'right', color:'#888', fontSize:10 }}>{h.overlap_sec}s</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Connections */}
              {detail.connections?.length>0 && (
                <div style={{ marginBottom:16 }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:6 }}>Connected accounts</div>
                  {detail.connections.map((c:any,i:number)=>{
                    const strong = ['cid','ip','mqid'].includes(c.reason);
                    const labels:any={cid:'Same device',ip:'Same IP',mqid:'Same MQID',family:'Family',ib:'Same IB'};
                    return (
                      <div key={i} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 10px', background:'#373f4d', borderRadius:7, marginBottom:4, fontSize:11 }}>
                        <span style={{ fontFamily:'monospace', color:'#00aaff' }}>#{c.login}</span>
                        <span style={{ flex:1 }} />
                        <span style={{ fontSize:9, padding:'2px 8px', borderRadius:4, background: strong?'rgba(255,93,108,0.15)':'rgba(120,120,120,0.15)', color: strong?'#ff5d6c':'#999', fontWeight:600 }}>{labels[c.reason]||c.reason}</span>
                        {c.value && c.value!=='account' && <span style={{ fontSize:10, color:'#777', fontFamily:'monospace' }}>{c.value}</span>}
                      </div>
                    );
                  })}
                </div>
              )}
            </>)}
          </div>
        </div>
      )}
    </div>
  );
}
