import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import MyLoyalty from './MyLoyalty';

const TIER_COLOR: any = { bronze:'#cd7f32', silver:'#c0c0c0', gold:'#ffd700', platinum:'#7fd3ff' };
const TIER_BG: any = { bronze:'rgba(205,127,50,0.15)', silver:'rgba(192,192,192,0.15)', gold:'rgba(255,215,0,0.15)', platinum:'rgba(127,211,255,0.15)' };
const TIER_RATE: any = { bronze:4, silver:5, gold:6, platinum:7 };
const TIER_ORDER = ['bronze','silver','gold','platinum'];
const fmtP = (n:number) => Math.round(n).toLocaleString();
const menuBtn: React.CSSProperties = { display:'block', width:'100%', textAlign:'left', padding:'9px 10px', background:'none', border:'none', color:'#e8e8e8', fontSize:12.5, cursor:'pointer', borderRadius:6 };

export default function Loyalty() {
  const [stats, setStats] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [tier, setTier] = useState('all');
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [rewards, setRewards] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [sortBy, setSortBy] = useState('lifetime');
  // clicking a member name opens a small menu: client page OR their loyalty page (client view).
  const [menu, setMenu] = useState<any>(null);          // { m, x, y }
  const [clientView, setClientView] = useState<number|null>(null);  // client_id to preview in client perspective

  // navigate to the Clients page for this member.
  // Dashboard's 'navigate' handler switches to clients + fires 'clients_search';
  // openProfile = client_id makes Clients fetch /clients/{id} directly (exact match).
  const goToClient = (m:any) => {
    setMenu(null);
    try {
      window.dispatchEvent(new CustomEvent('navigate', {
        detail: { page: 'clients', search: m.name || String(m.client_id), openProfile: m.client_id }
      }));
    } catch {}
  };

  const openNameMenu = (m:any, e:any) => {
    e.stopPropagation();
    setMenu({ m, x: Math.min(e.clientX, window.innerWidth - 240), y: e.clientY });
  };
  // close the name menu on any outside click / escape
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const esc = (ev:any) => { if (ev.key === 'Escape') setMenu(null); };
    window.addEventListener('click', close);
    window.addEventListener('keydown', esc);
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', esc); };
  }, [menu]);

  useEffect(() => { apiGet('/loyalty/stats').then(setStats).catch(()=>{}); }, []);
  useEffect(() => { apiGet('/loyalty/rewards').then((d:any)=>setRewards(d?.rewards||[])).catch(()=>{}); }, []);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ tier, search, limit:'200' });
    apiGet(`/loyalty/leaderboard?${p}`).then((d:any)=>setMembers(d?.members||[])).catch(()=>setMembers([])).finally(()=>setLoading(false));
  }, [tier, search]);

  const TIER_RANK: any = { bronze:0, silver:1, gold:2, platinum:3 };
  const sortedMembers = [...members].sort((a,b) => {
    if (sortBy === 'points') return b.points_balance - a.points_balance;
    if (sortBy === 'tier') return (TIER_RANK[b.tier]-TIER_RANK[a.tier]) || (b.lifetime_points-a.lifetime_points);
    if (sortBy === 'streak') return b.current_streak - a.current_streak;
    return b.lifetime_points - a.lifetime_points; // default: lifetime
  });

  const openMember = (id:number) => {
    setDetail({ loading:true });
    apiGet(`/loyalty/member/${id}`).then(setDetail).catch(()=>setDetail(null));
  };

  const redeem = async (rewardId:number) => {
    if (!detail) return;
    setMsg('');
    const res:any = await apiPost('/loyalty/redeem', { client_id: detail.client_id, reward_id: rewardId });
    if (res?.ok) {
      setMsg(`Redeemed ${res.reward}. New balance: ${fmtP(res.new_balance)} pts`);
      openMember(detail.client_id);
      apiGet('/loyalty/stats').then(setStats).catch(()=>{});
    } else {
      setMsg(res?.error === 'insufficient points' ? `Not enough points (need ${fmtP(res.needed)}, have ${fmtP(res.balance)})` : (res?.error || 'Redemption failed'));
    }
  };

  const TIER_TABS = [['all','All'],['bronze','Bronze'],['silver','Silver'],['gold','Gold'],['platinum','Platinum']];

  return (
    <div style={{ color:'#e8e8e8', padding:16 }}>
      <div style={{ display:'flex', alignItems:'baseline', gap:12, marginBottom:16 }}>
        <h2 style={{ margin:0, fontSize:20, fontWeight:600 }}>📊 TN Point Program</h2>
        <span style={{ fontSize:12, color:'#888' }}>Loyalty rewards · earn points by trading</span>
      </div>

      {/* Stats strip */}
      {stats && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:10, marginBottom:18 }}>
          {[
            ['Members', stats.members, '#fff'],
            ['Bronze', stats.bronze, TIER_COLOR.bronze],
            ['Silver', stats.silver, TIER_COLOR.silver],
            ['Gold', stats.gold, TIER_COLOR.gold],
            ['Platinum', stats.platinum, TIER_COLOR.platinum],
            ['Points out', fmtP(stats.points_outstanding), '#00e5a0'],
          ].map(([label,val,color]:any)=>(
            <div key={label} style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'12px 14px' }}>
              <div style={{ fontSize:11, color:'#888', marginBottom:4 }}>{label}</div>
              <div style={{ fontSize:21, fontWeight:600, color }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display:'flex', gap:8, marginBottom:12, flexWrap:'wrap' }}>
        {TIER_TABS.map(([k,label])=>(
          <button key={k} onClick={()=>setTier(k)}
            style={{ padding:'6px 14px', borderRadius:8, fontSize:12, cursor:'pointer',
              background: tier===k? TIER_BG[k]||'rgba(0,170,255,0.15)':'transparent',
              border:`1px solid ${tier===k?(TIER_COLOR[k]||'#00aaff'):'#626d80'}`,
              color: tier===k?(TIER_COLOR[k]||'#00aaff'):'#aaa' }}>{label}</button>
        ))}
        <select value={sortBy} onChange={e=>setSortBy(e.target.value)}
          style={{ marginLeft:'auto', padding:'6px 10px', borderRadius:8, background:'var(--bg-input,#373f4d)', border:'1px solid #626d80', color:'#fff', fontSize:12 }}>
          <option value="lifetime">Sort: Lifetime points</option>
          <option value="points">Sort: Points balance</option>
          <option value="tier">Sort: Tier</option>
          <option value="streak">Sort: Current streak</option>
        </select>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search name or ID..."
          style={{ padding:'6px 12px', borderRadius:8, background:'var(--bg-input,#373f4d)', border:'1px solid #626d80', color:'#fff', fontSize:12 }} />
      </div>

      {/* Leaderboard */}
      <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, overflow:'hidden' }}>
        <div style={{ display:'grid', gridTemplateColumns:'50px 1fr 90px 100px 80px 110px', gap:8, padding:'10px 14px', fontSize:10, color:'#666', textTransform:'uppercase', borderBottom:'1px solid #4f596b' }}>
          <span>#</span><span>Member</span><span>Tier</span><span style={{textAlign:'right'}}>Points</span><span style={{textAlign:'right'}}>Streak</span><span style={{textAlign:'right'}}>Best</span>
        </div>
        {loading && <div style={{ padding:20, color:'#666', fontSize:13 }}>Loading…</div>}
        {!loading && members.length===0 && <div style={{ padding:20, color:'#666', fontSize:13 }}>No members yet.</div>}
        <div style={{ maxHeight:560, overflowY:'auto' }}>
          {sortedMembers.map((m,i)=>(
            <div key={m.client_id} onClick={()=>openMember(m.client_id)}
              style={{ display:'grid', gridTemplateColumns:'50px 1fr 90px 100px 80px 110px', gap:8, padding:'11px 14px', fontSize:12.5, borderBottom:'1px solid #373f4d', cursor:'pointer', alignItems:'center' }}
              onMouseEnter={e=>(e.currentTarget.style.background='#161922')}
              onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
              <span style={{ color:'#666' }}>{i+1}</span>
              <span>
                <span onClick={(e)=>openNameMenu(m,e)} style={{ color:'#4ea1ff', cursor:'pointer', textDecoration:'underline', textDecorationStyle:'dotted' }}
                  title="Open…">{m.name}</span>
                <span style={{ color:'#666', fontSize:10 }}> #{m.client_id} {m.country&&'· '+m.country}</span>
              </span>
              <span><span style={{ padding:'3px 9px', borderRadius:6, fontSize:10.5, fontWeight:700, textTransform:'uppercase', background:TIER_BG[m.tier], color:TIER_COLOR[m.tier] }}>{m.tier}</span></span>
              <span style={{ textAlign:'right', color:'#00e5a0', fontWeight:600 }}>{fmtP(m.points_balance)}</span>
              <span style={{ textAlign:'right', color: m.current_streak>=10?'#ffaa00':'#aaa' }}>🔥 {m.current_streak}</span>
              <span style={{ textAlign:'right', fontSize:10 }}>
                <span style={{ color: TIER_COLOR[m.best_tier]||'#888', fontWeight:600, textTransform:'uppercase' }}>{m.best_tier||m.tier}</span>
                <span style={{ color:'#666' }}> · {m.best_streak}d</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Name click menu: open client page OR their loyalty page (client perspective) */}
      {menu && (
        <div onClick={(e)=>e.stopPropagation()} style={{ position:'fixed', top:menu.y, left:menu.x, zIndex:200,
          background:'#1c2230', border:'1px solid #4f596b', borderRadius:10, padding:6, minWidth:230,
          boxShadow:'0 12px 40px -8px rgba(0,0,0,0.7)' }}>
          <div style={{ fontSize:11, color:'#888', padding:'6px 10px 8px', borderBottom:'1px solid #373f4d', marginBottom:4 }}>
            {menu.m.name} <span style={{ color:'#666' }}>· #{menu.m.client_id}</span>
          </div>
          <button onClick={()=>{ setClientView(menu.m.client_id); setMenu(null); }}
            style={menuBtn}>🎁 View their loyalty page <span style={{ color:'#888', fontSize:11 }}>(client view)</span></button>
          <button onClick={()=>goToClient(menu.m)} style={menuBtn}>👤 Open client page</button>
        </div>
      )}

      {/* Client-perspective loyalty page (reuses the portal MyLoyalty view) */}
      {clientView!=null && (
        <div onClick={()=>setClientView(null)} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', zIndex:150, display:'flex', justifyContent:'center', alignItems:'flex-start', overflowY:'auto', padding:'24px 12px' }}>
          <div onClick={e=>e.stopPropagation()} style={{ width:1020, maxWidth:'98vw', background:'#0B0E14', borderRadius:18, border:'1px solid #2a3240', position:'relative' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 18px', borderBottom:'1px solid #1A1F2B' }}>
              <span style={{ fontSize:12, color:'#9aa3b3', letterSpacing:'0.1em', textTransform:'uppercase', fontWeight:700 }}>Client view · how the customer sees their loyalty</span>
              <button onClick={()=>setClientView(null)} style={{ background:'none', border:'none', color:'#888', fontSize:24, cursor:'pointer', lineHeight:1 }}>×</button>
            </div>
            <MyLoyalty clientId={clientView} />
          </div>
        </div>
      )}

      {/* Member detail drawer */}
      {detail && (
        <div onClick={()=>{setDetail(null);setMsg('');}} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.6)', zIndex:100, display:'flex', justifyContent:'flex-end' }}>
          <div onClick={e=>e.stopPropagation()} style={{ width:720, maxWidth:'95vw', height:'100%', overflowY:'auto', background:'#262c36', borderLeft:'1px solid #4f596b', padding:24 }}>
            {detail.loading ? <div style={{ color:'#888' }}>Loading…</div> : detail.error ? <div style={{ color:'#ff5d6c' }}>Not found</div> : (<>
              {/* Header */}
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:18 }}>
                <div>
                  <div style={{ fontSize:20, fontWeight:600 }}>{detail.name}</div>
                  <div style={{ fontSize:12, color:'#888' }}>#{detail.client_id} {detail.country&&'· '+detail.country} · Referral: {detail.referral_code}</div>
                </div>
                <button onClick={()=>{setDetail(null);setMsg('');}} style={{ background:'none', border:'none', color:'#888', fontSize:22, cursor:'pointer' }}>×</button>
              </div>

              {/* Tier badge + points */}
              <div style={{ display:'flex', gap:12, marginBottom:18, alignItems:'stretch' }}>
                <div style={{ flex:'0 0 auto', background:TIER_BG[detail.tier], border:`1px solid ${TIER_COLOR[detail.tier]}`, borderRadius:12, padding:'18px 24px', textAlign:'center', minWidth:130 }}>
                  <div style={{ fontSize:28 }}>{detail.tier==='platinum'?'💎':detail.tier==='gold'?'🥇':detail.tier==='silver'?'🥈':'🥉'}</div>
                  <div style={{ fontSize:16, fontWeight:700, textTransform:'uppercase', color:TIER_COLOR[detail.tier], marginTop:4 }}>{detail.tier}</div>
                  <div style={{ fontSize:10, color:'#888', marginTop:2 }}>{TIER_RATE[detail.tier]} pts / lot</div>
                </div>
                <div style={{ flex:1, background:'#373f4d', borderRadius:12, padding:'18px 20px', display:'flex', flexDirection:'column', justifyContent:'center' }}>
                  <div style={{ fontSize:11, color:'#888' }}>Points balance</div>
                  <div style={{ fontSize:34, fontWeight:700, color:'#00e5a0' }}>{fmtP(detail.points_balance)}</div>
                  <div style={{ fontSize:11, color:'#666' }}>Lifetime earned: {fmtP(detail.lifetime_points)}</div>
                </div>
              </div>

              {/* Tier progress bar */}
              <div style={{ marginBottom:18 }}>
                <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:8 }}>Tier progress</div>
                <div style={{ display:'flex', alignItems:'center', gap:4 }}>
                  {TIER_ORDER.map((t,i)=>{
                    const reached = TIER_ORDER.indexOf(detail.tier) >= i;
                    return (
                      <React.Fragment key={t}>
                        <div style={{ flex:1, textAlign:'center' }}>
                          <div style={{ height:6, borderRadius:3, background: reached? TIER_COLOR[t] : '#4f596b' }} />
                          <div style={{ fontSize:9, marginTop:4, color: reached? TIER_COLOR[t] : '#555', textTransform:'uppercase' }}>{t}</div>
                        </div>
                      </React.Fragment>
                    );
                  })}
                </div>
                {detail.next_tier && (
                  <div style={{ fontSize:11, color:'#888', marginTop:8 }}>
                    {detail.streak_to_promotion > 0
                      ? `${detail.streak_to_promotion} more consecutive trading days → promote to ${detail.next_tier} (needs ${detail.promo_streak_needed}-day streak)`
                      : `Eligible for promotion to ${detail.next_tier}!`}
                  </div>
                )}
                {!detail.next_tier && <div style={{ fontSize:11, color:TIER_COLOR.platinum, marginTop:8 }}>Top tier reached 💎</div>}
                <div style={{ fontSize:10.5, color:'#777', marginTop:6 }}>
                  🔥 Streak = consecutive trading days (weekends don't count as gaps). Any missed trading day resets it. Promotions: Silver 30 · Gold 30 · Platinum 60 days.
                </div>
              </div>

              {/* Best achievement badge */}
              <div style={{ display:'flex', gap:10, marginBottom:18 }}>
                <div style={{ flex:1, background:'linear-gradient(135deg, rgba(255,215,0,0.08), rgba(127,211,255,0.05))', border:'1px solid #2a2d36', borderRadius:10, padding:'12px 16px', display:'flex', alignItems:'center', gap:12 }}>
                  <span style={{ fontSize:24 }}>🏆</span>
                  <div>
                    <div style={{ fontSize:10, color:'#666', textTransform:'uppercase' }}>Best achievement</div>
                    <div style={{ fontSize:13 }}>
                      Peak tier <span style={{ color: TIER_COLOR[detail.best_tier]||'#fff', fontWeight:700, textTransform:'uppercase' }}>{detail.best_tier||detail.tier}</span>
                      <span style={{ color:'#666' }}> · </span>
                      Longest streak <span style={{ color:'#ffaa00', fontWeight:700 }}>🔥 {detail.best_streak} days</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Streak + inactivity */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10, marginBottom:18 }}>
                <div style={{ background:'#373f4d', borderRadius:8, padding:'12px 14px' }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase' }}>Current streak</div>
                  <div style={{ fontSize:22, fontWeight:600, color:'#ffaa00' }}>🔥 {detail.current_streak}</div>
                  <div style={{ fontSize:10, color:'#666' }}>best {detail.best_streak} days</div>
                </div>
                <div style={{ background:'#373f4d', borderRadius:8, padding:'12px 14px' }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase' }}>Last trade</div>
                  <div style={{ fontSize:14, fontWeight:600, marginTop:4 }}>{detail.last_trade_date||'—'}</div>
                  <div style={{ fontSize:10, color:'#666' }}>{detail.days_inactive!=null?`${detail.days_inactive}d ago`:''}</div>
                </div>
                <div style={{ background:'#373f4d', borderRadius:8, padding:'12px 14px' }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase' }}>Demotion in</div>
                  <div style={{ fontSize:22, fontWeight:600, color: detail.demote_in_days!=null && detail.demote_in_days<=5?'#ff5d6c':'#aaa' }}>
                    {detail.demote_in_days!=null? `${detail.demote_in_days}d` : '—'}
                  </div>
                  <div style={{ fontSize:10, color:'#666' }}>{detail.tier==='bronze'?'floor tier':'30d inactive = demote'}</div>
                </div>
              </div>

              {/* Rewards catalog */}
              <div style={{ marginBottom:18 }}>
                <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:8 }}>Rewards catalog</div>
                {msg && <div style={{ fontSize:12, color:'#00e5a0', marginBottom:8, padding:'6px 10px', background:'rgba(0,229,160,0.1)', borderRadius:6 }}>{msg}</div>}
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                  {rewards.map(rw=>{
                    const afford = detail.points_balance >= rw.cost_points;
                    return (
                      <div key={rw.id} style={{ background:'#373f4d', borderRadius:8, padding:'12px 14px', border:`1px solid ${afford?'#1e2a22':'#373f4d'}` }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                          <span style={{ fontSize:13, fontWeight:600 }}>{rw.name}</span>
                          <span style={{ fontSize:12, color:'#00e5a0', fontWeight:600 }}>{fmtP(rw.cost_points)} pts</span>
                        </div>
                        <div style={{ fontSize:10.5, color:'#888', margin:'4px 0 8px' }}>{rw.description}</div>
                        <button disabled={!afford} onClick={()=>redeem(rw.id)}
                          style={{ width:'100%', padding:'6px', borderRadius:6, fontSize:11, fontWeight:600, cursor: afford?'pointer':'not-allowed',
                            background: afford?'rgba(0,229,160,0.15)':'#373f4d',
                            border:`1px solid ${afford?'#00e5a0':'#626d80'}`, color: afford?'#00e5a0':'#555' }}>
                          {afford?'Redeem':'Not enough points'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Recent activity */}
              {detail.ledger?.length>0 && (
                <div style={{ marginBottom:12 }}>
                  <div style={{ fontSize:10, color:'#666', textTransform:'uppercase', marginBottom:8 }}>Recent point activity</div>
                  <div style={{ background:'#373f4d', borderRadius:8, overflow:'hidden', maxHeight:240, overflowY:'auto' }}>
                    {detail.ledger.map((l:any,i:number)=>(
                      <div key={i} style={{ display:'flex', justifyContent:'space-between', padding:'7px 12px', fontSize:11, borderBottom:'1px solid #373f4d' }}>
                        <span style={{ color:'#aaa' }}>{l.date} · {l.symbol||l.kind} {l.lots>0?`(${l.lots.toFixed(2)} lots @ ${l.tier})`:''}</span>
                        <span style={{ color: l.points>=0?'#00e5a0':'#ff5d6c', fontWeight:600 }}>{l.points>=0?'+':''}{fmtP(l.points)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>)}
          </div>
        </div>
      )}
    </div>
  );
}
