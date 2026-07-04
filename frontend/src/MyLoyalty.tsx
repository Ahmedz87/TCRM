import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from './api';

/* ── per-tier identity: each tier restyles the whole page ── */
const TIERS: any = {
  bronze:   { name: 'Bronze',   accent: '#C77B45', accent2: '#E0A06A', glow: 'rgba(199,123,69,0.55)',  heroBg: 'radial-gradient(120% 80% at 50% 0%, #1a1208 0%, #0B0E14 55%)' },
  silver:   { name: 'Silver',   accent: '#AEB7C2', accent2: '#D6DCE4', glow: 'rgba(174,183,194,0.5)',  heroBg: 'radial-gradient(120% 80% at 50% 0%, #373f4d 0%, #0B0E14 55%)' },
  gold:     { name: 'Gold',     accent: '#E8B84B', accent2: '#F4D36B', glow: 'rgba(232,184,75,0.6)',   heroBg: 'radial-gradient(120% 80% at 50% 0%, #1a1407 0%, #0B0E14 55%)' },
  platinum: { name: 'Platinum', accent: '#6FE3D4', accent2: '#A6F0E6', glow: 'rgba(111,227,212,0.6)',  heroBg: 'radial-gradient(120% 80% at 50% 0%, #07191a 0%, #0B0E14 55%)' },
};
const ORDER = ['bronze', 'silver', 'gold', 'platinum'];
const MEDAL: any = { bronze: '🥉', silver: '🥈', gold: '🥇', platinum: '💎' };
const fmt = (n: number) => Math.round(n || 0).toLocaleString();

const STATUS_STYLE: any = {
  won:        { label: 'Won 🎉',     c: '#34D399', bg: 'rgba(52,211,153,0.14)' },
  funded:     { label: 'Funded',     c: '#E8B84B', bg: 'rgba(232,184,75,0.14)' },
  verified:   { label: 'Verified',   c: '#6FE3D4', bg: 'rgba(111,227,212,0.14)' },
  registered: { label: 'Registered', c: '#9aa3b3', bg: 'rgba(154,163,179,0.12)' },
  invited:    { label: 'Invited',    c: '#9aa3b3', bg: 'rgba(154,163,179,0.10)' },
  pending:    { label: 'Pending',    c: '#E8B84B', bg: 'rgba(232,184,75,0.10)' },
  pending_admin_review: { label: 'In review', c: '#E8B84B', bg: 'rgba(232,184,75,0.10)' },
  ineligible: { label: 'Ineligible', c: '#F2667A', bg: 'rgba(242,102,122,0.14)' },
};

function useCountUp(target: number, ms = 1300) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let raf = 0, start = 0;
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min(1, (ts - start) / ms);
      setVal(ease(p) * target);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return val;
}

export default function MyLoyalty({ clientId }: { clientId?: number }) {
  const [cid, setCid] = useState<number | undefined>(clientId);
  const [cidInput, setCidInput] = useState(clientId ? String(clientId) : '');
  const [data, setData] = useState<any>(null);
  const [rewards, setRewards] = useState<any[]>([]);
  const [refs, setRefs] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inv, setInv] = useState({ name: '', phone: '' });
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const load = (id: number) => {
    setLoading(true);
    Promise.all([
      apiGet(`/loyalty/member/${id}`),
      apiGet('/loyalty/rewards'),
      apiGet(`/loyalty/referrals/${id}`),
    ]).then(([m, r, rf]: any) => {
      setData(m?.error ? null : m);
      setRewards(r?.rewards || []);
      setRefs(rf || null);
    }).catch(() => setData(null)).finally(() => setLoading(false));
  };
  useEffect(() => { if (cid) load(cid); }, [cid]);

  const fireConfetti = (x: number, y: number) => {
    const cv = canvasRef.current; if (!cv) return;
    cv.width = cv.offsetWidth; cv.height = cv.offsetHeight;
    const ctx = cv.getContext('2d'); if (!ctx) return;
    const cols = ['#E8B84B', '#F4D36B', '#6FE3D4', '#34D399', '#fff'];
    const parts: any[] = [];
    for (let i = 0; i < 70; i++) parts.push({ x, y, vx: (Math.random() - 0.5) * 8, vy: -Math.random() * 9 - 2, g: 0.3, life: 1, col: cols[i % cols.length], s: Math.random() * 4 + 2 });
    const tick = () => {
      ctx.clearRect(0, 0, cv.width, cv.height);
      let alive = false;
      parts.forEach(p => { if (p.life <= 0) return; alive = true; p.vy += p.g; p.x += p.vx; p.y += p.vy; p.life -= 0.012; ctx.globalAlpha = Math.max(0, p.life); ctx.fillStyle = p.col; ctx.fillRect(p.x, p.y, p.s, p.s); });
      ctx.globalAlpha = 1;
      if (alive) requestAnimationFrame(tick);
    };
    tick();
  };

  const claim = async (rid: number, e: any) => {
    if (!data) return;
    setToast('');
    const res: any = await apiPost('/loyalty/redeem', { client_id: data.client_id, reward_id: rid });
    if (res?.ok) {
      const cv = canvasRef.current;
      if (cv && e?.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); const c = cv.getBoundingClientRect(); fireConfetti(r.left - c.left + r.width / 2, r.top - c.top); }
      setToast(`Claimed ${res.reward}! New balance ${fmt(res.new_balance)} pts.`);
      load(data.client_id);
    } else setToast(res?.error === 'insufficient points' ? `Not enough points — need ${fmt(res.needed)}, you have ${fmt(res.balance)}.` : (res?.error || 'Could not claim reward.'));
  };

  const sendInvite = async () => {
    if (!data || !inv.name.trim()) return;
    const res: any = await apiPost('/loyalty/referral', { referrer_client_id: data.client_id, referred_name: inv.name.trim(), referred_phone: inv.phone.trim(), bonus_points: 100 });
    if (res?.ok) { setToast(`Invite sent to ${inv.name}. You'll earn 100 pts when they fund.`); setInv({ name: '', phone: '' }); setInviteOpen(false); load(data.client_id); }
  };

  const Picker = <ClientSearch onPick={(id: number) => { setCidInput(String(id)); setCid(id); }} />;

  if (!cid) return <div style={S.page}>{Picker}<div style={S.empty}>Enter a client ID to preview their loyalty page.</div></div>;
  if (loading && !data) return <div style={S.page}>{Picker}<div style={S.empty}>Loading…</div></div>;
  if (!data) return <div style={S.page}>{Picker}<div style={S.empty}>This client isn’t in the loyalty program yet.</div></div>;

  return <LoyaltyView data={data} rewards={rewards} refs={refs} toast={toast} inviteOpen={inviteOpen} inv={inv}
    setInviteOpen={setInviteOpen} setInv={setInv} claim={claim} sendInvite={sendInvite} canvasRef={canvasRef} picker={Picker} />;
}

function LoyaltyView({ data, rewards, refs, toast, inviteOpen, inv, setInviteOpen, setInv, claim, sendInvite, canvasRef, picker }: any) {
  const t = TIERS[data.tier] || TIERS.bronze;
  const promoNeed = data.promo_streak_needed || 30;
  const xpPct = Math.min(100, Math.round((data.current_streak / promoNeed) * 100));

  const balCount = useCountUp(data.points_balance);
  const lifeCount = useCountUp(data.lifetime_points);
  const streakCount = useCountUp(data.current_streak, 1100);

  const [xpW, setXpW] = useState(0);
  const [rewardW, setRewardW] = useState(0);
  useEffect(() => { const id = setTimeout(() => setXpW(xpPct), 250); return () => clearTimeout(id); }, [xpPct]);

  const nextBig = [...rewards].filter(r => r.cost_points > data.points_balance).sort((a, b) => a.cost_points - b.cost_points)[0];
  const nextBigPct = nextBig ? Math.min(100, Math.round((data.points_balance / nextBig.cost_points) * 100)) : 100;
  useEffect(() => { const id = setTimeout(() => setRewardW(nextBigPct), 400); return () => clearTimeout(id); }, [nextBigPct]);

  const activeDays = new Set<string>();
  (data.ledger || []).forEach((l: any) => { if (l.date) activeDays.add(l.date); });
  if (data.last_trade_date) activeDays.add(data.last_trade_date);

  const RDAYS = 30;
  const filledTail = Math.min(data.current_streak, RDAYS);

  return (
    <div style={{ ...S.page, background: t.heroBg, borderRadius: 18 }}>
      {picker}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ ...S.eyebrow, color: t.accent }}>My TN Points</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, color: '#34D399', letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 700 }}>
          <span style={{ ...S.blink, width: 6, height: 6, borderRadius: 99, background: '#34D399', display: 'inline-block' }} />Live
        </span>
      </div>

      <div style={{ position: 'relative', background: 'linear-gradient(160deg,#141821,#0d1016)', border: `1px solid ${t.accent}55`, borderRadius: 20, padding: 26, marginBottom: 14, overflow: 'hidden' }}>
        <div style={{ ...S.sheen }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap', position: 'relative' }}>
          <div style={{ position: 'relative', width: 104, height: 104, flex: '0 0 auto' }}>
            <div style={{ ...S.ring, borderColor: t.accent, boxShadow: `0 0 34px -6px ${t.glow}, inset 0 0 18px -8px ${t.glow}` }} />
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={S.float}>{MEDAL[data.tier]}</div>
              <div style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: t.accent, marginTop: 4, fontWeight: 800 }}>{t.name}</div>
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 230 }}>
            <div style={S.eyebrow}>Points balance</div>
            <div style={{ fontSize: 64, fontWeight: 900, letterSpacing: '-0.035em', lineHeight: 1, color: '#fff', fontVariantNumeric: 'tabular-nums', textShadow: `0 0 30px ${t.glow.replace(/0\.[0-9]+/, '0.25')}` }}>{fmt(balCount)}</div>
            <div style={{ fontSize: 13, color: '#9aa3b3', marginTop: 8 }}>
              {data.next_tier
                ? <>Earning <b style={{ color: t.accent }}>{data.tier_rate} pts</b> / lot · <b style={{ color: '#fff' }}>{data.streak_to_promotion}</b> trading days to <b style={{ color: TIERS[data.next_tier].accent }}>{TIERS[data.next_tier].name}</b></>
                : <>Top tier reached · <b style={{ color: t.accent }}>{data.tier_rate} pts</b> / lot 💎</>}
            </div>
          </div>
        </div>
        {data.next_tier && (
          <div style={{ marginTop: 22 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9aa3b3', marginBottom: 6 }}>
              <span style={S.eyebrow}>Level up to {TIERS[data.next_tier].name}</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}><b style={{ color: t.accent }}>{data.current_streak}</b> / {promoNeed} day streak</span>
            </div>
            <div style={{ height: 14, borderRadius: 99, background: '#1A1F2B', overflow: 'hidden', border: '1px solid #2a2f3c' }}>
              <div style={{ ...S.xpbar, height: '100%', width: `${xpW}%`, background: `linear-gradient(90deg, ${t.accent}, ${t.accent2}, ${TIERS[data.next_tier].accent})`, backgroundSize: '200% 100%' }} />
            </div>
          </div>
        )}
      </div>

      {nextBig && (
        <div style={{ background: 'linear-gradient(135deg,#14110a,#12161F)', border: `1px solid ${t.accent}40`, borderRadius: 16, padding: 18, marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 38, filter: `drop-shadow(0 0 12px ${t.glow})` }}>🎯</div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={S.eyebrow}>Closest reward</div>
              <div style={{ fontSize: 17, fontWeight: 800, color: '#fff', margin: '2px 0 8px' }}>{nextBig.name} — <span style={{ color: t.accent }}>{nextBigPct}% there</span></div>
              <div style={{ height: 9, borderRadius: 99, background: '#1A1F2B', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${rewardW}%`, borderRadius: 99, background: `linear-gradient(90deg,${t.accent},${t.accent2})`, transition: 'width 1.4s cubic-bezier(.2,.9,.2,1)' }} />
              </div>
              <div style={{ fontSize: 11, color: '#9aa3b3', marginTop: 6 }}>{fmt(data.points_balance)} / {fmt(nextBig.cost_points)} pts · <b style={{ color: '#fff' }}>{fmt(nextBig.cost_points - data.points_balance)}</b> to go</div>
            </div>
          </div>
        </div>
      )}

      <div style={S.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
          <span style={S.eyebrow}>Trading streak</span>
          <span style={{ fontSize: 12, color: '#9aa3b3' }}>🔥 <b style={{ color: t.accent }}>{data.current_streak}</b> days · best <b style={{ color: '#fff' }}>{data.best_streak}</b></span>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 54 }}>
          {Array.from({ length: RDAYS }, (_, i) => {
            const fromEnd = RDAYS - i;
            const filled = fromEnd <= filledTail;
            const h = filled ? 20 + Math.min(28, (filledTail - fromEnd + 1) * 4) : 8;
            return <div key={i} style={{ flex: 1, height: h, borderRadius: 2, background: filled ? `linear-gradient(180deg,${t.accent2},${t.accent})` : '#222a38', transformOrigin: 'bottom', animation: filled && fromEnd === 1 ? 'tipPulse 1.3s ease-in-out infinite' : 'none' }} title={filled ? 'Active' : 'No trade'} />;
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 9.5, color: '#5a6373', letterSpacing: '0.08em', textTransform: 'uppercase' }}><span>~30 days ago</span><span>Today ●</span></div>
      </div>

      <MonthCalendar activeDays={activeDays} accent={t.accent} accent2={t.accent2} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 14 }}>
        <Chip label="Streak" value={`${Math.round(streakCount)}d`} sub="days 🔥" color={t.accent} accent={t.accent} />
        <Chip label="Lifetime" value={fmt(lifeCount)} sub="points earned" color="#34D399" accent={t.accent} />
        <Chip label={data.tier === 'bronze' ? 'Tier floor' : 'Demotion in'} value={data.tier === 'bronze' ? '—' : (data.demote_in_days != null ? `${data.demote_in_days}d` : '—')} sub={data.tier === 'bronze' ? 'Bronze floor' : 'keep trading'} color={data.demote_in_days != null && data.demote_in_days <= 5 ? '#F2667A' : '#6FE3D4'} accent={t.accent} />
      </div>

      <div style={S.panel}>
        <div style={{ ...S.eyebrow, marginBottom: 14 }}>Tier ladder</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {ORDER.map((k) => {
            const reached = ORDER.indexOf(data.tier) >= ORDER.indexOf(k);
            const isBest = data.best_tier === k && data.best_tier !== data.tier;
            const tk = TIERS[k];
            return (
              <div key={k} style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ height: 8, borderRadius: 4, background: reached ? tk.accent : '#222a38', boxShadow: data.tier === k ? `0 0 12px ${tk.glow}` : 'none' }} />
                <div style={{ fontSize: 10, marginTop: 6, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800, color: reached ? tk.accent : '#5a6373' }}>{tk.name}</div>
                {data.tier === k && <div style={{ fontSize: 9, color: '#9aa3b3', marginTop: 2 }}>you are here</div>}
                {isBest && <div style={{ fontSize: 9, color: tk.accent, marginTop: 2 }}>🏆 best</div>}
              </div>
            );
          })}
        </div>
      </div>

      <div style={S.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
          <span style={S.eyebrow}>Claim rewards</span>
          <span style={{ fontSize: 11, color: '#9aa3b3' }}>1 pt = $1 bonus · cash = pts ÷ 12</span>
        </div>
        {toast && <div style={S.toast}>{toast}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {rewards.map((rw: any) => {
            const afford = data.points_balance >= rw.cost_points;
            return (
              <div key={rw.id} className="rwcard" style={{ background: '#0d1016', border: `1px solid ${afford ? t.accent + '66' : '#232a38'}`, borderRadius: 12, padding: 14, transition: 'transform .15s', opacity: afford ? 1 : 0.8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={{ fontSize: 13.5, fontWeight: 800, color: '#fff' }}>{rw.name}</span>
                  <span style={{ fontSize: 12, fontWeight: 800, color: t.accent, fontVariantNumeric: 'tabular-nums' }}>{fmt(rw.cost_points)}</span>
                </div>
                <div style={{ fontSize: 11, color: '#9aa3b3', margin: '5px 0 10px', minHeight: 30 }}>{rw.description}</div>
                <button disabled={!afford} onClick={(e: any) => claim(rw.id, e)} style={{ width: '100%', padding: 9, borderRadius: 8, fontSize: 12, fontWeight: 800, cursor: afford ? 'pointer' : 'not-allowed', background: afford ? t.accent : '#1A1F2B', color: afford ? '#0B0E14' : '#5a6373', border: `1px solid ${afford ? t.accent : '#232a38'}` }}>
                  {afford ? 'Claim now' : `${fmt(rw.cost_points - data.points_balance)} to go`}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div style={S.panel}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
          <span style={S.eyebrow}>Your invites · earn 100 pts each</span>
          <span style={{ fontSize: 11, color: '#9aa3b3' }}>Code <b style={{ color: t.accent, letterSpacing: '0.05em' }}>{data.referral_code}</b>{refs?.summary && <> · {refs.summary.won} won · {refs.summary.pending} pending</>}</span>
        </div>
        {refs?.invites?.length > 0 ? (
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #232a38' }}>
            {refs.invites.map((iv: any) => {
              const st = STATUS_STYLE[iv.status] || STATUS_STYLE.invited;
              return (
                <div key={iv.id} style={S.inviteRow}>
                  <span style={{ width: 28, height: 28, borderRadius: 99, background: '#1A1F2B', display: 'grid', placeItems: 'center', fontSize: 11, color: '#9aa3b3', fontWeight: 700 }}>{(iv.name || '?').slice(0, 2).toUpperCase()}</span>
                  <span style={{ flex: 1, fontSize: 13, color: '#E7ECF3' }}>{iv.name}</span>
                  <span style={{ fontSize: 12, color: '#9aa3b3', fontVariantNumeric: 'tabular-nums' }}>{iv.phone}</span>
                  <span style={{ fontSize: 10.5, fontWeight: 700, padding: '3px 9px', borderRadius: 6, color: st.c, background: st.bg }}>{st.label}</span>
                </div>
              );
            })}
          </div>
        ) : <div style={{ fontSize: 12, color: '#9aa3b3', padding: '6px 0' }}>No invites yet. Invite a friend — earn 100 points when they fund their account.</div>}
        {!inviteOpen ? (
          <button onClick={() => setInviteOpen(true)} style={{ marginTop: 12, padding: '9px 18px', borderRadius: 8, fontSize: 12, fontWeight: 800, background: t.accent, color: '#0B0E14', border: 'none', cursor: 'pointer' }}>+ Invite a friend</button>
        ) : (
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <input autoFocus value={inv.name} onChange={(e: any) => setInv({ ...inv, name: e.target.value })} placeholder="Friend's name" style={{ ...S.input, flex: 1, minWidth: 140 }} />
            <input value={inv.phone} onChange={(e: any) => setInv({ ...inv, phone: e.target.value })} placeholder="Phone (optional)" style={{ ...S.input, flex: 1, minWidth: 140 }} />
            <button onClick={sendInvite} style={{ padding: '9px 18px', borderRadius: 8, fontSize: 12, fontWeight: 800, background: t.accent, color: '#0B0E14', border: 'none', cursor: 'pointer' }}>Send</button>
            <button onClick={() => { setInviteOpen(false); setInv({ name: '', phone: '' }); }} style={S.btnGhost}>Cancel</button>
          </div>
        )}
      </div>

      {data.ledger?.length > 0 && (
        <div style={S.panel}>
          <div style={{ ...S.eyebrow, marginBottom: 12 }}>Recent points</div>
          <div className="lscroll" style={{ maxHeight: 240, overflowY: 'auto', paddingRight: 12 }}>
            {data.ledger.map((l: any, i: number) => (
              <div key={i} style={S.ledgerRow}>
                <span style={{ color: '#9aa3b3', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.date} · <span style={{ color: '#E7ECF3' }}>{l.symbol || l.kind}</span> {l.lots > 0 ? `· ${l.lots.toFixed(2)} lots @ ${l.tier}` : ''}</span>
                <span style={{ color: l.points >= 0 ? '#34D399' : '#F2667A', fontWeight: 800, fontVariantNumeric: 'tabular-nums', flex: '0 0 auto', paddingLeft: 12 }}>{l.points >= 0 ? '+' : ''}{fmt(l.points)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, pointerEvents: 'none', width: '100%', height: '100%' }} />
      <style>{KEYFRAMES}</style>
    </div>
  );
}

function MonthCalendar({ activeDays, accent, accent2 }: any) {
  const now = new Date();
  const year = now.getFullYear(), month = now.getMonth();
  const startDow = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = now.getDate();
  const monthName = now.toLocaleString('default', { month: 'long', year: 'numeric' });
  const pad = (n: number) => String(n).padStart(2, '0');
  const cells: any[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  const activeCount = cells.filter(d => d && activeDays.has(`${year}-${pad(month + 1)}-${pad(d)}`)).length;

  return (
    <div style={S.panel}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16 }}>
        <span style={S.eyebrow}>Active days · {monthName}</span>
        <span style={{ fontSize: 11, color: '#9aa3b3' }}><b style={{ color: accent }}>{activeCount}</b> active this month</span>
      </div>
      <div style={{ maxWidth: 392, margin: '0 auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6 }}>
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => <div key={i} style={{ textAlign: 'center', fontSize: 10, color: '#5a6373', letterSpacing: '0.06em', fontWeight: 700, paddingBottom: 4 }}>{d}</div>)}
          {cells.map((d, i) => {
            if (!d) return <div key={i} />;
            const key = `${year}-${pad(month + 1)}-${pad(d)}`;
            const active = activeDays.has(key);
            const isToday = d === today;
            const isWeekend = (i % 7 === 0 || i % 7 === 6);
            const future = d > today;
            return (
              <div key={i} className={'calcell' + (active ? ' act' : '')} style={{
                aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 9, fontSize: 12.5,
                fontWeight: active ? 800 : 600, fontVariantNumeric: 'tabular-nums',
                background: active ? `linear-gradient(140deg,${accent2},${accent})` : (future ? 'transparent' : (isWeekend ? '#0d1016' : '#161b25')),
                color: active ? '#0B0E14' : (future ? '#39414f' : (isWeekend ? '#3a4150' : '#9aa3b3')),
                border: isToday ? `1.5px solid ${accent}` : '1px solid #1a2030',
                boxShadow: active ? `0 3px 12px -3px ${accent}aa` : 'none',
              }} title={active ? 'Traded' : (future ? '' : (isWeekend ? 'Weekend' : 'No trade'))}>{d}</div>
            );
          })}
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 18, fontSize: 10, color: '#5a6373', marginTop: 14 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 11, height: 11, borderRadius: 3, background: `linear-gradient(140deg,${accent2},${accent})` }} />Traded</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 11, height: 11, borderRadius: 3, background: '#161b25', border: '1px solid #1a2030' }} />No trade</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 11, height: 11, borderRadius: 3, border: `1.5px solid ${accent}` }} />Today</span>
      </div>
    </div>
  );
}

const TIER_DOT: any = { bronze: '#C77B45', silver: '#AEB7C2', gold: '#E8B84B', platinum: '#6FE3D4' };

function ClientSearch({ onPick }: { onPick: (id: number) => void }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return; }
    setLoading(true);
    const id = setTimeout(() => {
      apiGet(`/loyalty/search?q=${encodeURIComponent(q.trim())}`)
        .then((r: any) => { setResults(r?.results || []); setOpen(true); })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const h = (e: any) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const maskPhone = (p: string) => p && p.length > 4 ? p.slice(0, 3) + ' *** ' + p.slice(-2) : p;

  return (
    <div ref={boxRef} style={{ position: 'relative', marginBottom: 16, maxWidth: 460 }}>
      <span style={{ ...S.eyebrow, display: 'block', marginBottom: 6 }}>Find a client</span>
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        placeholder="Search by name, email, phone, or ID…"
        style={{ ...S.input, width: '100%', boxSizing: 'border-box' }}
      />
      {open && (results.length > 0 || loading) && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, zIndex: 50,
          background: '#12161F', border: '1px solid #2a3240', borderRadius: 10, overflow: 'hidden',
          maxHeight: 320, overflowY: 'auto', boxShadow: '0 12px 40px -8px rgba(0,0,0,0.6)',
        }}>
          {loading && <div style={{ padding: 12, fontSize: 12, color: '#9aa3b3' }}>Searching…</div>}
          {!loading && results.map((r) => (
            <div key={r.client_id}
              onClick={() => { onPick(r.client_id); setOpen(false); setQ(r.name); }}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', cursor: 'pointer', borderBottom: '1px solid #1A1F2B' }}
              onMouseEnter={(e: any) => e.currentTarget.style.background = '#1A1F2B'}
              onMouseLeave={(e: any) => e.currentTarget.style.background = 'transparent'}>
              <span style={{ width: 8, height: 8, borderRadius: 99, background: TIER_DOT[r.tier] || '#5a6373', flex: '0 0 auto' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: '#E7ECF3', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</div>
                <div style={{ fontSize: 11, color: '#9aa3b3', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {r.email || maskPhone(r.phone) || `ID ${r.client_id}`} · #{r.client_id}
                </div>
              </div>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: TIER_DOT[r.tier] || '#9aa3b3', textTransform: 'capitalize' }}>{r.tier}</span>
              <span style={{ fontSize: 11, color: '#9aa3b3', fontVariantNumeric: 'tabular-nums' }}>{fmt(r.points)}</span>
            </div>
          ))}
          {!loading && results.length === 0 && <div style={{ padding: 12, fontSize: 12, color: '#9aa3b3' }}>No matches.</div>}
        </div>
      )}
    </div>
  );
}

function Chip({ label, value, sub, color, accent }: any) {
  return (
    <div className="chip" style={{ background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 16, transition: 'transform .15s, border-color .15s' }}
      onMouseEnter={(e: any) => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.borderColor = accent + '66'; }}
      onMouseLeave={(e: any) => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.borderColor = '#232a38'; }}>
      <div style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#9aa3b3', fontWeight: 800 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 900, color, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      <div style={{ fontSize: 10, color: '#5a6373' }}>{sub}</div>
    </div>
  );
}

const KEYFRAMES = `
@keyframes sheenMove { 0%{left:-40%} 100%{left:120%} }
@keyframes ringpulse { 0%,100%{filter:brightness(1)} 50%{filter:brightness(1.3)} }
@keyframes floaty { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }
@keyframes xpshift { 0%{background-position:0% 50%} 100%{background-position:200% 50%} }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }
@keyframes tipPulse {0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.14)}}
@keyframes popIn {0%{opacity:0;transform:scale(.9)}100%{opacity:1;transform:scale(1)}}
.rwcard:hover{transform:translateY(-3px);}
.lscroll::-webkit-scrollbar{width:8px;height:8px}
.lscroll::-webkit-scrollbar-track{background:transparent}
.lscroll::-webkit-scrollbar-thumb{background:#2a3240;border-radius:8px}
.lscroll::-webkit-scrollbar-thumb:hover{background:#3a4250}
.lscroll{scrollbar-width:thin;scrollbar-color:#2a3240 transparent}
.calcell{transition:transform .12s ease, box-shadow .12s ease}
.calcell.act:hover{transform:scale(1.08)}
`;

const S: any = {
  page: { color: '#E7ECF3', padding: 20, maxWidth: 980, margin: '0 auto', fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif', position: 'relative' },
  eyebrow: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#9aa3b3', fontWeight: 800 },
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 16, padding: 18, marginBottom: 14 },
  empty: { padding: 40, textAlign: 'center', color: '#9aa3b3', fontSize: 14, background: '#12161F', border: '1px solid #232a38', borderRadius: 14 },
  input: { padding: '8px 12px', borderRadius: 9, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 13, outline: 'none' },
  btnGhost: { padding: '8px 14px', borderRadius: 9, background: 'transparent', border: '1px solid #2a3240', color: '#E7ECF3', fontSize: 12.5, cursor: 'pointer' },
  toast: { fontSize: 12.5, color: '#34D399', background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 8, padding: '8px 12px', marginBottom: 12 },
  inviteRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderBottom: '1px solid #1A1F2B', background: '#0d1016' },
  ledgerRow: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', fontSize: 12, borderBottom: '1px solid #1A1F2B' },
  sheen: { position: 'absolute', top: '-50%', left: '-40%', width: '60%', height: '200%', transform: 'skewX(-20deg)', background: 'linear-gradient(90deg,transparent,rgba(255,255,255,0.05),transparent)', animation: 'sheenMove 4.5s ease-in-out infinite' },
  ring: { position: 'absolute', inset: 0, borderRadius: 24, border: '2px solid', animation: 'ringpulse 2.6s ease-in-out infinite' },
  float: { fontSize: 34, lineHeight: 1, animation: 'floaty 3s ease-in-out infinite' },
  xpbar: { borderRadius: 99, animation: 'xpshift 2.5s linear infinite', transition: 'width 1.6s cubic-bezier(.2,.9,.2,1)' },
  blink: { animation: 'blink 1.4s ease-in-out infinite' },
};
