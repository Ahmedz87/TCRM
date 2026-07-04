import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, placeCall } from './api';
import { CT, Pager } from './crmTable';

const API = '/api';

const statusColor = (s: string) => {
  if (s === 'active')    return { bg: 'rgba(0,229,160,0.1)',  text: '#00e5a0' };
  if (s === 'pending')   return { bg: 'rgba(255,170,0,0.1)',  text: '#ffaa00' };
  if (s === 'suspended') return { bg: 'rgba(255,77,77,0.1)',  text: '#ff4d4d' };
  return { bg: 'rgba(136,136,136,0.1)', text: '#888' };
};

const networkColors: any = {
  green:  { bg: 'rgba(0,229,160,0.12)',  text: '#00e5a0' },
  yellow: { bg: 'rgba(255,200,0,0.12)',  text: '#ffc800' },
  orange: { bg: 'rgba(255,140,0,0.12)',  text: '#ff8c00' },
  red:    { bg: 'rgba(255,77,77,0.12)',  text: '#ff4d4d' },
};

const ACCOUNT_TYPES = ['all','live','demo','islamic','managed'];
const LEVERAGE_OPTIONS = ['all','1:1','1:10','1:50','1:100','1:200','1:500'];

// ── ACCOUNT DETAIL PAGE ──────────────────────────────────────────────────
function AccountDetail({ account, onBack, lang }: any) {
  const [tab, setTab] = useState('overview');
  const [accountTab, setAccountTab] = useState('open');
  const [detail, setDetail] = useState<any>(account);
  const [loading, setLoading] = useState(false);
  const isAr = lang === 'ar';

  useEffect(() => {
    const fetchDetail = async () => {
      setLoading(true);
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API}/trading-accounts/${account.login}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        setDetail({ ...account, ...data });
      } catch { setDetail(account); }
      setLoading(false);
    };
    fetchDetail();
  }, [account.login]);

  const tabs = [
    { key: 'overview',    label: 'Overview' },
    { key: 'deposits',    label: 'Deposits' },
    { key: 'withdrawals', label: 'Withdrawals' },
    { key: 'internal',    label: 'Internal transfers' },
    { key: 'positions',   label: 'Open positions' },
    { key: 'history',     label: 'Trade history' },
    { key: 'bonuses',     label: 'Bonuses' },
    { key: 'network',     label: 'Network / CID / IP' },
  ];

  const mockDeposits = detail.deposits_list || [];
  const mockWithdrawals = detail.withdrawals_list || [];
  if (!detail) return <div style={{padding:40,textAlign:'center',color:'#555'}}>Loading...</div>;
  const mockInternal = detail.internal_list || [];
  const mockOpen = (detail.open_positions||[]).map((p:any) => ({ ticket:p.ticket, symbol:p.symbol, type:p.direction||p.type||'buy', volume:p.volume, open_price:p.open_price, current:p.current||p.open_price, pnl:p.pnl||p.profit||0, profit:p.pnl||p.profit||0, swap:p.swap||0, commission:p.commission||0, open_time:p.open_time||p.date, open_timestamp:p.open_timestamp||0 }));
  const mockHistory = (detail.trade_history||[]).map((p:any) => {
    const dur = p.duration_secs || 0;
    const durStr = dur > 0 ? (dur >= 3600 ? Math.floor(dur/3600)+'h '+(Math.floor((dur%3600)/60))+'m' : Math.floor(dur/60)+'m '+( dur%60)+'s') : '—';
    return { 
      ticket: p.ticket, symbol: p.symbol, type: p.direction||'buy', 
      volume: p.volume, open_price: p.open_price, close_price: p.close_price||p.open_price, 
      profit: p.profit, commission: p.commission||0, swap: p.swap||0,
      open_time: p.open_time||'', close_time: p.close_time||'', 
      open_timestamp: p.open_timestamp, close_timestamp: p.close_timestamp,
      duration_secs: p.duration_secs||0, duration: durStr 
    };
  });
  const mockBonuses = (detail.bonuses_list||[]).map((b:any) => ({ type: b.tx_type==='bonus_deposit'?'Deposit bonus':'Withdrawal bonus', amount:b.amount, date:b.date, comment:b.comment||'' }));
  const mockNetwork = { ip: detail.last_ip||account.last_ip||'—', cid: detail.cid||account.cid||'—', mqid: String(detail.mqid||account.mqid||'—'), connections: detail.network_connections||[] };

  return (
    <div style={{ position:'fixed', inset:0, background:'var(--bg-main,#20252f)', zIndex:500, overflow:'hidden', color:'var(--text,#fff)', fontFamily:'sans-serif', display:'flex', flexDirection:'column' }}>

      {/* Topbar */}
      <div style={{ display:'flex', alignItems:'center', gap:12, padding:'12px 24px', background:'var(--bg-card,#2c333e)', borderBottom:'1px solid var(--border,#4f596b)', position:'sticky', top:0, zIndex:10, flexWrap:'wrap' }}>
        <button onClick={onBack} style={{ background:'transparent', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text2,#888)', padding:'6px 14px', cursor:'pointer', fontSize:13 }}>← Back</button>
        <div style={{ width:40, height:40, borderRadius:12, background:'linear-gradient(135deg,#0066ff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:16, flexShrink:0 }}>
          {(account.name||'?')[0]}
        </div>
        <div>
          <div style={{ fontSize:16, fontWeight:500 }}>{account.name}</div>
          <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>
            #{account.login} · {account.group_name} · 1:{account.leverage}
          </div>
        </div>
        <div style={{ marginLeft:'auto', display:'flex', gap:8, alignItems:'center', flexWrap:'wrap' }}>
          <span style={{ fontSize:11, padding:'4px 10px', borderRadius:99, ...statusColor(account.is_active?'active':'suspended') }}>
            {account.is_active ? 'Active' : 'Suspended'}
          </span>
          <span style={{ fontSize:11, padding:'4px 10px', borderRadius:99, background:'rgba(0,102,255,0.1)', color:'#4d9fff' }}>
            {account.account_type || 'live'}
          </span>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(130px,1fr))', gap:10, padding:'16px 24px 0' }}>
        {[
          { label:'Balance',     value:`$${(account.balance||0).toLocaleString()}`,      color:'var(--text,#fff)', icon:'💰' },
          { label:'Equity',      value:`$${(account.equity||account.balance||0).toLocaleString()}`,        color: (account.equity||account.balance) < account.balance ? '#ff4d4d':'#00e5a0', icon:'📈' },
          { label:'Credit',      value:`$${(account.credit||0).toLocaleString()}`,        color:'#ffaa00', icon:'🎁' },
          { label:'Margin level',value: account.margin_level ? `${account.margin_level.toFixed(0)}%`:'—', color: (account.margin_level||0)<80?'#ff4d4d':'#00e5a0', icon:'⚖️' },
          { label:'Total dep.',  value:`$${(account.total_deposits||0).toLocaleString()}`, color:'#00e5a0', icon:'⬆️' },
          { label:'Total with.', value:`$${(account.total_withdrawals||0).toLocaleString()}`, color:'#ff8888', icon:'⬇️' },
          { label:'Volume (lots)',value:(account.total_volume||0).toLocaleString(), color:'#0066ff', icon:'📊' },
          { label:'Trades',      value:(account.total_trades||0).toLocaleString(), color:'#9966ff', icon:'🔄' },
        ].map((s,i) => (
          <div key={i} style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:'14px 16px' }}>
            <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6, display:'flex', alignItems:'center', gap:5 }}><span>{s.icon}</span>{s.label}</div>
            <div style={{ fontSize:18, fontWeight:500, color:s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:2, padding:'14px 24px 0', borderBottom:'1px solid var(--border,#4f596b)', marginTop:14, overflowX:'auto' }}>
        {tabs.map(t => (
          <div key={t.key} onClick={() => setTab(t.key)}
            style={{ padding:'8px 16px', cursor:'pointer', fontSize:13, fontWeight:tab===t.key?500:400, color:tab===t.key?'var(--text,#fff)':'var(--text3,#555)', borderBottom:tab===t.key?'2px solid var(--accent,#00e5a0)':'2px solid transparent', marginBottom:-1, whiteSpace:'nowrap', borderRadius:'6px 6px 0 0', background:tab===t.key?'var(--bg-input,#373f4d)':'transparent', transition:'all 0.15s' }}>
            {t.label}
          </div>
        ))}
      </div>

      <div style={{ padding:'20px 24px', paddingBottom:40, flex:1, overflowY:'auto', minHeight:0 }}>

        {/* OVERVIEW */}
        {tab === 'overview' && (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
            <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16 }}>
              <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:10, textTransform:'uppercase', letterSpacing:1 }}>Account info</div>
              {[
                ['Login',        `#${account.login}`],
                ['Name',         account.name],
                ['Phone',        account.phone || '—'],
                ['Email',        account.email || '—'],
                ['Group',        account.group_name],
                ['Leverage',     `1:${account.leverage}`],
                ['Account type', account.account_type || 'live'],
                ['Agent/IB',     account.agent || '—'],
                ['Registered',   account.reg_date || '—'],
              ].map(([k,v]) => (
                <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:'1px solid var(--border,#373f4d)', fontSize:12 }}>
                  <span style={{ color:'var(--text3,#555)' }}>{k}</span>
                  <span style={{ fontWeight:500, maxWidth:200, textAlign:'right', wordBreak:'break-all' }}>{v as string}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16, marginBottom:12 }}>
                <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:10, textTransform:'uppercase', letterSpacing:1 }}>Identity</div>
                {[
                  ['CID',      account.cid  || mockNetwork.cid],
                  ['IP address',account.last_ip || mockNetwork.ip],
                  ['MQID',     account.mqid || mockNetwork.mqid],
                  ['Client',   account.client_name || '—'],
                  ['IB',       account.ib_name || '—'],
                  ['Sales agent', account.agent_name || '—'],
                  ['Credit at',  account.credit_at ? new Date(account.credit_at).toLocaleDateString() : '—'],
                  ['Country',  account.country || '—'],
                  ['City',     account.city || '—'],
                ].map(([k,v]) => (
                  <div key={k as string} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:'1px solid var(--border,#373f4d)', fontSize:12 }}>
                    <span style={{ color:'var(--text3,#555)' }}>{k}</span>
                    <span style={{ fontWeight:500, fontFamily: ['CID','IP address','MQID'].includes(k as string)?'monospace':'inherit', fontSize: ['CID','IP address','MQID'].includes(k as string)?11:12 }}>{v as string}</span>
                  </div>
                ))}
              </div>
              {/* Network summary */}
              <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16 }}>
                <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:10, textTransform:'uppercase', letterSpacing:1 }}>Network connections</div>
                {mockNetwork.connections.length === 0 ? (
                  <div style={{ fontSize:12, color:'var(--text3,#555)' }}>No connections detected</div>
                ) : mockNetwork.connections.map((c:any,i:number) => (
                  <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 0', borderBottom:'1px solid var(--border,#373f4d)' }}>
                    <div style={{ width:30, height:30, borderRadius:8, background:'var(--bg-input,#373f4d)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:12 }}>{c.name[0]}</div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:13, fontWeight:500, color:'var(--accent,#00e5a0)', cursor:'pointer' }}>{c.name}</div>
                      <div style={{ fontSize:10, color:'var(--text3,#555)' }}>#{c.login}</div>
                    </div>
                    <div style={{ display:'flex', gap:4 }}>
                      {c.reasons.map((r:any,ri:number) => (
                        <span key={ri} style={{ fontSize:9, padding:'2px 6px', borderRadius:4, background:'rgba(0,102,255,0.15)', color:'#4d9fff' }}>{r}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* DEPOSITS */}
        {tab === 'deposits' && (
          <TxTable rows={mockDeposits} type="deposit" />
        )}

        {/* WITHDRAWALS */}
        {tab === 'withdrawals' && (
          <TxTable rows={mockWithdrawals} type="withdrawal" />
        )}

        {/* INTERNAL TRANSFERS */}
        {tab === 'internal' && (
          <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
              <thead>
                <tr style={{ background:'var(--bg-input,#373f4d)' }}>
                  {['Date','Type','Amount','From','To','Reference'].map(h => (
                    <th key={h} style={{ padding:'10px 14px', textAlign:'left', color:'var(--text3,#555)', fontWeight:500, borderBottom:'1px solid var(--border,#4f596b)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mockInternal.map((d:any,i:number) => (
                  <tr key={i} style={{ borderBottom:'1px solid var(--border,#373f4d)' }}>
                    <td style={{ padding:'10px 14px', color:'var(--text2,#888)' }}>{d.date}</td>
                    <td style={{ padding:'10px 14px' }}><span style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background: (d.type||'').includes('in')?'rgba(0,229,160,0.1)':'rgba(255,136,136,0.1)', color: (d.type||'').includes('in')?'#00e5a0':'#ff8888' }}>{d.type}</span></td>
                    <td style={{ padding:'10px 14px', color: (d.type||'').includes('in')?'#00e5a0':'#ff8888', fontWeight:500 }}>${d.amount.toLocaleString()}</td>
                    <td style={{ padding:'10px 14px', color:'var(--text2,#888)', fontFamily:'monospace', fontSize:11 }}>#{d.from}</td>
                    <td style={{ padding:'10px 14px', color:'var(--text2,#888)', fontFamily:'monospace', fontSize:11 }}>#{d.to}</td>
                    <td style={{ padding:'10px 14px', color:'var(--text3,#555)', fontFamily:'monospace', fontSize:11 }}>{d.ref}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* OPEN POSITIONS & HISTORY */}
        {(tab === 'positions' || tab === 'history') && (
          <div>
            <div style={{ display:'flex', gap:6, marginBottom:14 }}>
              {[['open','Open positions'],['closed','Closed positions'],['history','Trade history']].map(([k,l]) => (
                <button key={k} onClick={() => setAccountTab(k)}
                  style={{ padding:'6px 14px', borderRadius:7, border:`1px solid ${accountTab===k?'var(--accent,#00e5a0)':'var(--border2,#626d80)'}`, background:accountTab===k?'rgba(0,229,160,0.1)':'transparent', color:accountTab===k?'#00e5a0':'var(--text2,#888)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                  {l}
                </button>
              ))}
            </div>
            <TradesTable rows={accountTab==='open' ? mockOpen : mockHistory} type={accountTab==='open' ? 'open' : 'history'} />
          </div>
        )}

        {/* BONUSES */}
        {tab === 'bonuses' && (
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {mockBonuses.length === 0 ? (
              <div style={{ padding:30, textAlign:'center', color:'var(--text3,#555)' }}>No bonus records found</div>
            ) : mockBonuses.map((b:any,i:number) => (
              <div key={i} style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                  <div>
                    <div style={{ fontSize:14, fontWeight:500 }}>{b.type}</div>
                    <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:3 }}>Expires: {b.expires}</div>
                  </div>
                  <div style={{ textAlign:'right' }}>
                    <div style={{ fontSize:18, fontWeight:500, color:'#ffaa00' }}>${b.amount}</div>
                    <span style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background: b.status==='completed'?'rgba(0,229,160,0.1)':'rgba(255,170,0,0.1)', color: b.status==='completed'?'#00e5a0':'#ffaa00' }}>{b.status}</span>
                  </div>
                </div>
                <div style={{ height:6, background:'var(--bg-input,#373f4d)', borderRadius:3, overflow:'hidden', marginBottom:6 }}>
                  <div style={{ height:'100%', borderRadius:3, background:'#00e5a0', width:`${(b.lots_done/b.lots_req)*100}%`, transition:'width 0.5s' }}></div>
                </div>
                <div style={{ fontSize:11, color:'var(--text3,#555)' }}>{b.lots_done} / {b.lots_req} lots traded ({((b.lots_done/b.lots_req)*100).toFixed(0)}%)</div>
              </div>
            ))}
          </div>
        )}

        {/* NETWORK / CID / IP */}
        {tab === 'network' && (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
            {/* Identifiers */}
            <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16 }}>
              <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:12, textTransform:'uppercase', letterSpacing:1 }}>All identifiers used</div>
              {[
                { type:'IP Address', values: detail.all_ips?.length ? detail.all_ips : [mockNetwork.ip],   color:'#0066ff', icon:'🌐' },
                { type:'CID',        values: detail.all_cids?.length ? detail.all_cids : [mockNetwork.cid],  color:'#9966ff', icon:'🪪' },
                { type:'MQID',       values: detail.all_mqids?.length ? detail.all_mqids.map(String) : [String(mockNetwork.mqid)], color:'#ffaa00', icon:'🔑' },
              ].map((id,i) => (
                <div key={i} style={{ padding:'10px 12px', borderRadius:8, border:'1px solid var(--border,#4f596b)', marginBottom:8, background:'var(--bg-input,#373f4d)' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:6 }}>
                    <span style={{ fontSize:16 }}>{id.icon}</span>
                    <div style={{ fontSize:10, color:'var(--text3,#555)' }}>{id.type}</div>
                    {id.values.length > 1 && <span style={{ fontSize:9, color:'#ff4d4d', marginLeft:'auto' }}>⚠ {id.values.length} used</span>}
                    {id.values.length === 1 && <span style={{ fontSize:9, color:'#00e5a0', marginLeft:'auto' }}>✓ Unique</span>}
                  </div>
                  {id.values.map((v:string,vi:number) => (
                    <div key={vi} style={{ fontSize:12, fontFamily:'monospace', color:id.color, fontWeight:500, padding:'2px 0' }}>{v||'—'}</div>
                  ))}
                </div>
              ))}
            </div>

            {/* Connected accounts */}
            <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:12, padding:16 }}>
              <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:12, textTransform:'uppercase', letterSpacing:1 }}>
                Connected accounts ({mockNetwork.connections.length})
              </div>
              {mockNetwork.connections.length === 0 ? (
                <div style={{ fontSize:12, color:'var(--text3,#555)', textAlign:'center', padding:20 }}>No connections detected — clean account</div>
              ) : mockNetwork.connections.map((c:any,i:number) => (
                <div key={i} style={{ padding:'12px', borderRadius:10, border:'1px solid var(--border,#4f596b)', marginBottom:8, background:'var(--bg-input,#373f4d)' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:8 }}>
                    <div style={{ width:32, height:32, borderRadius:8, background:'linear-gradient(135deg,#0066ff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700 }}>{c.name[0]}</div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:13, fontWeight:500, color:'var(--accent,#00e5a0)', cursor:'pointer' }}>{c.name}</div>
                      <div style={{ fontSize:10, color:'var(--text3,#555)' }}>#{c.login}</div>
                    </div>
                    <span style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background: c.risk==='high'?'rgba(255,77,77,0.1)':'rgba(255,170,0,0.1)', color: c.risk==='high'?'#ff4d4d':'#ffaa00' }}>{c.risk} risk</span>
                  </div>
                  <div style={{ display:'flex', gap:4 }}>
                    {c.reasons.map((r:any,ri:number) => (
                      <span key={ri} style={{ fontSize:10, padding:'3px 8px', borderRadius:6, background:'rgba(0,102,255,0.15)', color:'#4d9fff' }}>
                        {r === 'IP' ? '🌐 Same IP' : r === 'CID' ? '🪪 Same CID' : r === 'IB' ? '🔗 Same IB' : r}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TxTable({ rows, type }: any) {
  return (
    <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, overflow:'hidden' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
        <thead>
          <tr style={{ background:'var(--bg-input,#373f4d)' }}>
            {['Date','Amount','Method','Status','Reference'].map(h => (
              <th key={h} style={{ padding:'10px 14px', textAlign:'left', color:'var(--text3,#555)', fontWeight:500, borderBottom:'1px solid var(--border,#4f596b)' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((d: any, i: number) => (
            <tr key={i} style={{ borderBottom:'1px solid var(--border,#373f4d)' }}>
              <td style={{ padding:'10px 14px', color:'var(--text2,#888)' }}>{d.date}</td>
              <td style={{ padding:'10px 14px', color: type==='deposit'?'#00e5a0':'#ff8888', fontWeight:500 }}>${d.amount.toLocaleString()}</td>
              <td style={{ padding:'10px 14px', color:'var(--text2,#888)' }}>{d.method}</td>
              <td style={{ padding:'10px 14px' }}>
                <span style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background: d.status==='approved'?'rgba(0,229,160,0.1)':'rgba(255,170,0,0.1)', color: d.status==='approved'?'#00e5a0':'#ffaa00' }}>{d.status}</span>
              </td>
              <td style={{ padding:'10px 14px', color:'var(--text3,#555)', fontFamily:'monospace', fontSize:11 }}>{d.ref}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({ rows: rawRows, type }: any) {
  const rows = rawRows || [];
  const [sortCol, setSortCol] = React.useState('');
  const [sortDir, setSortDir] = React.useState<'asc'|'desc'>('desc');
  const isOpen = type === 'open' || type === 'positions';

  const toggle = (col: string) => {
    if (sortCol === col) setSortDir(d => d==='asc'?'desc':'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const sorted = [...rows].sort((a:any, b:any) => {
    if (!sortCol) return 0;
    const av = a[sortCol]||0, bv = b[sortCol]||0;
    return sortDir==='asc' ? (av>bv?1:-1) : (av<bv?1:-1);
  });

  // age / duration as dd hh:mm:ss
  const fmtAge = (secs: number) => {
    if (!secs || secs <= 0) return '—';
    secs = Math.floor(secs);
    const pad = (n: number) => String(n).padStart(2, '0');
    const d = Math.floor(secs / 86400);
    const h = Math.floor((secs % 86400) / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return (d > 0 ? d + 'd ' : '') + `${pad(h)}:${pad(m)}:${pad(s)}`;
  };

  // open/close datetime with seconds (hh:mm:ss)
  const fmtTime = (ts: number, date: string) => {
    if (ts && ts > 1000000) {
      const d = new Date(ts * 1000);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    }
    return date || '—';
  };
  // seconds for a trade leg from timestamp or a parseable date string
  const legSec = (ts: number, str: string) => ts && ts > 1000000 ? ts : (str ? Math.floor(Date.parse(str) / 1000) : 0);

  const fmtPrice = (n: number) => n ? n.toFixed(5).replace(/\.?0+$/, '') : '—';
  const fmtProfit = (n: number) => {
    const v = n || 0;
    return { text: (v >= 0 ? '+' : '-') + '$' + Math.abs(v).toFixed(2), color: v >= 0 ? '#00e5a0' : '#ff4d4d' };
  };

  // Totals
  const totalPnl   = rows.reduce((s:number, r:any) => s + (r.pnl || r.profit || 0), 0);
  const totalProfit = rows.reduce((s:number, r:any) => s + (r.profit || 0), 0);

  const th = (label: string, col: string) => (
    <th onClick={() => toggle(col)}
      style={{ padding:'9px 12px', textAlign:'left', color: sortCol===col?'#00e5a0':'#555', fontWeight:500, borderBottom:'1px solid #373f4d', whiteSpace:'nowrap', cursor:'pointer', fontSize:11 }}>
      {label}{sortCol===col?(sortDir==='asc'?' ↑':' ↓'):' ↕'}
    </th>
  );

  return (
    <div style={{ background:'#2c333e', border:'1px solid #4f596b', borderRadius:10, overflow:'hidden' }}>
      <div style={{ overflowX:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ background:'#373f4d', position:'sticky', top:0, zIndex:5 }}>
              {th('Ticket','ticket')}
              {th('Symbol','symbol')}
              {th('Type','type')}
              {th('Volume','volume')}
              {th('Open price','open_price')}
              {isOpen ? th('Current price','current') : th('Close price','close_price')}
              {isOpen ? th('PnL','pnl') : th('Profit','profit')}
              {!isOpen && th('Commission','commission')}
              {!isOpen && th('Swap','swap')}
              {th('Open time','open_timestamp')}
              {!isOpen && th('Close time','close_timestamp')}
              {th('Age','age')}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr><td colSpan={12} style={{ padding:30, textAlign:'center', color:'#555' }}>No records found</td></tr>
            ) : sorted.map((t: any, i: number) => {
              const pnl = isOpen ? (t.pnl || t.profit || 0) : (t.profit || 0);
              const pnlFmt = fmtProfit(pnl);
              // Age: closed = close − open; open = now − open
              const oSec = legSec(t.open_timestamp, t.open_time);
              const cSec = legSec(t.close_timestamp, t.close_time);
              const age = isOpen
                ? (oSec ? Math.floor(Date.now() / 1000) - oSec : 0)
                : (oSec && cSec ? cSec - oSec : t.duration_secs || 0);
              return (
                <tr key={i} style={{ borderBottom:'1px solid #2c333e' }}>
                  <td style={{ padding:'8px 12px', fontFamily:'monospace', color:'#666', fontSize:11 }}>{t.ticket}</td>
                  <td style={{ padding:'8px 12px', fontWeight:600 }}>{t.symbol}</td>
                  <td style={{ padding:'8px 12px' }}>
                    <span style={{ color:(t.type||'').toLowerCase()==='buy'?'#00e5a0':'#ff4d4d', fontWeight:700, fontSize:11 }}>
                      {(t.type||t.direction||'').toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding:'8px 12px', color:'#888' }}>{t.volume}</td>
                  <td style={{ padding:'8px 12px', color:'#888' }}>{fmtPrice(t.open_price)}</td>
                  <td style={{ padding:'8px 12px', color:'#888' }}>{fmtPrice(isOpen ? (t.current||t.close_price) : t.close_price)}</td>
                  <td style={{ padding:'8px 12px' }}><span style={{ color: pnlFmt.color, fontWeight:700, fontSize:13 }}>{pnlFmt.text}</span></td>
                  {!isOpen && <td style={{ padding:'8px 12px', color:'#666' }}>{t.commission ? '$'+t.commission.toFixed(2) : '—'}</td>}
                  {!isOpen && <td style={{ padding:'8px 12px', color:'#666' }}>{t.swap ? '$'+t.swap.toFixed(2) : '—'}</td>}
                  <td style={{ padding:'8px 12px', color:'#555', fontSize:11 }}>{fmtTime(t.open_timestamp, t.open_time)}</td>
                  {!isOpen && <td style={{ padding:'8px 12px', color:'#555', fontSize:11 }}>{fmtTime(t.close_timestamp, t.close_time)}</td>}
                  <td style={{ padding:'8px 12px', color: isOpen ? '#ffaa00' : '#888', fontSize:11, fontFamily:'monospace' }}>{fmtAge(age)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr style={{ background:'#373f4d', borderTop:'2px solid #626d80' }}>
              <td colSpan={isOpen ? 6 : 6} style={{ padding:'9px 12px', color:'#555', fontSize:11 }}>
                {rows.length} {isOpen ? 'open positions' : 'closed trades'}
              </td>
              <td style={{ padding:'9px 12px', fontWeight:700, color: (isOpen?totalPnl:totalProfit)>=0?'#00e5a0':'#ff4d4d', fontSize:13 }}>
                {fmtProfit(isOpen ? totalPnl : totalProfit).text}
              </td>
              {!isOpen && <td colSpan={5} style={{ padding:'9px 12px', color:'#555', fontSize:11 }}>Total</td>}
              {isOpen && <td colSpan={2} />}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}


// ── MAIN TRADING ACCOUNTS TABLE ──────────────────────────────────────────
export default function TradingAccounts({ lang }: any) {
  const isAr = lang === 'ar';
  const [accounts, setAccounts] = useState<any[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState('');
  const [sort, setSort]         = useState('balance');
  const [page, setPage]         = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [period, setPeriod]     = useState('all_time');
  const [kpis, setKpis]         = useState<any>(null);
  const [total, setTotal]       = useState(0);
  const [sortCol, setSortCol]   = useState('');
  const [sortDir, setSortDir]   = useState<'asc'|'desc'>('desc');
  const [detail, setDetail]     = useState<any>(null);
  const [settingsMenu, setSettingsMenu] = useState<any>(null);
  const [archivedTab, setArchivedTab]   = useState<'active'|'archived'>('active');
  const [filterType, setFilterType]     = useState('all');
  const [filterLeverage, setFilterLeverage] = useState('all');
  const [filterStatus, setFilterStatus]     = useState('all');
  const [showFilters, setShowFilters]       = useState(false);
  const [filterCountry, setFilterCountry]   = useState('');
  const [filterCity, setFilterCity]         = useState('');
  const [filterIB, setFilterIB]             = useState('');
  const [filterAgent, setFilterAgent]       = useState('');
  const [phoneAccount, setPhoneAccount]     = useState<any>(null);
  const [emailAccount, setEmailAccount]     = useState<any>(null);
  const [actionMenu, setActionMenu]         = useState<any>(null);
  const [actionStep, setActionStep]         = useState<'menu'|'form'>('menu');
  const [actionType, setActionType]         = useState('');
  const [actionNote, setActionNote]         = useState('');
  const [callLaterDays, setCallLaterDays]   = useState(0);
  const [callLaterHours, setCallLaterHours] = useState(0);
  const [saving, setSaving]                 = useState(false);

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), search, sort });
      if (archivedTab === 'archived') params.set('archived', 'archived');
      const data = await apiGet(`/trading-accounts?${params}`);
      setAccounts(data.accounts || []);
      setTotal(data.total || 0);
    } catch(err: any) {
      console.error('Error:', err);
      setAccounts([]);
      setTotal(0);
    }
    setLoading(false);
  }, [page, search, pageSize, sort, archivedTab]);

  useEffect(() => { fetchAccounts(); }, [fetchAccounts]);

  useEffect(() => {
    setKpis(null);
    apiGet(`/dashboard/kpis?period=${period}`)
      .then((data: any) => setKpis(data)).catch(() => {});
  }, [period]);

  const toggleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d==='asc'?'desc':'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const filtered = accounts.filter(a => {
    if (filterType !== 'all' && a.account_type !== filterType) return false;
    if (filterStatus !== 'all') {
      const isActive = a.is_active;
      if (filterStatus === 'active'    && !isActive)  return false;
      if (filterStatus === 'suspended' && isActive)   return false;
    }
    if (filterLeverage !== 'all' && `1:${a.leverage}` !== filterLeverage) return false;
    if (filterCountry && a.country !== filterCountry) return false;
    if (filterCity    && a.city    !== filterCity)    return false;
    if (filterIB      && String(a.agent) !== filterIB && a.ib_code !== filterIB) return false;
    if (filterAgent   && a.agent_name !== filterAgent) return false;
    return true;
  });

  const hasClickFilters = filterCountry || filterCity || filterIB || filterAgent;
  const clearClickFilters = () => { setFilterCountry(''); setFilterCity(''); setFilterIB(''); setFilterAgent(''); };

  const saveAction = async () => {
    if (!actionMenu) return;
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API}/clients/action`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ login: actionMenu.login, action: actionType, note: actionNote, call_later_days: callLaterDays, call_later_hours: callLaterHours })
      });
      setActionMenu(null); setActionStep('menu'); setActionNote('');
      setCallLaterDays(0); setCallLaterHours(0);
    } catch(e) { console.error(e); }
    setSaving(false);
  };

  const sorted = [...filtered].sort((a,b) => {
    const map: any = { 'Balance':'balance','Equity':'equity','Credit':'credit','Margin%':'margin_level','Volume':'total_volume','Trades':'total_trades' };
    const key = map[sortCol];
    if (!key) return 0;
    return sortDir==='asc' ? (a[key]||0)-(b[key]||0) : (b[key]||0)-(a[key]||0);
  });

  const SORTABLE = ['Balance','Equity','Credit','Margin%','Volume','Trades'];

  const SETTINGS_ACTIONS = [
    { label:'Deposit',                  icon:'💰', color:'#00e5a0' },
    { label:'Withdrawal',               icon:'💸', color:'#ff8888' },
    { label:'Transfer',                 icon:'↔️', color:'#0066ff' },
    { label:'Reset balance',            icon:'🔄', color:'#888' },
    { label:'Update balance',           icon:'✏️', color:'#ffaa00' },
    { label:'IB accounts',              icon:'🔗', color:'#ff8c00' },
    { label:'Change leverage',          icon:'⚖️', color:'#9966ff' },
    { label:'Change master password',   icon:'🔑', color:'#888' },
    { label:'Change investor password', icon:'👁',  color:'#888' },
    { label:'Switch account type',      icon:'🔀', color:'#888' },
    { label:'Switch group',             icon:'📂', color:'#888' },
    { label:'Open position',            icon:'📈', color:'#00e5a0' },
    { label:'Close position',           icon:'📉', color:'#ff4d4d' },
    { label:'Subscribe to LD',          icon:'📡', color:'#0066ff' },
    { label:'Delete',                   icon:'🗑', color:'#ff4d4d' },
  ];

  if (detail) return <AccountDetail account={detail} onBack={() => setDetail(null)} lang={lang} />;

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', direction:isAr?'rtl':'ltr', overflow:'hidden', minHeight:0 }}>

      {/* KPI bar + period selector */}
      <div style={{ background:'var(--bg-main,#262c36)', borderBottom:'1px solid var(--border,#4f596b)', flexShrink:0 }}>
        <div style={{ display:'flex', gap:4, padding:'8px 14px 0', overflowX:'auto' }}>
          {[['all_time','All time'],['today','Today'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l]) => (
            <button key={k} onClick={() => setPeriod(k)}
              style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${period===k?'#00e5a0':'#626d80'}`, background:period===k?'rgba(0,229,160,0.1)':'transparent', color:period===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
              {l}
            </button>
          ))}
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,minmax(0,1fr))', gap:8, padding:'8px 14px 10px' }}>
          {[
            { label:'Total accounts',   value: total.toLocaleString(),                                    color:'#00e5a0' },
            { label:'Total deposits',   value: '$'+((kpis?.deposits||0)/1000).toFixed(1)+'K',             color:'#00e5a0' },
            { label:'Total withdrawals',value: '$'+((kpis?.withdrawals||0)/1000).toFixed(1)+'K',          color:'#ff8888' },
            { label:'Net deposit',      value: '$'+((kpis?.net_deposit||0)/1000).toFixed(1)+'K',          color:(kpis?.net_deposit||0)>=0?'#00e5a0':'#ff4d4d' },
            { label:'Active traders',   value: (kpis?.active_traders||0).toLocaleString(),                color:'#00aaff' },
            { label:'Pending withdrawals',value:(kpis?.pending_w||0).toString(),                          color:(kpis?.pending_w||0)>0?'#ffaa00':'#555' },
            { label:'New clients',      value: (kpis?.new_clients||0).toLocaleString(),                   color:'#00aaff' },
            { label:'IB commission',    value: '$'+((kpis?.ib_comm||0)/1000).toFixed(1)+'K',              color:'#ff8c00' },
          ].map((k,i) => (
            <div key={i} style={{ background:'var(--bg-card,#2c333e)', borderRadius:10, padding:'10px 14px', border:'1px solid var(--border,#373f4d)' }}>
              <div style={{ fontSize:10, color:'var(--text3,#555)', marginBottom:4 }}>{k.label}</div>
              <div style={{ fontSize:18, fontWeight:500, color:k.color }}>{k.value}</div>
            </div>
          ))}
        </div>
      </div>      {/* Header */}
      <div style={{ background:'var(--bg-card,#2c333e)', borderBottom:'1px solid var(--border,#4f596b)', flexShrink:0 }}>
        <div style={{ display:'flex', gap:6, padding:'8px 14px 0', alignItems:'center', flexWrap:'wrap' }}>
          {([['active','Active accounts'],['archived','🗄 Archive Trading Accounts']] as [string,string][]).map(([k,l])=>(
            <button key={k} onClick={()=>{ setArchivedTab(k as any); setPage(1); }}
              style={{ padding:'6px 14px', borderRadius:8, border:`1px solid ${archivedTab===k?'#ffaa00':'var(--border2,#626d80)'}`, background:archivedTab===k?'rgba(255,170,0,0.12)':'transparent', color:archivedTab===k?'#ffaa00':'var(--text2,#888)', cursor:'pointer', fontSize:12, fontWeight:archivedTab===k?700:400, fontFamily:'inherit' }}>
              {l}
            </button>
          ))}
          {archivedTab==='archived' && <span style={{ fontSize:11, color:'var(--text3,#888)' }}>Archived from MT4/MT5 (idle · balance &lt; $1). Read-only — history, IB/sales commission &amp; loyalty preserved; clients can't deposit or transfer.</span>}
        </div>

        <div style={{ padding:'10px 14px', display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
          <div>
            <div style={{ fontSize:15, fontWeight:500 }}>{archivedTab==='archived' ? 'Archived trading accounts' : 'Trading accounts'}</div>
            <div style={{ fontSize:11, color:'var(--text3,#555)' }}>{total.toLocaleString()} accounts</div>
          </div>
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search login, name, email, group..."
            style={{ flex:1, maxWidth:280, padding:'7px 12px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:12, outline:'none' }} />
          <div style={{ display:'flex', gap:4 }}>
            {[{key:'new',label:'Newest'},{key:'balance',label:'Balance'},{key:'equity',label:'Equity'},{key:'deposit',label:'Deposits'}].map(s=>(
              <button key={s.key} onClick={()=>{setSort(s.key);setPage(1);}}
                style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${sort===s.key?'#00e5a0':'#626d80'}`,background:sort===s.key?'rgba(0,229,160,0.1)':'transparent',color:sort===s.key?'#00e5a0':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
                {s.label}
              </button>
            ))}
          </div>
          <button onClick={() => setShowFilters(v=>!v)}
            style={{ padding:'6px 12px', borderRadius:8, border:`1px solid ${showFilters?'#00e5a0':'var(--border2,#626d80)'}`, background:showFilters?'rgba(0,229,160,0.1)':'transparent', color:showFilters?'#00e5a0':'var(--text2,#888)', cursor:'pointer', fontSize:12 }}>
            ⚙ Filters
          </button>
          {hasClickFilters && (
            <div style={{ display:'flex', gap:5, flexWrap:'wrap', alignItems:'center' }}>
              {filterCountry && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,102,255,0.15)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterCountry('')}>🌍 {filterCountry} ✕</span>}
              {filterCity    && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,102,255,0.15)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterCity('')}>🏙 {filterCity} ✕</span>}
              {filterIB      && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(255,140,0,0.15)', color:'#ff8c00', cursor:'pointer' }} onClick={() => setFilterIB('')}>🔗 {filterIB} ✕</span>}
              {filterAgent   && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(153,102,255,0.15)', color:'#9966ff', cursor:'pointer' }} onClick={() => setFilterAgent('')}>👤 {filterAgent} ✕</span>}
              <span style={{ fontSize:11, color:'#ff4d4d', cursor:'pointer' }} onClick={clearClickFilters}>Clear all</span>
            </div>
          )}
          <button style={{ padding:'7px 14px', background:'#00e5a0', border:'none', borderRadius:8, color:'#20252f', fontWeight:700, cursor:'pointer', fontSize:12, marginLeft:'auto' }}>
            + Add account
          </button>
        </div>

        {showFilters && (
          <div style={{ padding:'10px 14px', borderTop:'1px solid var(--border,#4f596b)', background:'var(--bg-input,#373f4d)', display:'flex', gap:12, flexWrap:'wrap' }}>
            <div>
              <div style={{ fontSize:10, color:'var(--text3,#555)', marginBottom:4, textTransform:'uppercase' }}>Account type</div>
              <div style={{ display:'flex', gap:4 }}>
                {ACCOUNT_TYPES.map(t => (
                  <button key={t} onClick={() => setFilterType(t)}
                    style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${filterType===t?'#00e5a0':'var(--border2,#626d80)'}`, background:filterType===t?'rgba(0,229,160,0.1)':'transparent', color:filterType===t?'#00e5a0':'var(--text2,#888)', cursor:'pointer', fontSize:11, textTransform:'capitalize' }}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize:10, color:'var(--text3,#555)', marginBottom:4, textTransform:'uppercase' }}>Status</div>
              <div style={{ display:'flex', gap:4 }}>
                {['all','active','suspended'].map(s => (
                  <button key={s} onClick={() => setFilterStatus(s)}
                    style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${filterStatus===s?'#00e5a0':'var(--border2,#626d80)'}`, background:filterStatus===s?'rgba(0,229,160,0.1)':'transparent', color:filterStatus===s?'#00e5a0':'var(--text2,#888)', cursor:'pointer', fontSize:11, textTransform:'capitalize' }}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize:10, color:'var(--text3,#555)', marginBottom:4, textTransform:'uppercase' }}>Leverage</div>
              <select value={filterLeverage} onChange={e => setFilterLeverage(e.target.value)}
                style={{ padding:'5px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                {LEVERAGE_OPTIONS.map(l => <option key={l} value={l}>{l==='all'?'All leverage':l}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div style={CT.scroll}>
        <table style={CT.table}>
          <thead>
            <tr style={CT.theadTr}>
              {(['Account','Account type','Leverage','Balance','Equity','Credit','Margin%','Client','IB','Sales','Country','Status','Created','Settings'] as string[]).map(h => {
                const sortable = SORTABLE.includes(h);
                const active   = sortCol === h;
                const align    = (['Balance','Equity','Credit','Margin%'].includes(h) ? 'right' : 'left') as 'left'|'right';
                return (
                  <th key={h} onClick={() => sortable && toggleSort(h)}
                    style={{ ...CT.th(active, align), cursor:sortable?'pointer':'default' }}>
                    <span style={{ display:'inline-flex', alignItems:'center', gap:4 }}>
                      {h}
                      {sortable && (
                        <span style={{ display:'inline-flex', flexDirection:'column', lineHeight:1, fontSize:8, opacity:active?1:0.3 }}>
                          <span style={{ color:active&&sortDir==='asc'?'var(--accent,#00e5a0)':'inherit' }}>▲</span>
                          <span style={{ color:active&&sortDir==='desc'?'var(--accent,#00e5a0)':'inherit' }}>▼</span>
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={15} style={{ padding:60, textAlign:'center', color:'var(--text3,#555)' }}>Loading...</td></tr>
            ) : sorted.length === 0 ? (
              <tr><td colSpan={15} style={{ padding:60, textAlign:'center', color:'var(--text3,#555)' }}>No accounts found</td></tr>
            ) : sorted.map((a,i) => (
              <tr key={i} style={CT.row()}
                onMouseEnter={e => (e.currentTarget.style.background='var(--bg-input,#2c333e)')}
                onMouseLeave={e => (e.currentTarget.style.background='transparent')}>

                {/* Account number — click to open detail */}
                <td style={CT.td}>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <span style={{ color:'var(--accent,#00e5a0)', cursor:'pointer', fontFamily:'monospace', fontWeight:500 }} onClick={() => setDetail(a)}>
                      {a.login}
                    </span>
                    {a.archived && <span title={`Archived${a.archive_reason?(' · '+a.archive_reason):''}`} style={{ fontSize:9, fontWeight:800, padding:'1px 6px', borderRadius:4, background:'rgba(255,170,0,0.15)', color:'#ffaa00', border:'1px solid rgba(255,170,0,0.35)' }}>🗄 ARCHIVED</span>}
                  </div>
                  <div style={{ fontSize:10, color:'var(--text3,#555)', marginTop:1 }}>{a.name}</div>
                  {a.phone && (
                    <div onClick={() => setPhoneAccount(a)} title={a.phone} style={{ fontSize:10, color:'#888', cursor:'pointer', marginTop:2, display:'flex', alignItems:'center', gap:3 }}
                      onMouseEnter={e=>(e.currentTarget.style.color='#00e5a0')} onMouseLeave={e=>(e.currentTarget.style.color='#888')}>
                      📞 ···{(a.phone||'').slice(-4)}
                    </div>
                  )}
                </td>

                <td style={CT.td}>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, background:'rgba(0,102,255,0.1)', color:'#4d9fff' }}>{a.account_type||'live'}</span>
                </td>
                <td style={{ ...CT.td, color:'var(--text2,#888)' }}>1:{a.leverage}</td>
                <td style={{ ...CT.td, fontWeight:500, textAlign:'right' }}>${(a.balance||0).toLocaleString()}</td>
                <td style={{ ...CT.td, textAlign:'right', color: (a.equity||a.balance||0)<(a.balance||0)?'#ff4d4d':'#00e5a0' }}>{'$'+((a.equity||0)>0?(a.equity||0):(a.balance||0)).toLocaleString()}</td>
                <td style={{ ...CT.td, textAlign:'right', color:'#ffaa00' }}>${(a.credit||0).toLocaleString()}</td>
                <td style={{ ...CT.td, textAlign:'right' }}>
                  {(a.margin_level||0) > 0
                    ? <span style={{ color:(a.margin_level||0)<80?'#ff4d4d':(a.margin_level||0)<150?'#ffaa00':'#00e5a0', fontWeight:500 }}>{(a.margin_level||0).toFixed(0)}%</span>
                    : <span style={{ color:'var(--text3,#555)' }}>—</span>}
                </td>
                <td style={{ ...CT.td, color:'var(--text2,#888)', fontSize:11 }}>{a.name || a.client_name || '—'}</td>
                <td style={{ ...CT.td, color:'var(--text2,#888)', fontSize:11, cursor:'pointer' }} onClick={() => (a.ib_display||a.ib_code||a.agent) && setFilterIB(String(a.ib_code||a.agent))} title="Filter by IB">{a.ib_display || a.ib_name || a.ib_code || (a.agent?`#${a.agent}`:'—')}</td>
                <td style={{ ...CT.td, color:'var(--text2,#888)', fontSize:11, cursor:'pointer' }} onClick={() => a.agent_name && setFilterAgent(a.agent_name)} title="Filter by agent">{a.agent_name || '—'}</td>
                <td style={CT.td}>
                  <div style={{ color:'var(--text2,#888)', cursor:'pointer', fontSize:12 }} onClick={() => a.country && setFilterCountry(a.country)} title="Filter by country">{a.country || '—'}</div>
                  <div style={{ color:'var(--text3,#555)', cursor:'pointer', fontSize:10 }} onClick={() => a.city && setFilterCity(a.city)} title="Filter by city">{a.city || ''}</div>
                </td>
                <td style={CT.td}>
                  <span style={{ fontSize:10, padding:'2px 7px', borderRadius:99, ...statusColor(a.is_active?'active':'suspended') }}>
                    {a.is_active ? 'Active' : 'Suspended'}
                  </span>
                </td>
                <td style={{ ...CT.td, color:'var(--text3,#555)', fontSize:11 }}>
                  {(a.created_at||a.reg_date) ? new Date(a.created_at||a.reg_date).toLocaleDateString() : '—'}
                </td>

                {/* Call action + Settings gear */}
                <td style={CT.td}>
                  <div style={{ display:'flex', gap:4, alignItems:'center' }}>
                    <button onClick={e => { e.stopPropagation(); setActionMenu(a); setActionStep('menu'); setActionType(''); }}
                      style={{ padding:'4px 8px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:6, color:'var(--text2,#888)', cursor:'pointer', fontSize:11, whiteSpace:'nowrap' }}>
                      Action ▾
                    </button>
                    <div style={{ position:'relative', display:'inline-block' }}>
                      <button onClick={e => { e.stopPropagation(); setSettingsMenu(settingsMenu?.login===a.login ? null : a); }}
                        style={{ width:28, height:28, borderRadius:6, border:'1px solid var(--border2,#626d80)', background:'var(--bg-input,#373f4d)', color:'var(--text2,#888)', cursor:'pointer', fontSize:14, display:'flex', alignItems:'center', justifyContent:'center' }}>
                        ⚙
                      </button>
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <Pager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize} count={accounts.length} total={total} label="accounts" />

      {/* Phone modal */}
      {phoneAccount && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={() => setPhoneAccount(null)}>
          <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:14, padding:24, width:320 }} onClick={e => e.stopPropagation()}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
              <div style={{ fontSize:14, fontWeight:500 }}>Contact {phoneAccount.name}</div>
              <div onClick={() => setPhoneAccount(null)} style={{ cursor:'pointer', color:'#555', fontSize:18 }}>✕</div>
            </div>
            <div style={{ fontSize:13, color:'var(--text2,#888)', marginBottom:16, fontFamily:'monospace' }}>{phoneAccount.phone || 'No phone'}</div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <button onClick={() => { placeCall(phoneAccount.phone); setPhoneAccount(null); }}
                style={{ padding:'12px', borderRadius:10, border:'1px solid rgba(0,229,160,0.3)', background:'rgba(0,229,160,0.08)', color:'#00e5a0', cursor:'pointer', fontSize:13, fontWeight:500 }}>📞 Call via Yeastar PBX</button>
              <button onClick={() => { window.open(`https://wa.me/${(phoneAccount.phone||'').replace(/[^0-9]/g,'')}?text=Hello ${phoneAccount.name}`,'_blank'); setPhoneAccount(null); }}
                style={{ padding:'12px', borderRadius:10, border:'1px solid rgba(37,211,102,0.3)', background:'rgba(37,211,102,0.08)', color:'#25d366', cursor:'pointer', fontSize:13, fontWeight:500 }}>💬 WhatsApp</button>
              <button onClick={() => { setEmailAccount(phoneAccount); setPhoneAccount(null); }}
                style={{ padding:'12px', borderRadius:10, border:'1px solid rgba(0,102,255,0.3)', background:'rgba(0,102,255,0.08)', color:'#4d9fff', cursor:'pointer', fontSize:13, fontWeight:500 }}>✉️ Send email</button>
            </div>
          </div>
        </div>
      )}

      {/* Action modal */}
      {actionMenu && (
        <div style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,0.65)' }} onClick={() => { setActionMenu(null); setActionStep('menu'); }}>
          <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:14, padding:22, width:300 }}
            onClick={e => e.stopPropagation()}>
            {actionStep === 'menu' && (
              <>
                <div style={{ fontSize:13, fontWeight:500, marginBottom:3 }}>#{actionMenu.login} — {actionMenu.name}</div>
                <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:16 }}>Select outcome</div>
                {[
                  { key:'connected_done', icon:'✓', label:'Connected & Done',  sub:'Resurfaces in 14 days', color:'#00e5a0' },
                  { key:'no_answer',      icon:'✗', label:'No Answer',          sub:'Resurfaces in 2 hours', color:'#ffaa00' },
                  { key:'call_later',     icon:'⏰', label:'Call Later',         sub:'Set custom follow-up',  color:'#0066ff' },
                  { key:'not_interested', icon:'⊘', label:'Not Interested',     sub:'Pass to manager',       color:'#ff4d4d' },
                ].map(a => (
                  <div key={a.key} onClick={() => { setActionType(a.key); setActionStep('form'); }}
                    style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid var(--border,#4f596b)' }}
                    onMouseEnter={e => (e.currentTarget.style.background='var(--bg-input,#373f4d)')}
                    onMouseLeave={e => (e.currentTarget.style.background='transparent')}>
                    <div style={{ width:30, height:30, borderRadius:8, background:`${a.color}22`, color:a.color, display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>{a.icon}</div>
                    <div>
                      <div style={{ fontSize:13, fontWeight:500, color:a.color }}>{a.label}</div>
                      <div style={{ fontSize:11, color:'var(--text3,#555)' }}>{a.sub}</div>
                    </div>
                  </div>
                ))}
              </>
            )}
            {actionStep === 'form' && (
              <>
                <div style={{ display:'flex', gap:8, marginBottom:16 }}>
                  <div onClick={() => setActionStep('menu')} style={{ cursor:'pointer', color:'#888', fontSize:12 }}>← Back</div>
                  <div style={{ fontSize:13, fontWeight:500, color: actionType==='connected_done'?'#00e5a0':actionType==='no_answer'?'#ffaa00':actionType==='call_later'?'#0066ff':'#ff4d4d' }}>
                    {actionType==='connected_done'?'Connected & Done':actionType==='no_answer'?'No Answer':actionType==='call_later'?'Call Later':'Not Interested'}
                  </div>
                </div>
                {actionType === 'call_later' && (
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:12 }}>
                    <div>
                      <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Days</div>
                      <input type="number" value={callLaterDays} onChange={e=>setCallLaterDays(parseInt(e.target.value)||0)} min={0}
                        style={{ width:'100%', padding:'8px 10px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
                    </div>
                    <div>
                      <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Hours</div>
                      <input type="number" value={callLaterHours} onChange={e=>setCallLaterHours(parseInt(e.target.value)||0)} min={0} max={23}
                        style={{ width:'100%', padding:'8px 10px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
                    </div>
                  </div>
                )}
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Note (optional)</div>
                  <textarea value={actionNote} onChange={e=>setActionNote(e.target.value)} rows={3}
                    placeholder="Add a note..."
                    style={{ width:'100%', padding:'8px 10px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:12, outline:'none', resize:'none' as any, boxSizing:'border-box' as any }} />
                </div>
                <button onClick={saveAction} disabled={saving}
                  style={{ width:'100%', padding:11, background: actionType==='connected_done'?'#00e5a0':actionType==='no_answer'?'#ffaa00':actionType==='call_later'?'#0066ff':'#ff4d4d', border:'none', borderRadius:8, color:'#fff', fontWeight:700, cursor:'pointer', fontSize:13 }}>
                  {saving ? '...' : 'Save'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Settings dropdown */}
      {settingsMenu && (
        <div style={{ position:'fixed', inset:0, zIndex:200 }} onClick={() => setSettingsMenu(null)}>
          <div style={{ position:'fixed', top:'auto', right:60, background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:12, padding:8, width:220, zIndex:201, boxShadow:'0 8px 32px rgba(0,0,0,0.4)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ fontSize:11, color:'var(--text3,#555)', padding:'6px 10px', marginBottom:4 }}>Account #{settingsMenu.login}</div>
            {SETTINGS_ACTIONS.map((action,i) => (
              <div key={i} onClick={() => setSettingsMenu(null)}
                style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', borderRadius:7, cursor:'pointer', fontSize:13 }}
                onMouseEnter={e => (e.currentTarget.style.background='var(--bg-input,#373f4d)')}
                onMouseLeave={e => (e.currentTarget.style.background='transparent')}>
                <span style={{ fontSize:15, width:20, textAlign:'center' }}>{action.icon}</span>
                <span style={{ color: action.label==='Delete'?'#ff4d4d':'var(--text,#fff)' }}>{action.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Mock data
const mockAccounts: any[] = [
  { login:577671, name:'Ahmed Al-Rashid',   email:'ahmed@email.com',   phone:'+971501234567', city:'Dubai',        country:'UAE',          last_ip:'41.234.12.5',   cid:'C100021', mqid:'9876543', balance:500,   equity:999,   credit:0,    margin_level:0,   leverage:500, group_name:'Standard', account_type:'live',    agent:335002671, is_active:true,  reg_date:'2026-06-05', client_name:'Ahmed Al-Rashid', ib_code:'IB-001', agent_name:'Sara Sales', total_deposits:500,   total_withdrawals:0,    total_volume:12,  total_trades:8  },
  { login:577670, name:'Mohammed Hassan',   email:'mhassen@email.com', phone:'+201234567890', city:'Cairo',        country:'Egypt',         last_ip:'197.44.12.9',   cid:'C100028', mqid:'8765432', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:500, group_name:'Standard', account_type:'live',    agent:'NA',       is_active:true,  reg_date:'2026-06-05', client_name:'Mohammed Hassan', ib_code:'IB-002', agent_name:'Omar Agent', total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
  { login:311509, name:'Fatima Nasser',     email:'fatima@email.com',  phone:'+966512345678', city:'Riyadh',       country:'Saudi Arabia',  last_ip:'185.44.22.9',   cid:'C100077', mqid:'7654321', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:500, group_name:'Zero',     account_type:'live',    agent:'NA',       is_active:true,  reg_date:'2026-06-05', client_name:'Fatima Nasser',   ib_code:'',       agent_name:'',           total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
  { login:577667, name:'Omar Khalil',       email:'omar@email.com',    phone:'+905301234567', city:'Istanbul',     country:'Turkey',        last_ip:'194.165.8.77',  cid:'C100112', mqid:'6543210', balance:483.87,equity:725.81,credit:0,    margin_level:212, leverage:500, group_name:'Standard', account_type:'live',    agent:335002872,  is_active:true,  reg_date:'2026-06-05', client_name:'Omar Khalil',     ib_code:'IB-003', agent_name:'Sara Sales', total_deposits:5000,  total_withdrawals:200,  total_volume:45,  total_trades:22 },
  { login:5011127,name:'Sara Ibrahim',      email:'sara@email.com',    phone:'+9715541234567',city:'Dubai',        country:'UAE',           last_ip:'41.234.12.5',   cid:'C100134', mqid:'5432109', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:1,   group_name:'Cent',     account_type:'demo',    agent:'NA',       is_active:true,  reg_date:'2026-06-05', client_name:'Sara Ibrahim',    ib_code:'IB-001', agent_name:'Sara Sales', total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
  { login:577666, name:'Khalid Mansour',    email:'khalid@email.com',  phone:'+962791234567', city:'Amman',        country:'Jordan',        last_ip:'176.22.45.8',   cid:'C100201', mqid:'4321098', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:500, group_name:'Standard', account_type:'live',    agent:'NA',       is_active:true,  reg_date:'2026-06-05', client_name:'Khalid Mansour',  ib_code:'',       agent_name:'',           total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
  { login:439054, name:'Nadia Farouk',      email:'nadia@email.com',   phone:'+9613123456',   city:'Beirut',       country:'Lebanon',       last_ip:'82.149.33.11',  cid:'C100245', mqid:'3210987', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:100, group_name:'Standard', account_type:'live',    agent:2100051227, is_active:true,  reg_date:'2026-06-05', client_name:'Nadia Farouk',    ib_code:'IB-004', agent_name:'',           total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
  { login:577673, name:'Yusuf Zayed',       email:'yusuf@email.com',   phone:'+96891234567',  city:'Muscat',       country:'Oman',          last_ip:'94.56.78.33',   cid:'C100312', mqid:'2109876', balance:0,     equity:0,     credit:0,    margin_level:0,   leverage:500, group_name:'Standard', account_type:'islamic', agent:'NA',       is_active:false, reg_date:'2026-06-03', client_name:'Yusuf Zayed',     ib_code:'',       agent_name:'',           total_deposits:0,     total_withdrawals:0,    total_volume:0,   total_trades:0  },
];
