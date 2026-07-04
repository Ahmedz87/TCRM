import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from './api';
import { TH, fmtMoney } from './theme';

// ─────────────────────────────────────────────────────────────────────────────
// Bonus system UI: a fixed KPI bar (top of dashboard) + a full Bonus page.
// Welcome bonus runs a state machine (KYC → login → device check → claim).
// Deposit bonus shows a tiered progress checklist (50% / 20% / special offers),
// with consumed/finished lines struck-through. Special offers show a countdown.
// ─────────────────────────────────────────────────────────────────────────────

export function useBonusStatus(pollWhileAwaiting = false) {
  const [data, setData] = useState<any>(null);
  const timer = useRef<any>(null);
  const reload = () => apiGet('/portal/bonus/status').then(setData).catch(() => {});
  useEffect(() => {
    reload();
    return () => { if (timer.current) clearInterval(timer.current); };
    // eslint-disable-next-line
  }, []);
  // Auto-advance the welcome bonus STEP BY STEP: poll while it's in any non-final, waiting state
  // (KYC being read → log into MT → team review) so the KPI updates itself with no page refresh.
  // Stop once it reaches a state the client acts on or that's final (eligible/blocked/claimed/…).
  useEffect(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    const POLL = ['kyc_review', 'pending_review', 'awaiting_login', 'review', 'in_review', 'submitted'];
    if (pollWhileAwaiting && POLL.includes(data?.welcome?.state)) {
      // poll faster while the AI/login step resolves; slower while a human review is pending
      const ms = data?.welcome?.state === 'review' ? 15000 : 5000;
      timer.current = setInterval(reload, ms);
    }
    return () => { if (timer.current) clearInterval(timer.current); };
    // eslint-disable-next-line
  }, [pollWhileAwaiting, data?.welcome?.state]);
  return { data, reload };
}

// animated "waiting for login" dots: . .. ... ....
function useDots() {
  const [n, setN] = useState(1);
  useEffect(() => { const t = setInterval(() => setN(x => (x % 3) + 1), 450); return () => clearInterval(t); }, []);
  // render inside a FIXED-WIDTH inline-block so the animation never changes the
  // element's width (the cycling dots used to jitter the whole KPI on mobile).
  return <span style={{ display: 'inline-block', width: 16, textAlign: 'left' }}>{'.'.repeat(n)}</span>;
}

// responsive flag
function useIsMobile(bp = 760) {
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.innerWidth <= bp);
  useEffect(() => { const o = () => setM(window.innerWidth <= bp); window.addEventListener('resize', o); return () => window.removeEventListener('resize', o); }, [bp]);
  return m;
}

function timeLeft(ends?: string): string {
  if (!ends) return '';
  const end = new Date(ends.replace(' ', 'T')).getTime();
  const ms = end - Date.now();
  if (ms <= 0) return 'ended';
  const d = Math.floor(ms / 86400000), h = Math.floor((ms % 86400000) / 3600000), m = Math.floor((ms % 3600000) / 60000);
  if (d > 0) return `${d}d ${h}h left`;
  if (h > 0) return `${h}h ${m}m left`;
  return `${m}m left`;
}

// ── the welcome button: label + action vary with state ──
function WelcomeButton({ w, onClaim, onUploadKyc, claiming, big }: any) {
  const dots = useDots();
  const base: any = { padding: big ? '13px 28px' : '9px 16px', borderRadius: 11, border: 'none', fontSize: big ? 15 : 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' };
  const grad = { ...base, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', boxShadow: big ? '0 6px 20px rgba(232,184,75,0.35)' : 'none' };
  const green = { ...base, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', boxShadow: big ? '0 6px 20px rgba(58,210,159,0.35)' : 'none' };
  const dim = { ...base, background: TH.panel2, color: TH.muted, border: `1px solid ${TH.border2}`, cursor: 'default' };
  switch (w.state) {
    case 'kyc_upload': return <button style={grad} onClick={onUploadKyc}>Upload your KYC</button>;
    case 'kyc_review': return <button style={dim} disabled>KYC under review</button>;
    case 'awaiting_login': return <button style={{ ...dim, color: TH.gold, minWidth: big ? 210 : 188, textAlign: 'center' }} disabled>Log in to your account{dots}</button>;
    case 'eligible': return <button style={green} disabled={claiming} onClick={onClaim}>{claiming ? 'Claiming…' : 'Claim your bonus'}</button>;
    case 'review': return <button style={{ ...dim, color: TH.gold }} disabled>Under team review{dots}</button>;
    case 'blocked': return <button style={dim} disabled>Not eligible</button>;
    case 'not_eligible': case 'family_claimed': return <button style={dim} disabled>Not eligible</button>;
    case 'claimed': return <span style={{ fontSize: 13, fontWeight: 800, color: TH.accent }}>✓ Claimed</span>;
    default: return <button style={dim} disabled>Unavailable</button>;
  }
}

// ════════════ FIXED KPI HERO (top of dashboard) — ONE offer at a time ════════════
// Shows a single big, fancy offer with one CTA. Rolls forward as each is consumed:
//   welcome bonus → (claimed/gone) → 50% deposit → 20% deposit → special offers.
export function BonusBar({ onDeposit, onUploadKyc }: { onDeposit?: () => void; onUploadKyc?: () => void }) {
  const { data, reload } = useBonusStatus(true);
  const [claiming, setClaiming] = useState(false);
  const [flash, setFlash] = useState('');
  const mobile = useIsMobile();

  if (!data || !data.enabled) return null;
  if (data.blocked) {
    return <div style={S.heroWrap}><div style={{ color: TH.muted, fontSize: 13 }}>🎁 Bonuses are not available in {data.country}.</div></div>;
  }

  const w = data.welcome, dep = data.deposit, offers = data.offers || [], bday = data.birthday;
  const liveOffer = offers.find((o: any) => !o.claimed);
  const tier1Left = dep.tier1_bonus_remaining, capLeft = dep.cap_remaining;

  const claim = async () => {
    setClaiming(true);
    try { const r: any = await apiPost('/portal/bonus/welcome/claim', {}); setFlash(r?.message || 'Bonus credited!'); reload(); }
    catch (e: any) { setFlash(e?.message || 'Could not claim.'); }
    finally { setClaiming(false); setTimeout(() => setFlash(''), 4500); }
  };
  const claimBirthday = async () => {
    setClaiming(true);
    try { const r: any = await apiPost('/portal/bonus/birthday/claim', {}); setFlash(r?.message || '🎂 Birthday bonus credited!'); reload(); }
    catch (e: any) { setFlash(e?.message || 'Could not claim.'); }
    finally { setClaiming(false); setTimeout(() => setFlash(''), 4500); }
  };

  // pick the ONE current offer, in priority order. Each bonus TYPE has its OWN colour theme so the
  // client sees they've rolled onto a different reward: welcome=gold (green once ready to claim),
  // 50% deposit=blue, 20% deposit=purple, special offer=pink.
  const welcomeActionable = !['claimed', 'disabled'].includes(w.state);
  // Birthday is time-sensitive — it takes the top slot during the client's birthday window.
  const bdayActionable = bday && bday.in_window && ['eligible', 'need_deposit'].includes(bday.state);
  let item: any = null;
  if (bdayActionable) {
    if (bday.state === 'eligible') {
      item = { eyebrow: '🎂 Happy Birthday!', big: fmtMoney(bday.amount), small: 'birthday gift', theme: 'cake',
        sub: 'Your birthday gift is ready — claim it now and it lands straight on your trading account.',
        button: <button style={{ padding: '13px 28px', borderRadius: 11, border: 'none', fontSize: 15, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap', background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', boxShadow: '0 6px 20px rgba(58,210,159,0.35)' }} disabled={claiming} onClick={claimBirthday}>{claiming ? 'Claiming…' : 'Claim your $100 🎂'}</button> };
    } else {
      item = { eyebrow: '🎂 Happy Birthday!', big: fmtMoney(bday.amount), small: 'gift locked', theme: 'cake', deposit: true,
        sub: "Your birthday gift is locked — you don't have a deposit in the last 365 days. Make a deposit to unlock your $100." };
    }
  } else if (welcomeActionable) {
    item = { eyebrow: '🎁 Welcome bonus', big: fmtMoney(w.amount), small: 'free credit',
      theme: w.state === 'eligible' ? 'green' : 'gold',
      sub: (w.reason || '') + (w.note ? '  ' + w.note : ''), button: <WelcomeButton w={w} onClaim={claim} onUploadKyc={onUploadKyc} claiming={claiming} big /> };
  } else if (liveOffer) {
    item = { eyebrow: `✨ Limited offer · ${timeLeft(liveOffer.ends_at)}`, big: `${liveOffer.percent}%`, theme: 'pink', deposit: true,
      small: `up to ${fmtMoney(liveOffer.cap)}`, sub: `${liveOffer.name}${liveOffer.min_deposit ? ` · min deposit ${fmtMoney(liveOffer.min_deposit)}` : ''}` };
  } else if (tier1Left > 0) {
    item = { eyebrow: `🎁 ${dep.tier1_pct}% Deposit bonus`, big: `+${fmtMoney(tier1Left)}`, small: 'bonus available', theme: 'blue', deposit: true,
      sub: `Get ${dep.tier1_pct}% on your next deposit (then ${dep.tier2_pct}% above). Up to ${fmtMoney(dep.total_cap)} total.` };
  } else if (capLeft > 0) {
    item = { eyebrow: `🎁 ${dep.tier2_pct}% Deposit bonus`, big: `${dep.tier2_pct}%`, small: `up to ${fmtMoney(capLeft)} more`, theme: 'purple', deposit: true,
      sub: `Earn ${dep.tier2_pct}% bonus on every deposit, up to your ${fmtMoney(dep.total_cap)} cap.` };
  }

  // all bonuses consumed
  if (!item) {
    return (
      <div style={S.heroWrap}>
        <div style={S.heroInner}>
          <div style={{ flex: 1 }}>
            <div style={S.heroEyebrow}>🎁 Bonuses</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#fff', marginTop: 2 }}>You've claimed all available bonuses 🎉</div>
          </div>
          <span style={S.heroCredit}>Bonus credit <b style={{ color: TH.gold }}>{fmtMoney(data.credit)}</b></span>
        </div>
      </div>
    );
  }

  const th = BTHEMES[item.theme] || BTHEMES.gold;
  const button = item.deposit
    ? <button style={{ ...S.heroBtn, background: th.btn, color: th.btnText, boxShadow: `0 6px 20px ${th.accent}59` }} onClick={onDeposit}>Deposit now</button>
    : item.button;

  return (
    <div style={{ ...S.heroWrap, background: th.wrap, border: `1px solid ${th.border}`, boxShadow: th.shine, ...(mobile ? { padding: '16px 14px' } : {}) }}>
      <div style={{ ...S.heroGlow, background: th.glow }} />
      {flash && <div style={S.flash}>{flash}</div>}
      <div style={{ ...S.heroInner, ...(mobile ? { flexDirection: 'column', gap: 12, alignItems: 'stretch' } : {}) }}>
        {!mobile && <div style={S.heroSpacer} />}
        <div style={S.heroContent}>
          <div style={{ ...S.heroEyebrow, color: th.accent }}>{item.eyebrow}</div>
          <div style={{ ...S.heroHeadline, ...(mobile ? { gap: 8 } : {}) }}>
            <span style={{ ...S.heroBig, backgroundImage: th.big, ...(mobile ? { fontSize: 40 } : {}) }}>{item.big}</span>
            {item.small && <span style={{ ...S.heroSmall, ...(mobile ? { fontSize: 15 } : {}) }}>{item.small}</span>}
          </div>
          <div style={S.heroSub}>{item.sub}</div>
        </div>
        <div style={{ ...S.heroRight, ...(mobile ? { flexDirection: 'column', alignItems: 'center', gap: 8, width: '100%' } : {}) }}>
          {button}
          <span style={S.heroCredit}>Bonus credit <b style={{ color: th.accent }}>{fmtMoney(data.credit)}</b></span>
        </div>
      </div>
    </div>
  );
}

// Per-bonus-type colour themes for the KPI hero.
const BTHEMES: any = {
  gold:   { wrap: 'linear-gradient(120deg,#1c1608 0%,#14110a 45%,#12161F 100%)', border: 'rgba(232,184,75,0.45)', shine: '0 0 0 1px rgba(232,184,75,0.18), 0 10px 40px rgba(232,184,75,0.14)', glow: 'radial-gradient(circle, rgba(232,184,75,0.22), transparent 70%)', accent: '#F8500A', big: 'linear-gradient(92deg,#FFF1C2,#FF7A1A 40%,#F8500A 70%,#C77B45)', btn: 'linear-gradient(90deg,#F8500A,#FF7A1A)', btnText: '#0B0E14' },
  green:  { wrap: 'linear-gradient(120deg,#07261b 0%,#0b1a14 45%,#12161F 100%)', border: 'rgba(58,210,159,0.5)',  shine: '0 0 0 1px rgba(58,210,159,0.20), 0 10px 40px rgba(58,210,159,0.18)', glow: 'radial-gradient(circle, rgba(58,210,159,0.26), transparent 70%)', accent: '#3ad29f', big: 'linear-gradient(92deg,#d8fff1,#5fe9c0 45%,#2bb88a)', btn: 'linear-gradient(90deg,#3ad29f,#2bb88a)', btnText: '#06231a' },
  blue:   { wrap: 'linear-gradient(120deg,#0a1830 0%,#0b1422 45%,#12161F 100%)', border: 'rgba(58,134,255,0.5)',  shine: '0 0 0 1px rgba(58,134,255,0.20), 0 10px 40px rgba(58,134,255,0.18)', glow: 'radial-gradient(circle, rgba(58,134,255,0.26), transparent 70%)', accent: '#5a9bff', big: 'linear-gradient(92deg,#dbe8ff,#6fa8ff 45%,#3a86ff)', btn: 'linear-gradient(90deg,#3a86ff,#5a9bff)', btnText: '#fff' },
  purple: { wrap: 'linear-gradient(120deg,#190e2c 0%,#130e20 45%,#12161F 100%)', border: 'rgba(168,108,255,0.5)', shine: '0 0 0 1px rgba(168,108,255,0.20), 0 10px 40px rgba(168,108,255,0.18)', glow: 'radial-gradient(circle, rgba(168,108,255,0.26), transparent 70%)', accent: '#b285ff', big: 'linear-gradient(92deg,#eaddff,#b285ff 45%,#8b5cf6)', btn: 'linear-gradient(90deg,#8b5cf6,#a86cff)', btnText: '#fff' },
  pink:   { wrap: 'linear-gradient(120deg,#290c1c 0%,#1f0a16 45%,#12161F 100%)', border: 'rgba(240,85,138,0.5)',  shine: '0 0 0 1px rgba(240,85,138,0.20), 0 10px 40px rgba(240,85,138,0.18)', glow: 'radial-gradient(circle, rgba(240,85,138,0.26), transparent 70%)', accent: '#ff6aa0', big: 'linear-gradient(92deg,#ffdbe8,#ff8fb8 45%,#f0558a)', btn: 'linear-gradient(90deg,#f0558a,#ff6aa0)', btnText: '#fff' },
  cake:   { wrap: 'linear-gradient(120deg,#2a0f24 0%,#1a1030 45%,#12161F 100%)', border: 'rgba(255,138,200,0.55)', shine: '0 0 0 1px rgba(255,138,200,0.22), 0 10px 40px rgba(255,138,200,0.20)', glow: 'radial-gradient(circle, rgba(255,138,200,0.30), transparent 70%)', accent: '#ff8ac8', big: 'linear-gradient(92deg,#fff0fa,#ffb3e0 40%,#c77bff 80%)', btn: 'linear-gradient(90deg,#f0558a,#c77bff)', btnText: '#fff' },
};

// ════════════════════════ FULL BONUS PAGE ════════════════════════
export default function BonusPage({ onDeposit, onUploadKyc }: { onDeposit?: () => void; onUploadKyc?: () => void }) {
  const { data, reload } = useBonusStatus(true);
  const [claiming, setClaiming] = useState(false);
  const [flash, setFlash] = useState('');

  if (!data) return <div style={S.page}><div style={S.empty}>Loading bonuses…</div></div>;

  const claim = async () => {
    setClaiming(true);
    try { const r: any = await apiPost('/portal/bonus/welcome/claim', {}); setFlash(r?.message || 'Bonus credited!'); reload(); }
    catch (e: any) { setFlash(e?.message || 'Could not claim.'); }
    finally { setClaiming(false); setTimeout(() => setFlash(''), 5000); }
  };
  const claimBirthday = async () => {
    setClaiming(true);
    try { const r: any = await apiPost('/portal/bonus/birthday/claim', {}); setFlash(r?.message || '🎂 Birthday bonus credited!'); reload(); }
    catch (e: any) { setFlash(e?.message || 'Could not claim.'); }
    finally { setClaiming(false); setTimeout(() => setFlash(''), 5000); }
  };

  if (!data.enabled) return <div style={S.page}><h1 style={S.h1}>Bonuses</h1><div style={S.empty}>The bonus program is currently unavailable.</div></div>;
  if (data.blocked) return <div style={S.page}><h1 style={S.h1}>Bonuses</h1><div style={S.empty}>🎁 Bonuses are not available in {data.country}.</div></div>;

  const w = data.welcome, dep = data.deposit, offers = data.offers || [], bday = data.birthday;
  const tier1Left = dep.tier1_bonus_remaining, capLeft = dep.cap_remaining;

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Bonuses</h1>
      <div style={{ fontSize: 13, color: TH.muted, marginBottom: 18 }}>Current bonus credit on your account: <b style={{ color: TH.gold }}>{fmtMoney(data.credit)}</b></div>
      {flash && <div style={S.flash}>{flash}</div>}

      {/* BIRTHDAY — only around the client's birthday */}
      {bday && bday.enabled && bday.in_window && (
        <div style={{ ...S.card, border: '1px solid rgba(255,138,200,0.5)', boxShadow: '0 0 26px rgba(255,138,200,0.12)' }}>
          <div style={S.cardTop}>
            <div>
              <div style={S.cardEyebrow}>🎂 Birthday bonus</div>
              <div style={{ fontSize: 34, fontWeight: 900, color: '#fff', textDecoration: bday.state === 'claimed' ? 'line-through' : 'none' }}>{fmtMoney(bday.amount)}</div>
              <div style={{ fontSize: 12.5, color: TH.muted, marginTop: 4 }}>
                {bday.state === 'claimed' ? 'Happy Birthday! Your gift has been credited. 🎉'
                  : bday.state === 'eligible' ? 'Happy Birthday from TNFX! Claim your $100 gift — it lands on your trading account.'
                  : "Your birthday gift is locked — you don't have a deposit in the last 365 days. Deposit to unlock your $100."}
              </div>
            </div>
            {bday.state === 'eligible'
              ? <button style={{ padding: '9px 16px', borderRadius: 11, border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a' }} disabled={claiming} onClick={claimBirthday}>{claiming ? 'Claiming…' : 'Claim your $100 🎂'}</button>
              : bday.state === 'need_deposit'
              ? <button style={S.depBtn} onClick={onDeposit}>Deposit to unlock</button>
              : <span style={{ fontSize: 13, fontWeight: 800, color: TH.accent }}>✓ Claimed 🎂</span>}
          </div>
        </div>
      )}

      {/* WELCOME */}
      <div style={{ ...S.card, ...(w.state === 'eligible' ? S.cardShine : {}) }}>
        <div style={S.cardTop}>
          <div>
            <div style={S.cardEyebrow}>Welcome bonus</div>
            <div style={{ fontSize: 34, fontWeight: 900, color: '#fff', textDecoration: ['claimed', 'not_eligible', 'blocked'].includes(w.state) ? 'line-through' : 'none' }}>{fmtMoney(w.amount)}</div>
            <div style={{ fontSize: 12.5, color: TH.muted, marginTop: 4 }}>{w.reason}</div>
            {w.note && <div style={{ fontSize: 11, color: TH.muted, marginTop: 3, opacity: 0.8 }}>{w.note}</div>}
          </div>
          <WelcomeButton w={w} onClaim={claim} onUploadKyc={onUploadKyc} claiming={claiming} />
        </div>
        <div style={S.steps}>
          <Step n={1} label="Verify your KYC" done={w.kyc === 'verified'} active={['kyc_upload', 'kyc_review'].includes(w.state)} />
          <Step n={2} label="Log into MT" done={['eligible', 'review', 'blocked', 'not_eligible', 'claimed'].includes(w.state)} active={w.state === 'awaiting_login'} />
          <Step n={3} label="Device & family check" done={['eligible', 'claimed'].includes(w.state)} active={w.state === 'review'} fail={['blocked', 'not_eligible'].includes(w.state)} />
          <Step n={4} label="Claim" done={w.state === 'claimed'} active={w.state === 'eligible'} />
        </div>
      </div>

      {/* DEPOSIT BONUS */}
      <div style={S.card}>
        <div style={S.cardEyebrow}>Deposit bonus</div>
        <div style={{ fontSize: 13, color: TH.muted, marginBottom: 14 }}>
          {dep.tier1_pct}% on the first {fmtMoney(dep.tier1_cap)} of deposits, then {dep.tier2_pct}% above — up to {fmtMoney(dep.total_cap)} total bonus.
        </div>
        <ProgressLine label={`${dep.tier1_pct}% deposit bonus`} sub={tier1Left > 0 ? `remaining ${fmtMoney(tier1Left)}` : 'fully earned'} done={tier1Left <= 0} pct={tier1Left <= 0 ? 100 : Math.min(99, (dep.given / (dep.given + tier1Left || 1)) * 100)} />
        <ProgressLine label={`${dep.tier2_pct}% deposit bonus`} sub={capLeft > 0 ? `remaining ${fmtMoney(capLeft)} of ${fmtMoney(dep.total_cap)} cap` : 'cap reached'} done={capLeft <= 0} pct={capLeft <= 0 ? 100 : Math.min(99, (dep.given / dep.total_cap) * 100)} />
        <button style={{ ...S.depBtn, marginTop: 12 }} onClick={onDeposit}>Deposit & get your bonus</button>
      </div>

      {/* SPECIAL OFFERS */}
      {offers.length > 0 && (
        <div style={S.card}>
          <div style={S.cardEyebrow}>✨ Special offers</div>
          {offers.map((o: any) => (
            <div key={o.id} style={{ ...S.offerRow, opacity: o.claimed ? 0.55 : 1 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 800, color: o.claimed ? '#5a6470' : TH.gold, textDecoration: o.claimed ? 'line-through' : 'none' }}>
                  {o.name} — {o.percent}% up to {fmtMoney(o.cap)}
                </div>
                <div style={{ fontSize: 11.5, color: TH.muted, marginTop: 2 }}>
                  {o.min_deposit ? `Min deposit ${fmtMoney(o.min_deposit)} · ` : ''}{o.claimed ? 'already used' : timeLeft(o.ends_at)}
                </div>
              </div>
              {!o.claimed && <button style={S.depBtn} onClick={onDeposit}>Deposit now</button>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Step({ n, label, done, active, fail }: any) {
  const c = fail ? TH.neg : done ? TH.accent : active ? TH.gold : TH.muted;
  return (
    <div style={{ flex: 1, textAlign: 'center' }}>
      <div style={{ width: 30, height: 30, borderRadius: 99, margin: '0 auto', display: 'grid', placeItems: 'center', background: (done || active) ? c : TH.panel2, color: (done || active) ? '#0B0E14' : TH.muted, fontWeight: 800, fontSize: 13, border: `1px solid ${c}` }}>
        {fail ? '✕' : done ? '✓' : n}
      </div>
      <div style={{ fontSize: 10.5, color: c, marginTop: 6, fontWeight: 600 }}>{label}</div>
    </div>
  );
}

function ProgressLine({ label, sub, done, pct }: any) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: done ? '#5a6470' : TH.text, textDecoration: done ? 'line-through' : 'none' }}>{done ? '✓ ' : ''}{label}</span>
        <span style={{ fontSize: 11.5, color: TH.muted }}>{sub}</span>
      </div>
      <div style={{ height: 7, borderRadius: 6, background: TH.panel2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: done ? TH.accent : 'linear-gradient(90deg,#F8500A,#FF7A1A)', borderRadius: 6 }} />
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 820, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: '0 0 4px', color: '#fff' },
  empty: { padding: 40, textAlign: 'center', color: TH.muted, fontSize: 14, background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: 14 },
  flash: { background: 'rgba(58,210,159,0.10)', border: '1px solid rgba(58,210,159,0.3)', color: TH.accent, borderRadius: 10, padding: '10px 14px', fontSize: 13, marginBottom: 14, fontWeight: 600 },
  // fixed KPI hero (single offer)
  heroWrap: { position: 'relative', overflow: 'hidden', background: 'linear-gradient(120deg,#1c1608 0%,#14110a 45%,#12161F 100%)', border: '1px solid rgba(232,184,75,0.45)', borderRadius: 18, padding: '20px 24px', marginBottom: 18 },
  heroShine: { boxShadow: '0 0 0 1px rgba(232,184,75,0.18), 0 10px 40px rgba(232,184,75,0.14)' },
  heroGlow: { position: 'absolute', top: -60, right: -40, width: 220, height: 220, borderRadius: '50%', background: 'radial-gradient(circle, rgba(232,184,75,0.22), transparent 70%)', pointerEvents: 'none' },
  heroInner: { position: 'relative', display: 'flex', alignItems: 'center', gap: 18, zIndex: 1 },
  heroSpacer: { flex: '0 0 20%' },                       // pushes the headline toward ~1/3 across
  heroContent: { flex: 1, minWidth: 0, textAlign: 'center' },
  heroRight: { flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 },
  heroEyebrow: { fontSize: 12, letterSpacing: '0.16em', textTransform: 'uppercase', color: TH.gold, fontWeight: 800 },
  heroHeadline: { marginTop: 4, lineHeight: 1, display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 10, flexWrap: 'wrap' },
  heroBig: { fontSize: 58, fontWeight: 900, letterSpacing: '-0.02em', backgroundImage: 'linear-gradient(92deg,#FFF1C2,#FF7A1A 40%,#F8500A 70%,#C77B45)', WebkitBackgroundClip: 'text', backgroundClip: 'text', WebkitTextFillColor: 'transparent', color: 'transparent', filter: 'drop-shadow(0 3px 16px rgba(232,184,75,0.4))' },
  heroSmall: { fontSize: 18, fontWeight: 700, color: TH.muted, letterSpacing: 0 },
  heroSub: { fontSize: 12.5, color: '#cdd4de', marginTop: 10, maxWidth: 480, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.5 },
  heroBtn: { padding: '13px 30px', borderRadius: 11, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 15, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 6px 20px rgba(232,184,75,0.35)', whiteSpace: 'nowrap' },
  heroCredit: { fontSize: 10.5, color: TH.muted },
  depBtn: { padding: '10px 20px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 13, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' },
  // full page cards
  card: { background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: 16, padding: 22, marginBottom: 16 },
  cardShine: { border: '1px solid rgba(232,184,75,0.5)', boxShadow: '0 0 26px rgba(232,184,75,0.12)' },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' },
  cardEyebrow: { fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: TH.muted, fontWeight: 800, marginBottom: 8 },
  steps: { display: 'flex', gap: 8, marginTop: 20, borderTop: `1px solid ${TH.border}`, paddingTop: 18 },
  offerRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '12px 0', borderTop: `1px solid ${TH.border}` },
};
