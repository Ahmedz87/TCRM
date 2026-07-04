import React, { useState, useEffect, useMemo } from 'react';
import tnfxLogo from './assets/tnfx-logo.png';
import { apiGet, apiPost } from './api';

// live countdown — ticks each second from a seconds value, shows "Xd Yh Zm Ws"
function Countdown({ seconds, color }:{ seconds:number; color:string }) {
  const [s, setS] = useState(seconds);
  useEffect(() => { setS(seconds); }, [seconds]);
  useEffect(() => {
    if (s <= 0) return;
    const t = setInterval(() => setS(x => Math.max(0, x - 1)), 1000);
    return () => clearInterval(t);
  }, [s]);
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60), sec = s%60;
  return <span style={{ color, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>
    {s<=0 ? 'expired' : `${d>0?d+'d ':''}${h}h ${m}m ${String(sec).padStart(2,'0')}s`}</span>;
}

// ── formatters ──────────────────────────────────────────────────────────────
const usd  = (n:number) => '$' + Math.round(n||0).toLocaleString();
const usdK = (n:number) => Math.abs(n||0) >= 1000 ? '$' + ((n||0)/1000).toFixed((Math.abs(n||0)>=100000)?0:1) + 'K' : '$' + Math.round(n||0).toLocaleString();
const num  = (n:number) => Math.round(n||0).toLocaleString();
const initialsOf = (s:string) => (s||'').split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]||'').join('').toUpperCase() || '—';

// ── light theme ─────────────────────────────────────────────────────────────
const C = {
  bg:'#f4f6fa', card:'#ffffff', card2:'#f7f9fc', soft:'#fbfcfe',
  border:'#e7ebf2', borderH:'#dde3ec',
  text:'#101828', text2:'#5a6b85', text3:'#8c99ad',
  blue:'#2f6bff',   blueBg:'#eef3ff',
  green:'#0fae7a',  greenBg:'#e6f8f1',
  red:'#e5484d',    redBg:'#fdecec',
  amber:'#d98a00',  amberBg:'#fcf3e0',
  purple:'#6d5cff', purpleBg:'#eeecff',
};
const SANS = "'Inter','Plus Jakarta Sans',-apple-system,'Segoe UI',sans-serif";

// tier ladder — matches backend TIER_NAMES (5..10). `req` = what's needed to REACH that tier.
const BTIERS = [
  { level:5,  name:'Bronze',  color:'#b06f33', bg:'#f6ece1', icon:'🥉', req:{ ftd:0,   lots:0,     deposit:0 } },
  { level:6,  name:'Silver',  color:'#7a8696', bg:'#eef1f5', icon:'🥈', req:{ ftd:5,   lots:100,   deposit:10000 } },
  { level:7,  name:'Gold',    color:'#c39a1f', bg:'#fbf2d6', icon:'🥇', req:{ ftd:15,  lots:500,   deposit:50000 } },
  { level:8,  name:'Diamond', color:'#2f9bd0', bg:'#e6f4fb', icon:'💎', req:{ ftd:40,  lots:2000,  deposit:150000 } },
  { level:9,  name:'Elite',   color:'#6d5cff', bg:'#eeecff', icon:'⭐', req:{ ftd:100, lots:6000,  deposit:500000 } },
  { level:10, name:'Master',  color:'#e5484d', bg:'#fdecec', icon:'👑', req:{ ftd:250, lots:20000, deposit:1500000 } },
];
const bt     = (l:number) => BTIERS.find(t=>t.level===l) || BTIERS[0];
const btNext = (l:number) => BTIERS.find(t=>t.level===l+1);

const PLATFORM_COLORS:any = { facebook:'#1877f2', instagram:'#e1306c', tiktok:'#111', snapchat:'#caa800', google:'#4285f4', whatsapp:'#25d366', direct:'#5a6b85', '':'#5a6b85' };

// ── shared styles ───────────────────────────────────────────────────────────
const S:any = {
  page:   { padding:'20px 22px', maxWidth:1360, margin:'0 auto' },
  card:   { background:C.card, border:`1px solid ${C.border}`, borderRadius:14, boxShadow:'0 1px 2px rgba(16,24,40,0.05)' },
  th:     { padding:'11px 14px', textAlign:'left', fontWeight:600, fontSize:11, textTransform:'uppercase', letterSpacing:'.04em', borderBottom:`1px solid ${C.border}`, whiteSpace:'nowrap', background:C.card2, position:'sticky' as any, top:0 },
  td:     { padding:'11px 14px', borderBottom:`1px solid ${C.border}`, fontSize:13, whiteSpace:'nowrap' as any },
  input:  { padding:'9px 12px', borderRadius:9, fontSize:13, outline:'none', fontFamily:SANS },
  secLbl: { fontSize:14, fontWeight:700, color:C.text, marginBottom:13 },
  btnPri: { padding:'9px 16px', background:C.blue, color:'#fff', border:'none', borderRadius:9, fontSize:12.5, fontWeight:600, cursor:'pointer' },
  btnGhost:{ padding:'9px 14px', background:C.card, color:C.blue, border:`1px solid ${C.borderH}`, borderRadius:9, fontSize:12.5, fontWeight:600, cursor:'pointer' },
};
const badge = (bg:string, col:string):React.CSSProperties => ({ fontSize:11, padding:'3px 9px', borderRadius:99, fontWeight:600, background:bg, color:col, display:'inline-block', whiteSpace:'nowrap' });

// ── small components ─────────────────────────────────────────────────────────
function Kpi({ label, value, sub, accent, icon }:any) {
  return (
    <div style={{ ...S.card, padding:'15px 17px' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:9 }}>
        <span style={{ fontSize:11.5, color:C.text2, fontWeight:600, textTransform:'uppercase', letterSpacing:'.03em' }}>{label}</span>
        {icon && <span style={{ fontSize:14, opacity:.85 }}>{icon}</span>}
      </div>
      <div style={{ fontSize:25, fontWeight:700, color:C.text, letterSpacing:'-0.5px', lineHeight:1.05 }}>{value}</div>
      {sub && <div style={{ fontSize:12, color:accent||C.text3, marginTop:7 }}>{sub}</div>}
    </div>
  );
}
function MiniStat({ label, value, sub, accent }:any) {
  return (
    <div style={{ ...S.card, padding:'13px 14px' }}>
      <div style={{ fontSize:10.5, color:C.text2, fontWeight:600, textTransform:'uppercase', letterSpacing:'.03em', marginBottom:6 }}>{label}</div>
      <div style={{ fontSize:19, fontWeight:700, color:accent||C.text }}>{value}</div>
      {sub && <div style={{ fontSize:10.5, color:C.text3, marginTop:4 }}>{sub}</div>}
    </div>
  );
}
function EmptyRow({ cols, loading }:{ cols:number; loading:boolean }) {
  return <tr><td colSpan={cols} style={{ ...S.td, textAlign:'center', color:C.text3, padding:34 }}>{loading ? 'Loading…' : 'Nothing to show'}</td></tr>;
}
function Bar({ pct, color }:{ pct:number; color:string }) {
  return <div style={{ height:7, borderRadius:99, background:C.card2, overflow:'hidden' }}>
    <div style={{ height:'100%', borderRadius:99, width:`${Math.max(2,Math.min(100,pct))}%`, background:color }} /></div>;
}

const TRADE_PERIODS:[string,string][] = [
  ['today','Today'],['yesterday','Yesterday'],['this_week','This week'],['last_week','Last week'],
  ['last_7_days','Last 7 days'],['this_month','This month'],['last_month','Last month'],
  ['this_year','This year'],['last_year','Last year'],['all_time','All time'],['custom','Custom'],
];
// Light trades table (the dark IBTradesTab stays for the admin profile view). Shows ONLY
// eligible (commission-paid) trades, with a period selector and country/city/client filters.
function LightTrades({ ibId, preview }:{ ibId?:number; preview:boolean }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('this_month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [country, setCountry] = useState('');
  const [city, setCity] = useState('');
  const [client, setClient] = useState('');
  const [campaign, setCampaign] = useState('');
  const [groupBy, setGroupBy] = useState('list');   // list | day | week | month | year
  const inp:React.CSSProperties = { padding:'7px 10px', borderRadius:8, fontSize:12, outline:'none', background:'#fff', color:C.text, border:`1px solid ${C.borderH}` };
  useEffect(() => {
    setLoading(true);
    const ep = preview ? `/ibs/${ibId}/trades` : '/portal/ib-trades';
    const p = new URLSearchParams({ period, view:'eligible', page:'1', page_size:'100' });
    if (period==='custom') { if (dateFrom) p.set('date_from',dateFrom); if (dateTo) p.set('date_to',dateTo); }
    if (country) p.set('country',country);
    if (city) p.set('city',city);
    if (client) p.set('client_login',client);
    if (campaign) p.set('campaign',campaign);
    if (groupBy!=='list') p.set('group_by',groupBy);
    apiGet(`${ep}?${p}`).then(d=>setData(d)).catch(()=>setData(null)).finally(()=>setLoading(false));
  }, [ibId, preview, period, dateFrom, dateTo, country, city, client, campaign, groupBy]);
  const t = data?.totals || { trades:0, lots:0, commission:0 };
  const rows = data?.trades || [];
  const groups = data?.groups || null;
  const opts = data?.filters || { countries:[], cities:[], campaigns:[] };
  const grouped = groupBy!=='list';
  return (
    <div style={{ ...S.card, overflow:'hidden' }}>
      {/* period tabs (row on top, like Clients / Leads) */}
      <div style={{ display:'flex', gap:6, padding:'10px 14px', borderBottom:`1px solid ${C.border}`, flexWrap:'wrap', alignItems:'center' }}>
        {TRADE_PERIODS.map(([k,l])=>(
          <button key={k} onClick={()=>setPeriod(k)} style={{ padding:'6px 12px', borderRadius:8, fontSize:12, cursor:'pointer', fontWeight:600,
            border:`1px solid ${period===k?C.blue:C.borderH}`, background:period===k?C.blueBg:C.card, color:period===k?C.blue:C.text2 }}>{l}</button>
        ))}
        {period==='custom' && (<>
          <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} style={inp} />
          <span style={{ color:C.text3 }}>—</span>
          <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} style={inp} />
        </>)}
      </div>
      {/* filters */}
      <div style={{ display:'flex', gap:8, padding:'12px 14px', borderBottom:`1px solid ${C.border}`, flexWrap:'wrap', alignItems:'center' }}>
        <select value={country} onChange={e=>setCountry(e.target.value)} style={inp}>
          <option value="">All countries</option>{(opts.countries||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <select value={city} onChange={e=>setCity(e.target.value)} style={inp}>
          <option value="">All cities</option>{(opts.cities||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <select value={campaign} onChange={e=>setCampaign(e.target.value)} style={inp}>
          <option value="">All campaigns</option>{(opts.campaigns||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <input value={client} onChange={e=>setClient(e.target.value)} placeholder="Trading account / login…" style={{ ...inp, width:150 }} />
        <span style={{ fontSize:11.5, color:C.text3, marginLeft:4 }}>Display:</span>
        <select value={groupBy} onChange={e=>setGroupBy(e.target.value)} style={inp}>
          {[['list','Per trade'],['day','Daily'],['week','Weekly'],['month','Monthly'],['year','Yearly']].map(([k,l])=><option key={k} value={k}>{l}</option>)}
        </select>
        {(country||city||client||campaign) && <button onClick={()=>{setCountry('');setCity('');setClient('');setCampaign('');}} style={{ ...inp, color:C.red, cursor:'pointer' }}>✕ Clear</button>}
        <div style={{ marginLeft:'auto', fontSize:12.5, color:C.text2 }}>
          {num(t.trades)} eligible · {num(t.lots)} lots · <b style={{ color:C.green }}>{usd(t.commission)} commission</b>
        </div>
      </div>
      <div style={{ overflowX:'auto', maxHeight:560 }}>
        {grouped ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr>{['Period','Trades','Lots','Commission','Profit'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
            <tbody>
              {(groups||[]).map((g:any,i:number)=>(
                <tr key={i} className="ibp-row">
                  <td style={{ ...S.td, fontWeight:600 }}>{g.bucket}</td>
                  <td style={S.td}>{num(g.trades)}</td>
                  <td className="cp" style={S.td}>{num(g.lots)} lots</td>
                  <td className="cg" style={{ ...S.td, fontWeight:600 }}>{usd(g.commission)}</td>
                  <td className={g.profit>=0?'cg':'cr'} style={S.td}>{g.profit>=0?'+':''}{usd(g.profit)}</td>
                </tr>
              ))}
              {(!groups || groups.length===0) && <EmptyRow cols={5} loading={loading} />}
            </tbody>
          </table>
        ) : (
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr>{['Client','Login','Open','Symbol','Side','Lots','Profit','Commission','Hold','Closed'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r:any,i:number) => {
              const buy = String(r.direction||'').toLowerCase().startsWith('b');
              return (
                <tr key={i} className="ibp-row">
                  <td style={{ ...S.td, fontWeight:500 }}>{r.client || '—'}</td>
                  <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>#{r.login}</td>
                  <td className="cm" style={S.td}>{r.open_time ? String(r.open_time).slice(0,16).replace('T',' ') : '—'}</td>
                  <td style={S.td}>{r.symbol}</td>
                  <td style={S.td}><span style={badge(buy?C.greenBg:C.redBg, buy?C.green:C.red)}>{buy?'BUY':'SELL'}</span></td>
                  <td style={S.td}>{(r.lots||0).toFixed(2)}</td>
                  <td className={(r.profit||0)>=0?'cg':'cr'} style={{ ...S.td, fontWeight:600 }}>{(r.profit||0)>=0?'+':''}{usd(r.profit)}</td>
                  <td className="cm" style={S.td}>{usd(r.commission)}</td>
                  <td className="cm" style={S.td}>{r.hold_min!=null ? `${r.hold_min}m` : '—'}</td>
                  <td className="cm" style={S.td}>{r.close_time ? String(r.close_time).slice(0,16).replace('T',' ') : '—'}</td>
                </tr>
              );
            })}
            {rows.length===0 && <EmptyRow cols={10} loading={loading} />}
          </tbody>
        </table>
        )}
      </div>
    </div>
  );
}

// ── demo (standalone nav) sample data ────────────────────────────────────────
const MOCK_CLIENTS = [
  { login:10021, name:'Ahmed Al-Rashid',  country:'UAE',          balance:24500, dep:30000, wd:5500,  volume:125, kyc:'verified', reg:'2026-01-20', campaign:'Facebook-Iraq' },
  { login:10028, name:'Mohammed Hassan',  country:'Egypt',        balance:8200,  dep:10000, wd:1800,  volume:42,  kyc:'pending',  reg:'2026-02-14', campaign:'Instagram' },
  { login:10077, name:'Fatima Nasser',    country:'Saudi Arabia', balance:3100,  dep:0,     wd:0,     volume:0,   kyc:'pending',  reg:'2026-03-01', campaign:'TikTok' },
  { login:10112, name:'Omar Khalil',      country:'Turkey',       balance:51800, dep:60000, wd:8200,  volume:445, kyc:'verified', reg:'2025-11-10', campaign:'Facebook-Jordan' },
  { login:10134, name:'Sara Ibrahim',     country:'Jordan',       balance:5200,  dep:8000,  wd:1000,  volume:22,  kyc:'verified', reg:'2026-04-05', campaign:'Instagram' },
  { login:10156, name:'Khalid Mansour',   country:'Kuwait',       balance:12400, dep:0,     wd:0,     volume:0,   kyc:'pending',  reg:'2026-02-28', campaign:'Direct' },
];
const MOCK_MANAGER = { name:'Sara Abdullah', title:'Senior IB Manager', email:'sara@tnfx.co', phone:'+971 55 244 1596', department:'Partnerships' };
const MOCK_COMMISSIONS = [
  { client_login:10112, client_name:'Omar Khalil',    lots:445, pts_per_lot:8, commission_usd:2980, status:'unpaid' },
  { client_login:10021, client_name:'Ahmed Al-Rashid',lots:125, pts_per_lot:8, commission_usd:840,  status:'unpaid' },
  { client_login:10028, client_name:'Mohammed Hassan',lots:42,  pts_per_lot:8, commission_usd:280,  status:'paid' },
];

// ── challenges sample (gamification) ─────────────────────────────────────────
const CH1 = [   // career path (sequential)
  { id:1, stage:1, name:'Getting Started', desc:'Onboard your first 5 clients',         reward:50,   status:'completed' },
  { id:2, stage:2, name:'First Blood',     desc:'Bring your first funded client (FTD)', reward:100,  status:'completed' },
  { id:3, stage:3, name:'Momentum',        desc:'10 funded clients + 100 lots traded',  reward:250,  status:'active', progress:62 },
  { id:4, stage:4, name:'Rising Star',     desc:'25 funded clients + 500 lots',         reward:600,  status:'locked' },
  { id:5, stage:5, name:'Power Partner',   desc:'50 funded clients + 2,000 lots',       reward:1500, status:'locked' },
  { id:6, stage:6, name:'Legend',          desc:'100 funded clients + 6,000 lots',      reward:4000, status:'locked' },
];
const CH2 = [   // weekly challenges
  { id:1, emoji:'🩸', name:'First Blood',    desc:'Bring 1 FTD this week',          target:1,     progress:1,     reward:15  },
  { id:2, emoji:'⚔️', name:'Double Down',    desc:'Bring 2 FTDs this week',         target:2,     progress:2,     reward:30  },
  { id:3, emoji:'🎯', name:'Hat Trick',      desc:'Bring 3 FTDs this week',         target:3,     progress:2,     reward:60  },
  { id:4, emoji:'📊', name:'Volume Hunter',  desc:'Clients trade 50 lots',          target:50,    progress:32,    reward:120 },
  { id:5, emoji:'💵', name:'Cash Flow',      desc:'Clients deposit $5,000',         target:5000,  progress:3200,  reward:30  },
  { id:6, emoji:'🔗', name:'Link Builder',   desc:'10 referral registrations',      target:10,    progress:7,     reward:20  },
  { id:7, emoji:'🐋', name:'Whale Hunter',   desc:'Clients deposit $50,000',        target:50000, progress:12000, reward:400 },
  { id:8, emoji:'🌍', name:'Gulf Dominator', desc:'3 FTDs from UAE / KSA / Kuwait', target:3,     progress:1,     reward:100 },
];

// ══════════════════════════════════════════════════════════════════════════════
export default function IBPortal({ lang, ibId, onBack }:any) {
  const [tab, setTab] = useState('dashboard');
  const [cliSearch, setCliSearch] = useState('');
  const [cliCountry, setCliCountry] = useState('');
  const [cliCity, setCliCity] = useState('');
  const [cliPeriod, setCliPeriod] = useState('all');   // filter by acquisition (first-deposit) period
  const [cliSort, setCliSort] = useState<{col:string;dir:'asc'|'desc'}>({ col:'volume', dir:'desc' });
  const [leadSearch, setLeadSearch] = useState('');
  const [leadCountry, setLeadCountry] = useState('');
  const [leadCity, setLeadCity] = useState('');
  const [leadCampaign, setLeadCampaign] = useState('');
  const [myCampaigns, setMyCampaigns] = useState<any[]>([]);
  const [campModal, setCampModal] = useState(false);
  const [campForm, setCampForm] = useState<any>({ name:'', platform:'', website:'' });
  const [copied, setCopied] = useState('');
  const [refLinks, setRefLinks] = useState<any[]>([]);   // existing (Plugit) referral links
  const [ibOps, setIbOps] = useState<any>(null);          // payout operations
  const [ibPromos, setIbPromos] = useState<any>(null);    // level-promotion history
  const [payModal, setPayModal] = useState<string | null>(null);   // 'withdraw' | 'transfer'
  const [payForm, setPayForm] = useState<any>({ amount:'', to_account:'' });
  const [chData, setChData] = useState<any>(null);   // real challenge data (preview)
  const preview = !!ibId;

  const [R, setR] = useState<any>(null);
  useEffect(() => {
    if (!ibId) { setR(null); return; }
    setR(null);
    apiGet(`/ibs/${ibId}?period=all_time`).then(setR).catch(()=>{});
  }, [ibId]);

  // campaigns (E) + challenges (F) — real data when previewing a specific IB
  const loadCampaigns = () => {
    if (!ibId) return;
    apiGet(`/ibs/${ibId}/campaigns`).then((d:any)=>setMyCampaigns(d.campaigns||[])).catch(()=>{});
    apiGet(`/ibs/${ibId}/referral-links`).then((d:any)=>setRefLinks(d.links||[])).catch(()=>{});
  };
  const loadCh = () => { if (ibId) apiGet(`/ibs/${ibId}/challenges`).then(setChData).catch(()=>{}); };
  const loadOps = () => { if (ibId) apiGet(`/ibs/${ibId}/operations`).then(setIbOps).catch(()=>{}); };
  const loadPromos = () => { if (ibId) apiGet(`/ibs/${ibId}/promotions`).then(setIbPromos).catch(()=>{}); };
  useEffect(() => { loadCampaigns(); loadCh(); loadOps(); loadPromos(); /* eslint-disable-next-line */ }, [ibId]);
  const submitPayout = async () => {
    if (!ibId || !(parseFloat(payForm.amount) > 0)) return;
    try {
      await apiPost(`/ibs/${ibId}/operations`, { kind: payModal, amount: parseFloat(payForm.amount), to_account: payForm.to_account });
      setPayModal(null); setPayForm({ amount:'', to_account:'' }); loadOps();
      alert('Request submitted — it will show in the admin Withdrawals page for approval.');
    } catch { alert('Could not submit request'); }
  };
  const createCampaign = async () => {
    if (!ibId || !campForm.name.trim()) return;
    try { await apiPost(`/ibs/${ibId}/campaigns`, campForm); setCampModal(false); setCampForm({ name:'', platform:'', website:'' }); loadCampaigns(); }
    catch { alert('Could not create campaign'); }
  };
  const chAction = async (path:string, key:string) => {
    if (!ibId) return;
    try { const d:any = await apiPost(`/ibs/${ibId}/challenges/${path}`, { key }); setChData(d); }
    catch (e:any) { alert(e?.message || 'Action failed'); }
  };

  // identity
  const level    = preview ? (R?.ib_level || 5) : 8;
  const T        = bt(level);
  const NT       = btNext(level);
  const ibName   = preview ? (R?.name || `IB #${ibId}`) : 'Ahmad Zaman';
  const ibCode   = preview ? (R?.ib_code || '') : 'IB-001';
  const tierName = preview ? (R?.tier || T.name) : T.name;
  const manager  = preview ? R?.manager : MOCK_MANAGER;

  // per-trading-account rows
  const accounts = useMemo(() => {
    if (preview) return (R?.clients || []).map((c:any) => ({
      login:c.login, cus:c.customer_no || `#${c.login}`, name:c.name, country:c.country, city:c.city, balance:c.balance,
      dep:c.total_dep, wd:c.total_with, volume:c.volume, commission:c.commission||0, kyc:c.kyc,
      reg:c.reg_date, campaign:c.campaign || 'Direct', first_trade:c.first_trade,
      email:c.email, phone:c.phone, first_deposit:c.first_deposit,
      email_v:!!c.email_verified, phone_v:!!c.phone_verified,
    }));
    return MOCK_CLIENTS.map((c:any,i:number) => ({ ...c, cus:`CUS${100000+i}`, commission:Math.round((c.volume||0)*7), city:c.city||'', email:`${(c.name||'').split(' ')[0].toLowerCase()}@example.com`, phone:'+9647xxxxxxxx', first_deposit:c.reg, first_trade:c.reg, email_v:false, phone_v:false }));
  }, [R, preview]);

  // CLIENTS = one row per person (customer_no), summing all their trading accounts
  const clients = useMemo(() => {
    const m:any = {};
    accounts.forEach((a:any) => {
      const key = a.cus;
      if (!m[key]) m[key] = { ...a, accounts:0, dep:0, wd:0, volume:0, commission:0, balance:0, kyc:'pending', email_v:false, phone_v:false, first_deposit:null, reg:a.reg };
      const g = m[key];
      g.accounts++; g.dep += (a.dep||0); g.wd += (a.wd||0); g.volume += (a.volume||0);
      g.commission += (a.commission||0); g.balance += (a.balance||0);
      if (a.kyc==='verified') g.kyc = 'verified';
      g.email_v = g.email_v || a.email_v; g.phone_v = g.phone_v || a.phone_v;
      if (a.first_deposit && (!g.first_deposit || a.first_deposit < g.first_deposit)) g.first_deposit = a.first_deposit;
      if (a.reg && (!g.reg || a.reg < g.reg)) g.reg = a.reg;
    });
    return Object.values(m);
  }, [accounts]);

  const k = preview ? {
    clients:R?.total_clients||0, active:R?.period?.active_clients||R?.active_clients||0,
    ftd:R?.funnel?.ftd||0, leads:R?.funnel?.leads||0, verified:R?.funnel?.verified_leads||0, subIbs:R?.funnel?.sub_ibs||0,
    commission:R?.total_commission||0, unpaid:R?.unpaid_commission||0, paid:R?.paid_commission||0,
    volume:R?.total_volume||0, deposits:R?.period?.deposits||0, withdrawals:R?.period?.withdrawals||0, balance:R?.balance||0,
  } : {
    clients:145, active:89, ftd:34, leads:223, verified:120, subIbs:4,
    commission:24800, unpaid:3200, paid:21600, volume:8420, deposits:248000, withdrawals:42000, balance:3200,
  };

  const leadsList = useMemo(() => clients.filter((c:any) => (c.dep||0) <= 0), [clients]);
  const topClients = useMemo(() => [...clients].sort((a:any,b:any)=>(b.volume||0)-(a.volume||0)).slice(0,8), [clients]);
  const campaigns = useMemo(() => {
    const m:any = {};
    clients.forEach((c:any) => {
      const key = c.campaign || 'Direct';
      if (!m[key]) m[key] = { name:key, leads:0, ftds:0, deposits:0, volume:0 };
      m[key].leads++; m[key].volume += (c.volume||0);
      if ((c.dep||0) > 0) { m[key].ftds++; m[key].deposits += (c.dep||0); }
    });
    return Object.values(m).sort((a:any,b:any)=>b.deposits-a.deposits);
  }, [clients]);
  const commissions = preview ? (R?.commissions || []) : MOCK_COMMISSIONS;

  // tier progression: gap to next level
  const tierGaps = NT ? [
    { l:'Funded clients (FTD)', cur:k.ftd,      tgt:NT.req.ftd,     fmt:num  },
    { l:'Volume (lots)',        cur:k.volume,   tgt:NT.req.lots,    fmt:num  },
    { l:'Net deposits',         cur:k.deposits, tgt:NT.req.deposit, fmt:usdK },
  ] : [];

  const tabs = [
    { key:'dashboard', label:'Dashboard' }, { key:'clients', label:'Clients' },
    { key:'leads', label:'Leads' }, { key:'trades', label:'Trades' },
    { key:'campaigns', label:'Campaigns' }, { key:'challenges', label:'Challenges' },
    { key:'marketing', label:'Banners' }, { key:'earnings', label:'Earnings' },
  ];

  // option lists for filters (from the real account rows)
  const countryOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.country).filter(Boolean))) as string[]).sort(), [accounts]);
  const cityOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.city).filter(Boolean))) as string[]).sort(), [accounts]);
  const campaignOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.campaign).filter(Boolean))) as string[]).sort(), [accounts]);

  const periodCutoff = (p:string) => {
    if (p==='all') return null;
    const d = new Date(); d.setHours(0,0,0,0);
    if (p==='today') return d;
    if (p==='this_week') { d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d; }
    if (p==='this_month') { d.setDate(1); return d; }
    if (p==='this_year') { d.setMonth(0,1); return d; }
    if (p==='last_30') { d.setDate(d.getDate()-30); return d; }
    if (p==='last_90') { d.setDate(d.getDate()-90); return d; }
    return null;
  };
  const filteredClients = useMemo(() => {
    const cut = periodCutoff(cliPeriod);
    let list = clients.filter((c:any) =>
      (!cliSearch || `${c.name} ${c.cus} ${c.country||''}`.toLowerCase().includes(cliSearch.toLowerCase()))
      && (!cliCountry || c.country===cliCountry)
      && (!cliCity || c.city===cliCity)
      && (!cut || (c.first_deposit && new Date(c.first_deposit) >= cut)));
    const dir = cliSort.dir==='asc' ? 1 : -1;
    list = [...list].sort((a:any,b:any)=>((a[cliSort.col]||0)-(b[cliSort.col]||0))*dir);
    return list;
  }, [clients, cliSearch, cliCountry, cliCity, cliPeriod, cliSort]);
  const toggleSort = (col:string) => setCliSort(s => s.col===col ? { col, dir:s.dir==='asc'?'desc':'asc' } : { col, dir:'desc' });

  const filteredLeads = useMemo(() => leadsList.filter((c:any) =>
    (!leadSearch || `${c.name} ${c.cus} ${c.country||''}`.toLowerCase().includes(leadSearch.toLowerCase()))
    && (!leadCountry || c.country===leadCountry)
    && (!leadCity || c.city===leadCity)
    && (!leadCampaign || c.campaign===leadCampaign)), [leadsList, leadSearch, leadCountry, leadCity, leadCampaign]);

  const loadingPreview = preview && !R;

  // Challenge view: real (preview, from chData) or sample (demo standalone).
  const cv:any = (preview ? chData : null) || {
    career: CH1.map((c:any) => ({ key:'c'+c.id, stage:c.stage, name:c.name, desc:c.desc, reward:c.reward, target:{},
      status: c.status==='completed' ? 'claimed' : c.status==='active' ? 'active' : 'available',
      progress:{}, pct:c.progress||0, seconds_left: c.status==='active' ? 26*86400 : null })),
    weekly: CH2.map((c:any) => ({ key:'w'+c.id, emoji:c.emoji, name:c.name, desc:c.desc, target:c.target,
      progress:c.progress, pct:Math.min(100,Math.round(c.progress/c.target*100)), ready:c.progress>=c.target, claimed:false })),
    seconds_to_reset: 4*86400,
  };
  const ch2ToClaim = (cv.weekly||[]).filter((w:any)=>w.ready && !w.claimed).reduce((s:number,w:any)=>s+w.reward,0);

  return (
    <div className="ibp" style={{ height:'100%', overflowY:'auto', background:C.bg, color:C.text, fontFamily:SANS }}>

      {/* ── Header ── */}
      <div style={{ background:C.card, borderBottom:`1px solid ${C.border}`, position:'sticky', top:0, zIndex:20 }}>
        <div style={{ maxWidth:1360, margin:'0 auto', padding:'13px 22px', display:'flex', alignItems:'center', justifyContent:'space-between', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:13 }}>
            {preview && onBack && <button onClick={onBack} style={{ ...S.btnGhost, padding:'7px 12px' }} title="Back to IB Admin">← Back</button>}
            <div style={{ background:'#0b1220', borderRadius:9, padding:'7px 10px', display:'flex', alignItems:'center' }}>
              <img src={tnfxLogo} alt="TNFX" style={{ height:22, width:'auto', display:'block' }} />
            </div>
            <div>
              <div style={{ fontSize:15, fontWeight:700, color:C.text, letterSpacing:'-.2px' }}>Partner Portal</div>
              <div style={{ fontSize:11, color:C.text3 }}>TNFX Introducing Broker</div>
            </div>
            {preview && <span style={{ ...badge(C.amberBg, C.amber), marginLeft:4 }}>👁 Admin preview</span>}
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:11 }}>
            <div style={{ textAlign:'right' }}>
              <div style={{ fontSize:13, fontWeight:700, color:C.text }}>{ibName}</div>
              <div style={{ fontSize:11.5, color:C.text2 }}>
                <span style={{ ...badge(T.bg, T.color), padding:'2px 8px' }}>{T.icon} {tierName} · L{level}</span>
                {ibCode && <span style={{ color:C.text3, marginLeft:6 }}>{ibCode}</span>}
              </div>
              {preview && R?.accounts && R.accounts.length > 0 && (
                <div style={{ fontSize:10.5, color:C.text3, marginTop:3 }}>
                  {R.accounts.map((a:any,i:number)=>(
                    <span key={i} style={{ marginLeft:i?8:0 }}><span style={{ color:C.text2, fontWeight:600 }}>{a.platform}</span> #{a.account}</span>
                  ))}
                </div>
              )}
            </div>
            <div style={{ width:38, height:38, borderRadius:'50%', background:C.blueBg, color:C.blue, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700 }}>{initialsOf(ibName)}</div>
          </div>
        </div>
        <div style={{ maxWidth:1360, margin:'0 auto', padding:'0 22px', display:'flex', gap:2, overflowX:'auto' }}>
          {tabs.map(t => {
            const on = tab===t.key;
            return <div key={t.key} className="ibp-tab" onClick={()=>setTab(t.key)}
              style={{ padding:'12px 15px', fontSize:13, fontWeight:on?700:500, cursor:'pointer', whiteSpace:'nowrap', color:on?C.blue:C.text2, borderBottom:`2.5px solid ${on?C.blue:'transparent'}` }}>{t.label}</div>;
          })}
        </div>
      </div>

      {/* ══ DASHBOARD ══ */}
      {tab==='dashboard' && (
        <div style={S.page}>
          {/* main KPIs full width */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:13, marginBottom:16 }}>
            <Kpi label="Clients"      value={loadingPreview?'…':num(k.clients)}    sub={`${num(k.active)} active traders`} accent={C.blue}   icon="👥" />
            <Kpi label="Funded (FTD)" value={loadingPreview?'…':num(k.ftd)}        sub={`${num(k.verified)} KYC verified`} accent={C.green}  icon="✅" />
            <Kpi label="Commission"   value={loadingPreview?'…':usd(k.commission)} sub={`${usd(k.unpaid)} unpaid`}         accent={C.amber}  icon="💰" />
            <Kpi label="Volume"       value={loadingPreview?'…':num(k.volume)}     sub="lots · all time"                  accent={C.purple} icon="📊" />
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'minmax(0,1.75fr) minmax(0,1fr)', gap:16, alignItems:'start' }}>
            {/* LEFT: tier + top clients */}
            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              {/* tier card — live / gamified */}
              {(() => {
                const overall = NT ? Math.round(tierGaps.reduce((s,g)=>s+(g.tgt?Math.min(100,g.cur/g.tgt*100):100),0)/Math.max(1,tierGaps.length)) : 100;
                const remainingMet = NT ? tierGaps.filter(g=>g.cur>=g.tgt).length : 3;
                return (
                <div style={{ ...S.card, overflow:'hidden' }}>
                  {/* hero header with live gradient + overall progress */}
                  <div style={{ position:'relative', overflow:'hidden', padding:'18px 20px',
                    background:`linear-gradient(115deg, ${T.color}14, ${NT?NT.color:T.color}22 55%, ${C.blue}10)` }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:12, flexWrap:'wrap' }}>
                      <div style={{ display:'flex', alignItems:'center', gap:13 }}>
                        <div className="ibp-float" style={{ fontSize:34, lineHeight:1 }}>{T.icon}</div>
                        <div>
                          <div style={{ fontSize:11, color:C.text3, textTransform:'uppercase', letterSpacing:'.1em', fontWeight:700 }}>Your partner tier</div>
                          <div style={{ fontSize:22, fontWeight:800, color:C.text }}>{tierName} <span style={{ color:C.text3, fontWeight:600, fontSize:14 }}>· Level {level} · {level} pts/lot</span></div>
                        </div>
                      </div>
                      {NT && (
                        <div style={{ textAlign:'right' }}>
                          <div style={{ fontSize:10.5, color:C.text3, textTransform:'uppercase', letterSpacing:'.08em', fontWeight:700 }}>Next</div>
                          <div style={{ fontSize:16, fontWeight:800, color:NT.color }}>{NT.icon} {NT.name}</div>
                          <div style={{ fontSize:11, color:C.green, fontWeight:700 }}>+1 pt/lot 🔥</div>
                        </div>
                      )}
                    </div>
                    {NT && (
                      <div style={{ marginTop:14 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:6 }}>
                          <span style={{ fontSize:12.5, fontWeight:700, color:C.text }}>🚀 {overall}% of the way to {NT.name}</span>
                          <span style={{ fontSize:11.5, color:C.text2 }}><b style={{ color:C.green }}>{remainingMet}/3</b> targets met</span>
                        </div>
                        <div style={{ position:'relative', height:11, borderRadius:99, background:'#fff', border:`1px solid ${C.border}`, overflow:'hidden' }}>
                          <div className="ibp-bar-fill" style={{ height:'100%', width:`${overall}%`, borderRadius:99, background:`linear-gradient(90deg, ${T.color}, ${NT.color})` }} />
                          <div className="ibp-shimmer" style={{ position:'absolute', inset:0, width:`${overall}%`, borderRadius:99 }} />
                        </div>
                      </div>
                    )}
                  </div>

                  <div style={{ padding:'16px 20px 20px' }}>
                    {/* roadmap with pulsing current node */}
                    <div style={{ display:'flex', alignItems:'center', padding:'0 2px', marginBottom:NT?18:0 }}>
                      {BTIERS.map((t,i) => {
                        const here = t.level===level, passed = t.level < level;
                        return (
                          <React.Fragment key={t.level}>
                            <div style={{ textAlign:'center', minWidth:50 }}>
                              <div className={here?'ibp-pulse':''} style={{ width:here?44:34, height:here?44:34, borderRadius:'50%', margin:'0 auto 5px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:here?19:14,
                                background:(here||passed)?t.bg:C.card2, border:`${here?2.5:1.5}px solid ${(here||passed)?t.color:C.borderH}` }}>{t.icon}</div>
                              <div style={{ fontSize:here?11:9.5, color:(here||passed)?t.color:C.text3, fontWeight:here?700:500 }}>{t.name}</div>
                              {here && <div style={{ fontSize:9, color:C.blue, fontWeight:700 }}>You</div>}
                            </div>
                            {i<BTIERS.length-1 && <div style={{ flex:1, height:3, borderRadius:2, background: passed?`linear-gradient(90deg,${BTIERS[i].color},${BTIERS[i+1].color})`:C.border }} />}
                          </React.Fragment>
                        );
                      })}
                    </div>
                    {/* what's missing for next level */}
                    {NT ? (
                      <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:16 }}>
                        <div style={{ fontSize:12.5, fontWeight:700, color:C.text, marginBottom:13 }}>What you need to unlock {NT.icon} {NT.name}</div>
                        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:14 }}>
                          {tierGaps.map((g,i) => {
                            const pct = g.tgt ? Math.min(100, g.cur/g.tgt*100) : 100;
                            const left = Math.max(0, g.tgt - g.cur), done = left<=0;
                            return (
                              <div key={i} style={{ background:C.card2, border:`1px solid ${C.border}`, borderRadius:11, padding:'12px 13px' }}>
                                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:5 }}>
                                  <span style={{ fontSize:11, color:C.text2 }}>{g.l}</span>
                                  <span style={{ fontSize:11, fontWeight:800, color:done?C.green:C.blue }}>{done?'✓':`${Math.round(pct)}%`}</span>
                                </div>
                                <div style={{ fontSize:15, fontWeight:800, color:C.text, marginBottom:8 }}>{g.fmt(g.cur)} <span style={{ fontSize:11, color:C.text3, fontWeight:400 }}>/ {g.fmt(g.tgt)}</span></div>
                                <div style={{ position:'relative', height:8, borderRadius:99, background:'#fff', border:`1px solid ${C.border}`, overflow:'hidden' }}>
                                  <div className="ibp-bar-fill" style={{ height:'100%', width:`${pct}%`, borderRadius:99, background:done?C.green:`linear-gradient(90deg,${C.blue},${C.purple})` }} />
                                  {!done && <div className="ibp-shimmer" style={{ position:'absolute', inset:0, width:`${pct}%`, borderRadius:99 }} />}
                                </div>
                                <div style={{ fontSize:10.5, fontWeight:600, color:done?C.green:C.amber, marginTop:7 }}>{done?'Achieved! 🎉':`${g.fmt(left)} to go`}</div>
                              </div>
                            );
                          })}
                        </div>
                        <div style={{ marginTop:14, padding:'11px 14px', borderRadius:10, background:C.blueBg, color:C.blue, fontSize:12.5, fontWeight:600, textAlign:'center' }}>
                          💪 Keep pushing — hit all 3 targets and you auto-upgrade to {NT.name} ({NT.level} pts/lot on every lot).
                        </div>
                      </div>
                    ) : (
                      <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:16, textAlign:'center', fontSize:13, fontWeight:700, color:C.amber }}>👑 You've reached the top tier — Master. Maximum commission rate unlocked!</div>
                    )}
                  </div>
                </div>
                );
              })()}

              {/* top clients */}
              <div style={{ ...S.card, overflow:'hidden' }}>
                <div style={{ padding:'14px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ fontSize:13.5, fontWeight:700 }}>Top clients by volume</span>
                  <span onClick={()=>setTab('clients')} style={{ fontSize:12, color:C.blue, cursor:'pointer', fontWeight:600 }}>View all →</span>
                </div>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr>{['Client','Country','City','Volume','KYC'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                  <tbody>
                    {topClients.map((c:any,i:number)=>(
                      <tr key={i} className="ibp-row">
                        <td style={{ ...S.td, fontWeight:500 }}>{c.name}<div style={{ fontSize:11, color:C.text3 }}>{c.cus}</div></td>
                        <td className="cm" style={S.td}>{c.country||'—'}</td>
                        <td className="cm" style={S.td}>{c.city||'—'}</td>
                        <td className="cp" style={{ ...S.td, fontWeight:600 }}>{num(c.volume)} lots</td>
                        <td style={S.td}><span style={badge(c.kyc==='verified'?C.greenBg:C.amberBg, c.kyc==='verified'?C.green:C.amber)}>{c.kyc||'pending'}</span></td>
                      </tr>
                    ))}
                    {topClients.length===0 && <EmptyRow cols={5} loading={loadingPreview} />}
                  </tbody>
                </table>
              </div>
            </div>

            {/* RIGHT: manager + funnel + mini stats */}
            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              {/* manager */}
              <div style={{ ...S.card, padding:18 }}>
                <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:13 }}>Your account manager</div>
                <div style={{ display:'flex', alignItems:'center', gap:13, marginBottom:15 }}>
                  <div style={{ width:50, height:50, borderRadius:'50%', background:C.blueBg, color:C.blue, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, fontWeight:700, overflow:'hidden', flexShrink:0 }}>
                    {manager?.avatar_url ? <img src={manager.avatar_url} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} /> : (manager?.name ? initialsOf(manager.name) : '—')}
                  </div>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:14.5, fontWeight:700, color:C.text }}>{manager?.name || 'Unassigned'}</div>
                    <div style={{ fontSize:12, color:C.text2 }}>{manager?.title || (manager?'Account Manager':'—')}</div>
                  </div>
                </div>
                {manager ? (<>
                  {[{ic:'✉',l:'Email',v:manager.email||'—'},{ic:'📱',l:'Phone',v:manager.phone||'—'},...(manager.department?[{ic:'🏢',l:'Team',v:manager.department}]:[])].map((r:any,i:number)=>(
                    <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 0', borderTop:`1px solid ${C.border}` }}>
                      <span style={{ width:26, height:26, borderRadius:7, background:C.card2, display:'flex', alignItems:'center', justifyContent:'center', fontSize:12 }}>{r.ic}</span>
                      <div style={{ minWidth:0 }}>
                        <div style={{ fontSize:9.5, color:C.text3, textTransform:'uppercase', letterSpacing:'.05em' }}>{r.l}</div>
                        <div style={{ fontSize:12.5, color:C.text, overflow:'hidden', textOverflow:'ellipsis' }}>{r.v}</div>
                      </div>
                    </div>
                  ))}
                  <div style={{ display:'flex', gap:8, marginTop:13 }}>
                    <a href={manager.email?`mailto:${manager.email}`:undefined} style={{ ...S.btnPri, flex:1, textAlign:'center', textDecoration:'none' }}>✉ Email</a>
                    <a href={manager.phone?`tel:${manager.phone}`:undefined} style={{ ...S.btnGhost, flex:1, textAlign:'center', textDecoration:'none' }}>📞 Call</a>
                  </div>
                </>) : <div style={{ fontSize:12.5, color:C.text3, padding:'8px 0' }}>No manager assigned yet.</div>}
              </div>

              {/* funnel */}
              <div style={{ ...S.card, padding:18 }}>
                <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:14 }}>Client funnel</div>
                {(() => {
                  const lead=k.leads||k.clients||0, ver=k.verified||0, ftd=k.ftd||0, mx=Math.max(lead,1);
                  const steps=[{l:'Clients',v:lead,c:C.blue},{l:'KYC verified',v:ver,c:C.purple},{l:'Funded (FTD)',v:ftd,c:C.green}];
                  return (<>
                    {steps.map((s,i)=>(
                      <div key={i} style={{ marginBottom:13 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                          <span style={{ fontSize:12, color:C.text2 }}>{s.l}</span>
                          <span style={{ fontSize:14, fontWeight:700, color:s.c }}>{num(s.v)}</span>
                        </div>
                        <Bar pct={s.v/mx*100} color={s.c} />
                      </div>
                    ))}
                    <div style={{ display:'flex', justifyContent:'space-between', marginTop:14, paddingTop:12, borderTop:`1px solid ${C.border}` }}>
                      <span style={{ fontSize:12, color:C.text2 }}>Conversion</span>
                      <span style={{ fontSize:15, fontWeight:700, color:C.green }}>{lead?Math.round(ftd/lead*100):0}%</span>
                    </div>
                  </>);
                })()}
              </div>

              {/* mini stats */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                <MiniStat label="Active traders" value={num(k.active)} sub="traded this period" accent={C.green} />
                <MiniStat label="Sub-IBs" value={num(k.subIbs)} sub="in your network" accent={C.blue} />
                <MiniStat label="Paid out" value={usd(k.paid)} sub="commission paid" accent={C.text} />
                <MiniStat label="Own balance" value={usd(k.balance)} sub="IB account" accent={C.text} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ CLIENTS ══ */}
      {tab==='clients' && (
        <div style={S.page}>
          <div style={{ display:'flex', gap:9, marginBottom:13, alignItems:'center', flexWrap:'wrap' }}>
            <input placeholder="Search name, customer ID, country…" value={cliSearch} onChange={e=>setCliSearch(e.target.value)}
              style={{ ...S.input, width:250, background:C.card, color:C.text, border:`1px solid ${C.borderH}` }} />
            <select value={cliCountry} onChange={e=>setCliCountry(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All countries</option>{countryOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={cliCity} onChange={e=>setCliCity(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All cities</option>{cityOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={cliPeriod} onChange={e=>setCliPeriod(e.target.value)} title="Filter by first-deposit date" style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              {[['all','All time'],['today','Today'],['this_week','This week'],['this_month','This month'],['last_30','Last 30 days'],['last_90','Last 90 days'],['this_year','This year']].map(([k,l])=><option key={k} value={k}>{l}</option>)}
            </select>
            <span style={{ fontSize:12.5, color:C.text3, marginLeft:'auto' }}>{filteredClients.length} client(s)</span>
          </div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:640 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>
                  {['Customer ID','Name','Country','City','Accounts','Volume','Commission','First deposit','Reg date','KYC'].map(h => {
                    const sortable = h==='Volume'||h==='Commission';
                    const col = h==='Volume'?'volume':'commission';
                    const active = sortable && cliSort.col===col;
                    return <th key={h} style={{ ...S.th, cursor:sortable?'pointer':'default', color:active?C.blue:C.text3 }}
                      onClick={()=>sortable&&toggleSort(col)}>{h}{active?(cliSort.dir==='asc'?' ▲':' ▼'):(sortable?' ↕':'')}</th>;
                  })}
                </tr></thead>
                <tbody>
                  {filteredClients.map((c:any,i:number)=>(
                    <tr key={i} className="ibp-row">
                      <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>{c.cus}</td>
                      <td style={{ ...S.td, fontWeight:500 }}>{c.name}</td>
                      <td className="cm" style={S.td}>{c.country||'—'}</td>
                      <td className="cm" style={S.td}>{c.city||'—'}</td>
                      <td className="cm" style={S.td}>{c.accounts>1 ? <span title={`${c.accounts} trading accounts summed`} style={badge(C.blueBg,C.blue)}>{c.accounts}</span> : c.accounts}</td>
                      <td className="cp" style={{ ...S.td, fontWeight:600 }}>{num(c.volume)} lots</td>
                      <td className="cg" style={{ ...S.td, fontWeight:600 }}>{c.commission>0?usd(c.commission):'—'}</td>
                      <td className="cm" style={S.td}>{c.first_deposit ? String(c.first_deposit).slice(0,10) : '—'}</td>
                      <td className="cm" style={S.td}>{c.reg ? String(c.reg).slice(0,10) : '—'}</td>
                      <td style={S.td}><span style={badge(c.kyc==='verified'?C.greenBg:C.amberBg, c.kyc==='verified'?C.green:C.amber)}>{c.kyc||'pending'}</span></td>
                    </tr>
                  ))}
                  {filteredClients.length===0 && <EmptyRow cols={10} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ══ LEADS ══ */}
      {tab==='leads' && (() => {
        const VBadge = ({ ok, label }:{ ok:boolean; label:string }) => (
          <span title={`${label} ${ok?'verified':'not verified'}`} style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:22, height:22, borderRadius:6, background:ok?C.greenBg:C.amberBg, color:ok?C.green:C.amber, fontWeight:800 }}>{ok?'✓':'▢'}</span>
        );
        return (
        <div style={S.page}>
          <div style={{ fontSize:12.5, color:C.text2, marginBottom:11 }}>Registered clients who haven't deposited yet — your warm prospects. <span style={{ color:C.text3 }}>({filteredLeads.length})</span></div>
          <div style={{ display:'flex', gap:9, marginBottom:13, alignItems:'center', flexWrap:'wrap' }}>
            <input placeholder="Search name, customer ID…" value={leadSearch} onChange={e=>setLeadSearch(e.target.value)}
              style={{ ...S.input, width:230, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }} />
            <select value={leadCountry} onChange={e=>setLeadCountry(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All countries</option>{countryOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={leadCity} onChange={e=>setLeadCity(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All cities</option>{cityOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={leadCampaign} onChange={e=>setLeadCampaign(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All campaigns</option>{campaignOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:640 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Customer ID','Name','Country','City','Phone','Email','Campaign','KYC','Reg date'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {filteredLeads.map((c:any,i:number)=>(
                    <tr key={i} className="ibp-row">
                      <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>{c.cus}</td>
                      <td style={{ ...S.td, fontWeight:500 }}>{c.name}</td>
                      <td className="cm" style={S.td}>{c.country||'—'}</td>
                      <td className="cm" style={S.td}>{c.city||'—'}</td>
                      <td style={S.td}><VBadge ok={c.phone_v} label="Phone" /></td>
                      <td style={S.td}><VBadge ok={c.email_v} label="Email" /></td>
                      <td style={S.td}><span style={badge(C.card2, C.text2)}>{c.campaign||'Direct'}</span></td>
                      <td style={S.td}><VBadge ok={c.kyc==='verified'} label="KYC" /></td>
                      <td className="cm" style={S.td}>{c.reg ? String(c.reg).slice(0,10) : '—'}</td>
                    </tr>
                  ))}
                  {filteredLeads.length===0 && <EmptyRow cols={9} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        );
      })()}

      {/* ══ TRADES ══ */}
      {tab==='trades' && <div style={S.page}><LightTrades ibId={ibId} preview={preview} /></div>}

      {/* ══ CAMPAIGNS ══ */}
      {tab==='campaigns' && (
        <div style={S.page}>
          {/* My campaigns + create (E) */}
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:13 }}>
            <div style={S.secLbl}>My campaigns &amp; referral links</div>
            {preview && <button onClick={()=>setCampModal(true)} style={S.btnPri}>+ Create campaign</button>}
          </div>
          <div style={{ ...S.card, overflow:'hidden', marginBottom:18 }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>{['Campaign','Platform','Website','Referral link','Clicks'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
              <tbody>
                {myCampaigns.map((c:any)=>(
                  <tr key={c.id} className="ibp-row">
                    <td style={{ ...S.td, fontWeight:600 }}>{c.name}</td>
                    <td style={S.td}>{c.platform ? <span style={badge(`${PLATFORM_COLORS[c.platform.toLowerCase()]||C.text2}1a`, PLATFORM_COLORS[c.platform.toLowerCase()]||C.text2)}>{c.platform}</span> : '—'}</td>
                    <td className="cm" style={S.td}>{c.website ? <a href={c.website} target="_blank" rel="noreferrer" style={{ color:C.blue }}>{c.website.replace(/^https?:\/\//,'').slice(0,28)}</a> : '—'}</td>
                    <td style={S.td}>
                      <span style={{ fontFamily:'monospace', fontSize:11.5, color:C.blue }}>{c.ref_link}</span>
                      <button onClick={()=>{ navigator.clipboard?.writeText(c.ref_link); setCopied(c.ref_code); setTimeout(()=>setCopied(''),1500); }}
                        style={{ ...S.btnGhost, padding:'3px 8px', marginLeft:8, fontSize:11 }}>{copied===c.ref_code?'✓ Copied':'Copy'}</button>
                    </td>
                    <td className="cp" style={S.td}>{num(c.clicks)}</td>
                  </tr>
                ))}
                {myCampaigns.length===0 && <tr><td colSpan={5} style={{ ...S.td, textAlign:'center', color:C.text3, padding:26 }}>No campaigns yet — create one to get a referral link.</td></tr>}
              </tbody>
            </table>
          </div>

          {campModal && (
            <div onClick={()=>setCampModal(false)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.45)', zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
              <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:420, maxWidth:'95vw', padding:22 }}>
                <div style={{ fontSize:16, fontWeight:800, color:C.text, marginBottom:14 }}>Create campaign</div>
                {[['name','Campaign name *','e.g. Instagram Iraq'],['platform','Platform','facebook / instagram / tiktok / website…'],['website','Website / landing URL','https://…']].map(([k,label,ph]:any)=>(
                  <div key={k} style={{ marginBottom:12 }}>
                    <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>{label}</label>
                    <input value={campForm[k]} onChange={e=>setCampForm((f:any)=>({...f,[k]:e.target.value}))} placeholder={ph}
                      style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                ))}
                <div style={{ fontSize:11.5, color:C.text3, marginBottom:14 }}>A unique referral link will be generated for this campaign.</div>
                <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                  <button onClick={()=>setCampModal(false)} style={S.btnGhost}>Cancel</button>
                  <button onClick={createCampaign} disabled={!campForm.name.trim()} style={{ ...S.btnPri, opacity:campForm.name.trim()?1:0.5 }}>Create</button>
                </div>
              </div>
            </div>
          )}

          {/* Existing (Plugit) referral links — kept working */}
          {refLinks.length > 0 && (
            <div style={{ marginBottom:18 }}>
              <div style={{ ...S.secLbl, display:'flex', alignItems:'center', gap:8 }}>🔗 Your existing referral links <span style={{ fontSize:11, fontWeight:500, color:C.text3 }}>· still active — keep using them</span></div>
              <div style={{ ...S.card, overflow:'hidden' }}>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr>{['Campaign code','Referrer ID','Referral link','Clicks'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                  <tbody>
                    {refLinks.map((l:any,i:number)=>(
                      <tr key={i} className="ibp-row">
                        <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>{l.campaign_code||'—'}</td>
                        <td className="cm" style={S.td}>{l.referrer_id||'—'}</td>
                        <td style={S.td}>
                          <span style={{ fontFamily:'monospace', fontSize:11, color:C.blue }}>{(l.custom_link||'').slice(0,52)}{(l.custom_link||'').length>52?'…':''}</span>
                          <button onClick={()=>{ navigator.clipboard?.writeText(l.custom_link); setCopied(l.custom_link); setTimeout(()=>setCopied(''),1500); }}
                            style={{ ...S.btnGhost, padding:'3px 8px', marginLeft:8, fontSize:11 }}>{copied===l.custom_link?'✓ Copied':'Copy'}</button>
                        </td>
                        <td className="cp" style={S.td}>{num(l.clicks)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ fontSize:12.5, color:C.text2, marginBottom:13 }}>Performance grouped by the campaign each client came from.</div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>{['Campaign','Clients','Funded','Conversion','Deposits','Volume'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
              <tbody>
                {campaigns.map((c:any,i:number)=>{
                  const plat = (c.name||'').split(/[-_ ]/)[0].toLowerCase();
                  const col = PLATFORM_COLORS[plat] || C.text2;
                  return (
                    <tr key={i} className="ibp-row">
                      <td style={S.td}><span style={badge(`${col}1a`, col)}>{c.name}</span></td>
                      <td style={{ ...S.td, fontWeight:600 }}>{num(c.leads)}</td>
                      <td className="cg" style={S.td}>{num(c.ftds)}</td>
                      <td className="cm" style={S.td}>{c.leads?Math.round(c.ftds/c.leads*100):0}%</td>
                      <td className="cg" style={{ ...S.td, fontWeight:600 }}>{usd(c.deposits)}</td>
                      <td className="cp" style={S.td}>{num(c.volume)} lots</td>
                    </tr>
                  );
                })}
                {campaigns.length===0 && <EmptyRow cols={6} loading={loadingPreview} />}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ══ CHALLENGES (gamification: CH1 career + CH2 weekly) ══ */}
      {tab==='challenges' && (
        <div style={S.page}>
          {/* claim banner */}
          <div style={{ ...S.card, padding:'16px 20px', marginBottom:16, display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:12, background:`linear-gradient(100deg, ${C.blueBg}, ${C.card})` }}>
            <div>
              <div style={{ fontSize:16, fontWeight:800, color:C.text }}>🎮 Partner Challenges</div>
              <div style={{ fontSize:12.5, color:C.text2, marginTop:3 }}>Accept a mission — the clock starts and progress counts from that moment. We email you on start, finish & time-out.</div>
            </div>
            <div style={{ textAlign:'right' }}>
              <div style={{ fontSize:11, color:C.text3, textTransform:'uppercase', letterSpacing:'.06em' }}>Ready to claim</div>
              <div style={{ fontSize:22, fontWeight:800, color:C.green }}>{usd(ch2ToClaim)}</div>
            </div>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'minmax(0,1fr) minmax(0,1.1fr)', gap:16, alignItems:'start' }}>
            {/* Career path */}
            <div style={{ ...S.card, padding:18 }}>
              <div style={{ ...S.secLbl, display:'flex', alignItems:'center', gap:8 }}>⚔️ Career Path <span style={{ fontSize:11, fontWeight:500, color:C.text3 }}>· accept to start the timer</span></div>
              <div>
                {(cv.career||[]).map((ch:any,i:number) => {
                  const st = ch.status;
                  const dot = st==='claimed'||st==='completed'?C.green : st==='active'?C.blue : st==='expired'?C.red : C.borderH;
                  const last = i===(cv.career.length-1);
                  return (
                    <div key={ch.key} style={{ display:'flex', gap:13, paddingBottom:last?0:16 }}>
                      <div style={{ display:'flex', flexDirection:'column', alignItems:'center' }}>
                        <div style={{ width:30, height:30, borderRadius:'50%', background: dot+'22', border:`2px solid ${dot}`, color:dot, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, flexShrink:0 }}>{(st==='claimed'||st==='completed')?'✓':ch.stage}</div>
                        {!last && <div style={{ width:2, flex:1, minHeight:24, background:C.border, marginTop:2 }} />}
                      </div>
                      <div style={{ flex:1 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
                          <div>
                            <div style={{ fontSize:13.5, fontWeight:700, color:C.text }}>{ch.name}</div>
                            <div style={{ fontSize:12, color:C.text2, marginTop:2 }}>{ch.desc}</div>
                          </div>
                          <span style={{ ...badge(C.amberBg, C.amber), flexShrink:0 }}>+{usd(ch.reward)}</span>
                        </div>
                        {st==='available' && (
                          <button onClick={()=>preview && chAction('accept', ch.key)} style={{ ...S.btnPri, padding:'7px 14px', marginTop:9 }}>Accept challenge</button>
                        )}
                        {st==='active' && (
                          <div style={{ marginTop:9 }}>
                            <Bar pct={ch.pct||0} color={C.blue} />
                            <div style={{ display:'flex', justifyContent:'space-between', marginTop:6 }}>
                              <span style={{ fontSize:11, color:C.blue, fontWeight:600 }}>In progress · {ch.pct||0}%
                                {ch.progress && Object.keys(ch.progress).length>0 ? ' · '+Object.entries(ch.progress).map(([k,v]:any)=>`${num(v)}/${num(ch.target[k])} ${k}`).join(', ') : ''}</span>
                              <span style={{ fontSize:11, color:C.text3 }}>⏱ {ch.seconds_left!=null ? <Countdown seconds={ch.seconds_left} color={C.amber} /> : '—'}</span>
                            </div>
                          </div>
                        )}
                        {st==='completed' && (
                          <button onClick={()=>preview && chAction('claim', ch.key)} style={{ ...S.btnPri, padding:'7px 14px', marginTop:9, background:C.green }}>🎉 Claim {usd(ch.reward)}</button>
                        )}
                        {st==='claimed' && <div style={{ fontSize:11, color:C.green, marginTop:6, fontWeight:600 }}>✓ Completed · reward credited</div>}
                        {st==='expired' && (
                          <div style={{ marginTop:9, display:'flex', alignItems:'center', gap:10 }}>
                            <span style={{ fontSize:11, color:C.red, fontWeight:600 }}>⏰ Time's up</span>
                            <button onClick={()=>preview && chAction('rechallenge', ch.key)} style={{ ...S.btnGhost, padding:'6px 12px' }}>↻ Re-challenge</button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Weekly challenges */}
            <div>
              <div style={{ ...S.secLbl, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <span style={{ display:'flex', alignItems:'center', gap:8 }}>🏆 Weekly Challenges</span>
                <span style={{ fontSize:11, fontWeight:500, color:C.text3 }}>resets in <Countdown seconds={cv.seconds_to_reset||0} color={C.amber} /></span>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                {(cv.weekly||[]).map((ch:any) => (
                  <div key={ch.key} style={{ ...S.card, padding:14, border:`1px solid ${ch.ready&&!ch.claimed?C.green:C.border}` }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:6 }}>
                      <div style={{ fontSize:18 }}>{ch.emoji}</div>
                      <span style={badge(C.amberBg, C.amber)}>+{usd(ch.reward)}</span>
                    </div>
                    <div style={{ fontSize:13, fontWeight:700, color:C.text }}>{ch.name}</div>
                    <div style={{ fontSize:11.5, color:C.text2, margin:'3px 0 11px', minHeight:30 }}>{ch.desc}</div>
                    <Bar pct={ch.pct} color={ch.ready?C.green:C.blue} />
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginTop:9 }}>
                      <span style={{ fontSize:10.5, color:C.text3 }}>{num(ch.progress)} / {num(ch.target)}</span>
                      {ch.claimed ? <span style={{ fontSize:11, color:C.green, fontWeight:700 }}>✓ Claimed</span>
                        : ch.ready ? <button onClick={()=>preview && chAction('claim-weekly', ch.key)} style={{ ...S.btnPri, padding:'5px 12px', background:C.green }}>Claim {usd(ch.reward)}</button>
                        : <span style={{ fontSize:11, color:C.text3 }}>{ch.pct}%</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ BANNERS ══ */}
      {tab==='marketing' && (
        <div style={S.page}>
          <div style={S.secLbl}>Marketing materials</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap:12 }}>
            {[{name:'Leaderboard banner',size:'728 × 90'},{name:'Medium rectangle',size:'300 × 250'},{name:'Story',size:'1080 × 1920 · IG/TikTok'},{name:'Square post',size:'1080 × 1080 · IG/FB'},{name:'Email template',size:'HTML · AR + EN'},{name:'Landing page',size:`partner.tnfx.co/${ibCode||'IB'}`}].map((m,i)=>(
              <div key={i} style={{ ...S.card, padding:16, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <div><div style={{ fontSize:13, fontWeight:600, color:C.text }}>{m.name}</div><div style={{ fontSize:11.5, color:C.text3, marginTop:2 }}>{m.size}</div></div>
                <button style={S.btnGhost}>↓ Download</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ══ EARNINGS ══ */}
      {tab==='earnings' && (
        <div style={S.page}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:14 }}>
            <Kpi label="Total earned" value={usd(k.commission)} accent={C.amber} icon="💰" />
            <Kpi label="Paid out"     value={usd(k.paid)}       accent={C.green} icon="✔" />
            <Kpi label="Pending"      value={usd(k.unpaid)}     accent={C.amber} icon="⏳" />
            <Kpi label="Rate"         value={`${level} pts/lot`} sub={tierName}  accent={C.purple} icon="🏅" />
          </div>
          {/* Withdraw / internal transfer + payout history */}
          <div style={{ ...S.card, padding:16, marginBottom:16 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12, flexWrap:'wrap' }}>
              <div style={S.secLbl}>Payouts</div>
              <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
                <button onClick={()=>{ setPayForm({ amount:'', to_account:'' }); setPayModal('withdraw'); }} style={S.btnPri}>💸 Withdraw</button>
                <button onClick={()=>{ setPayForm({ amount:'', to_account:(R?.accounts?.[0]?.account||'') }); setPayModal('transfer'); }} style={S.btnGhost}>🔁 Internal transfer</button>
              </div>
            </div>
            {ibOps?.summary && (
              <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:12 }}>
                <MiniStat label="Total paid out" value={usd(ibOps.summary.paid_out)} accent={C.red} />
                <MiniStat label="Withdrawn" value={usd(ibOps.summary.withdrawn)} accent={C.amber} />
                <MiniStat label="Transferred" value={usd(ibOps.summary.transferred)} accent={C.blue} />
              </div>
            )}
            <div style={{ overflowX:'auto', maxHeight:280 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Date','Type','Amount','Method','To','Status'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {(ibOps?.operations||[]).slice(0,50).map((o:any,i:number)=>{
                    const st = o.status==='Approved'?C.green:o.status==='Declined'?C.red:C.amber;
                    return (
                      <tr key={i} className="ibp-row">
                        <td className="cm" style={S.td}>{o.op_date?String(o.op_date).slice(0,10):'—'}</td>
                        <td style={S.td}>{o.request_type?.replace(' Wallet','')}</td>
                        <td style={{ ...S.td, fontWeight:600 }}>{usd(o.amount)}</td>
                        <td className="cm" style={S.td}>{o.payment_type||'—'}</td>
                        <td className="cm" style={S.td}>{o.to_account||'—'}</td>
                        <td style={S.td}><span style={badge(`${st}22`, st)}>{o.status}</span></td>
                      </tr>
                    );
                  })}
                  {(!ibOps || (ibOps.operations||[]).length===0) && <tr><td colSpan={6} style={{ ...S.td, textAlign:'center', color:C.text3, padding:20 }}>No payouts yet</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {/* Level promotion history */}
          {(ibPromos?.promotions?.length > 0) && (
            <div style={{ ...S.card, padding:16, marginBottom:16 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
                <div style={S.secLbl}>🎖 Your level promotions</div>
                <div style={{ marginLeft:'auto', fontSize:11.5, color:C.text3 }}>current: <b style={{ color:C.purple }}>{level} pts/lot ({tierName})</b></div>
              </div>
              <div style={{ position:'relative', paddingLeft:20 }}>
                <div style={{ position:'absolute', left:5, top:4, bottom:4, width:2, background:C.border }} />
                {(ibPromos.promotions||[]).map((p:any,i:number)=>(
                  <div key={i} style={{ position:'relative', marginBottom:14 }}>
                    <div style={{ position:'absolute', left:-20, top:2, width:11, height:11, borderRadius:99, background:C.amber, border:`2px solid ${C.card||'#fff'}` }} />
                    <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                      <span className="cm" style={{ fontSize:12, color:C.text2 }}>{p.date}</span>
                      <span style={badge('#8892a022', C.text2)}>Level {p.from_level}</span>
                      <span style={{ color:C.amber, fontWeight:700 }}>→</span>
                      <span style={badge(`${C.green}22`, C.green)}>Level {p.to_level}</span>
                      <span style={{ fontSize:11, color:C.green }}>Promoted! 🎉</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {payModal && (
            <div onClick={()=>setPayModal(null)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.45)', zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
              <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:400, maxWidth:'95vw', padding:22 }}>
                <div style={{ fontSize:16, fontWeight:800, color:C.text, marginBottom:14 }}>{payModal==='withdraw'?'💸 Request withdrawal':'🔁 Internal transfer'}</div>
                <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>Amount (USD)</label>
                <input type="number" value={payForm.amount} onChange={e=>setPayForm((f:any)=>({...f,amount:e.target.value}))} placeholder="0.00"
                  style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:12 }} />
                {payModal==='transfer' && (<>
                  <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>To trading account</label>
                  <select value={payForm.to_account} onChange={e=>setPayForm((f:any)=>({...f,to_account:e.target.value}))}
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:12 }}>
                    {(R?.accounts||[]).map((a:any,i:number)=><option key={i} value={a.account}>{a.platform} · #{a.account}</option>)}
                    {(!R?.accounts || R.accounts.length===0) && <option value="">No trading accounts</option>}
                  </select>
                </>)}
                <div style={{ fontSize:11.5, color:C.text3, marginBottom:14 }}>{payModal==='transfer'?'Moves commission to your selected trading account. Needs admin approval.':'Withdrawal request — needs admin approval.'}</div>
                <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                  <button onClick={()=>setPayModal(null)} style={S.btnGhost}>Cancel</button>
                  <button onClick={submitPayout} disabled={!(parseFloat(payForm.amount)>0)} style={{ ...S.btnPri, opacity:parseFloat(payForm.amount)>0?1:0.5 }}>Submit request</button>
                </div>
              </div>
            </div>
          )}

          <div style={S.secLbl}>Commission by client</div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:560 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Client','Login','Lots','Pts/lot','Commission','Status'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {commissions.map((t:any,i:number)=>(
                    <tr key={i} className="ibp-row">
                      <td style={{ ...S.td, fontWeight:500 }}>{t.client_name}</td>
                      <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>#{t.client_login}</td>
                      <td className="cp" style={S.td}>{num(t.lots)}</td>
                      <td className="cm" style={S.td}>{t.pts_per_lot}</td>
                      <td className="ca" style={{ ...S.td, fontWeight:700 }}>{usd(t.commission_usd)}</td>
                      <td style={S.td}><span style={badge(t.status==='paid'?C.greenBg:C.amberBg, t.status==='paid'?C.green:C.amber)}>{t.status}</span></td>
                    </tr>
                  ))}
                  {commissions.length===0 && <EmptyRow cols={6} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Scoped overrides — the admin app injects global dark rules (td/input/hover);
          beat them with higher-specificity !important so the light portal stays light. */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        .ibp *::-webkit-scrollbar{width:10px;height:10px}
        .ibp *::-webkit-scrollbar-thumb{background:#cfd6e2;border-radius:99px}
        .ibp *::-webkit-scrollbar-thumb:hover{background:#b6c0d0}
        .ibp *::-webkit-scrollbar-track{background:transparent}
        .ibp-tab:hover{color:${C.blue} !important}
        .ibp td{color:${C.text} !important}
        .ibp th{color:${C.text3} !important}
        .ibp td.cg{color:${C.green} !important}
        .ibp td.cr{color:${C.red} !important}
        .ibp td.cb{color:${C.blue} !important}
        .ibp td.cp{color:${C.purple} !important}
        .ibp td.ca{color:${C.amber} !important}
        .ibp td.cm{color:${C.text2} !important}
        .ibp tr:hover td{background:transparent !important}
        .ibp-row:hover td{background:${C.soft} !important}
        .ibp input, .ibp select, .ibp textarea{background:#ffffff !important; color:${C.text} !important; border-color:${C.borderH} !important}
        .ibp input::placeholder{color:#9aa6b8}
        @keyframes ibpShimmer{0%{background-position:-160% 0}100%{background-position:160% 0}}
        @keyframes ibpPulse{0%,100%{box-shadow:0 0 0 0 rgba(47,107,255,0.45)}50%{box-shadow:0 0 0 7px rgba(47,107,255,0)}}
        @keyframes ibpFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
        .ibp-shimmer{background:linear-gradient(100deg, rgba(255,255,255,0) 20%, rgba(255,255,255,0.55) 50%, rgba(255,255,255,0) 80%);background-size:200% 100%;animation:ibpShimmer 1.8s linear infinite}
        .ibp-pulse{animation:ibpPulse 2s ease-out infinite}
        .ibp-float{animation:ibpFloat 2.8s ease-in-out infinite}
        .ibp-bar-fill{transition:width .9s cubic-bezier(.22,1,.36,1)}
      `}</style>
    </div>
  );
}
