import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';

const SEV_COLOR: Record<string,string> = { critical:'#ff4d4d', high:'#ffaa00', medium:'#ffee00' };
const SEV_BG:    Record<string,string> = { critical:'rgba(255,77,77,0.12)', high:'rgba(255,170,0,0.12)', medium:'rgba(255,238,0,0.08)' };
const SEV_ICON:  Record<string,string> = { critical:'🔴', high:'🟠', medium:'🟡' };
const STATUS_COLOR: Record<string,string> = { open:'#555', frozen:'#ff4d4d', hold_wd:'#ffaa00', reviewing:'#00aaff', resolved:'#00e5a0' };

const ABUSE_LABELS: Record<string,string> = {
  // System 1: Bonus
  bonus_hedge_l1:             '🎁 Bonus Hedge — Classic',
  bonus_hedge_l2:             '🎁 Bonus Hedge — Split Volume',
  bonus_eer:                  '🎁 Bonus — Double & Dash',
  bonus_farm:                 '🎁 Bonus Farm',
  // System 2: Swap
  swap_profitable_hold:       '💱 Swap — Profit Hold',
  swap_consecutive_overnight: '💱 Swap — Consecutive Night',
  swap_symbol_exclusivity:    '💱 Swap — Symbol Exclusivity',
  swap_coordinated_farm:      '💱 Swap Farm',
  // System 3: Toxic
  night_latency_arb:          '☢️ Night Latency Arb',
  night_exotic_concentration: '☢️ Night Concentration',
  toxic_latency_arb:          '☢️ Latency Arb',
  midnight_exotic_arb:        '☢️ Midnight Exotic Arb',
  midnight_exotic_hedge:      '☢️ Midnight Exotic Hedge',
  // Other
  device_cluster:             'Device Cluster',
  cpa_fraud:                  'CPA Fraud',
  round_trip:                 'Round Trip',
  classic_hedge:              'Classic Hedge',
  ib_self_referral:           'IB Self-Referral',
};

function RiskBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6 }}>
      <div style={{ flex:1, height:4, background:'#373f4d', borderRadius:2, overflow:'hidden' }}>
        <div style={{ height:4, width:`${value}%`, background:color, borderRadius:2, transition:'width .3s' }} />
      </div>
      <span style={{ fontSize:11, fontWeight:700, color, width:28, textAlign:'right' }}>{value}</span>
    </div>
  );
}

function NetworkRing({ score }: { score: number }) {
  const color = score >= 70 ? '#ff4d4d' : score >= 40 ? '#ffaa00' : '#00aaff';
  const r = 14, circ = 2*Math.PI*r;
  const dash = (score/100) * circ;
  return (
    <div style={{ position:'relative', width:36, height:36, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <svg width="36" height="36" style={{ position:'absolute', top:0, left:0, transform:'rotate(-90deg)' }}>
        <circle cx="18" cy="18" r={r} fill="none" stroke="#373f4d" strokeWidth="3" />
        <circle cx="18" cy="18" r={r} fill="none" stroke={color} strokeWidth="3"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
      </svg>
      <span style={{ fontSize:10, fontWeight:700, color }}>{score}</span>
    </div>
  );
}

function CaseDetail({ case: c, onClose, onAction }: any) {
  const color = SEV_COLOR[c.severity] || '#888';
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    apiGet(`/abuse/cases/${c.id}`).then(setDetail).catch(()=>{});
  }, [c.id]);

  const doAction = async (action: string) => {
    setLoading(true);
    try {
      await apiPost(`/abuse/cases/${c.id}/action`, { action, note });
      onAction && onAction(c.id, action);
      onClose();
    } catch(e) { alert('Failed'); }
    setLoading(false);
  };

  return (
    <div style={{ position:'fixed', inset:0, zIndex:200, display:'flex' }}>
      <div style={{ flex:1, background:'rgba(0,0,0,0.6)' }} onClick={onClose} />
      <div style={{ width:460, background:'#2c333e', borderLeft:'1px solid #4f596b', display:'flex', flexDirection:'column', overflow:'hidden' }}>
        {/* Header */}
        <div style={{ padding:'16px', borderBottom:'1px solid #4f596b', flexShrink:0 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
                <span style={{ fontSize:11, padding:'2px 10px', borderRadius:99, background:SEV_BG[c.severity], color, fontWeight:700 }}>
                  {SEV_ICON[c.severity]} {c.severity?.toUpperCase()}
                </span>
                <span style={{ fontSize:11, color: STATUS_COLOR[c.status]||'#555', padding:'2px 8px', background:'#373f4d', borderRadius:99 }}>{c.status}</span>
              </div>
              <div style={{ fontSize:16, fontWeight:700 }}>{ABUSE_LABELS[c.abuse_type] || c.abuse_type}</div>
              {c.symbol && <div style={{ fontSize:12, color:'#555', marginTop:2 }}>{c.symbol}</div>}
            </div>
            <button onClick={onClose} style={{ background:'none', border:'none', color:'#555', cursor:'pointer', fontSize:20, padding:4 }}>✕</button>
          </div>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'14px 16px' }}>
          {/* Score cards */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, marginBottom:16 }}>
            {[['Risk Score', c.risk_score, color], ['Network', c.network_score, c.network_score>=70?'#ff4d4d':c.network_score>=40?'#ffaa00':'#00aaff'], ['Confidence', c.confidence, '#00e5a0']].map(([l,v,cl])=>(
              <div key={l as string} style={{ background:'#373f4d', borderRadius:8, padding:'10px', textAlign:'center' }}>
                <div style={{ fontSize:9, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{l}</div>
                <div style={{ fontSize:24, fontWeight:700, color:cl as string }}>{v}</div>
                <div style={{ fontSize:9, color:'#444' }}>/100</div>
              </div>
            ))}
          </div>

          {/* Evidence */}
          <div style={{ marginBottom:16 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Evidence</div>
            <div style={{ background:'#373f4d', borderRadius:8, padding:12, fontSize:12, color:'#aaa', lineHeight:1.8 }}>{c.evidence}</div>
          </div>

          {/* Recommendation */}
          {detail?.recommendation && (
            <div style={{ marginBottom:16 }}>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Recommended action</div>
              <div style={{ background:'rgba(255,170,0,0.08)', border:'1px solid rgba(255,170,0,0.3)', borderRadius:8, padding:'10px 12px', fontSize:13, color:'#ffaa00', fontWeight:600 }}>
                {detail.recommendation}
              </div>
            </div>
          )}

          {/* Proof trades — the actual trades that triggered this case */}
          {detail?.proof_trades?.length > 0 && (
            <div style={{ marginBottom:16 }}>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>
                Proof — top trades ({detail.proof_trades.length})
              </div>
              <div style={{ background:'#373f4d', borderRadius:8, overflow:'hidden' }}>
                <div style={{ display:'grid', gridTemplateColumns:'auto 1fr auto auto auto auto', gap:8, padding:'7px 10px', fontSize:9, color:'#555', textTransform:'uppercase', borderBottom:'1px solid #4f596b' }}>
                  <span>Dir</span><span>Symbol</span><span style={{textAlign:'right'}}>Vol</span><span style={{textAlign:'right'}}>Open→Close</span><span style={{textAlign:'right'}}>P&L</span><span style={{textAlign:'right'}}>Time</span>
                </div>
                <div style={{ maxHeight:260, overflowY:'auto' }}>
                  {detail.proof_trades.map((t:any, i:number) => (
                    <div key={i} style={{ display:'grid', gridTemplateColumns:'auto 1fr auto auto auto auto', gap:8, padding:'6px 10px', fontSize:11, borderBottom:'1px solid #373f4d', alignItems:'center' }}>
                      <span style={{ width:34, textAlign:'center', fontSize:9, fontWeight:700, padding:'1px 0', borderRadius:4, background: t.direction==='buy'?'rgba(0,229,160,0.15)':'rgba(255,93,108,0.15)', color: t.direction==='buy'?'#00e5a0':'#ff5d6c' }}>
                        {t.direction==='buy'?'BUY':'SELL'}
                      </span>
                      <span style={{ color:'#ccc' }}>{t.symbol}<span style={{ color:'#555', fontSize:9 }}> #{t.login}</span></span>
                      <span style={{ textAlign:'right', color:'#aaa' }}>{t.volume.toFixed(2)}</span>
                      <span style={{ textAlign:'right', color:'#777', fontSize:10 }}>{t.open_price?t.open_price.toFixed(2):'—'}→{t.close_price?t.close_price.toFixed(2):'—'}</span>
                      <span style={{ textAlign:'right', fontWeight:600, color: t.profit>=0?'#00e5a0':'#ff5d6c' }}>${t.profit.toFixed(0)}</span>
                      <span style={{ textAlign:'right', color:'#555', fontSize:9 }}>{(t.time||'').slice(5)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Linked accounts */}
          {detail?.accounts?.length > 0 && (
            <div style={{ marginBottom:16 }}>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Linked accounts</div>
              {detail.accounts.map((a:any, i:number) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', background:'#373f4d', borderRadius:8, marginBottom:6 }}>
                  <div style={{ width:8, height:8, borderRadius:'50%', background: i===0?'#00e5a0':'#00aaff', flexShrink:0 }} />
                  <span style={{ fontFamily:'monospace', fontSize:11, color:'#00aaff' }}>#{a.login}</span>
                  <span style={{ flex:1, fontSize:12 }}>{a.name}</span>
                  {a.credit > 0 && <span style={{ fontSize:9, padding:'1px 6px', borderRadius:4, background:'rgba(255,170,0,0.15)', color:'#ffaa00' }}>bonus ${(a.credit||0).toLocaleString()}</span>}
                  {a.is_islamic && <span style={{ fontSize:9, padding:'1px 6px', borderRadius:4, background:'rgba(0,170,255,0.15)', color:'#00aaff' }}>swap-free</span>}
                  <span style={{ fontSize:11, color:'#555' }}>{a.country}</span>
                  <span style={{ fontSize:12, color:'#00e5a0', fontWeight:600 }}>${(a.balance||0).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}

          {/* How accounts are connected */}
          {detail?.connections?.length > 0 && (
            <div style={{ marginBottom:16 }}>
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>How they're connected</div>
              {detail.connections.map((cx:any, i:number) => {
                const strong = ['cid','ip','mqid'].includes(cx.reason);
                const labels:any = { cid:'Same device (CID)', ip:'Same IP address', mqid:'Same MetaQuotes ID', family:'Family link', ib:'Same IB' };
                return (
                  <div key={i} style={{ display:'flex', alignItems:'center', gap:8, padding:'7px 10px', background:'#373f4d', borderRadius:8, marginBottom:5, fontSize:11 }}>
                    <span style={{ fontFamily:'monospace', color:'#00aaff' }}>#{cx.login_a}</span>
                    <span style={{ color:'#555' }}>↔</span>
                    <span style={{ fontFamily:'monospace', color:'#00aaff' }}>#{cx.login_b}</span>
                    <span style={{ flex:1 }} />
                    <span style={{ fontSize:9, padding:'2px 8px', borderRadius:4,
                        background: strong?'rgba(255,93,108,0.15)':'rgba(120,120,120,0.15)',
                        color: strong?'#ff5d6c':'#999', fontWeight:600 }}>
                      {labels[cx.reason] || cx.reason}
                    </span>
                    {cx.value && cx.value!=='account' && <span style={{ fontSize:10, color:'#777', fontFamily:'monospace' }}>{cx.value}</span>}
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ marginBottom:16 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Network score breakdown</div>
            <div style={{ background:'#373f4d', borderRadius:8, padding:12 }}>
              {[['📱 Same device (CID)', 50, '#ff4d4d'], ['🌐 Same IP address', 35, '#00aaff'], ['👤 Same name', 30, '#ffaa00'], ['✉️ Same email', 25, '#cc88ff'], ['🤝 Same IB/agent', 15, '#00e5a0']].map(([label, pts, cl])=>(
                <div key={label as string} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'5px 0', borderBottom:'1px solid #4f596b', fontSize:11 }}>
                  <span style={{ color:'#888' }}>{label}</span>
                  <span style={{ color:cl as string, fontWeight:600 }}>+{pts} pts</span>
                </div>
              ))}
              <div style={{ display:'flex', justifyContent:'space-between', padding:'8px 0 0', fontSize:13, fontWeight:700 }}>
                <span>Total network score</span>
                <span style={{ color }}>{c.network_score} / 100</span>
              </div>
            </div>
          </div>

          {/* Financial */}
          <div style={{ marginBottom:16 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Financial impact</div>
            <div style={{ background:'#373f4d', borderRadius:8, padding:12 }}>
              {[['Total deposits', `$${(c.total_deposits||0).toLocaleString()}`, '#00e5a0'], ['Exposure / extraction', `$${(c.exposure||0).toLocaleString()}`, '#ff4d4d']].map(([k,v,cl])=>(
                <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'5px 0', borderBottom:'1px solid #4f596b', fontSize:12 }}>
                  <span style={{ color:'#555' }}>{k}</span>
                  <span style={{ color:cl as string, fontWeight:600 }}>{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Note */}
          <div style={{ marginBottom:16 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:6 }}>Review note</div>
            <textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="Add compliance note..."
              rows={2} style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#e0e0e0', fontSize:12, outline:'none', resize:'none', fontFamily:'inherit', boxSizing:'border-box' as any }} />
          </div>
        </div>

        {/* Actions */}
        <div style={{ padding:'12px 16px', borderTop:'1px solid #4f596b', display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, flexShrink:0 }}>
          {c.severity === 'critical' && (
            <button onClick={()=>doAction('freeze')} disabled={loading}
              style={{ padding:10, background:'#ff4d4d', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
              🔒 Freeze accounts
            </button>
          )}
          <button onClick={()=>doAction('hold_wd')} disabled={loading}
            style={{ padding:10, background:'#ffaa00', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            ⏸ Hold withdrawals
          </button>
          <button onClick={()=>doAction('review')} disabled={loading}
            style={{ padding:10, background:'#00e5a0', border:'none', borderRadius:8, color:'#000', fontWeight:700, cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            ✅ Mark reviewed
          </button>
          <button onClick={()=>doAction('clear')} disabled={loading}
            style={{ padding:10, background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#888', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            ✓ Clear / False +
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AbuseDetection() {
  const [stats, setStats]         = useState<any>(null);
  const [cases, setCases]         = useState<any[]>([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [tab, setTab]             = useState('bonus');
  const [sevFilter, setSevFilter] = useState('');
  const [statusFilter, setStatus] = useState('');
  const [search, setSearch]       = useState('');
  const [loading, setLoading]     = useState(false);
  const [running, setRunning]     = useState(false);
  const [selected, setSelected]   = useState<any>(null);

  const loadStats = useCallback(() => {
    const systemTabs = ['bonus','swap','toxic'];
    const p = new URLSearchParams();
    if (tab !== 'all' && systemTabs.includes(tab)) p.set('system', tab);
    else if (tab !== 'all' && !systemTabs.includes(tab)) p.set('abuse_type', tab);
    if (sevFilter) p.set('severity', sevFilter);
    apiGet(`/abuse/stats?${p}`).then(setStats).catch(()=>{});
  }, [tab, sevFilter]);

  const loadCases = useCallback(async () => {
    setLoading(true);
    try {
      const systemTabs = ['bonus','swap','toxic'];
      const p = new URLSearchParams({
        page: String(page), page_size: '50',
        ...(sevFilter && { severity: sevFilter }),
        ...(tab !== 'all' && !systemTabs.includes(tab) && { abuse_type: tab }),
        ...(systemTabs.includes(tab) && { system: tab }),
        ...(statusFilter && { status: statusFilter }),
        ...(search && { search }),
      });
      const data = await apiGet(`/abuse/cases?${p}`);
      setCases(data.cases || []);
      setTotal(data.total || 0);
    } catch(e) { console.error(e); }
    setLoading(false);
  }, [page, tab, sevFilter, statusFilter, search]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { loadCases(); }, [loadCases]);

  const runDetection = async () => {
    setRunning(true);
    try {
      await apiPost('/abuse/run-detection', {});
      setTimeout(() => { loadStats(); loadCases(); setRunning(false); }, 5000);
    } catch(e) { setRunning(false); }
  };

  const TABS = [
    ['bonus','🎁 Bonus Hedge'],
    ['swap','💱 Swap Abuse'],
    ['toxic','☢️ Toxic Flow'],
    ['bonus_hedge_l1','Bonus Classic'],
    ['bonus_hedge_l2','Bonus Split'],
    ['bonus_eer','Double & Dash'],
    ['bonus_farm','Bonus Farm'],
    ['swap_profitable_hold','Profit Hold'],
    ['swap_consecutive_overnight','Consec. Night'],
    ['swap_symbol_exclusivity','Exclusivity'],
    ['swap_coordinated_farm','Swap Farm'],
    ['night_latency_arb','Night Latency'],
    ['night_exotic_concentration','Night Conc.'],
    ['toxic_latency_arb','Latency Arb'],
    ['midnight_exotic_arb','Midnight Arb'],
    ['midnight_exotic_hedge','Midnight Hedge'],
  ];

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0, background:'#20252f' }}>

      {/* KPI bar */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr) repeat(3,1fr)', gap:6, padding:'8px 14px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
        {[
          { label:'Total cases',   value: stats?.total||0,    color:'#e0e0e0' },
          { label:'🎁 Bonus',        value: stats?.bonus_cases||0, color:'#ffaa00' },
          { label:'💱 Swap',         value: stats?.swap_cases||0,  color:'#cc88ff' },
          { label:'☢️ Toxic',        value: stats?.toxic_cases||0, color:'#ff4d4d' },
          { label:'🔴 Critical',   value: stats?.critical||0, color:'#ff4d4d' },
          { label:'🟠 High',       value: stats?.high||0,     color:'#ffaa00' },
          { label:'🟡 Medium',     value: stats?.medium||0,   color:'#ffee00' },
          { label:'Pending',       value: stats?.pending||0,  color:'#ff4d4d' },
          { label:'Frozen',        value: stats?.frozen||0,   color:'#ff4d4d' },
          { label:'Resolved',      value: stats?.resolved||0, color:'#00e5a0' },
        ].map((k,i) => (
          <div key={i} style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:8, padding:'8px 12px' }}>
            <div style={{ fontSize:9, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:3 }}>{k.label}</div>
            <div style={{ fontSize:20, fontWeight:700, color:k.color }}>{k.value.toLocaleString()}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:4, padding:'6px 14px', background:'#262c36', borderBottom:'1px solid #373f4d', overflowX:'auto', flexShrink:0 }}>
        {TABS.map(([k,l])=>(
          <button key={k} onClick={()=>{ setTab(k); setPage(1); }}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${tab===k?'#00e5a0':'#626d80'}`, background:tab===k?'rgba(0,229,160,0.08)':'transparent', color:tab===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
            {l}
          </button>
        ))}
        <button onClick={runDetection} disabled={running}
          style={{ marginLeft:'auto', padding:'4px 16px', borderRadius:6, border:'1px solid #626d80', background:running?'#626d80':'rgba(0,229,160,0.1)', color:running?'#555':'#00e5a0', cursor:running?'default':'pointer', fontSize:11, fontWeight:600, whiteSpace:'nowrap', fontFamily:'inherit' }}>
          {running ? '⏳ Running...' : '⚡ Run Detection'}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display:'flex', gap:8, padding:'6px 14px', background:'#2c333e', borderBottom:'1px solid #373f4d', flexShrink:0, flexWrap:'wrap', alignItems:'center' }}>
        <input value={search} onChange={e=>{ setSearch(e.target.value); setPage(1); }} placeholder="Search login, symbol..."
          style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11, width:200, outline:'none' }} />
        {['critical','high','medium'].map(s=>(
          <button key={s} onClick={()=>setSevFilter(sevFilter===s?'':s)}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${sevFilter===s?SEV_COLOR[s]:(SEV_COLOR[s]+'44')}`, background:sevFilter===s?SEV_BG[s]:'transparent', color:SEV_COLOR[s], cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
            {SEV_ICON[s]} {s.charAt(0).toUpperCase()+s.slice(1)}
          </button>
        ))}
        <select value={statusFilter} onChange={e=>{ setStatus(e.target.value); setPage(1); }}
          style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#888', fontSize:11 }}>
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="frozen">Frozen</option>
          <option value="hold_wd">Hold W/D</option>
          <option value="reviewing">Reviewing</option>
          <option value="resolved">Resolved</option>
        </select>
        <span style={{ marginLeft:'auto', fontSize:11, color:'#555' }}>{total.toLocaleString()} cases</span>
      </div>

      {/* Table */}
      <div style={{ flex:1, overflow:'auto', minHeight:0 }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ background:'#262c36', position:'sticky', top:0, zIndex:5 }}>
              {['Flag','Type','Accounts','Symbol','Network','Risk','Confidence','Deposits','Exposure','Detected','Status','Actions'].map(h=>(
                <th key={h} style={{ padding:'8px 10px', textAlign:'left', color:'#555', fontWeight:500, fontSize:10, borderBottom:'1px solid #373f4d', whiteSpace:'nowrap', textTransform:'uppercase', letterSpacing:.5 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={12} style={{ padding:40, textAlign:'center', color:'#555' }}>Loading...</td></tr>
            ) : cases.length === 0 ? (
              <tr><td colSpan={12} style={{ padding:40, textAlign:'center', color:'#555' }}>
                No cases found. Click "Run Detection" to scan for abuse patterns.
              </td></tr>
            ) : cases.map((c:any) => {
              const color = SEV_COLOR[c.severity] || '#888';
              return (
                <tr key={c.id} onClick={()=>setSelected(c)} style={{ borderBottom:'1px solid #262c36', cursor:'pointer' }}
                  onMouseEnter={e=>(e.currentTarget.style.background='#2c333e')}
                  onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                  <td style={{ padding:'8px 10px' }}>
                    <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:SEV_BG[c.severity], color, fontWeight:700, whiteSpace:'nowrap' }}>
                      {SEV_ICON[c.severity]} {c.severity}
                    </span>
                  </td>
                  <td style={{ padding:'8px 10px' }}>
                    <div style={{ fontWeight:600, fontSize:12 }}>{ABUSE_LABELS[c.abuse_type]||c.abuse_type}</div>
                  </td>
                  <td style={{ padding:'8px 10px' }}>
                    <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
                      {(() => {
                        const al = Array.isArray(c.all_logins)
                          ? c.all_logins
                          : (typeof c.all_logins === 'string' && c.all_logins
                              ? c.all_logins.split(',').map((x:string)=>x.trim()).filter(Boolean)
                              : [c.login_a]);
                        return (<>
                          {al.slice(0,3).map((l:any,i:number)=>(
                            <span key={i} style={{ fontSize:10, padding:'1px 6px', borderRadius:99, background:'rgba(0,170,255,0.12)', color:'#00aaff', fontFamily:'monospace' }}>#{l}</span>
                          ))}
                          {al.length > 3 && <span style={{ fontSize:10, color:'#555' }}>+{al.length-3} more</span>}
                        </>);
                      })()}
                    </div>
                  </td>
                  <td style={{ padding:'8px 10px', fontWeight:600, color:c.symbol?'#fff':'#555' }}>{c.symbol||'—'}</td>
                  <td style={{ padding:'8px 10px' }}><NetworkRing score={c.network_score||0} /></td>
                  <td style={{ padding:'8px 10px', minWidth:80 }}><RiskBar value={c.risk_score||0} color={color} /></td>
                  <td style={{ padding:'8px 10px', color: c.confidence>=80?'#00e5a0':c.confidence>=60?'#ffaa00':'#555', fontWeight:600 }}>{c.confidence}%</td>
                  <td style={{ padding:'8px 10px', color:'#00e5a0', fontWeight:600 }}>${(c.total_deposits||0).toLocaleString()}</td>
                  <td style={{ padding:'8px 10px', color:color, fontWeight:600 }}>${(c.exposure||0).toLocaleString()}</td>
                  <td style={{ padding:'8px 10px', color:'#555', fontSize:11, whiteSpace:'nowrap' }}>
                    {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td style={{ padding:'8px 10px' }}>
                    <span style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background:'#373f4d', color:STATUS_COLOR[c.status]||'#555' }}>{c.status}</span>
                  </td>
                  <td style={{ padding:'8px 10px' }} onClick={e=>e.stopPropagation()}>
                    <div style={{ display:'flex', gap:4 }}>
                      {c.severity==='critical' && (
                        <button onClick={()=>setSelected(c)}
                          style={{ padding:'3px 8px', background:'rgba(255,77,77,0.1)', border:'1px solid rgba(255,77,77,0.3)', borderRadius:5, color:'#ff4d4d', cursor:'pointer', fontSize:10 }}>Freeze</button>
                      )}
                      <button onClick={()=>setSelected(c)}
                        style={{ padding:'3px 8px', background:'rgba(0,170,255,0.1)', border:'1px solid rgba(0,170,255,0.3)', borderRadius:5, color:'#00aaff', cursor:'pointer', fontSize:10 }}>Review</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {total > 50 && (
          <div style={{ display:'flex', justifyContent:'center', gap:8, padding:'12px' }}>
            <button onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={page===1}
              style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:page===1?'#626d80':'#888', cursor:page===1?'default':'pointer', fontSize:12 }}>← Prev</button>
            <span style={{ padding:'5px 10px', color:'#555', fontSize:12 }}>Page {page} · {total} cases</span>
            <button onClick={()=>setPage(p=>p+1)} disabled={cases.length<50}
              style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:cases.length<50?'#626d80':'#00e5a0', cursor:cases.length<50?'default':'pointer', fontSize:12 }}>Next →</button>
          </div>
        )}
      </div>

      {selected && <CaseDetail case={selected} onClose={()=>setSelected(null)} onAction={()=>{ loadStats(); loadCases(); }} />}
    </div>
  );
}

