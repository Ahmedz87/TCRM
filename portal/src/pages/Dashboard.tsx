import React, { useState, useEffect } from 'react';
import { apiGet } from '../api';
import { BonusBar } from '../Bonus';
import OpportunityCard from '../OpportunityCard';

const fmtMoney = (n: number) => '$' + (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtNum = (n: number) => (n || 0).toLocaleString();
const TIER_C: any = { bronze: '#C77B45', silver: '#AEB7C2', gold: '#F8500A', platinum: '#6FE3D4' };

export default function Dashboard({ go, onNewAccount, onDeposit, onUploadKyc }: { go?: (k: string) => void; onNewAccount?: () => void; onDeposit?: () => void; onUploadKyc?: () => void }) {
  const [d, setD] = useState<any>(null);
  const [manager, setManager] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [ops, setOps] = useState<any[]>([]);

  useEffect(() => {
    apiGet('/portal/dashboard').then(setD).catch(() => {}).finally(() => setLoading(false));
    apiGet('/portal/manager').then((m: any) => setManager(m?.manager || null)).catch(() => {});
    apiGet('/autochartist/opportunities?limit=6').then((r: any) => setOps(r?.opportunities || [])).catch(() => {});
  }, []);

  if (loading) return <div style={S.page}><div style={S.empty}>Loading your dashboard…</div></div>;
  if (!d) return <div style={S.page}><div style={S.empty}>Could not load dashboard.</div></div>;

  const k = d.kpis, p = d.profile, sales = d.sales;
  const initials = (p.name || '?').split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase();
  const tierC = TIER_C[k.loyalty_tier] || '#C77B45';

  const kpis = [
    { label: 'Total balance', value: fmtMoney(k.balance), sub: `${k.accounts} account${k.accounts === 1 ? '' : 's'}`, color: '#fff' },
    { label: 'Equity', value: fmtMoney(k.equity), sub: 'live', color: '#fff' },
    { label: 'P/L (30d)', value: (k.open_pl >= 0 ? '+' : '') + fmtMoney(k.open_pl).replace('$', '$'), sub: 'realized', color: k.open_pl >= 0 ? '#34D399' : '#F2667A' },
    { label: 'Total deposits', value: fmtMoney(k.deposits), sub: 'all time', color: '#fff' },
    { label: 'Loyalty points', value: fmtNum(k.loyalty_points), sub: `${k.loyalty_tier} · ${k.loyalty_streak}d streak`, color: tierC },
    { label: 'Trades (30d)', value: fmtNum(k.trades_30), sub: `${k.win_rate}% win rate`, color: '#6FE3D4' },
  ];

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Welcome back, {p.name.split(' ')[0]} 👋</h1>

      {/* fixed bonus KPI row */}
      <BonusBar onDeposit={() => onDeposit ? onDeposit() : (go && go('deposit'))} onUploadKyc={() => onUploadKyc ? onUploadKyc() : (go && go('bonus'))} />

      <div style={S.grid}>
        {/* KPI row 1 (3) */}
        {kpis.slice(0, 3).map((kp, i) => <Kpi key={i} {...kp} />)}

        {/* sales manager card — spans 2 rows, top-right */}
        <div style={S.profileCard}>
          <div style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#7b8794', fontWeight: 700, alignSelf: 'flex-start' }}>Your account manager</div>
          {manager ? (
            <>
              {manager.avatar_url
                ? <img src={manager.avatar_url} alt={manager.name} style={{ width: 64, height: 64, borderRadius: '50%', objectFit: 'cover', marginTop: 14 }} onError={(e: any) => { e.target.style.display = 'none'; }} />
                : <div style={{ ...S.avatar, marginTop: 14 }}>{(manager.name || '?').split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()}</div>}
              <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', marginTop: 12, textAlign: 'center' }}>{manager.name}</div>
              <div style={{ fontSize: 11.5, color: '#7b8794', marginTop: 2 }}>{manager.role}</div>
              <div style={S.profileRows}>
                {manager.phone && <div style={S.pRow}><span style={S.pIcon}>📞</span><span style={S.pText}>{manager.phone}</span></div>}
                {manager.email && <div style={S.pRow}><span style={S.pIcon}>✉️</span><span style={S.pText}>{manager.email}</span></div>}
              </div>
              <div style={{ display: 'flex', gap: 8, width: '100%', marginTop: 'auto' }}>
                {manager.whatsapp && <a href={manager.whatsapp} target="_blank" rel="noreferrer" style={{ flex: 1, textAlign: 'center', padding: '9px', borderRadius: 9, background: '#25D366', color: '#fff', fontSize: 12, fontWeight: 700, textDecoration: 'none' }}>WhatsApp</a>}
                {manager.phone && <a href={`tel:${manager.phone}`} style={{ flex: 1, textAlign: 'center', padding: '9px', borderRadius: 9, background: 'transparent', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>Call</a>}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#7b8794', fontSize: 12.5, textAlign: 'center' }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>👤</div>
              An account manager will be assigned to you shortly.
            </div>
          )}
        </div>

        {/* KPI row 2 (3) */}
        {kpis.slice(3, 6).map((kp, i) => <Kpi key={i + 3} {...kp} />)}
      </div>

      {/* big Sales tile — spans 2 columns */}
      <div style={S.salesTile}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={S.eyebrow}>Your sales · referrals</div>
            <div style={{ fontSize: 40, fontWeight: 900, color: '#fff', marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>
              {sales.won}<span style={{ fontSize: 18, color: '#8A93A3', fontWeight: 600 }}> won</span>
            </div>
          </div>
          <div style={{ fontSize: 34 }}>🤝</div>
        </div>
        <div style={S.salesStats}>
          <div><div style={S.sNum}>{sales.invites}</div><div style={S.sLbl}>invited</div></div>
          <div><div style={S.sNum}>{sales.pending}</div><div style={S.sLbl}>pending</div></div>
          <div><div style={{ ...S.sNum, color: '#34D399' }}>{fmtNum(sales.points_earned)}</div><div style={S.sLbl}>pts earned</div></div>
        </div>
        <button onClick={() => go && go('loyalty')} style={S.salesBtn}>Invite friends · earn 100 pts each</button>
      </div>

      {/* Live Autochartist opportunities (native cards) */}
      {ops.length > 0 && (
        <div style={S.acCard}>
          <div style={S.acHead}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 15, fontWeight: 800, color: '#fff' }}>📈 Live Opportunities</span>
              <span style={S.acPill}>Autochartist · FREE</span>
            </div>
            <button onClick={() => go && go('autochartist')} style={S.acBtn}>See all →</button>
          </div>
          <div style={S.acGrid}>
            {ops.slice(0, 3).map((o, i) => (
              <OpportunityCard key={i} o={o} compact onTrade={() => go && go('charts')} />
            ))}
          </div>
        </div>
      )}

      <div style={S.quickRow}>
        <QuickAction icon="💳" label="Deposit" onClick={() => onDeposit ? onDeposit() : (go && go('deposit'))} />
        <QuickAction icon="💸" label="Withdraw" onClick={() => go && go('withdraw')} />
        <QuickAction icon="🔁" label="Transfer" onClick={() => go && go('transfer')} />
        <QuickAction icon="➕" label="New account" onClick={() => onNewAccount ? onNewAccount() : (go && go('accounts'))} />
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, color }: any) {
  return (
    <div style={S.kpi}>
      <div style={S.eyebrow}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || '#fff', marginTop: 6, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      <div style={{ fontSize: 11, color: '#8A93A3', marginTop: 2 }}>{sub}</div>
    </div>
  );
}

function QuickAction({ icon, label, onClick }: any) {
  return (
    <button onClick={onClick} style={S.quick}>
      <span style={{ fontSize: 20 }}>{icon}</span>
      <span style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</span>
    </button>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 980, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: '0 0 22px', color: '#fff' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridAutoRows: 'minmax(108px, auto)', gap: 12, marginBottom: 14 },
  kpi: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18 },
  eyebrow: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700 },
  profileCard: { gridColumn: '4', gridRow: '1 / span 2', background: 'linear-gradient(160deg,#141821,#0d1016)', border: '1px solid #232a38', borderRadius: 16, padding: 20, display: 'flex', flexDirection: 'column', alignItems: 'center' },
  avatar: { width: 64, height: 64, borderRadius: 99, background: 'linear-gradient(135deg,#F8500A,#C77B45)', color: '#0B0E14', display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 24 },
  tierPill: { fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', padding: '4px 12px', borderRadius: 99, border: '1px solid', marginTop: 10 },
  profileRows: { width: '100%', marginTop: 16, display: 'flex', flexDirection: 'column', gap: 9 },
  pRow: { display: 'flex', alignItems: 'center', gap: 9 },
  pIcon: { fontSize: 13, width: 18, textAlign: 'center', flex: '0 0 auto' },
  pText: { fontSize: 12, color: '#cdd4de', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  profileBtn: { marginTop: 'auto', width: '100%', padding: '9px', borderRadius: 9, background: 'transparent', border: '1px solid #2a3240', color: '#E7ECF3', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  salesTile: { background: 'linear-gradient(135deg,#14110a,#12161F)', border: '1px solid rgba(232,184,75,0.28)', borderRadius: 16, padding: 22, marginBottom: 14 },
  salesStats: { display: 'flex', gap: 30, marginTop: 16 },
  sNum: { fontSize: 22, fontWeight: 800, color: '#fff', fontVariantNumeric: 'tabular-nums' },
  sLbl: { fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2 },
  salesBtn: { marginTop: 18, padding: '10px 18px', borderRadius: 9, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer' },
  acCard: { background: '#0d1016', border: '1px solid #232a38', borderRadius: 16, padding: 14, marginBottom: 14 },
  acHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 10, flexWrap: 'wrap' },
  acPill: { fontSize: 10.5, fontWeight: 800, color: '#0B0E14', background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', padding: '4px 11px', borderRadius: 99 },
  acBtn: { padding: '8px 14px', borderRadius: 9, background: 'transparent', border: '1px solid #2f3a48', color: '#E7ECF3', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  acGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 },
  quickRow: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 },
  quick: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '18px', borderRadius: 14, background: '#12161F', border: '1px solid #232a38', color: '#E7ECF3', cursor: 'pointer' },
  empty: { padding: 40, textAlign: 'center', color: '#8A93A3', fontSize: 14, background: '#12161F', border: '1px solid #232a38', borderRadius: 14 },
};
