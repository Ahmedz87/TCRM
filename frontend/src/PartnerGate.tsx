import React, { useState, useEffect, useRef, useMemo } from 'react';
import { apiGet, apiPost } from './api';
import { COUNTRIES, byIso, isoFlag, normalizeNational, validNational, e164 } from './countries';
import IBPortal from './IBPortal';
import IBAdmin from './IBAdmin';
import CommissionProfiles from './CommissionProfiles';
import ChallengeSettings from './ChallengeSettings';
import tnfxLogo from './assets/tnfx-logo.png';
import tnfxMark from './assets/tnfx-mark.png';
import dashShot from './assets/dashboard-capture.jpg';

/* ══════════════════════════════════════════════════════════════════════════
   "The Ledger" — institutional fintech landing for partner1.tnfx.co.
   Design rules: near-black layered surfaces, 1px hairlines instead of boxes,
   tabular numerals do the persuasion, orange ONLY where money or action lives.
   No emoji in chrome, no floating mascots, one-shot restrained motion.
   ══════════════════════════════════════════════════════════════════════════ */
const T = {
  bg0: '#14161D', bg1: '#1B1E27', bg2: '#242836',
  line: 'rgba(255,255,255,0.09)', line2: 'rgba(255,255,255,0.18)',
  t1: '#F5F5F3', t2: 'rgba(245,245,243,0.68)', t3: 'rgba(245,245,243,0.52)',
  grad: 'linear-gradient(135deg,#ff4700,#ff9100)', acc: '#ff9100',
};

const FONT = `-apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`;

const PG_CSS = `
html { scroll-behavior: smooth; }
.pg-land { font-variant-numeric: tabular-nums; }
#commission, #how, #tools { scroll-margin-top: 76px; }
.pg-land button, .pg-auth button { font-family: ${FONT}; }
.pg-land :focus-visible, .pg-auth :focus-visible { outline: 2px solid #ff9100; outline-offset: 2px; }

/* reveal-on-scroll (progressive enhancement: visible unless .js pre-state applies) */
.rv { opacity: 1; }
.js .rv:not(.in) { opacity: 0; transform: translateY(14px); }
.js .rv.in { opacity: 1; transform: none;
  transition: opacity .5s cubic-bezier(.16,1,.3,1), transform .5s cubic-bezier(.16,1,.3,1); }

/* gradient text — guarded so unsupported browsers get solid orange, never invisible */
.pg-gradtxt { color: #ff9100; }
@supports (-webkit-background-clip: text) {
  .pg-gradtxt { background: linear-gradient(135deg,#ff4700,#ff9100);
    -webkit-background-clip: text; background-clip: text; color: transparent; }
}

/* buttons */
.pg-cta { background: linear-gradient(135deg,#ff4700,#ff9100); color: #fff; border: none;
  font-weight: 600; letter-spacing: .01em; cursor: pointer; border-radius: 10px;
  transition: transform .15s ease, filter .15s ease; }
.pg-cta:hover { transform: translateY(-1px); filter: brightness(1.08); }
.pg-ghost { background: transparent; color: #F5F5F3; border: 1px solid rgba(255,255,255,0.16);
  font-weight: 600; cursor: pointer; border-radius: 10px; transition: border-color .15s ease, background .15s ease; }
.pg-ghost:hover { border-color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.04); }

/* top bar blur fallback */
.pg-top { background: rgba(20,22,29,0.82); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
@supports not (backdrop-filter: blur(12px)) { .pg-top { background: rgba(20,22,29,0.97); } }

/* dashboard capture pieces — off-centre, softly present */
.pg-shot { position: absolute; border-radius: 14px; border: 1px solid rgba(255,255,255,0.13);
  box-shadow: 0 40px 90px rgba(0,0,0,0.5); filter: blur(0.7px) brightness(0.98);
  pointer-events: none; user-select: none; }
.pg-heroshot { display: block; }
@media (max-width: 1020px) { .pg-heroshot { display: none; } }
.pg-authright { display: flex; }
@media (max-width: 880px) { .pg-authright { display: none !important; } .pg-authgrid { grid-template-columns: minmax(0,1fr) !important; } }

/* commission rail: 6 columns >=1100px, ledger rows below (judge warning: 900px overflows) */
.pg-rail-d { display: grid; grid-template-columns: repeat(6, 1fr); }
.pg-rail-m { display: none; }
.pg-col { position: relative; padding: 22px 14px 0; transition: background .18s ease; }
.pg-col + .pg-col { border-left: 1px solid rgba(255,255,255,0.09); }
.pg-col:hover { background: #1B1E27; }
.pg-col .pg-rate { transition: none; }
@supports (-webkit-background-clip: text) {
  .pg-col:hover .pg-rate { background: linear-gradient(135deg,#ff4700,#ff9100);
    -webkit-background-clip: text; background-clip: text; color: transparent; }
}
.pg-tick { position: absolute; left: 50%; transform: translateX(-50%) scaleX(0); transform-origin: left;
  width: 44px; height: 2px; background: rgba(255,255,255,0.25); z-index: 2; }
.js .in .pg-tick { animation: pgTick .4s ease-out forwards; }
.pg-tick.top { background: linear-gradient(90deg,#ff4700,#ff9100); }
.pg-col:hover .pg-tick { background: linear-gradient(90deg,#ff4700,#ff9100); }
@keyframes pgTick { from { transform: translateX(-50%) scaleX(0); } to { transform: translateX(-50%) scaleX(1); } }
@keyframes pgStepIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }
.pg-stepfade { animation: pgStepIn .34s cubic-bezier(.16,1,.3,1); }

/* nav / responsive */
.pg-nav { display: flex; gap: 28px; }
.pg-login-txt { display: none; }
.pg-stick { display: none; }
.pg-topline { overflow-x: clip; }
@media (max-width: 1099.98px) {
  .pg-rail-d { display: none; }
  .pg-rail-m { display: block; }
}
@media (max-width: 900px) {
  .pg-nav { display: none; }
  .pg-2col { grid-template-columns: 1fr !important; }
  .pg-steps { grid-template-columns: 1fr 1fr !important; }
  .pg-bull { display: none; }
}
@media (max-width: 768px) {
  .pg-stick { display: block; }
  .pg-land { padding-bottom: 84px; }
}
@media (max-width: 720px) {
  .pg-proof { grid-template-columns: 1fr 1fr !important; }
  .pg-proof > div { padding: 22px 10px !important;
    border-left: none !important; border-top: 1px solid rgba(255,255,255,0.09) !important; }
  .pg-proof > div:nth-child(-n+2) { border-top: none !important; }
  .pg-proof > div:nth-child(even) { border-left: 1px solid rgba(255,255,255,0.09) !important; }
}
@media (max-width: 640px) { .pg-steps { grid-template-columns: 1fr !important; } }
@media (max-width: 560px) { .pg-brandtag { display: none; } }
@media (max-width: 460px) {
  .pg-login-btn { display: none; }
  .pg-login-txt { display: inline; }
  .pg-toplogo { height: 21px !important; }
  .pg-topcta { padding: 0 13px !important; font-size: 13px !important; }
  .pg-topline { gap: 8px !important; padding: 0 14px !important; }
}

/* spinner — the one allowed loop (status indicator) */
.pg-spin { display: inline-block; width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.35); border-top-color: #fff; animation: pgSpin .8s linear infinite;
  vertical-align: -2px; margin-right: 8px; }
@keyframes pgSpin { to { transform: rotate(360deg); } }

/* auth tab underline */
.pg-tabu { transition: transform .2s cubic-bezier(.16,1,.3,1); }

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .js .rv:not(.in) { opacity: 1; transform: none; }
  .pg-land *, .pg-auth * { animation-duration: .01ms !important; transition-duration: .01ms !important; }
  .pg-tick { transform: translateX(-50%) scaleX(1); }
}
`;

/* Real commission ladder — ib_tier_requirements is the source of truth (Jul 2026). */
const TIERS = [
  { name: 'Bronze',    rate: 5,  dep: '',         lots: '',      accts: '',    entry: true },
  { name: 'Silver',    rate: 6,  dep: '$1,500',   lots: '20',    accts: '5' },
  { name: 'Golden',    rate: 7,  dep: '$10,000',  lots: '50',    accts: '15' },
  { name: 'Diamond',   rate: 8,  dep: '$100,000', lots: '200',   accts: '40' },
  { name: 'Legendary', rate: 9,  dep: '$300,000', lots: '1,000', accts: '100' },
  { name: 'Prime IB',  rate: 10, dep: '$500,000', lots: '2,500', accts: '200', top: true },
];

/* One-shot count-up for the proof rail (reduced-motion shows final instantly). */
function CountUp({ to, prefix = '', suffix = '', grad = false }:
                 { to: number; prefix?: string; suffix?: string; grad?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [val, setVal] = useState(0);
  const done = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setVal(to); return; }
    let dead = false;
    const io = new IntersectionObserver((es) => {
      if (!es[0].isIntersecting || done.current) return;
      done.current = true;
      const t0 = performance.now(), dur = 1000;
      const step = (t: number) => {
        if (dead) return;
        const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
        setVal(Math.round(to * e));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      io.disconnect();
    }, { threshold: 0.4 });
    io.observe(el);
    return () => { dead = true; io.disconnect(); };
  }, [to]);
  return (
    <span ref={ref} className={grad ? 'pg-gradtxt' : undefined}
      style={{ fontSize: 'clamp(30px, 4vw, 44px)', fontWeight: 700, letterSpacing: '-0.03em', color: grad ? undefined : T.t1 }}>
      {prefix}{val.toLocaleString('en-US')}{suffix}
    </span>
  );
}

/** Admin view on the partner site: search + pick any IB, then see the portal EXACTLY as
 *  that IB sees it (same component, same data, staff token). */
function StaffIbPicker({ onPick }: { onPick: (ib: any) => void }) {
  const [q, setQ] = useState('');
  const [ibs, setIbs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    let stale = false;   // don't let an earlier slow response overwrite newer results
    const t = setTimeout(() => {
      apiGet(`/ibs?search=${encodeURIComponent(q)}&page_size=30&sort=clients`)
        .then((d: any) => { if (!stale) setIbs(d.ibs || []); })
        .catch(() => { if (!stale) setIbs([]); })
        .finally(() => { if (!stale) setLoading(false); });
    }, 250);
    return () => { stale = true; clearTimeout(t); };
  }, [q]);
  return (
    <div style={{ maxWidth:760, margin:'40px auto', padding:'0 16px' }}>
      <div style={{ fontSize:19, fontWeight:800, color:'#101828', marginBottom:4 }}>View as IB</div>
      <div style={{ fontSize:12.5, color:'#667085', marginBottom:14 }}>
        Pick a partner to see their portal exactly as they see it — dashboard, clients, commission, links.</div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search IB by name, code, email or phone…"
        autoFocus
        style={{ width:'100%', padding:'12px 14px', background:'#fff', border:'1px solid #d6dbe3', borderRadius:10,
                 color:'#1c2430', fontSize:14, outline:'none', boxSizing:'border-box', marginBottom:12 }} />
      <div style={{ background:'#fff', border:'1px solid #e4e7ec', borderRadius:14, overflow:'hidden' }}>
        {loading && <div style={{ padding:18, color:'#98a2b3', fontSize:13 }}>Searching…</div>}
        {!loading && ibs.length === 0 && <div style={{ padding:18, color:'#98a2b3', fontSize:13 }}>No IBs found.</div>}
        {!loading && ibs.map((ib: any) => (
          <div key={ib.id} onClick={() => onPick(ib)}
            style={{ display:'flex', alignItems:'center', gap:12, padding:'11px 16px', cursor:'pointer',
                     borderBottom:'1px solid #f2f4f7' }}
            onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
            <div style={{ width:34, height:34, borderRadius:9, background:'#eef4ff', color:'#3358d4',
                          display:'flex', alignItems:'center', justifyContent:'center', fontWeight:800 }}>
              {(ib.name || '?')[0]}</div>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:13.5, fontWeight:700, color:'#101828', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                {ib.name} {ib.ib_code ? <span style={{ color:'#98a2b3', fontWeight:500 }}>· {ib.ib_code}</span> : null}</div>
              <div style={{ fontSize:11.5, color:'#667085' }}>{ib.email || '—'} · {ib.country || ''}</div>
            </div>
            <div style={{ fontSize:11.5, color:'#475467', textAlign:'right' }}>
              <div><b>{ib.total_clients || 0}</b> clients</div>
              <div>level {ib.ib_level || 5}{ib.status === 'pending' ? ' · PENDING' : ''}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


/* ── Admin "IB Requests" queue: signup applications. IB-manager acts, sales-manager reads ── */
function IbRequests() {
  const [reqs, setReqs] = useState<any>(null);
  const [act, setAct] = useState<any>(null);   // {ib, level}
  const load = () => apiGet('/ib-admin/requests?status=pending').then(setReqs).catch(() => setReqs({ can_act:false, requests:[] }));
  useEffect(() => { load(); }, []);
  if (!reqs) return <div style={{ padding:26, color:'#98a2b3' }}>Loading…</div>;
  const canAct = reqs.can_act;
  const doAction = async (ib:any, action:string, level?:number) => {
    try { await apiPost(`/ib-admin/requests/${ib.id}/action`, { action, ib_level: level, agent_id: ib._agent }); setAct(null); load(); }
    catch (e:any) { alert(e?.message || 'Action failed'); }
  };
  return (
    <div style={{ padding:'20px 24px', color:'#e8e8e8' }}>
      <div style={{ display:'flex', alignItems:'baseline', gap:12, marginBottom:6 }}>
        <div style={{ fontSize:19, fontWeight:800, color:'#fff' }}>IB Requests</div>
        <span style={{ fontSize:12, color:'#98a2b3' }}>{reqs.requests.length} pending{canAct ? '' : ' · read-only (sales manager)'}</span>
      </div>
      <div style={{ fontSize:12.5, color:'#98a2b3', marginBottom:16 }}>
        New partner applications. {canAct ? 'Approve to move forward; Activate sets the starting grade and links their MT agent.' : 'Only the IB manager can approve — you have read access.'}</div>
      <div style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:12, overflow:'auto' }}>
        <table style={{ borderCollapse:'collapse', width:'100%', minWidth:820 }}>
          <thead><tr style={{ background:'#2a3140' }}>
            {['Applicant','Contact','Country','Experience','Social','Applied', canAct ? 'Action' : ''].map(h=>
              <th key={h} style={{ padding:'9px 12px', fontSize:11, color:'#98a2b3', textAlign:'left', fontWeight:700, whiteSpace:'nowrap' }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {reqs.requests.map((r:any)=>(
              <tr key={r.id} style={{ borderTop:'1px solid #303848' }}>
                <td style={{ padding:'10px 12px' }}><div style={{ fontWeight:700, color:'#fff', fontSize:13 }}>{r.name}</div>
                  {r.bio && <div style={{ fontSize:11, color:'#98a2b3', maxWidth:220, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={r.bio}>{r.bio}</div>}</td>
                <td style={{ padding:'10px 12px', fontSize:12 }}><div>{r.email}</div><div style={{ color:'#98a2b3' }}>{r.phone}</div></td>
                <td style={{ padding:'10px 12px', fontSize:12 }}>{r.country||'—'}{r.city?`, ${r.city}`:''}</td>
                <td style={{ padding:'10px 12px', fontSize:12, maxWidth:230 }}>
                  <div style={{ fontWeight:600 }}>{r.profile?.status==='experienced' ? `Experienced${r.profile?.years?` · ${r.profile.years}y`:''}` : 'New to this'}</div>
                  {(r.profile?.companies||[]).map((c:any,i:number)=> c?.name ? (
                    <div key={i} style={{ color:'#98a2b3', fontSize:11 }}>• {c.name}{c.size?` — ${c.size} clients`:''}</div>
                  ) : null)}
                  {(r.profile?.sources?.length) ? <div style={{ color:'#7fb0ff', fontSize:10.5, marginTop:2 }}>{r.profile.sources.map((s:string)=>s==='online'?'Social/Web':'Relations').join(' · ')}</div> : null}
                  {r.profile?.relations_note ? <div style={{ color:'#98a2b3', fontSize:10.5, fontStyle:'italic' }}>{r.profile.relations_note}</div> : null}
                </td>
                <td style={{ padding:'10px 12px', fontSize:12 }}>{(r.social_links||[]).slice(0,5).map((s:any,i:number)=>(
                  <a key={i} href={absUrl(s.url)} target="_blank" rel="noreferrer" title={`${s.platform}${s.name?` · ${s.name}`:''} — ${absUrl(s.url)}`} style={{ display:'inline-flex', alignItems:'center', gap:2, color:'#7fb0ff', marginRight:9, textDecoration:'none', whiteSpace:'nowrap' }}>
                    {s.verified && <span style={{ color:'#2ecc71' }}>✓</span>}{s.label||s.platform}</a>
                ))}{(r.social_links||[]).length===0 && '—'}</td>
                <td style={{ padding:'10px 12px', fontSize:11.5, color:'#98a2b3' }}>{r.created_at ? String(r.created_at).slice(0,10) : '—'}</td>
                {canAct && <td style={{ padding:'10px 12px', whiteSpace:'nowrap' }}>
                  <button onClick={()=>setAct({ ib:r, level:5 })} style={{ padding:'5px 12px', borderRadius:7, border:'none', background:'#00b57f', color:'#fff', cursor:'pointer', fontSize:12, fontWeight:700, marginRight:6 }}>Activate</button>
                  <button onClick={()=>doAction(r,'reject')} style={{ padding:'5px 10px', borderRadius:7, border:'1px solid #6b3030', background:'transparent', color:'#ff8f80', cursor:'pointer', fontSize:12 }}>Reject</button>
                </td>}
              </tr>
            ))}
            {reqs.requests.length===0 && <tr><td colSpan={7} style={{ padding:26, textAlign:'center', color:'#667085' }}>No pending applications.</td></tr>}
          </tbody>
        </table>
      </div>
      {act && (
        <div onClick={()=>setAct(null)} style={{ position:'fixed', inset:0, zIndex:200, background:'rgba(0,0,0,0.6)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
          <div onClick={e=>e.stopPropagation()} style={{ width:400, maxWidth:'95vw', background:'#242b38', border:'1px solid #3a4356', borderRadius:14, padding:22, color:'#fff' }}>
            <div style={{ fontSize:16, fontWeight:800, marginBottom:4 }}>Activate {act.ib.name}</div>
            <div style={{ fontSize:12.5, color:'#98a2b3', marginBottom:16 }}>Set the starting grade (evaluate how big they are) and optionally link their MT agent account.</div>
            <label style={{ fontSize:11.5, color:'#98a2b3', fontWeight:600, display:'block', marginBottom:5 }}>Starting grade</label>
            <select value={act.level} onChange={e=>setAct({ ...act, level:+e.target.value })} style={{ width:'100%', padding:'9px 11px', background:'#2a3140', border:'1px solid #3a4356', borderRadius:8, color:'#fff', fontSize:13, marginBottom:12 }}>
              {[[5,'Bronze'],[6,'Silver'],[7,'Golden'],[8,'Diamond'],[9,'Legendary'],[10,'Prime IB']].map(([lv,nm]:any)=><option key={lv} value={lv}>IB-{lv} · {nm}</option>)}
            </select>
            <label style={{ fontSize:11.5, color:'#98a2b3', fontWeight:600, display:'block', marginBottom:5 }}>MT agent login (optional)</label>
            <input onChange={e=>{ act.ib._agent = e.target.value; }} placeholder="e.g. 335001706" style={{ width:'100%', padding:'9px 11px', background:'#2a3140', border:'1px solid #3a4356', borderRadius:8, color:'#fff', fontSize:13, marginBottom:16, boxSizing:'border-box' }} />
            <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
              <button onClick={()=>setAct(null)} style={{ padding:'8px 14px', borderRadius:8, border:'1px solid #3a4356', background:'transparent', color:'#98a2b3', cursor:'pointer' }}>Cancel</button>
              <button onClick={()=>doAction(act.ib,'activate',act.level)} style={{ padding:'8px 18px', borderRadius:8, border:'none', background:'#00b57f', color:'#fff', fontWeight:700, cursor:'pointer' }}>Activate partner</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Announcements admin: broadcast a banner to every IB's dashboard ── */
function AnnouncementsAdmin() {
  const [items, setItems] = useState<any[]>([]);
  const [f, setF] = useState<any>({ title:'', body:'', tone:'info' });
  const load = () => apiGet('/ib-admin/announcements').then((d:any)=>setItems(d.items||[])).catch(()=>{});
  useEffect(() => { load(); }, []);
  const post = async () => { if (!f.title.trim()) return; await apiPost('/ib-admin/announcements', f); setF({ title:'', body:'', tone:'info' }); load(); };
  const del = async (id:number) => { await apiPost('/ib-admin/announcements', { id, delete:true }); load(); };
  const inp:React.CSSProperties = { width:'100%', padding:'10px 12px', background:'#2a3140', border:'1px solid #3a4356', borderRadius:8, color:'#fff', fontSize:13, boxSizing:'border-box', marginBottom:10 };
  return (
    <div style={{ padding:'20px 24px', color:'#e8e8e8', maxWidth:720 }}>
      <div style={{ fontSize:19, fontWeight:800, color:'#fff', marginBottom:4 }}>Announcements</div>
      <div style={{ fontSize:12.5, color:'#98a2b3', marginBottom:16 }}>Post a banner that appears on every IB's dashboard — promotions, news, reminders.</div>
      <div style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:12, padding:16, marginBottom:18 }}>
        <input value={f.title} onChange={e=>setF({...f,title:e.target.value})} placeholder="Title (e.g. Ramadan 100% deposit bonus is live)" style={inp} />
        <textarea value={f.body} onChange={e=>setF({...f,body:e.target.value})} rows={2} placeholder="Message (optional)" style={{ ...inp, resize:'vertical' }} />
        <div style={{ display:'flex', gap:10, alignItems:'center' }}>
          <select value={f.tone} onChange={e=>setF({...f,tone:e.target.value})} style={{ ...inp, width:'auto', marginBottom:0 }}>
            <option value="info">Info (blue)</option><option value="promo">Promo (green)</option><option value="warn">Important (amber)</option>
          </select>
          <button onClick={post} disabled={!f.title.trim()} style={{ marginLeft:'auto', padding:'9px 20px', borderRadius:8, border:'none', background:'#00b57f', color:'#fff', fontWeight:700, cursor:'pointer', opacity:f.title.trim()?1:0.5 }}>Publish</button>
        </div>
      </div>
      {items.map(a=>(
        <div key={a.id} style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:10, padding:'12px 14px', marginBottom:9, display:'flex', alignItems:'center', gap:12, opacity:a.active?1:0.5 }}>
          <div style={{ flex:1 }}>
            <div style={{ fontWeight:700, color:'#fff', fontSize:13 }}>📣 {a.title} {!a.active && <span style={{ fontSize:11, color:'#98a2b3' }}>(hidden)</span>}</div>
            {a.body && <div style={{ fontSize:12, color:'#98a2b3', marginTop:2 }}>{a.body}</div>}
            <div style={{ fontSize:11, color:'#667085', marginTop:2 }}>{a.at ? String(a.at).slice(0,10) : ''}</div>
          </div>
          {a.active && <button onClick={()=>del(a.id)} style={{ padding:'5px 12px', borderRadius:7, border:'1px solid #6b3030', background:'transparent', color:'#ff8f80', cursor:'pointer', fontSize:12 }}>Hide</button>}
        </div>
      ))}
    </div>
  );
}

/* ── Staff workspace at partner1: sidebar with everything IB-admin ─────────── */
const ADMIN_TABS = [
  { key: 'ib_admin',   icon: '🤝', label: 'IB Admin',            desc: 'All IBs — profiles, levels, payouts' },
  { key: 'requests',   icon: '📥', label: 'IB Requests',         desc: 'New partner applications — approve / activate' },
  { key: 'announce',   icon: '📣', label: 'Announcements',       desc: 'Broadcast a banner to every IB' },
  { key: 'view_as',    icon: '👁️', label: 'View as IB',          desc: 'See the portal exactly as an IB sees it' },
  { key: 'challenges', icon: '🏆', label: 'Challenges & Career', desc: 'Set career stages + weekly challenges' },
  { key: 'profiles',   icon: '💰', label: 'Commission Profiles', desc: 'Per-level commission rules' },
];

function PartnerAdmin({ me }: { me: any }) {
  const [tab, setTab] = useState('ib_admin');
  // IBAdmin's permission checks (Zainab-only level changes) read these fields:
  const staffUser = { email: me.email || '', full_name: me.full_name || me.name || '', role: me.role || '' };
  // same visibility as the my1 sidebar: settings pages are admin-level only
  const isAdmin = ['super_admin', 'admin', 'director'].includes(me.role || '');
  // IB manager + admins + sales manager see Requests; only admins see the settings pages
  const canSeeReq = isAdmin || ['ib_manager', 'sales_manager'].includes(me.role || '');
  const tabs = ADMIN_TABS.filter(t =>
    ((t.key !== 'requests' && t.key !== 'announce') || canSeeReq) && (isAdmin || !['challenges', 'profiles'].includes(t.key)));
  const lightPane = tab === 'view_as';

  // View as IB opens a NEW TAB (?view_ib=<id>) with the raw portal — zero admin chrome,
  // pixel-identical to what the IB sees; closing the tab brings you back here.
  const openIbTab = (ib: any) => window.open(`/?view_ib=${ib.id}`, '_blank');

  return (
    <div style={{ display:'flex', height:'calc(100vh - 49px)', overflow:'hidden' }}>
      <div style={{ width:212, flexShrink:0, background:'#101828', borderRight:'1px solid #1f2937',
                    padding:'14px 10px', display:'flex', flexDirection:'column', gap:4 }}>
        <div style={{ fontSize:10.5, fontWeight:800, color:'#667085', letterSpacing:1.2, padding:'2px 10px 8px' }}>IB SYSTEM — ADMIN</div>
        {tabs.map(t => (
          <div key={t.key} onClick={() => setTab(t.key)} title={t.desc}
            style={{ display:'flex', alignItems:'center', gap:9, padding:'10px 10px', borderRadius:9, cursor:'pointer',
                     background: tab === t.key ? '#1d2939' : 'transparent',
                     color: tab === t.key ? '#fff' : '#98a2b3', fontSize:13, fontWeight: tab === t.key ? 700 : 500 }}>
            <span style={{ fontSize:15 }}>{t.icon}</span>{t.label}
          </div>
        ))}
        <div style={{ marginTop:'auto', fontSize:10.5, color:'#475467', padding:'0 10px 4px', lineHeight:1.5 }}>
          Same data as my1 — anything you change here shows in the IBs' portals instantly.</div>
      </div>
      <div style={{ flex:1, minWidth:0, overflow: tab === 'ib_admin' ? 'hidden' : 'auto',
                    display:'flex', flexDirection:'column',
                    background: lightPane ? '#f4f6f9' : 'var(--bg-main,#20252f)', color: lightPane ? '#101828' : 'var(--text,#fff)' }}>
        {tab === 'ib_admin'   && <IBAdmin user={staffUser} />}
        {tab === 'requests'   && <IbRequests />}
        {tab === 'announce'   && <AnnouncementsAdmin />}
        {tab === 'profiles'   && <CommissionProfiles />}
        {tab === 'challenges' && <ChallengeSettings />}
        {tab === 'view_as'    && <StaffIbPicker onPick={openIbTab} />}
      </div>
    </div>
  );
}

/* ── shared landing building blocks ───────────────────────────────────────── */
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
      <span style={{ width:20, height:1, background:T.grad, display:'inline-block' }} />
      <span style={{ fontSize:12, fontWeight:600, letterSpacing:'0.14em', color:T.t3, textTransform:'uppercase' }}>{children}</span>
    </div>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return <h2 style={{ fontSize:'clamp(28px, 4vw, 42px)', fontWeight:650, letterSpacing:'-0.025em',
                      lineHeight:1.1, color:T.t1, margin:'0 0 14px' }}>{children}</h2>;
}

/* ── Multi-step new-IB signup wizard (desk spec Jul 15 2026) ──
   basics → email OTP → mobile OTP → questionnaire + social links → agreement → submit. */
// social catalog with real brand domains (the client-side hard gate mirrors the server's).
// How an IB enters each platform:
//  • prefix   — we show a fixed domain (facebook.com/…) and they type only the handle
//  • username — they type just a @username, no link (we build the URL); these sites block bots
//  • url      — a full link (website / other)
// `multi` platforms (Telegram) let an IB add several channels / groups.
const SOCIAL_CAT: any[] = [
  { k:'facebook',  label:'Facebook',  mode:'prefix',   prefix:'facebook.com/', ph:'yourpage',    domains:['facebook.com','fb.com','fb.me'] },
  { k:'youtube',   label:'YouTube',   mode:'prefix',   prefix:'youtube.com/',  ph:'@yourchannel', domains:['youtube.com','youtu.be'] },
  { k:'telegram',  label:'Telegram',  mode:'prefix',   prefix:'t.me/',         ph:'yourchannel',  multi:true, domains:['t.me','telegram.me'] },
  { k:'instagram', label:'Instagram', mode:'username', build:(u:string)=>`instagram.com/${u}`,    ph:'username', domains:['instagram.com','instagr.am'] },
  { k:'tiktok',    label:'TikTok',    mode:'username', build:(u:string)=>`tiktok.com/@${u}`,       ph:'username', domains:['tiktok.com'] },
  { k:'snapchat',  label:'Snapchat',  mode:'username', build:(u:string)=>`snapchat.com/add/${u}`, ph:'username', domains:['snapchat.com'] },
  { k:'x',         label:'X',         mode:'username', build:(u:string)=>`x.com/${u}`,             ph:'username', domains:['x.com','twitter.com'] },
  { k:'whatsapp',  label:'WhatsApp',  mode:'prefix',   prefix:'wa.me/',        ph:'9647…',        domains:['wa.me','whatsapp.com'] },
  { k:'website',   label:'Website',   mode:'url', ph:'https://yoursite.com', domains:[] },
  { k:'other',     label:'Other',     mode:'url', ph:'https://…', domains:[] },
];
const socialCat = (k:string) => SOCIAL_CAT.find(c=>c.k===k);
// Build the full URL we verify/store from what the IB typed (a handle, a @username, or a full link).
// force an ABSOLUTE https:// URL — a protocol-less "facebook.com/x" is treated as a RELATIVE link
// by the browser (→ my1.tnfx.co/facebook.com/x), which is exactly the IB-Requests bug we're fixing.
const absUrl = (u:string):string => {
  const s = (u||'').trim();
  return !s ? '#' : (/^https?:\/\//i.test(s) ? s : 'https://' + s.replace(/^\/+/,''));
};
const buildSocialUrl = (cat:any, raw:string):string => {
  const v = (raw||'').trim();
  if (!cat || !v) return '';
  if (cat.mode==='url') return absUrl(v);
  if (cat.mode==='username') return absUrl(cat.build(v.replace(/^@+/,'').replace(/\s+/g,'')));
  // prefix: strip a pasted full link back down to just the handle, then re-prefix
  let h = v.replace(/^https?:\/\//i,'');
  (cat.domains||[]).forEach((d:string)=>{ h = h.replace(new RegExp('^'+d.replace(/\./g,'\\.')+'/?','i'),''); });
  return absUrl(cat.prefix + h.replace(/^\/+/,''));
};
// client-side domain gate — a "telegram" link that isn't t.me/telegram.me is rejected before we even call the server.
const domainOk = (platform:string, url:string) => {
  const cat = socialCat(platform);
  if (!cat || !cat.domains.length) return true;   // website / other → any host
  let u = (url||'').trim(); if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  let host = ''; try { host = new URL(u).hostname.toLowerCase(); } catch { return false; }
  return cat.domains.some((d:string) => host === d || host.endsWith('.' + d));
};

// inline brand logos (self-contained SVG — scale crisply on mobile, no external requests)
function SocialLogo({ k, size=26 }: { k:string; size?:number }) {
  const p = { width:size, height:size, viewBox:'0 0 24 24' };
  switch (k) {
    case 'facebook': return <svg {...p}><rect width="24" height="24" rx="6" fill="#1877F2"/><path fill="#fff" d="M15.5 8.4h-1.6c-.3 0-.6.3-.6.7V11h2.1l-.3 2.2h-1.8V19h-2.3v-5.8H8.8V11h1.9V9c0-1.6 1-2.9 2.9-2.9h1.9v2.3z"/></svg>;
    case 'instagram': return <svg {...p}><defs><linearGradient id="igG" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#FEDA75"/><stop offset=".45" stopColor="#FA7E1E"/><stop offset="1" stopColor="#D62976"/></linearGradient></defs><rect width="24" height="24" rx="6" fill="url(#igG)"/><rect x="6" y="6" width="12" height="12" rx="4" fill="none" stroke="#fff" strokeWidth="1.6"/><circle cx="12" cy="12" r="3" fill="none" stroke="#fff" strokeWidth="1.6"/><circle cx="16.3" cy="7.7" r="1" fill="#fff"/></svg>;
    case 'telegram': return <svg {...p}><rect width="24" height="24" rx="12" fill="#29A9EB"/><path fill="#fff" d="M5.6 11.7l12-4.6c.6-.2 1 .1.8.9l-2 9.4c-.1.6-.5.7-1 .4l-2.7-2-1.3 1.3c-.2.2-.3.3-.6.3l.2-2.9 5.2-4.7c.2-.2 0-.3-.3-.1L7.5 13l-2.6-.8c-.5-.2-.5-.6.7-.5z"/></svg>;
    case 'tiktok': return <svg {...p}><rect width="24" height="24" rx="6" fill="#010101"/><path fill="#EE1D52" d="M13.1 5.6h1.9c.2 1.4 1 2.6 2.8 2.8v1.9c-1.1 0-2.1-.4-2.8-.9v4.3a4 4 0 11-4-4c.2 0 .3 0 .5.1v2a2 2 0 102 2V5.6z"/><path fill="#fff" d="M13.4 5.9h1.9c.2 1.4 1 2.6 2.8 2.8v1.9c-1.1 0-2.1-.4-2.8-.9V14a4 4 0 11-4-4c.2 0 .3 0 .5 0v2c-.2 0-.3-.1-.5-.1a2 2 0 102 2V5.9z"/></svg>;
    case 'youtube': return <svg {...p}><rect x="2" y="5.2" width="20" height="13.6" rx="4" fill="#FF0000"/><path fill="#fff" d="M10 8.6l6 3.4-6 3.4z"/></svg>;
    case 'x': return <svg {...p}><rect width="24" height="24" rx="6" fill="#000"/><path fill="#fff" d="M13.6 10.8L18 5.6h-1.5l-3.6 4.2-2.9-4.2H5.6l4.6 6.7-4.6 5.4H7l3.9-4.6 3.1 4.6h4.4l-4.8-7zm-1.4 1.6l-.5-.7-3.6-5.1h1.7l2.9 4.1.5.7 3.8 5.4h-1.7l-3.1-4.4z"/></svg>;
    case 'whatsapp': return <svg {...p}><rect width="24" height="24" rx="12" fill="#25D366"/><path fill="#fff" d="M12 6a6 6 0 00-5.1 9.1L6 18l3-.9A6 6 0 1012 6zm-2 3.7c.1 0 .2 0 .3.2l.4.9v.2l-.1.2-.2.2c-.1.1-.1.2-.1.3.1.1.4.5.8.9.5.5 1 .6 1.1.7.1 0 .2 0 .3-.1l.3-.4c.1-.2.3 0 .4 0l.7.3.1.2s0 .3-.1.6c-.1.3-.6.6-.9.6-.2 0-.5.1-1.7-.4-1.5-.6-2.4-2.1-2.5-2.2-.1-.1-.6-.8-.6-1.5s.4-1 .5-1.2c.1-.2.3-.2.4-.2z"/></svg>;
    case 'snapchat': return <svg {...p}><rect width="24" height="24" rx="6" fill="#FFFC00"/><path fill="#fff" stroke="#111" strokeWidth=".4" d="M12 5.6c1.7 0 3 1.4 3 3.1 0 .6 0 .9.1 1 .1.1.4.1.7 0 .4-.1.7.1.7.4 0 .3-.5.5-.9.6-.2.1-.3.3-.2.5.3.7 1.1 1.3 1.7 1.5.2 0 .2.3 0 .5-.3.2-.8.2-1 .5-.2.2 0 .5-.3.6-.3.1-.7-.2-1.2-.1-.4.1-.7.6-1.4.8-.5.2-1.3.2-1.8 0-.7-.2-1-.7-1.4-.8-.5-.1-.9.2-1.2.1-.3-.1-.1-.4-.3-.6-.2-.3-.7-.3-1-.5-.2-.2-.2-.4 0-.5.6-.2 1.4-.8 1.7-1.5.1-.2 0-.4-.2-.5-.4-.1-.9-.3-.9-.6 0-.3.3-.5.7-.4.3.1.6.1.7 0 .1-.1.1-.4.1-1 0-1.7 1.3-3.1 3-3.1z"/></svg>;
    case 'website': return <svg {...p}><rect width="24" height="24" rx="6" fill="#0EA5A5"/><circle cx="12" cy="12" r="5.6" fill="none" stroke="#fff" strokeWidth="1.4"/><path d="M6.4 12h11.2M12 6.4c2 2.6 2 8.6 0 11.2M12 6.4c-2 2.6-2 8.6 0 11.2" fill="none" stroke="#fff" strokeWidth="1.2"/></svg>;
    default: return <svg {...p}><rect width="24" height="24" rx="6" fill="#6B7280"/><path fill="#fff" d="M10.2 12a1.7 1.7 0 011.7-1.7h1.4v1.4h-1.4a.3.3 0 000 .6h1.4v1.4h-1.4A1.7 1.7 0 0110.2 12zm3.1-1.7h1.4a1.7 1.7 0 010 3.4h-1.4v-1.4h1.4a.3.3 0 000-.6h-1.4v-1.4zM11 11.3h4v1.4h-4z"/></svg>;
  }
}
/* ── Email field with common-domain autocomplete (gmail/yahoo/outlook…) ── */
const EMAIL_DOMAINS = ['gmail.com','yahoo.com','outlook.com','hotmail.com','icloud.com'];
function EmailField({ value, onChange, style, placeholder, onKeyDown }:{ value:string; onChange:(v:string)=>void; style:React.CSSProperties; placeholder?:string; onKeyDown?:(e:React.KeyboardEvent<HTMLInputElement>)=>void }) {
  const [focus, setFocus] = useState(false);
  const suggestions = useMemo(() => {
    const v = (value||'').trim();
    const at = v.indexOf('@');
    if (at === -1) return v ? EMAIL_DOMAINS.map(d => `${v}@${d}`) : [];
    const local = v.slice(0, at); const dom = v.slice(at+1).toLowerCase();
    if (!local || EMAIL_DOMAINS.includes(dom)) return [];   // domain complete → nothing to suggest
    return EMAIL_DOMAINS.filter(d => d.startsWith(dom)).map(d => `${local}@${d}`);
  }, [value]);
  return (
    <div style={{ position:'relative' }}>
      <input value={value} onChange={e=>onChange(e.target.value)} onFocus={()=>setFocus(true)}
        onBlur={()=>setTimeout(()=>setFocus(false),150)} onKeyDown={onKeyDown} type="email" inputMode="email" autoCapitalize="none" spellCheck={false}
        placeholder={placeholder} style={style} />
      {focus && suggestions.length>0 && (
        <div style={{ position:'absolute', top:'calc(100% - 6px)', left:0, right:0, background:T.bg2, border:`1px solid ${T.line2}`, borderRadius:10, zIndex:40, boxShadow:'0 10px 30px rgba(0,0,0,0.45)', overflow:'hidden' }}>
          {suggestions.map(s=>(
            <div key={s} onMouseDown={()=>{ onChange(s); setFocus(false); }}
              style={{ padding:'10px 13px', cursor:'pointer', fontSize:14, color:T.t1 }}
              onMouseEnter={e=>e.currentTarget.style.background='rgba(255,145,0,0.10)'} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
              {s}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Searchable country list (shared by the country picker + the phone dial picker) ── */
function CountryMenu({ onPick, onClose }:{ onPick:(iso:string)=>void; onClose:()=>void }) {
  const [q, setQ] = useState('');
  const nq = q.trim().toLowerCase();
  const filtered = COUNTRIES.filter(x => !nq || x.name.toLowerCase().includes(nq) || x.dial.replace('+','').includes(nq.replace('+','')) || x.iso.toLowerCase()===nq);
  return <>
    <div onMouseDown={onClose} style={{ position:'fixed', inset:0, zIndex:60 }} />
    <div style={{ position:'absolute', top:'calc(100% + 6px)', left:0, width:300, maxWidth:'86vw', background:T.bg2, border:`1px solid ${T.line2}`, borderRadius:12, zIndex:61, boxShadow:'0 14px 44px rgba(0,0,0,0.55)', overflow:'hidden' }}>
      <div style={{ padding:8, borderBottom:`1px solid ${T.line}` }}>
        <input autoFocus value={q} onChange={e=>setQ(e.target.value)} placeholder="Search country or code…"
          onKeyDown={e=>{ if(e.key==='Enter'&&filtered[0]) onPick(filtered[0].iso); }}
          style={{ width:'100%', height:38, padding:'0 11px', background:'#10121A', border:`1px solid ${T.line2}`, borderRadius:8, color:T.t1, fontSize:14, outline:'none', boxSizing:'border-box' }} />
      </div>
      <div style={{ maxHeight:240, overflowY:'auto' }}>
        {filtered.map(x=>(
          <div key={x.iso} onMouseDown={()=>onPick(x.iso)}
            style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 13px', cursor:'pointer', fontSize:14 }}
            onMouseEnter={e=>e.currentTarget.style.background='rgba(255,255,255,0.05)'} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
            <span style={{ fontSize:19 }}>{isoFlag(x.iso)}</span>
            <span style={{ flex:1, color:T.t1 }}>{x.name}</span>
            <span style={{ color:T.t3 }}>{x.dial}</span>
          </div>
        ))}
        {filtered.length===0 && <div style={{ padding:16, textAlign:'center', color:T.t3, fontSize:13 }}>No country found</div>}
      </div>
    </div>
  </>;
}

/* ── Country of residence — searchable dropdown ── */
function CountrySelect({ iso, onPick, box }:{ iso:string; onPick:(iso:string)=>void; box:React.CSSProperties }) {
  const [open, setOpen] = useState(false);
  const c = byIso(iso);
  return (
    <div style={{ position:'relative' }}>
      <button type="button" onClick={()=>setOpen(o=>!o)}
        style={{ ...box, display:'flex', alignItems:'center', gap:8, textAlign:'left', cursor:'pointer', marginBottom:0 }}>
        {c ? <><span style={{ fontSize:18 }}>{isoFlag(c.iso)}</span><span style={{ color:T.t1 }}>{c.name}</span></> : <span style={{ color:T.t3 }}>Select your country</span>}
        <span style={{ marginLeft:'auto', color:T.t3 }}>▾</span>
      </button>
      {open && <CountryMenu onPick={i=>{ onPick(i); setOpen(false); }} onClose={()=>setOpen(false)} />}
    </div>
  );
}

/* ── Phone: [flag + dial code picker] [national number] + per-country length validation ── */
function PhoneField({ iso, national, onIso, onNational, box }:{ iso:string; national:string; onIso:(iso:string)=>void; onNational:(v:string)=>void; box:React.CSSProperties }) {
  const [open, setOpen] = useState(false);
  const c = byIso(iso) || COUNTRIES[0];
  const valid = validNational(national, c);
  const hint = c.len ? `Enter ${c.len} digits${c.prefix?` starting with ${c.prefix}`:''} (or ${c.len+1} with the leading 0).` : 'Enter your mobile number.';
  return (
    <div>
      <div style={{ display:'flex', gap:8, alignItems:'stretch' }}>
        <div style={{ position:'relative', flexShrink:0 }}>
          <button type="button" onClick={()=>setOpen(o=>!o)}
            style={{ ...box, width:'auto', display:'flex', alignItems:'center', gap:6, whiteSpace:'nowrap', cursor:'pointer', marginBottom:0, padding:'0 11px' }}>
            <span style={{ fontSize:18 }}>{isoFlag(c.iso)}</span>
            <span style={{ color:T.t1, fontWeight:600 }}>{c.dial}</span>
            <span style={{ color:T.t3 }}>▾</span>
          </button>
          {open && <CountryMenu onPick={i=>{ onIso(i); setOpen(false); }} onClose={()=>setOpen(false)} />}
        </div>
        <input value={national} onChange={e=>onNational(normalizeNational(e.target.value, c))} inputMode="tel" autoComplete="tel-national"
          placeholder={c.ex || 'Phone number'} style={{ ...box, flex:1, marginBottom:0, borderColor: (national && !valid) ? 'rgba(255,106,77,0.6)' : (box.border as string) }} />
      </div>
      {national && !valid
        ? <div style={{ fontSize:11.5, color:'#ff6a4d', marginTop:6 }}>{hint}</div>
        : (c.pre ? <div style={{ fontSize:11.5, color:T.t3, marginTop:6 }}>e.g. {c.ex} · common prefixes {c.pre}</div> : null)}
    </div>
  );
}

function SignupWizard({ form, setForm, onDone }: { form:any; setForm:(f:any)=>void; onDone:(tok:string)=>void }) {
  const [step, setStep] = useState(0);   // 0 basics, 1 email otp, 2 phone otp, 3 questionnaire, 4 agree
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sent, setSent] = useState(false);
  const [prof, setProf] = useState<any>({ status:'new', years:'', companies:[], type:[], sources:[], relations_note:'', website:'' });
  const [links, setLinks] = useState<any[]>([]);   // {platform,label,name,url,status:'idle'|'checking'|'ok'|'bad',message,name_match}
  const seqRef = useRef<Record<number, number>>({});
  const [bio, setBio] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [agreement, setAgreement] = useState<any>(null);
  useEffect(() => { apiGet('/ib-agreement').then(setAgreement).catch(()=>{}); }, []);
  // detect the visitor's country by IP → default the dial code + residence country (only while
  // untouched; a real IP-country override never clobbers something the user already picked/typed).
  useEffect(() => {
    fetch('https://ipapi.co/json/').then(r=>r.json()).then(d=>{
      const iso = d && d.country_code ? String(d.country_code).toUpperCase() : '';
      const c = byIso(iso); if (!c) return;
      setForm((s:any)=>({ ...s,
        dial_iso: s.phone_national ? s.dial_iso : iso,
        country_iso: s.country ? s.country_iso : iso,
        country: s.country || c.name,
      }));
    }).catch(()=>{});
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const box: React.CSSProperties = { width:'100%', height:46, padding:'0 13px', background:'#10121A',
    border:'1px solid rgba(255,255,255,0.14)', borderRadius:10, color:T.t1, fontSize:15, outline:'none', boxSizing:'border-box', marginBottom:10 };
  const lbl = (t:string) => <div style={{ fontSize:12.5, fontWeight:600, color:T.t2, margin:'2px 0 6px' }}>{t}</div>;

  // phone/country wiring: keep form.phone as the full E.164 number; national + dial_iso drive it.
  const setNational = (v:string) => setForm((s:any)=>({ ...s, phone_national:v, phone:e164(byIso(s.dial_iso), v) }));
  const setDialIso  = (iso:string) => setForm((s:any)=>{ const nn = normalizeNational(s.phone_national, byIso(iso)); return { ...s, dial_iso:iso, phone_national:nn, phone:e164(byIso(iso), nn) }; });
  const setCountryIso = (iso:string) => setForm((s:any)=>({ ...s, country_iso:iso, country:(byIso(iso)?.name || s.country),
    // if they haven't started the phone yet, follow the residence country for the dial code too
    ...(s.phone_national ? {} : { dial_iso:iso, phone:e164(byIso(iso), '') }) }));

  const sendOtp = async (channel:'email'|'sms') => {
    setErr(''); setBusy(true);
    try {
      const purpose = channel === 'email' ? 'signup_email' : 'signup_phone';
      const r:any = await apiPost('/ib-portal/auth/signup-otp', { channel, purpose, email:form.email, phone:form.phone });
      if (r?.sent === false) setErr(r?.detail || 'Could not send the code'); else setSent(true);
    } catch (e:any) { setErr(e?.message || 'Could not send the code'); }
    setBusy(false);
  };
  const verifyOtp = async (channel:'email'|'sms', next:number) => {
    setErr(''); setBusy(true);
    try {
      const purpose = channel === 'email' ? 'signup_email' : 'signup_phone';
      await apiPost('/ib-portal/auth/signup-otp/verify', { channel, purpose, email:form.email, phone:form.phone, code });
      setCode(''); setSent(false); setStep(next);
    } catch (e:any) { setErr(e?.message || 'Wrong or expired code'); }
    setBusy(false);
  };
  const submit = async () => {
    setErr(''); setBusy(true);
    try {
      const r:any = await apiPost('/ib-portal/auth/register', {
        ...form, bio, agreement_accepted: agreed,
        profile: {
          status: prof.status, years: prof.years, companies: prof.companies,
          type: prof.type, sources: prof.sources, relations_note: prof.relations_note, website: prof.website,
        },
        social_links: links.filter(l => l.url && l.status === 'ok').map(l => ({
          platform: l.platform, label: l.label, name: l.name, url: l.url,
          verified: true, name_match: l.name_match,
        })),
      });
      if (r?.access_token) onDone(r.access_token);
      else setErr(r?.detail || 'Could not submit');
    } catch (e:any) { setErr(e?.message || 'Could not submit'); }
    setBusy(false);
  };
  const patchLink = (i:number, patch:any) => setLinks(ls => ls.map((l,j)=> j===i ? { ...l, ...patch } : l));
  // toggle a platform from the logo grid: add a row if new, remove its row(s) if already selected
  const toggleSocial = (s:any) => setLinks(ls => {
    const has = ls.some(l => l.platform === s.k);
    if (has) return ls.filter(l => l.platform !== s.k);
    return [...ls, { platform:s.k, label:s.label, handle:'', name:'', url:'', status:'idle', message:'', name_match:null }];
  });
  // Telegram (multi): add a second/third channel or group after the first is added
  const addAnother = (s:any) => setLinks(ls => [...ls, { platform:s.k, label:s.label, handle:'', name:'', url:'', status:'idle', message:'', name_match:null }]);
  // verify one row: instant client-side domain gate, then the server existence/name check (async,
  // so the applicant can keep adding other links while this one spins). Per-row sequence guard.
  const checkLink = async (i:number) => {
    const l = links[i]; if (!l) return;
    const cat = socialCat(l.platform);
    const url = buildSocialUrl(cat, l.handle);   // build the full URL from the handle/username they typed
    if (!url) { patchLink(i, { url:'', status:'idle', message:'', name_match:null }); return; }
    const seq = (seqRef.current[i] || 0) + 1; seqRef.current[i] = seq;
    patchLink(i, { url, name:(l.handle||'').replace(/^@+/,''), status:'checking', message:'Checking…' });
    try {
      const r:any = await apiPost('/ib-portal/verify-social', { platform:l.platform, url, name:(l.handle||'').replace(/^@+/,'') });
      if (seqRef.current[i] !== seq) return;   // a newer check superseded this one
      patchLink(i, { status: r?.verified ? 'ok' : 'bad', message: r?.message || '', name_match: r?.name_match });
    } catch {
      if (seqRef.current[i] !== seq) return;
      patchLink(i, { status:'bad', message:'Could not check that — try again.' });
    }
  };

  const canBasics = form.name?.trim() && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email||'')
    && validNational(form.phone_national, byIso(form.dial_iso)) && (form.password||'').length>=8;
  return (
    <div style={{ width:'100%', maxWidth:440, boxSizing:'border-box' }}>
      <Eyebrow>Become a partner</Eyebrow>
      {/* step progress indicator — checks completed steps, highlights the current one */}
      <div style={{ display:'flex', alignItems:'flex-start', margin:'12px 0 22px' }}>
        {['Details','Verify','About you','Agreement'].map((label, i) => (
          <React.Fragment key={i}>
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6, flexShrink:0 }}>
              <div style={{ width:26, height:26, borderRadius:'50%', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11.5, fontWeight:800, transition:'all .3s',
                background: i<step ? T.grad : i===step ? 'rgba(255,145,0,0.14)' : '#181b23',
                border:`1.5px solid ${i<=step ? T.acc : 'rgba(255,255,255,0.14)'}`,
                color: i<step ? '#fff' : i===step ? T.acc : T.t3 }}>
                {i<step ? '✓' : i+1}
              </div>
              <span style={{ fontSize:9.5, fontWeight:600, color: i<=step ? T.t2 : T.t3, whiteSpace:'nowrap' }}>{label}</span>
            </div>
            {i < 3 && <div style={{ flex:1, height:2, borderRadius:2, marginTop:12, background: i<step ? T.acc : 'rgba(255,255,255,0.12)', transition:'background .35s' }} />}
          </React.Fragment>
        ))}
      </div>
      <div key={step} className="pg-stepfade">
      {step===0 && <>
        <div style={{ fontSize:21, fontWeight:700, marginBottom:14 }}>Let's get you started</div>
        {lbl('Full name')}<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} style={box} />
        {lbl('Email')}<div style={{ marginBottom:10 }}><EmailField value={form.email} onChange={v=>setForm({...form,email:v})} placeholder="you@example.com" style={box} /></div>
        {lbl('Mobile number')}<div style={{ marginBottom:10 }}><PhoneField iso={form.dial_iso} national={form.phone_national} onIso={setDialIso} onNational={setNational} box={box} /></div>
        <div style={{ display:'flex', gap:10 }}>
          <div style={{ flex:1, minWidth:0 }}>{lbl('Country')}<CountrySelect iso={form.country_iso} onPick={setCountryIso} box={box} /></div>
          <div style={{ flex:1, minWidth:0 }}>{lbl('City')}<input value={form.city} onChange={e=>setForm({...form,city:e.target.value})} style={box} /></div>
        </div>
        {lbl('Choose a password')}<input value={form.password} onChange={e=>setForm({...form,password:e.target.value})} type="password" placeholder="Min 8 characters" style={{ ...box, marginTop:10 }} />
        {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
        <button disabled={!canBasics} onClick={()=>{ setErr(''); setSent(false); setStep(1); }} className="pg-cta" style={{ width:'100%', height:48, marginTop:8, opacity:canBasics?1:0.5 }}>Continue →</button>
      </>}
      {step===1 && <>
        <div style={{ fontSize:21, fontWeight:700, marginBottom:6 }}>Verify your email</div>
        <div style={{ fontSize:13, color:T.t3, marginBottom:16 }}>We'll send a 6-digit code to {form.email}.</div>
        {!sent ? <button onClick={()=>sendOtp('email')} disabled={busy} className="pg-cta" style={{ width:'100%', height:46 }}>{busy&&<span className="pg-spin"/>}Send email code</button>
          : <>
            <input value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))} placeholder="6-digit code" inputMode="numeric" style={{ ...box, letterSpacing:6, textAlign:'center', fontSize:20 }} />
            <button onClick={()=>sendOtp('email')} style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:12, marginBottom:8 }}>Resend</button>
            <button onClick={()=>verifyOtp('email',2)} disabled={code.length!==6||busy} className="pg-cta" style={{ width:'100%', height:46, opacity:code.length===6?1:0.6 }}>{busy&&<span className="pg-spin"/>}Verify email</button>
          </>}
        {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'8px 0' }}>{err}</div>}
        <button onClick={()=>{ setErr(''); setSent(false); setStep(0); }} style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:13, marginTop:12 }}>← Back</button>
      </>}
      {step===2 && (() => {
        const onlineSel = prof.sources.includes('online');
        const anyChecking = links.some((l:any)=>l.status==='checking');
        const allVerified = links.every((l:any)=>l.status==='ok');
        const socialsReady = !onlineSel || (links.length>=1 && allVerified);
        const canContinue = prof.sources.length>0 && socialsReady;
        const setCompany = (idx:number, patch:any) => setProf((p:any)=>({...p, companies:p.companies.map((c:any,j:number)=> j===idx?{...c,...patch}:c)}));
        const addCompany = () => setProf((p:any)=>({...p, companies:[...p.companies, {name:'', size:''}]}));
        const rmCompany = (idx:number) => setProf((p:any)=>({...p, companies:p.companies.filter((_:any,j:number)=>j!==idx)}));
        const toggleSource = (s:string) => setProf((p:any)=>({...p, sources: p.sources.includes(s) ? p.sources.filter((x:string)=>x!==s) : [...p.sources, s]}));
        const card = (on:boolean):React.CSSProperties => ({ flex:1, minWidth:0, padding:'14px 8px', borderRadius:12, cursor:'pointer', fontWeight:600, fontSize:13, textAlign:'center',
          border:`1.5px solid ${on?T.acc:'rgba(255,255,255,0.14)'}`, background:on?'rgba(255,110,20,0.12)':'transparent', color:T.t1 });
        return <>
        <div style={{ fontSize:21, fontWeight:700, marginBottom:4 }}>A few quick questions 👋</div>
        <div style={{ fontSize:13, color:T.t3, marginBottom:18 }}>This helps us set you up with the right plan — under a minute.</div>

        {/* 1 ── experience */}
        {lbl('Have you worked as an IB / affiliate before?')}
        <div style={{ display:'flex', gap:10, marginBottom:14 }}>
          {[['new','No, I’m new','🌱'],['experienced','Yes, I have','⭐']].map(([v,t,ic])=>(
            <button key={v} onClick={()=>setProf({...prof,status:v})} style={card(prof.status===v)}>
              <div style={{ fontSize:22, marginBottom:5 }}>{ic}</div>{t}
            </button>
          ))}
        </div>

        {prof.status==='experienced' && <div style={{ borderLeft:`2px solid ${T.acc}`, paddingLeft:12, marginBottom:16 }}>
          {lbl('How many years?')}
          <input value={prof.years} onChange={e=>setProf({...prof,years:e.target.value.replace(/[^\d]/g,'').slice(0,2)})} inputMode="numeric" placeholder="e.g. 3" style={box} />
          {lbl('Which companies did you introduce clients for?')}
          {prof.companies.map((c:any,idx:number)=>(
            <div key={idx} style={{ background:'#10121A', border:`1px solid ${T.line}`, borderRadius:11, padding:11, marginBottom:9 }}>
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                <input value={c.name} onChange={e=>setCompany(idx,{name:e.target.value})} placeholder="Company / broker name" style={{ ...box, marginBottom:0, flex:1 }} />
                <button onClick={()=>rmCompany(idx)} title="Remove" style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:17, padding:4 }}>✕</button>
              </div>
              {c.name.trim() && <div style={{ marginTop:9 }}>
                {lbl('How big was your network there? (number of clients)')}
                <input value={c.size} onChange={e=>setCompany(idx,{size:e.target.value.replace(/[^\d]/g,'').slice(0,7)})} inputMode="numeric" placeholder="e.g. 120" style={{ ...box, marginBottom:0 }} />
              </div>}
            </div>
          ))}
          <button onClick={addCompany} style={{ width:'100%', height:42, borderRadius:10, cursor:'pointer', fontSize:13, fontWeight:600,
            border:`1px dashed ${T.line2}`, background:'transparent', color:T.acc }}>+ Add {prof.companies.length? 'another company':'a company'}</button>
        </div>}

        {/* 2 ── referral sources */}
        {lbl('Where do your referrals mainly come from?')}
        <div style={{ display:'flex', gap:10, marginBottom:14 }}>
          {[['online','Social media & website','📱'],['relations','Personal relations','🤝']].map(([v,t,ic])=>(
            <button key={v} onClick={()=>toggleSource(v)} style={card(prof.sources.includes(v))}>
              <div style={{ fontSize:20, marginBottom:4 }}>{ic}</div>{t}
            </button>
          ))}
        </div>
        {prof.sources.includes('relations') && <div style={{ marginBottom:14 }}>
          {lbl('Tell us about your network (optional)')}
          <input value={prof.relations_note} onChange={e=>setProf({...prof,relations_note:e.target.value})} placeholder="e.g. trading community, colleagues, family" style={box} />
        </div>}

        {/* 3 ── social channels + link verification (only if online) */}
        {onlineSel && <div style={{ marginBottom:6 }}>
          {lbl('Tap your channels — just enter your page handle or @username')}
          <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:12 }}>
            {SOCIAL_CAT.map(s=>{
              const on = links.some((l:any)=>l.platform===s.k);
              return <button key={s.k} onClick={()=>toggleSocial(s)} title={s.label}
                style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:5, width:62, padding:'9px 4px', borderRadius:12, cursor:'pointer',
                  border:`1.5px solid ${on?T.acc:'rgba(255,255,255,0.12)'}`, background:on?'rgba(255,110,20,0.10)':'transparent' }}>
                <SocialLogo k={s.k} size={26} />
                <span style={{ fontSize:10, lineHeight:1.1, color:on?T.t1:T.t3, fontWeight:600, textAlign:'center' }}>{s.label}</span>
              </button>;
            })}
          </div>
          {links.map((l:any,i:number)=>{
            const cat = socialCat(l.platform);
            const ring = l.status==='ok'?'rgba(40,199,111,0.5)': l.status==='bad'?'rgba(255,106,77,0.5)': l.status==='checking'?T.acc : T.line2;
            const lastOfKind = cat?.multi && links.map((x:any)=>x.platform).lastIndexOf(l.platform)===i;
            return <div key={i} style={{ background:'#10121A', border:`1px solid ${ring}`, borderRadius:12, padding:11, marginBottom:9 }}>
              <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:9 }}>
                <SocialLogo k={l.platform} size={22} />
                <span style={{ fontSize:13, fontWeight:700, color:T.t1, flex:1 }}>{l.label}</span>
                {l.status==='ok' && <span style={{ color:'#28c76f', fontSize:12.5, fontWeight:700 }}>✓ Added</span>}
                {l.status==='checking' && <span className="pg-spin" />}
                {l.status==='bad' && <span style={{ color:'#ff6a4d', fontSize:14, fontWeight:700 }}>!</span>}
                <button onClick={()=>setLinks((ls:any[])=>ls.filter((_,j)=>j!==i))} title="Remove" style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:16, padding:2 }}>✕</button>
              </div>
              {/* input: [facebook.com/] handle · [@] username · or a full link */}
              <div style={{ display:'flex', alignItems:'stretch', border:`1px solid ${T.line2}`, borderRadius:10, overflow:'hidden', background:'#0b0d14' }}>
                {cat?.mode==='prefix' && <span style={{ padding:'0 10px', display:'flex', alignItems:'center', fontSize:13, color:T.t3, background:'rgba(255,255,255,0.05)', whiteSpace:'nowrap' }}>{cat.prefix}</span>}
                {cat?.mode==='username' && <span style={{ padding:'0 12px', display:'flex', alignItems:'center', fontSize:16, fontWeight:700, color:T.t3, background:'rgba(255,255,255,0.05)' }}>@</span>}
                <input value={l.handle} onChange={e=>patchLink(i,{handle:e.target.value, status:'idle', message:''})}
                  onBlur={()=>checkLink(i)} onKeyDown={e=>{ if(e.key==='Enter'){ e.preventDefault(); (e.target as HTMLInputElement).blur(); } }}
                  placeholder={cat?.ph||''} inputMode={cat?.mode==='url'?'url':'text'} autoCapitalize="none" spellCheck={false}
                  style={{ flex:1, minWidth:0, height:42, padding:'0 12px', background:'transparent', border:'none', color:T.t1, fontSize:14, outline:'none' }} />
              </div>
              {l.message && <div style={{ fontSize:12, marginTop:6, color: l.status==='ok'?'#28c76f': l.status==='bad'?'#ff6a4d': T.t3 }}>{l.message}</div>}
              {lastOfKind && l.status==='ok' &&
                <button onClick={()=>addAnother(cat)} style={{ marginTop:8, background:'none', border:`1px dashed ${T.line2}`, color:T.acc, borderRadius:8, padding:'6px 11px', fontSize:12, fontWeight:700, cursor:'pointer' }}>+ Add another {l.label} channel / group</button>}
            </div>;
          })}
          {onlineSel && links.length>0 && !allVerified && !anyChecking &&
            <div style={{ fontSize:11.5, color:T.t3, marginBottom:8 }}>Enter your handle or @username for each — it turns green ✓ when added. Remove any you don’t use.</div>}
        </div>}

        {/* bio */}
        {lbl('Anything else about you? (optional)')}
        <textarea value={bio} onChange={e=>setBio(e.target.value)} rows={2} placeholder="A sentence about your audience" style={{ ...box, height:'auto', padding:'10px 13px', resize:'vertical' }} />

        {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
        <button onClick={()=>setStep(3)} disabled={!canContinue} className="pg-cta" style={{ width:'100%', height:48, marginTop:6, opacity:canContinue?1:0.5 }}>Continue →</button>
        {!canContinue && <div style={{ fontSize:11.5, color:T.t3, textAlign:'center', marginTop:7 }}>
          {prof.sources.length===0 ? 'Pick where your referrals come from to continue.'
            : anyChecking ? 'Verifying your links…'
            : 'Add & verify your channel link(s) to continue.'}
        </div>}
        <button onClick={()=>setStep(1)} style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:13, marginTop:10, width:'100%', textAlign:'center' }}>← Back</button>
        </>;
      })()}
      {step===3 && <>
        <div style={{ fontSize:21, fontWeight:700, marginBottom:12 }}>Partner agreement</div>
        <div style={{ fontSize:13, color:T.t2, lineHeight:1.6, maxHeight:200, overflowY:'auto', background:'#10121A', border:`1px solid ${T.line}`, borderRadius:10, padding:14, marginBottom:14 }}>
          {agreement?.summary || 'Loading agreement…'}
          {agreement?.url && <div style={{ marginTop:10 }}><a href={agreement.url} target="_blank" rel="noreferrer" style={{ color:T.acc }}>Read the full agreement →</a></div>}
        </div>
        <label style={{ display:'flex', alignItems:'flex-start', gap:10, cursor:'pointer', marginBottom:14 }}>
          <input type="checkbox" checked={agreed} onChange={e=>setAgreed(e.target.checked)} style={{ marginTop:3 }} />
          <span style={{ fontSize:13, color:T.t2 }}>I have read and accept the TNFX Introducing Broker Agreement{agreement?.version?` (v${agreement.version})`:''}.</span>
        </label>
        {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
        <button onClick={submit} disabled={!agreed||busy} className="pg-cta" style={{ width:'100%', height:48, opacity:agreed?1:0.5 }}>{busy&&<span className="pg-spin"/>}Submit application</button>
        <button onClick={()=>setStep(2)} style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:13, marginTop:10 }}>← Back</button>
      </>}
      </div>
    </div>
  );
}

/* Activation (existing IB, first login) + Forgot-password overlay.
   activate: choose SMS (verify the mobile is live) or email → OTP → set password.
   forgot:   email OTP → set password. */
function OtpOverlay({ flow, email, info, onClose, onDone }:
    { flow: 'activate'|'forgot'; email: string; info: any; onClose: () => void; onDone: (tok: string) => void }) {
  const [step, setStep] = useState<'method'|'code'|'password'>(flow === 'forgot' ? 'code' : 'method');
  const [channel, setChannel] = useState<'sms'|'email'>(info?.has_phone ? 'sms' : 'email');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sent, setSent] = useState(false);
  const box: React.CSSProperties = { width:'100%', height:46, padding:'0 13px', background:'#10121A',
    border:'1px solid rgba(255,255,255,0.14)', borderRadius:10, color:T.t1, fontSize:15.5, outline:'none', boxSizing:'border-box', marginBottom:10 };

  const sendCode = async () => {
    setErr(''); setBusy(true);
    try {
      const body: any = flow === 'forgot'
        ? { email }
        : { email, channel, purpose: 'activate', phone: channel === 'sms' ? phone : '' };
      const res: any = await apiPost(flow === 'forgot' ? '/ib-portal/auth/forgot/send' : '/ib-portal/auth/otp/send', body);
      if (res?.sent === false) { setErr(res?.detail || 'Could not send the code'); }
      else { setSent(true); setStep('code'); }
    } catch (e: any) { setErr(e?.message || 'Could not send the code'); }
    setBusy(false);
  };
  const finish = async () => {
    setErr(''); setBusy(true);
    try {
      const res: any = flow === 'forgot'
        ? await apiPost('/ib-portal/auth/forgot/reset', { email, code, password: pw })
        : await apiPost('/ib-portal/auth/activate', { email, code, channel, phone: channel === 'sms' ? phone : '', password: pw });
      if (res?.access_token) onDone(res.access_token);
      else setErr(res?.detail || 'Wrong or expired code');
    } catch (e: any) { setErr(e?.message || 'Wrong or expired code'); }
    setBusy(false);
  };

  return (
    <div onClick={onClose} style={{ position:'fixed', inset:0, zIndex:200, background:'rgba(8,9,12,0.75)',
      display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
      <div onClick={e => e.stopPropagation()} style={{ width:420, maxWidth:'100%', background:T.bg1,
        border:`1px solid ${T.line2}`, borderRadius:16, padding:26, color:T.t1, fontFamily:FONT }}>
        <div style={{ fontSize:19, fontWeight:700, marginBottom:4 }}>
          {flow === 'forgot' ? 'Reset your password'
            : step === 'method' ? `Welcome${info?.name ? ', ' + info.name.split(' ')[0] : ''} 👋`
            : 'Almost there'}</div>
        <div style={{ fontSize:13, color:T.t3, marginBottom:18, lineHeight:1.55 }}>
          {flow === 'forgot' ? `We'll email a code to ${email}.`
            : step === 'method' ? "Welcome to the new TNFX IB engine. To confirm it's really you, we'll send a one-time code to your mobile."
            : step === 'code' ? `Enter the 6-digit code we sent${channel === 'sms' ? ' to your mobile ' + (info?.phone_mask || ('••••' + phone.slice(-4))) : ' to ' + email}.`
            : 'Choose a password for your partner account.'}</div>

        {flow === 'activate' && step === 'method' && (<>
          {info?.has_phone && (
            <button onClick={() => setChannel('sms')} style={{ ...box, height:'auto', padding:'12px 13px', textAlign:'left',
              cursor:'pointer', borderColor: channel === 'sms' ? T.acc : 'rgba(255,255,255,0.14)' }}>
              <div style={{ fontWeight:700, fontSize:14 }}>📱 SMS code</div>
              <div style={{ fontSize:12, color:T.t3, marginTop:2 }}>To your number ending {info.phone_mask}</div>
            </button>
          )}
          {channel === 'sms' && (
            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Confirm full number with country code, e.g. +9647…" style={box} />
          )}
          <button onClick={() => setChannel('email')} style={{ ...box, height:'auto', padding:'12px 13px', textAlign:'left',
            cursor:'pointer', borderColor: channel === 'email' ? T.acc : 'rgba(255,255,255,0.14)' }}>
            <div style={{ fontWeight:700, fontSize:14 }}>✉️ Email code {info?.has_phone ? '(phone lost / dead?)' : ''}</div>
            <div style={{ fontSize:12, color:T.t3, marginTop:2 }}>To {email}</div>
          </button>
          {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
          <button onClick={sendCode} disabled={busy || (channel === 'sms' && !phone.trim())} className="pg-cta"
            style={{ width:'100%', height:46, marginTop:6, opacity: busy ? 0.7 : 1 }}>
            {busy && <span className="pg-spin" />}Send code</button>
        </>)}

        {step === 'code' && (<>
          {!sent && flow === 'forgot' && (
            <button onClick={sendCode} disabled={busy} className="pg-cta" style={{ width:'100%', height:46, marginBottom:12 }}>
              {busy && <span className="pg-spin" />}Send code to my email</button>
          )}
          {sent && <>
            <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="6-digit code" inputMode="numeric" style={{ ...box, letterSpacing:6, textAlign:'center', fontSize:20 }} />
            <button onClick={sendCode} disabled={busy} style={{ background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:12, marginBottom:8 }}>Resend code</button>
            {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
            <button onClick={() => { if (code.length === 6) { setErr(''); setStep('password'); } }}
              disabled={code.length !== 6} className="pg-cta" style={{ width:'100%', height:46, opacity: code.length === 6 ? 1 : 0.6 }}>Continue</button>
          </>}
        </>)}

        {step === 'password' && (<>
          <input value={pw} onChange={e => setPw(e.target.value)} type="password" placeholder="New password (min 8 characters)" style={box} />
          {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'4px 0' }}>{err}</div>}
          <button onClick={finish} disabled={busy || pw.length < 8} className="pg-cta"
            style={{ width:'100%', height:46, opacity: (busy || pw.length < 8) ? 0.7 : 1 }}>
            {busy && <span className="pg-spin" />}{flow === 'forgot' ? 'Reset & log in' : 'Set password & enter'}</button>
        </>)}

        <button onClick={onClose} style={{ width:'100%', background:'none', border:'none', color:T.t3, cursor:'pointer', fontSize:13, marginTop:14 }}>Cancel</button>
      </div>
    </div>
  );
}

/** partner1.tnfx.co — standalone IB portal. IBs log in / register here (scope='ib' JWT);
 *  approved IBs (agent_id linked by the desk) see their live IBPortal; fresh applications
 *  see a "under review" banner until the desk activates them in IB Admin. */
// PWA: install the manifest + a partner-scoped service worker, ONLY on the partner host
// (never on my1, so the admin app's caching is untouched). Also captures the install prompt.
let _deferredInstall: any = null;
function usePartnerPWA() {
  const [canInstall, setCanInstall] = useState(false);
  useEffect(() => {
    if (!/^partner/i.test(window.location.hostname)) return;
    if (!document.querySelector('link[rel="manifest"][data-partner]')) {
      const l = document.createElement('link');
      l.rel = 'manifest'; l.href = '/partner-manifest.json'; l.setAttribute('data-partner', '1');
      document.head.appendChild(l);
      const th = document.createElement('meta'); th.name = 'theme-color'; th.content = '#0b0c0f'; document.head.appendChild(th);
      const ac = document.createElement('meta'); ac.name = 'apple-mobile-web-app-capable'; ac.content = 'yes'; document.head.appendChild(ac);
      const at = document.createElement('link'); at.rel = 'apple-touch-icon'; at.href = '/logo192.png'; document.head.appendChild(at);
    }
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/partner-sw.js').catch(() => {});
    }
    const onPrompt = (e: any) => { e.preventDefault(); _deferredInstall = e; setCanInstall(true); };
    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => window.removeEventListener('beforeinstallprompt', onPrompt);
  }, []);
  const install = async () => { if (_deferredInstall) { _deferredInstall.prompt(); await _deferredInstall.userChoice; _deferredInstall = null; setCanInstall(false); } };
  return { canInstall, install };
}

export default function PartnerGate() {
  const { canInstall, install } = usePartnerPWA();
  const [token, setToken] = useState<string>(localStorage.getItem('token') || '');
  const [me, setMe] = useState<any>(null);
  const [mode, setMode] = useState<'login'|'register'>(
    new URLSearchParams(window.location.search).has('join') ? 'register' : 'login');
  // SEO sub-pages deep-link here: /?join=1 opens the signup form, /?login=1 the login form.
  const _q = new URLSearchParams(window.location.search);
  const [view, setView] = useState<'landing'|'auth'>(_q.has('join') || _q.has('login') ? 'auth' : 'landing');
  const [form, setForm] = useState<any>({ name:'', email:'', phone:'', country:'', city:'', password:'', dial_iso:'IQ', country_iso:'IQ', phone_national:'' });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  // OTP overlay: activation (existing IB, first login) + forgot-password
  const [otpFlow, setOtpFlow] = useState<null | 'activate' | 'forgot'>(null);
  const [otpInfo, setOtpInfo] = useState<any>(null);   // {name, phone_mask, has_phone}
  const busyRef = useRef(false);        // Enter-key can't race the button's disabled state
  const [scrolled, setScrolled] = useState(false);
  const [stick, setStick] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const heroCtaRef = useRef<HTMLButtonElement>(null);
  const openAuth = (m:'login'|'register') => {
    setMode(m); setErr(''); setStick(false); setView('auth'); window.scrollTo(0, 0);
  };

  useEffect(() => {
    if (!token) return;
    apiGet('/ib-portal/me').then(setMe).catch(() => { setToken(''); localStorage.removeItem('token'); });
  }, [token]);

  // one-shot scroll reveals + hairline under the top bar + sticky mobile CTA
  useEffect(() => {
    if (token || view !== 'landing') return;
    const root = rootRef.current;
    if (!root) return;
    const io = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: 0.15 });
    root.querySelectorAll('.rv').forEach(el => io.observe(el));
    let stickIo: IntersectionObserver | null = null;
    if (heroCtaRef.current) {
      stickIo = new IntersectionObserver(es => setStick(!es[0].isIntersecting && es[0].boundingClientRect.top < 0));
      stickIo.observe(heroCtaRef.current);
    }
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();                                    // sync after a view round-trip
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => { io.disconnect(); stickIo?.disconnect(); window.removeEventListener('scroll', onScroll); };
  }, [token, view]);

  const submit = async () => {
    if (busyRef.current) return;          // Enter-key double-submit guard
    busyRef.current = true;
    setErr(''); setBusy(true);
    try {
      // LOGIN: first ask the server what this email is. An existing IB WITHOUT a password
      // gets the smart activation wizard ("welcome to your new CRM, let's set your password").
      if (mode === 'login') {
        try {
          const lk: any = await apiPost('/ib-portal/auth/lookup', { email: form.email });
          if (lk?.kind === 'ib_activate') {
            setOtpInfo(lk); setOtpFlow('activate'); setBusy(false); busyRef.current = false; return;
          }
        } catch { /* fall through to normal login */ }
      }
      const path = mode === 'login' ? '/ib-portal/auth/login' : '/ib-portal/auth/register';
      const res: any = await apiPost(path, form);
      if (res && res.access_token) {
        localStorage.setItem('token', res.access_token);
        setToken(res.access_token);
      } else setErr(res?.detail || 'Failed — check your details');
    } catch (e: any) {
      // api.ts rejects on 4xx/5xx with the backend `detail` as the message
      // (429 lockout, validation errors...). It short-circuits 401 with a generic
      // "Session expired" message — on a LOGIN form a 401 means wrong credentials.
      const m = e?.message || '';
      if (m.startsWith('Session expired')) setErr('Wrong email or password');
      else setErr(m && m !== 'Parse error' ? m : 'Network error — try again');
    }
    busyRef.current = false;
    setBusy(false);
  };

  const logout = () => { localStorage.removeItem('token'); setToken(''); setMe(null); };

  // ── logged in ──
  if (token && me) {
    // staff "View as IB" tab: ?view_ib=<id> renders the RAW portal — no partner header,
    // no admin chrome, no back button — exactly the IB's own screen.
    const viewIb = me.staff ? parseInt(new URLSearchParams(window.location.search).get('view_ib') || '0', 10) : 0;
    if (viewIb > 0) {
      return (
        <div style={{ minHeight:'100vh', background:'#f4f6f9' }}>
          <IBPortal lang="en" ibId={viewIb} />
        </div>
      );
    }
    // A real approved IB sees ONLY their portal — its own header already carries the name, IB code,
    // available balance and (now) sign-out, so the extra partner top bar is removed here (desk request).
    if (!me.staff) {   // approved OR pending IB → their own portal (pending gets a yellow review bar)
      return (
        <div style={{ minHeight:'100vh', background:'#f4f6f9' }}>
          <IBPortal lang="en" ibId={me.ib_id} owner pending={me.pending} onLogout={logout} onInstall={canInstall ? install : undefined} />
        </div>
      );
    }
    return (
      <div style={{ minHeight:'100vh', background:'#f4f6f9' }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, padding:'12px 22px', background:'#101828',
                      color:'#fff', position:'sticky', top:0, zIndex:100 }}>
          <img src={tnfxLogo} alt="TNFX" style={{ height:22 }} />
          <span style={{ fontWeight:800, fontSize:13, letterSpacing:2.5, color:'#ff8b3d' }}>PARTNERS</span>
          <span style={{ fontSize:12, color:'#98a2b3' }}>{me.name} {me.ib_code ? `· ${me.ib_code}` : ''}{me.staff ? ' · ADMIN' : ''}</span>
          {canInstall && <button onClick={install} style={{ marginLeft:'auto', padding:'6px 14px', borderRadius:8,
            border:'none', background:'linear-gradient(92deg,#ff4700,#ff9100)', color:'#fff', cursor:'pointer', fontSize:12, fontWeight:700 }}>📲 Install app</button>}
          <button onClick={logout} style={{ marginLeft: canInstall ? '10px' : 'auto', padding:'6px 14px', borderRadius:8,
            border:'1px solid #344054', background:'transparent', color:'#98a2b3', cursor:'pointer', fontSize:12 }}>Log out</button>
        </div>
        {me.staff ? (
          <PartnerAdmin me={me} />
        ) : me.pending ? (
          <div style={{ maxWidth:520, margin:'80px auto', background:'#fff', border:'1px solid #e4e7ec',
                        borderRadius:16, padding:'40px 36px', boxShadow:'0 8px 28px rgba(16,24,40,0.06)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
              <span style={{ width:20, height:1, background:T.grad, display:'inline-block' }} />
              <span style={{ fontSize:11.5, fontWeight:700, letterSpacing:'0.14em', color:'#98a2b3' }}>APPLICATION</span>
            </div>
            <div style={{ fontSize:22, fontWeight:700, color:'#101828', letterSpacing:'-0.01em', marginBottom:10 }}>
              Application received.</div>
            <div style={{ fontSize:14, color:'#475467', lineHeight:1.65 }}>
              Thanks {me.name?.split(' ')[0] || ''} — your partner application is with our desk.
              Once approved, your account is linked and this portal shows your live clients,
              volume and commission. You'll be contacted at <b>{me.email}</b>.
            </div>
            <div style={{ marginTop:18, paddingTop:14, borderTop:'1px solid #f2f4f7', fontSize:12.5, color:'#98a2b3' }}>
              Bronze rate from day one — $5 per lot on gold and majors.</div>
          </div>
        ) : (
          <IBPortal lang="en" ibId={me.ib_id} owner />
        )}
      </div>
    );
  }

  /* ════════════════════════ AUTH — the bank door ════════════════════════ */
  if (view === 'auth') {
    const label = (txt: string) => (
      <div style={{ fontSize:13, fontWeight:600, color:T.t2, margin:'0 0 6px' }}>{txt}</div>);
    const input = (field: string, placeholder: string, type = 'text') => (
      <input value={form[field]} onChange={e => setForm({ ...form, [field]: e.target.value })}
        placeholder={placeholder} type={type}
        onKeyDown={e => { if (e.key === 'Enter') submit(); }}
        onFocus={e => { e.currentTarget.style.borderColor = '#ff7a1a'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(255,110,20,0.18)'; }}
        onBlur={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.10)'; e.currentTarget.style.boxShadow = 'none'; }}
        style={{ width:'100%', height:48, padding:'0 14px', background:'#10121A',
                 border:'1px solid rgba(255,255,255,0.12)', borderRadius:10, color:T.t1, fontSize:16,
                 outline:'none', boxSizing:'border-box', fontFamily:FONT }} />
    );
    return (
      <div className="pg-auth pg-authgrid" style={{ minHeight:'100vh', background:T.bg0, color:T.t1, fontFamily:FONT,
                                                    display:'grid', gridTemplateColumns:'1fr 1fr' }}>
        <style>{PG_CSS}</style>
        {otpFlow && <OtpOverlay flow={otpFlow} email={form.email} info={otpInfo}
          onClose={() => setOtpFlow(null)}
          onDone={(tok:string) => { setOtpFlow(null); localStorage.setItem('token', tok); setToken(tok); }} />}

        {/* ── LEFT half: the form ── */}
        <div style={{ display:'flex', flexDirection:'column', minHeight:'100vh', borderRight:`1px solid ${T.line}` }}>
        <div style={{ display:'flex', alignItems:'center', padding:'18px 28px' }}>
          <img src={tnfxLogo} alt="TNFX" style={{ height:24, cursor:'pointer' }} onClick={() => setView('landing')} />
          <button onClick={() => setView('landing')} style={{ marginLeft:'auto', background:'none', border:'none',
            color:T.t3, cursor:'pointer', fontSize:13.5, padding:'8px 4px' }}>← Back to overview</button>
        </div>
        <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', padding:'24px 16px' }}>
          <div style={{ width:'100%', maxWidth:420, boxSizing:'border-box' }}>
            <Eyebrow>Partner access</Eyebrow>
            <div style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.015em', marginBottom:4 }}>
              {mode === 'login' ? 'Welcome back, partner.' : 'Apply in 60 seconds.'}</div>
            <div style={{ fontSize:13, color:T.t3, marginBottom:22, lineHeight:1.55 }}>
              {mode === 'login'
                ? 'Log in to your commission dashboard.'
                : 'Our partner desk reviews every application and activates your account.'}</div>

            {/* tabs with sliding gradient underline */}
            <div style={{ position:'relative', display:'flex', borderBottom:`1px solid ${T.line}`, marginBottom:22 }}>
              {(['login','register'] as const).map(mm => (
                <button key={mm} onClick={() => { setMode(mm); setErr(''); }}
                  style={{ flex:1, padding:'11px 0', background:'none', border:'none', cursor:'pointer',
                           fontSize:15, fontWeight:600, color: mode === mm ? T.t1 : T.t3 }}>
                  {mm === 'login' ? 'Log in' : 'Apply'}
                </button>
              ))}
              <div className="pg-tabu" style={{ position:'absolute', bottom:-1, left:0, width:'50%', height:2,
                   background:T.grad, transform: mode === 'login' ? 'translateX(0)' : 'translateX(100%)' }} />
            </div>

            {mode === 'register' ? (
              <SignupWizard form={form} setForm={setForm}
                onDone={(tok:string) => { localStorage.setItem('token', tok); setToken(tok); }} />
            ) : (<>
            {label('Email')}<EmailField value={form.email} onChange={v => setForm({ ...form, email: v })} placeholder="you@example.com" onKeyDown={e => { if (e.key === 'Enter') submit(); }}
              style={{ width:'100%', height:48, padding:'0 14px', background:'#10121A', border:'1px solid rgba(255,255,255,0.12)', borderRadius:10, color:T.t1, fontSize:16, outline:'none', boxSizing:'border-box', fontFamily:FONT }} /><div style={{ height:14 }} />
            {label('Password')}{input('password', 'Your password', 'password')}

            {err && <div style={{ fontSize:13, color:'#ff6a4d', margin:'12px 0 0', lineHeight:1.5 }}>{err}</div>}

            <button onClick={submit} disabled={busy} className="pg-cta"
              style={{ width:'100%', height:48, fontSize:15, marginTop:20, opacity: busy ? 0.75 : 1 }}>
              {busy && <span className="pg-spin" />}
              {busy ? 'Signing in…' : 'Log in'}
            </button>

            <div style={{ textAlign:'center', marginTop:16 }}>
              <button onClick={() => { setMode('register'); setErr(''); }} style={{ background:'none', border:'none',
                color:T.acc, cursor:'pointer', fontSize:13 }}>New here? Apply as a partner →</button>
            </div>
            </>)}
            {mode === 'register' && (
              <div style={{ textAlign:'center', marginTop:16 }}>
                <button onClick={() => { setMode('login'); setErr(''); }} style={{ background:'none', border:'none',
                  color:T.acc, cursor:'pointer', fontSize:13 }}>Already a partner? Log in →</button>
              </div>
            )}
            {mode === 'login' && (
              <div style={{ textAlign:'center', marginTop:10 }}>
                <button onClick={() => { setOtpInfo(null); setOtpFlow('forgot'); setErr(''); }} style={{ background:'none', border:'none',
                  color:T.t3, cursor:'pointer', fontSize:12.5 }}>Forgot your password?</button>
              </div>
            )}
            <div style={{ marginTop:20, paddingTop:16, borderTop:`1px solid ${T.line}`, fontSize:12, color:T.t3 }}>
              FSA licensed · TNFX</div>
          </div>
        </div>
        <div style={{ padding:'0 24px 22px', fontSize:12, color:T.t3, textAlign:'center', lineHeight:1.6 }}>
          Trading foreign exchange and CFDs carries a high level of risk and may not be suitable for all investors.</div>
        </div>

        {/* ── RIGHT half: pure marketing — the number, and the product behind it ── */}
        <div className="pg-authright" style={{ position:'relative', overflow:'hidden', alignItems:'center',
             background:`radial-gradient(900px 640px at 30% 24%, rgba(255,71,0,0.13), transparent 58%), ${T.bg0}` }}>
          {/* dashboard capture — off-centre piece, softly out of focus */}
          <img src={dashShot} alt="" aria-hidden className="pg-shot"
            style={{ right:'-20%', bottom:'-14%', width:'108%', minWidth:640, opacity:0.56,
                     transform:'rotate(-2.5deg)',
                     maskImage:'linear-gradient(215deg, rgba(0,0,0,0.97) 32%, transparent 80%)',
                     WebkitMaskImage:'linear-gradient(215deg, rgba(0,0,0,0.97) 32%, transparent 80%)' }} />
          <div style={{ position:'relative', zIndex:2, padding:'0 8%', maxWidth:560 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:20 }}>
              <span style={{ width:20, height:1, background:T.grad, display:'inline-block' }} />
              <span style={{ fontSize:12, fontWeight:600, letterSpacing:'0.16em', color:T.t3 }}>TNFX PARTNER PROGRAM</span>
            </div>
            <div style={{ fontSize:15, fontWeight:600, letterSpacing:'0.22em', color:T.t2, marginBottom:2 }}>EARN UP TO</div>
            <div style={{ display:'flex', alignItems:'baseline', gap:14, lineHeight:0.95 }}>
              <span className="pg-gradtxt" style={{ fontSize:'clamp(110px, 12vw, 172px)', fontWeight:800,
                    letterSpacing:'-0.045em', fontStyle:'italic' }}>$10</span>
              <span style={{ fontSize:'clamp(24px, 2.6vw, 34px)', fontWeight:800, letterSpacing:'0.14em',
                    color:T.t1, fontStyle:'italic' }}>/ LOT</span>
            </div>
            <div style={{ fontSize:17, color:T.t2, lineHeight:1.6, margin:'22px 0 26px', maxWidth:'44ch' }}>
              On gold and major pairs — paid on <b style={{ color:T.t1 }}>every trade</b> your
              clients make, tracked live to the dollar, withdrawable anytime.
            </div>
            <div style={{ display:'flex', gap:26, borderTop:`1px solid ${T.line}`, paddingTop:18 }}>
              <div>
                <div style={{ fontSize:21, fontWeight:700, color:T.t1 }}>$10M+</div>
                <div style={{ fontSize:12.5, color:T.t3, marginTop:2 }}>paid to partners</div>
              </div>
              <div>
                <div style={{ fontSize:21, fontWeight:700, color:T.t1 }}>6,000+</div>
                <div style={{ fontSize:12.5, color:T.t3, marginTop:2 }}>active partners</div>
              </div>
              <div>
                <div style={{ fontSize:21, fontWeight:700, color:T.t1 }}>325,000+</div>
                <div style={{ fontSize:12.5, color:T.t3, marginTop:2 }}>trading clients</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ════════════════════════ LANDING — The Ledger ════════════════════════ */
  const container: React.CSSProperties = { maxWidth:1200, margin:'0 auto', padding:'0 24px' };
  const sect: React.CSSProperties = { padding:'104px 0' };

  return (
    <div ref={rootRef} className="pg-land js" style={{ minHeight:'100vh', background:T.bg0, color:T.t1, fontFamily:FONT }}>
      <style>{PG_CSS}</style>

      {/* ── 1 · top bar ── */}
      <div className="pg-top" style={{ position:'sticky', top:0, zIndex:100,
           borderBottom: scrolled ? `1px solid ${T.line}` : '1px solid transparent', transition:'border-color .2s ease' }}>
        <div className="pg-topline" style={{ ...container, height:64, display:'flex', alignItems:'center', gap:14 }}>
          <img src={tnfxLogo} alt="TNFX" className="pg-toplogo" style={{ height:26, flexShrink:0 }} />
          <span className="pg-brandtag" style={{ width:1, height:20, background:T.line2 }} />
          <span className="pg-brandtag" style={{ fontSize:11, fontWeight:700, letterSpacing:'0.18em', color:T.t3 }}>PARTNERS</span>
          <nav className="pg-nav" style={{ margin:'0 auto' }}>
            {[['Commission','#commission'],['How it works','#how'],['Partner tools','#tools']].map(([t,h]) => (
              <a key={h} href={h} style={{ fontSize:14, color:T.t2, textDecoration:'none' }}>{t}</a>
            ))}
          </nav>
          <div style={{ marginLeft:'auto', display:'flex', gap:10, alignItems:'center', flexShrink:0 }}>
            <button onClick={() => openAuth('login')} className="pg-ghost pg-login-btn"
              style={{ height:38, padding:'0 18px', fontSize:14 }}>Log in</button>
            <button onClick={() => openAuth('login')} className="pg-login-txt"
              style={{ background:'none', border:'none', color:T.t2, fontSize:14, cursor:'pointer', padding:'10px 4px' }}>Log in</button>
            <button onClick={() => openAuth('register')} className="pg-cta pg-topcta"
              style={{ height:38, padding:'0 18px', fontSize:14, whiteSpace:'nowrap' }}>Become a partner</button>
          </div>
        </div>
      </div>

      {/* ── 2 · hero ── */}
      <div style={{ position:'relative', overflow:'hidden' }}>
        <div style={{ position:'absolute', inset:0, background:'radial-gradient(1200px 500px at 70% -10%, rgba(255,71,0,0.10), transparent 60%)', pointerEvents:'none' }} />
        {/* the product itself, present but not shouting — off-centre, softly out of focus */}
        <img src={dashShot} alt="" aria-hidden className="pg-shot pg-heroshot"
          style={{ right:'-180px', top:'82px', width:760, transform:'rotate(2.5deg)', opacity:0.62,
                   maskImage:'linear-gradient(245deg, rgba(0,0,0,0.97) 40%, transparent 84%)',
                   WebkitMaskImage:'linear-gradient(245deg, rgba(0,0,0,0.97) 40%, transparent 84%)' }} />
        <div style={{ ...container, position:'relative', paddingTop:'clamp(64px, 10vw, 116px)', paddingBottom:72 }}>
          <div style={{ maxWidth:760 }}>
            <div className="rv"><Eyebrow>TNFX partner program</Eyebrow></div>
            <h1 className="rv" style={{ fontSize:'clamp(38px, 7vw, 66px)', fontWeight:700, letterSpacing:'-0.035em',
                 lineHeight:1.04, margin:'0 0 20px', transitionDelay:'60ms' }}>
              Get paid on every lot your clients trade.
            </h1>
            <p className="rv" style={{ fontSize:17, color:T.t2, lineHeight:1.65, maxWidth:'58ch', margin:'0 0 30px', transitionDelay:'120ms' }}>
              TNFX partners have earned more than <b style={{ color:T.t1 }}>$10,000,000</b> in commission
              introducing traders to an FSA-licensed broker. Up to <b style={{ color:T.t1 }}>$10 per lot</b> on
              gold and majors, tracked live to the dollar, withdrawable anytime.
            </p>
            <div className="rv" style={{ display:'flex', gap:12, flexWrap:'wrap', alignItems:'center', transitionDelay:'180ms' }}>
              <button ref={heroCtaRef} onClick={() => openAuth('register')} className="pg-cta"
                style={{ height:52, padding:'0 30px', fontSize:15 }}>Become a partner</button>
              <a href="#commission" className="pg-ghost" style={{ height:52, padding:'0 24px', fontSize:15,
                 display:'inline-flex', alignItems:'center', textDecoration:'none', boxSizing:'border-box' }}>See commission rates</a>
            </div>
            <div className="rv" style={{ fontSize:12, color:T.t3, marginTop:14, transitionDelay:'240ms' }}>
              60-second application · Reviewed by a real desk</div>
            <div className="rv" style={{ fontSize:12.5, color:T.t3, marginTop:34, letterSpacing:'0.02em', transitionDelay:'300ms' }}>
              FSA licensed&nbsp;&nbsp;·&nbsp;&nbsp;MT4 &amp; MT5&nbsp;&nbsp;·&nbsp;&nbsp;1000+ instruments&nbsp;&nbsp;·&nbsp;&nbsp;Instant local deposits</div>
          </div>
        </div>
      </div>

      {/* ── 3 · proof rail ── */}
      <div style={{ borderTop:`1px solid ${T.line}`, borderBottom:`1px solid ${T.line}` }}>
        <div className="pg-proof rv" style={{ ...container, display:'grid', gridTemplateColumns:'repeat(4, 1fr)' }}>
          {[
            { v: <CountUp to={10} prefix="$" suffix="M+" grad />, l: 'Commission paid to partners' },
            { v: <CountUp to={6000} suffix="+" />, l: 'Active partners' },
            { v: <CountUp to={325000} suffix="+" />, l: 'Trading clients' },
            { v: <CountUp to={10} prefix="$" />, l: 'Top rate per lot' },
          ].map((s, i) => (
            <div key={i} style={{ padding:'30px 18px', borderLeft: i ? `1px solid ${T.line}` : 'none' }}>
              <div>{s.v}</div>
              <div style={{ fontSize:13, color:T.t3, marginTop:6 }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 4 · commission rail (centerpiece) ── */}
      <div id="commission" style={{ ...sect, position:'relative', overflow:'hidden' }}>
        <img src={tnfxMark} alt="" className="pg-bull" aria-hidden
          style={{ position:'absolute', right:-120, top:'50%', transform:'translateY(-50%)', width:620,
                   opacity:0.055, filter:'grayscale(1)', pointerEvents:'none' }} />
        <div style={{ ...container, position:'relative' }}>
          <div className="rv"><Eyebrow>Commission structure</Eyebrow></div>
          <div className="rv" style={{ transitionDelay:'60ms' }}><H2>Six grades. One number that matters.</H2></div>
          <p className="rv" style={{ fontSize:16, color:T.t2, lineHeight:1.65, maxWidth:'62ch', margin:'0 0 46px', transitionDelay:'120ms' }}>
            Per-lot commission on gold and major pairs. Hit the thresholds and your rate moves
            up — no negotiation, no favoritism.
          </p>

          {/* desktop rail ≥1100px */}
          <div className="pg-rail-d rv" style={{ borderTop:`1px solid ${T.line}`, borderBottom:`1px solid ${T.line}`, position:'relative' }}>
            {/* hairline curve through the tick steps — makes the ascent read intentional */}
            <svg aria-hidden viewBox="0 0 600 106" preserveAspectRatio="none"
              style={{ position:'absolute', left:0, bottom:0, width:'100%', height:106, pointerEvents:'none', zIndex:1 }}>
              <polyline points="50,88 150,74 250,60 350,46 450,32 550,18" fill="none"
                stroke="rgba(255,255,255,0.13)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            </svg>
            {TIERS.map((t, i) => (
              <div key={t.name} className="pg-col" style={{ paddingBottom:96 }}>
                <div style={{ fontSize:12, fontWeight:600, letterSpacing:'0.14em', textTransform:'uppercase',
                              color: t.top ? T.acc : T.t3, marginBottom:12 }}>
                  {t.name}{t.top ? <span style={{ display:'block', fontSize:10, letterSpacing:'0.12em', color:T.t3, marginTop:3 }}>TOP GRADE</span> : null}
                </div>
                <div style={{ display:'flex', alignItems:'baseline', gap:5, marginBottom:18 }}>
                  <span className={t.top ? 'pg-rate pg-gradtxt' : 'pg-rate'}
                    style={{ fontSize:'clamp(36px, 3.6vw, 54px)', fontWeight:700, letterSpacing:'-0.03em',
                             color: t.top ? undefined : T.t1 }}>${t.rate}</span>
                  <span style={{ fontSize:13, color:T.t3 }}>/ lot</span>
                </div>
                {t.entry ? (
                  <div style={{ fontSize:13, color:T.t3, lineHeight:1.7 }}>Entry grade —<br />no requirements</div>
                ) : (
                  <div style={{ fontSize:13, lineHeight:1.85 }}>
                    <div><span style={{ color:T.t3 }}>Deposits</span> <span style={{ color:T.t2, float:'right' }}>{t.dep}</span></div>
                    <div style={{ clear:'both' }}><span style={{ color:T.t3 }}>Lots / mo</span> <span style={{ color:T.t2, float:'right' }}>{t.lots}</span></div>
                    <div style={{ clear:'both' }}><span style={{ color:T.t3 }}>Funded accts</span> <span style={{ color:T.t2, float:'right' }}>{t.accts}</span></div>
                  </div>
                )}
                {/* ascending tick — 14px step per grade, drawn once on reveal */}
                <div className="pg-tick" style={{ bottom:18 + i * 14, animationDelay:`${i * 90}ms` }} />
              </div>
            ))}
          </div>

          {/* mobile ledger <1100px — vertical rail with node dots (graft) */}
          <div className="pg-rail-m rv" style={{ borderTop:`1px solid ${T.line}` }}>
            {TIERS.map((t) => (
              <div key={t.name} style={{ display:'flex', alignItems:'center', gap:16, padding:'18px 2px',
                   borderBottom:`1px solid ${T.line}`, position:'relative', paddingLeft:22 }}>
                <div style={{ position:'absolute', left:4, top:0, bottom:0, width:2,
                              background: t.top ? T.grad : T.line }} />
                <div style={{ position:'absolute', left:0, top:'50%', transform:'translateY(-50%)', width:10, height:10,
                              borderRadius:'50%', background: t.top ? T.acc : T.bg2,
                              border: t.top ? 'none' : `1.5px solid ${T.line2}` }} />
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:13, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase',
                                color: t.top ? T.acc : T.t1 }}>{t.name}</div>
                  <div style={{ fontSize:12.5, color:T.t3, marginTop:4, lineHeight:1.5 }}>
                    {t.entry ? 'Entry grade — no requirements'
                             : `${t.dep} deposits · ${t.lots} lots/mo · ${t.accts} funded accts`}</div>
                </div>
                <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
                  <span className={t.top ? 'pg-gradtxt' : undefined}
                        style={{ fontSize:32, fontWeight:700, letterSpacing:'-0.03em', color: t.top ? undefined : T.t1 }}>${t.rate}</span>
                  <span style={{ fontSize:12, color:T.t3 }}>/ lot</span>
                </div>
              </div>
            ))}
          </div>

          <div className="rv" style={{ fontSize:12.5, color:T.t3, margin:'18px 0 30px', lineHeight:1.6 }}>
            Per standard lot on gold and major pairs. Grades are reviewed against cumulative client
            deposits, monthly traded volume, and funded accounts.</div>
          <button onClick={() => openAuth('register')} className="pg-cta rv"
            style={{ height:46, padding:'0 26px', fontSize:14.5 }}>Start at Bronze — apply now</button>
        </div>
      </div>

      {/* ── 5 · how it works ── */}
      <div id="how" style={{ borderTop:`1px solid ${T.line}`, background:T.bg1 }}>
        <div style={{ ...container, ...sect }}>
          <div className="rv"><Eyebrow>Getting started</Eyebrow></div>
          <div className="rv" style={{ transitionDelay:'60ms' }}><H2>From application to first commission.</H2></div>
          <div className="pg-steps" style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:'42px 48px', marginTop:48 }}>
            {[
              ['01', 'Apply in 60 seconds', 'Name, contact, and how you introduce clients. That is the whole form.'],
              ['02', 'Desk approval', 'Our partner desk reviews every application and activates your account.'],
              ['03', 'Share your link', 'Ready-made ad banners carry your referral link — post them anywhere your audience is.'],
              ['04', 'Earn per lot', 'Commission lands on every trade your clients make. Withdraw it anytime.'],
            ].map(([n, t, b], i) => (
              <div key={n} className="rv" style={{ transitionDelay:`${i * 70}ms` }}>
                <div style={{ fontSize:15, fontWeight:600, color:T.t3 }}>{n}</div>
                <div style={{ width:24, height:1, background:T.grad, margin:'10px 0 14px' }} />
                <div style={{ fontSize:19, fontWeight:600, letterSpacing:'-0.01em', marginBottom:8 }}>{t}</div>
                <div style={{ fontSize:15, color:T.t2, lineHeight:1.6 }}>{b}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 6 · partner tools ── */}
      <div id="tools" style={{ borderTop:`1px solid ${T.line}` }}>
        <div className="pg-2col" style={{ ...container, ...sect, display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:56, alignItems:'start' }}>
          <div>
            <div className="rv"><Eyebrow>Partner tools</Eyebrow></div>
            <div className="rv" style={{ transitionDelay:'60ms' }}><H2>Your entire book, in numbers.</H2></div>
            <p className="rv" style={{ fontSize:16, color:T.t2, lineHeight:1.65, maxWidth:'56ch', margin:'0 0 28px', transitionDelay:'120ms' }}>
              The partner dashboard shows every client, every lot, and every dollar in real time.
              No monthly statements, no guessing.</p>
            {[
              ['Real-time reporting', 'Every registration, deposit, and traded lot appears the moment it happens.', ''],
              ['Weekly challenges', 'Cash rewards for hitting weekly targets.', 'up to $1,000 / wk'],
              ['Career path', 'Promotion missions that move you up the grade ladder.', '$5 → $10 / lot'],
              ['Marketing kit', 'Ready-made banners with your referral link already embedded.', ''],
              ['Withdraw anytime', 'Your commission is yours — no lockups, no minimum cycles.', ''],
            ].map(([t, b, fig], i) => (
              <div key={t} className="rv" style={{ display:'flex', alignItems:'baseline', gap:16, padding:'17px 4px',
                   borderTop:`1px solid ${T.line}`, transitionDelay:`${i * 60}ms` }}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:17, fontWeight:600, letterSpacing:'-0.01em' }}>{t}</div>
                  <div style={{ fontSize:14.5, color:T.t2, lineHeight:1.55, marginTop:3 }}>{b}</div>
                </div>
                {fig && <div style={{ fontSize:14, fontWeight:600, color:T.acc, whiteSpace:'nowrap' }}>{fig}</div>}
              </div>
            ))}
          </div>
          {/* illustration ledger panel — honest mock, labelled */}
          <div className="rv" style={{ background:T.bg1, border:`1px solid ${T.line}`, borderRadius:14,
               padding:'24px 24px 18px', transitionDelay:'150ms' }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:18 }}>
              <span style={{ fontSize:11.5, fontWeight:700, letterSpacing:'0.14em', color:T.t3 }}>PARTNER DASHBOARD</span>
              <span style={{ fontSize:11, color:T.t3 }}>Illustration</span>
            </div>
            {[
              ['Clients', '48'],
              ['Funded accounts', '31'],
              ['Lots this month', '312'],
              ['Commission accrued', '$2,496'],
            ].map(([l, v], i) => (
              <div key={l} style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
                   padding:'15px 2px', borderTop: i ? `1px solid ${T.line}` : 'none' }}>
                <span style={{ fontSize:14, color:T.t2 }}>{l}</span>
                <span style={{ fontSize:17, fontWeight:600, color:T.t1 }}>{v}</span>
              </div>
            ))}
            <div style={{ marginTop:12, paddingTop:14, borderTop:`1px solid ${T.line}`,
                 display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <span style={{ fontSize:13, color:T.t3 }}>Withdrawable now</span>
              <span className="pg-gradtxt" style={{ fontSize:20, fontWeight:700 }}>$2,496</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── 7 · regional trust band ── */}
      <div style={{ borderTop:`1px solid ${T.line}`, borderBottom:`1px solid ${T.line}`, background:T.bg1 }}>
        <div className="pg-2col" style={{ ...container, padding:'84px 24px', display:'grid',
             gridTemplateColumns:'1fr 1fr', gap:48, alignItems:'center' }}>
          <div>
            <div className="rv"><H2>Built for the region you work in.</H2></div>
            <p className="rv" style={{ fontSize:16, color:T.t2, lineHeight:1.65, margin:0, transitionDelay:'80ms' }}>
              Your clients fund accounts in minutes through instant local deposit methods and trade
              1000+ instruments on MT4 and MT5 — with an FSA-licensed broker behind every trade.</p>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr' }}>
            {[
              ['FSA', 'Licensed broker'],
              ['MT4 & MT5', 'Both platforms'],
              ['1000+', 'Instruments'],
              ['Instant', 'Local deposit methods'],
            ].map(([v, l], i) => (
              <div key={l} className="rv" style={{ padding:'20px 18px',
                   borderLeft: i % 2 ? `1px solid ${T.line}` : 'none',
                   borderTop: i > 1 ? `1px solid ${T.line}` : 'none', transitionDelay:`${i * 60}ms` }}>
                <div style={{ fontSize:19, fontWeight:700, letterSpacing:'-0.01em' }}>{v}</div>
                <div style={{ fontSize:13, color:T.t3, marginTop:3 }}>{l}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 8 · final CTA ── */}
      <div style={{ padding:'128px 24px', textAlign:'center' }}>
        <div style={{ maxWidth:640, margin:'0 auto' }}>
          <div className="rv"><H2>Your first client can be trading this week.</H2></div>
          <p className="rv" style={{ fontSize:16, color:T.t2, lineHeight:1.6, margin:'0 0 32px', transitionDelay:'70ms' }}>
            A 60-second application. Bronze rate from day one. Commission on the very first lot.</p>
          <div className="rv" style={{ display:'flex', gap:20, justifyContent:'center', alignItems:'center',
               flexWrap:'wrap', transitionDelay:'140ms' }}>
            <button onClick={() => openAuth('register')} className="pg-cta"
              style={{ height:54, padding:'0 36px', fontSize:15.5 }}>Become a partner</button>
            <button onClick={() => openAuth('login')} style={{ background:'none', border:'none', color:T.t2,
              fontSize:14, cursor:'pointer', padding:'10px 4px' }}>Already a partner? Log in</button>
          </div>
        </div>
      </div>

      {/* ── 9 · footer ── */}
      <div style={{ borderTop:`1px solid ${T.line}`, background:T.bg0 }}>
        <div style={{ ...container, padding:'56px 24px 40px' }}>
          <div style={{ display:'flex', alignItems:'center', gap:18, flexWrap:'wrap' }}>
            <img src={tnfxLogo} alt="TNFX" style={{ height:22 }} />
            <div style={{ marginLeft:'auto', display:'flex', gap:22, flexWrap:'wrap', alignItems:'center' }}>
              <button onClick={() => openAuth('login')} style={{ background:'none', border:'none', color:T.t2,
                fontSize:14, cursor:'pointer', padding:0 }}>Partner login</button>
              <a href="#commission" style={{ color:T.t2, fontSize:14, textDecoration:'none' }}>Commission rates</a>
            </div>
          </div>
          <div style={{ fontSize:12.5, color:T.t3, marginTop:16 }}>
            FSA licensed&nbsp;&nbsp;·&nbsp;&nbsp;MT4 &amp; MT5 platforms&nbsp;&nbsp;·&nbsp;&nbsp;1000+ instruments&nbsp;&nbsp;·&nbsp;&nbsp;Instant local deposits</div>
          <div style={{ fontSize:12.5, color:T.t3, lineHeight:1.7, marginTop:26, paddingTop:22, borderTop:`1px solid ${T.line}` }}>
            TNFX is licensed by the Financial Services Authority (FSA). Trading foreign exchange and CFDs
            carries a high level of risk and may not be suitable for all investors. Partner commissions are
            paid on client trading activity; past partner earnings do not guarantee future results.</div>
          <div style={{ fontSize:12, color:T.t3, marginTop:14 }}>© 2026 TNFX. All rights reserved.</div>
        </div>
      </div>

      {/* ── sticky mobile CTA (graft) — appears after the hero CTA scrolls out ── */}
      <div className="pg-stick" style={{ position:'fixed', left:0, right:0, bottom:0, zIndex:120,
           transform: stick ? 'translateY(0)' : 'translateY(110%)', transition:'transform .25s ease-out' }}>
        <div className="pg-top" style={{ borderTop:`1px solid ${T.line}`, padding:'10px 16px' }}>
          <button onClick={() => openAuth('register')} className="pg-cta"
            style={{ width:'100%', height:48, fontSize:15 }}>Become a partner</button>
        </div>
      </div>
    </div>
  );
}
