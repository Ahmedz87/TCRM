import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import HedgeTraders from './HedgeTraders';
import { CT } from './crmTable';

// ── theme / maps ────────────────────────────────────────────────────────────────
const SEV = {
  critical: { c: '#ff4d4d', bg: 'rgba(255,77,77,0.14)', dot: '🔴', label: 'CRITICAL' },
  high:     { c: '#ffaa00', bg: 'rgba(255,170,0,0.14)', dot: '🟠', label: 'HIGH' },
  medium:   { c: '#ffd400', bg: 'rgba(255,212,0,0.10)', dot: '🟡', label: 'MEDIUM' },
} as Record<string, any>;

const TYPES: Record<string, { icon: string; label: string; short: string; legs: string }> = {
  margin_partner: { icon: '🔥', label: 'Margin-Out Partner', short: 'Margin-Out', legs: '2 accounts' },
  hedge_ratio:    { icon: '🔁', label: 'Hedge Account',      short: 'Hedge',      legs: '1 account' },
  bonus_ring:     { icon: '🎁', label: 'Bonus Ring',         short: 'Ring',       legs: '2-3 accounts' },
  bonus_cashout:  { icon: '🎁', label: 'Bonus Cash-Out',     short: 'Cash-Out',   legs: '1 account (cross-broker)' },
  chip_dump:      { icon: '🔀', label: 'Chip Dumping',       short: 'Chip Dump',  legs: '2 accounts' },
  swap_carry:     { icon: '💱', label: 'Swap Carry',         short: 'Swap',       legs: '1 account (solo)' },
  toxic_arb:      { icon: '☢️', label: 'Toxic / Latency',    short: 'Toxic',      legs: '1 account' },
};
const typeMeta = (t: string) => TYPES[t] || { icon: '⚑', label: t, short: t, legs: '' };

const REASON_LABEL: Record<string, string> = {
  cid: 'Same device', mqid: 'Same device', device: 'Same device', ip: 'Same IP',
  phone: 'Same phone', family: 'Same name / family', agent: 'Same IB / agent', ib: 'Same IB',
  abuse: 'Abuse link',
};
const EDGE_COLOR: Record<string, string> = {
  abuse: '#ff4d4d', cid: '#ff5d6c', mqid: '#ff5d6c', device: '#ff5d6c',
  phone: '#ffaa00', family: '#cc88ff', agent: '#00aaff', ib: '#00aaff', ip: '#5b7a9a',
};

// Plain-language explainers so a non-technical back-office reviewer gets it instantly.
const EXPLAIN: Record<string, { what: string; why: string; action: string }> = {
  margin_partner: {
    what: 'One account deliberately blew up (margin-out) while a connected account won almost the same amount at the same moment, same symbol, opposite side — money moved from the loser to the winner.',
    why: 'The losing side is usually bonus / credit (our money), so we end up funding a withdrawal that lands in the partner account.',
    action: 'Freeze both accounts and hold any pending withdrawal until reviewed.' },
  bonus_ring: {
    what: 'A group of linked accounts opened opposite trades against each other while holding bonus — as a group they took no real market risk, they just "turned over" the bonus.',
    why: 'The bonus is our money; turned over this way it becomes withdrawable with no genuine trading.',
    action: 'Freeze the group, claw back the bonus, block withdrawals.' },
  bonus_cashout: {
    what: 'Account took a bonus, barely traded, and withdrew more than it ever deposited.',
    why: 'The extra money came from the bonus — a direct cost to us.',
    action: 'Hold the withdrawal and verify the trading was genuine before paying.' },
  chip_dump: {
    what: 'Two linked accounts repeatedly traded opposite each other so one steadily fed money to the other.',
    why: 'Usually moves bonus / credit into a clean account that then withdraws it.',
    action: 'Freeze both accounts and review the withdrawal trail.' },
  swap_carry: {
    what: 'A swap-free (Islamic) account held positions overnight again and again to collect carry it should normally pay for.',
    why: 'We absorb the swap cost while the client keeps the profit.',
    action: 'Review swap-free eligibility; consider removing swap-free status.' },
  toxic_arb: {
    what: 'Account wins almost every trade with ultra-short holds — the signature of trading on a faster price feed than ours (latency arbitrage).',
    why: 'These wins come straight from the broker; it is not normal trading.',
    action: 'Review execution model; consider instant execution or flag as toxic flow.' },
  hedge_ratio: {
    what: 'A large share of this account\'s trades are hedged — it opens opposite buy + sell positions on the same symbol at the same size, locking the position instead of genuinely trading.',
    why: 'A signature of bonus abuse and risk-free promo farming: locked positions carry no market risk but can unlock a bonus or exploit a promotion.',
    action: 'Review the strategy and bonus eligibility; hold withdrawals if the account is bonus-funded.' },
};

const money = (n: number) => '$' + Math.round(n || 0).toLocaleString('en-GB');
const fmtDT = (s: string) => {
  if (!s) return '—';
  const d = new Date(s.replace(' ', 'T'));
  if (isNaN(+d)) return s.slice(0, 16);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};
const fmtEpoch = (e: number) => e ? new Date(e * 1000).toLocaleString(undefined,
  { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const fmtFull = (e: number) => e ? new Date(e * 1000).toLocaleString(undefined,
  { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const fmtClock = (e: number) => e ? new Date(e * 1000).toLocaleTimeString(undefined,
  { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const fmtHold = (s: number) => {
  if (s == null) return '';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${Math.round(s / 86400)}d`;
};

// ── atoms ────────────────────────────────────────────────────────────────────────
function ScoreBar({ v, c }: { v: number; c: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 70 }}>
      <div style={{ flex: 1, height: 5, background: '#373f4d', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: 5, width: `${v}%`, background: c, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color: c, width: 20, textAlign: 'right' }}>{v}</span>
    </div>
  );
}
function HotBadge() {
  return <span style={{ fontSize: 9, fontWeight: 800, padding: '1px 6px', borderRadius: 4,
    background: 'rgba(255,77,77,0.18)', color: '#ff5d6c' }}>🔥 HOT</span>;
}
function LegPill({ login, dir, vol, profit, open, close, hold }: any) {
  const buy = dir === 'buy';
  const col = profit !== undefined ? (profit >= 0 ? '#00e5a0' : '#ff5d6c') : (buy ? '#00e5a0' : '#ff5d6c');
  return (
    <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: '6px 9px', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#00aaff' }}>#{login}</span>
        {dir !== 'hold' && (
          <span style={{ fontSize: 9, fontWeight: 800, padding: '1px 5px', borderRadius: 4,
            background: buy ? 'rgba(0,229,160,0.15)' : 'rgba(255,93,108,0.15)', color: buy ? '#00e5a0' : '#ff5d6c' }}>
            {buy ? 'BUY' : 'SELL'}</span>
        )}
        <span style={{ fontSize: 11, color: '#bbb' }}>{vol}L</span>
        {profit !== undefined && (
          <span style={{ fontSize: 11, fontWeight: 700, color: col, marginLeft: 'auto' }}>
            {profit >= 0 ? '+' : ''}{money(profit)}</span>
        )}
      </div>
      {(open || close) && (
        <div style={{ fontSize: 9.5, color: '#7a8294', marginTop: 3, fontFamily: 'monospace' }}>
          {open ? `open ${fmtClock(open)}` : ''}{open && close ? ' → ' : ''}{close ? `close ${fmtClock(close)}` : ''}
          {hold != null && <span style={{ color: '#ffaa00' }}> · held {fmtHold(hold)}</span>}
        </div>
      )}
    </div>
  );
}
// ticket #76 (gap between the two accounts' open / close times) + #99 (each
// position's open→close hold, in seconds). Values come from the engine's
// proof-pair evidence: open_gap_s / close_gap_s (cross-account) and a_hold / b_hold
// (per-leg). Rendered as a compact strip, e.g. "open gap 3s · close gap 5s · A held 142s · B held 138s".
function TimeDiffStrip({ p }: { p: any }) {
  const sec = (v: any) => (v == null ? null : `${v}s`);
  const items: { label: string; val: string }[] = [];
  if (p.open_gap_s != null) items.push({ label: 'open gap', val: sec(p.open_gap_s)! });
  if (p.close_gap_s != null) items.push({ label: 'close gap', val: sec(p.close_gap_s)! });
  if (p.a_hold != null) items.push({ label: `#${p.a_login} held`, val: sec(p.a_hold)! });
  if (p.b_hold != null) items.push({ label: `#${p.b_login} held`, val: sec(p.b_hold)! });
  if (!items.length) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 7, fontSize: 9.5, fontFamily: 'monospace' }}>
      {items.map((it, i) => (
        <span key={i} style={{ background: '#1c2129', border: '1px solid #373f4d', borderRadius: 5, padding: '1px 6px', color: '#9aa3b2' }}>
          {it.label} <b style={{ color: '#ffaa00' }}>{it.val}</b>
        </span>
      ))}
    </div>
  );
}

// ── network graph ──────────────────────────────────────────────────────────────────
function NetworkGraph({ net, caseLogins }: { net: any; caseLogins: number[] }) {
  const nodes = net?.nodes || [];
  const edges = net?.edges || [];
  if (nodes.length < 2) return <div style={{ fontSize: 12, color: '#667', padding: 10 }}>No shared connections found between these accounts.</div>;

  const W = 460, H = 320, cx = W / 2, cy = H / 2;
  const R = Math.min(130, 70 + nodes.length * 5);
  const pos: Record<number, { x: number; y: number }> = {};
  // case accounts toward the centre-ish, neighbours on the ring
  const caseSet = new Set(caseLogins);
  const ring = nodes;
  ring.forEach((n: any, i: number) => {
    const a = (2 * Math.PI * i) / ring.length - Math.PI / 2;
    pos[n.login] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });

  const reasonsPresent = Array.from(new Set(edges.map((e: any) => e.reason)));

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ background: '#20252f', border: '1px solid #373f4d', borderRadius: 10 }}>
        {edges.map((e: any, i: number) => {
          const p1 = pos[e.a], p2 = pos[e.b]; if (!p1 || !p2) return null;
          const col = EDGE_COLOR[e.reason] || '#445';
          return <line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={col}
            strokeWidth={e.reason === 'abuse' ? 2.5 : 1.3} strokeDasharray={e.reason === 'abuse' ? '5 3' : undefined} opacity={0.75} />;
        })}
        {nodes.map((n: any) => {
          const p = pos[n.login]; if (!p) return null;
          const isCase = caseSet.has(n.login);
          return (
            <g key={n.login}>
              <circle cx={p.x} cy={p.y} r={isCase ? 13 : 8}
                fill={isCase ? '#ff4d4d' : '#2c333e'} stroke={isCase ? '#ff8a8a' : '#3a4150'} strokeWidth={isCase ? 2 : 1.2} />
              <text x={p.x} y={p.y - (isCase ? 18 : 13)} textAnchor="middle" fontSize="9.5"
                fill={isCase ? '#ffd0d0' : '#8a93a3'} fontFamily="monospace">#{n.login}</text>
            </g>
          );
        })}
      </svg>
      {/* legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 8, fontSize: 10, color: '#8a93a3' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff4d4d', display: 'inline-block' }} /> account under review</span>
        {reasonsPresent.map((r: any) => (
          <span key={r} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 14, height: 3, background: EDGE_COLOR[r] || '#445', display: 'inline-block', borderRadius: 2 }} />
            {REASON_LABEL[r] || r}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── detail drawer ──────────────────────────────────────────────────────────────────
function CaseDrawer({ row, onClose, onAction }: any) {
  const [d, setD] = useState<any>(null);
  const [net, setNet] = useState<any>(null);   // network graph, loaded lazily
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setD(null); setNet(null);
    apiGet(`/abuse/cases/${row.id}`).then(setD).catch(() => {});
    apiGet(`/abuse/cases/${row.id}/network`).then(setNet).catch(() => {});
  }, [row.id]);

  const sev = SEV[row.severity] || SEV.medium;
  const tm = typeMeta(row.abuse_type);
  const ev = d?.evidence_obj || {};
  const mf = ev.money_flow || {};
  const pairs = ev.proof_pairs || [];
  const trades = ev.proof_trades || d?.proof_trades || [];
  const signals = ev.signals || [];
  const links = ev.links || d?.connections || [];

  const act = async (action: string) => {
    setBusy(true);
    try { await apiPost(`/abuse/cases/${row.id}/action`, { action }); onAction(); onClose(); }
    catch { alert('Action failed'); } finally { setBusy(false); }
  };
  const Section = ({ title, children }: any) => (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 10, color: '#667', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 200, display: 'flex' }}>
      <div style={{ flex: 1, background: 'rgba(0,0,0,0.55)' }} onClick={onClose} />
      <div style={{ width: 500, maxWidth: '92vw', background: '#262c36', borderLeft: '1px solid #4f596b',
        display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {/* header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #373f4d', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 22 }}>{tm.icon}</span>
            <span style={{ fontSize: 17, fontWeight: 800 }}>{tm.label}</span>
            <span style={{ fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 99, background: sev.bg, color: sev.c }}>
              {sev.dot} {sev.label}</span>
            {row.hot && <HotBadge />}
            <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#667', fontSize: 22, cursor: 'pointer' }}>✕</button>
          </div>
          <div style={{ fontSize: 11, color: '#667', marginBottom: 6 }}>Case #{row.id} · caught {fmtDT(row.created_at)}</div>
          <div style={{ fontSize: 14, color: '#dfe3ea', lineHeight: 1.5 }}>{ev.headline || d?.evidence || row.evidence}</div>
          <div style={{ display: 'flex', gap: 20, marginTop: 12 }}>
            {[['Risk', row.risk_score, sev.c], ['Confidence', (d?.confidence ?? row.confidence) + '%', '#00e5a0'],
              ['Broker loss', money(ev.broker_loss ?? ev.at_risk ?? row.exposure), '#ff4d4d'],
              ['Accounts', (row.all_logins || []).length, '#00aaff']].map(([l, v, c]: any) => (
              <div key={l}><div style={{ fontSize: 9, color: '#556', textTransform: 'uppercase' }}>{l}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: c }}>{v}</div></div>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', minHeight: 0 }}>
          {!d && <div style={{ color: '#556', textAlign: 'center', padding: 20 }}>Loading…</div>}

          {EXPLAIN[row.abuse_type] && (
            <div style={{ background: '#101319', border: '1px solid #373f4d', borderRadius: 10, padding: '12px 14px', marginBottom: 18 }}>
              <div style={{ fontSize: 12.5, color: '#dfe3ea', lineHeight: 1.65 }}>
                <div style={{ marginBottom: 7 }}><b style={{ color: '#00e5a0' }}>What happened — </b>{EXPLAIN[row.abuse_type].what}</div>
                <div style={{ marginBottom: 7 }}><b style={{ color: '#ffaa00' }}>Why it costs us — </b>{EXPLAIN[row.abuse_type].why}</div>
                <div><b style={{ color: '#ff5d6c' }}>What to do — </b>{EXPLAIN[row.abuse_type].action}</div>
              </div>
            </div>
          )}

          {signals.length > 0 && (
            <Section title="Why it's flagged">
              {signals.map((s: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                  background: s.hit ? '#373f4d' : 'transparent', border: '1px solid ' + (s.hit ? '#262b35' : '#16181e'),
                  borderRadius: 8, marginBottom: 6, opacity: s.hit ? 1 : 0.45 }}>
                  <span style={{ fontSize: 16 }}>{s.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: s.hit ? '#e6e9ef' : '#889' }}>{s.hit ? '✓ ' : '○ '}{s.label}</div>
                    <div style={{ fontSize: 11, color: '#8a93a3' }}>{s.detail}</div>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 800, color: s.hit ? sev.c : '#445' }}>+{s.hit ? s.weight : 0}</span>
                </div>
              ))}
            </Section>
          )}

          {pairs.length > 0 && (
            <Section title={`The proof · ${pairs.length} matched ${row.abuse_type === 'chip_dump' || row.abuse_type === 'margin_partner' ? 'transfers' : 'pairs'}`}>
              <div style={{ fontSize: 10.5, color: '#7a8294', marginBottom: 8, lineHeight: 1.5 }}>
                {row.abuse_type === 'margin_partner'
                  ? <>Each row is one margin-out moment: the winner's profit vs the loser's blow-up loss in the same ±2 min window, on the same symbol, opposite side.</>
                  : <>These are the <b style={{ color: '#cfd6e0' }}>closing</b> trades (where the P&amp;L is realised). The gap is the time between the two accounts' <b style={{ color: '#cfd6e0' }}>closes</b>; each leg also shows its own open→close time and how long it was held.</>}
              </div>
              {pairs.slice(0, 25).map((p: any, i: number) => (
                <div key={i} style={{ border: '1px solid #373f4d', borderRadius: 10, padding: 8, marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, fontSize: 10, color: '#8a93a3' }}>
                    <span style={{ color: '#cfd6e0', fontWeight: 600 }}>📅 {fmtFull(p.t)}</span>
                    <span style={{ color: '#556' }}>·</span>
                    <span>{p.sym}</span>
                    <span style={{ marginLeft: 'auto', padding: '1px 7px', borderRadius: 99, background: '#373f4d', color: '#ffaa00', fontWeight: 700 }}>
                      {row.abuse_type === 'margin_partner' ? `margin-out window ${p.gap_s}s` : `closes ${p.gap_s}s apart`}
                    </span>
                  </div>
                  {/* ticket #76/#99: cross-account open/close gaps (s) + per-leg hold (s) */}
                  <TimeDiffStrip p={p} />
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 8, alignItems: 'center' }}>
                    <LegPill login={p.a_login} dir={p.a_dir} vol={p.a_vol} profit={p.a_profit} open={p.a_open} close={p.a_close} hold={p.a_hold} />
                    <div style={{ fontSize: 16, color: '#445' }}>⇄</div>
                    <LegPill login={p.b_login} dir={p.b_dir} vol={p.b_vol} profit={p.b_profit} open={p.b_open} close={p.b_close} hold={p.b_hold} />
                  </div>
                </div>
              ))}
            </Section>
          )}

          {pairs.length === 0 && trades.length > 0 && (
            <Section title={`Evidence trades (${trades.length})`}>
              <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, overflow: 'hidden' }}>
                {trades.slice(0, 20).map((t: any, i: number) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto auto', gap: 10, padding: '6px 10px', fontSize: 11, borderBottom: '1px solid #373f4d', alignItems: 'center' }}>
                    <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{t.login}</span>
                    <span style={{ color: '#ccc' }}>{t.symbol || t.sym}
                      {t.dir === 'hold' ? <span style={{ color: '#ffaa00' }}> · held {t.profit}h</span> :
                        (t.dir && <span style={{ color: '#667' }}> · {t.dir}</span>)}</span>
                    <span style={{ color: '#aaa' }}>{(t.volume ?? t.vol ?? 0)}L</span>
                    <span style={{ color: '#556', fontSize: 10 }}>{fmtEpoch(t.t)}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {mf.deposits !== undefined && (
            <Section title="Money flow">
              <div style={{ display: 'flex', alignItems: 'stretch', gap: 8 }}>
                {[['Deposited', mf.deposits, '#00aaff'], ['Bonus', mf.bonus, '#ffaa00'], ['Withdrawn', mf.withdrawals, '#ff4d4d']].map(([l, v, c]: any, i: number) => (
                  <React.Fragment key={l}>
                    <div style={{ flex: 1, background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: '10px 8px', textAlign: 'center' }}>
                      <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase' }}>{l}</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: c }}>{money(v)}</div></div>
                    {i < 2 && <div style={{ alignSelf: 'center', color: '#445', fontSize: 16 }}>→</div>}
                  </React.Fragment>
                ))}
              </div>
            </Section>
          )}

          {ev.accounts?.length > 0 && (
            <Section title={`Accounts in this case (${ev.accounts.length})`}>
              {ev.accounts.map((a: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, marginBottom: 5, fontSize: 12 }}>
                  <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{a.login}</span>
                  <span style={{ flex: 1, color: '#ccc' }}>{a.name || '—'}</span>
                  {a.credit > 0 && <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,170,0,0.15)', color: '#ffaa00' }}>bonus {money(a.credit)}</span>}
                  <span style={{ color: '#667' }}>{a.country || ''}</span>
                  <span style={{ color: '#00e5a0', fontWeight: 700 }}>{money(a.balance)}</span>
                </div>
              ))}
            </Section>
          )}

          {d?.relations && (() => {
            const rel = d.relations;
            const scoreCol = (s: number) => s >= 8 ? '#ff4d4d' : s >= 5 ? '#ff8c00' : s >= 3 ? '#ffd166' : s >= 1 ? '#8a93a3' : '#556';
            return (
            <Section title="Are these accounts connected?">
              {/* the verdict — first, before the per-account detail */}
              <div style={{ padding: '10px 12px', borderRadius: 8, marginBottom: 12, fontSize: 13, fontWeight: 700,
                background: rel.connected ? 'rgba(255,77,77,0.1)' : 'rgba(0,229,160,0.08)',
                border: `1px solid ${rel.connected ? '#ff4d4d55' : '#00e5a055'}`, color: rel.connected ? '#ff6b6b' : '#00e5a0' }}>
                {rel.connected
                  ? '⚠ These accounts ARE connected — operated by the same or linked parties'
                  : '○ These accounts are NOT directly connected to each other (each may still have its own network below)'}
              </div>
              {rel.same_person?.length > 0 && rel.same_person.map((g: number[], i: number) => (
                <div key={'sp' + i} style={{ fontSize: 12, color: '#ffd166', marginBottom: 6 }}>
                  👤 Same person: {g.map(l => '#' + l).join(', ')}
                </div>
              ))}
              {rel.inter?.map((e: any, i: number) => (
                <div key={'in' + i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: '#2c333e', borderRadius: 8, marginBottom: 5, fontSize: 11, border: '1px solid #4f596b', flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{e.login_a}</span>
                  <span style={{ color: '#556' }}>↔</span>
                  <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{e.login_b}</span>
                  {(e.reasons || []).map((r: any, j: number) => (
                    <span key={j} style={{ fontSize: 9, padding: '2px 8px', borderRadius: 4, fontWeight: 700, background: '#0a1a3a', color: '#7fb0ff' }}>{r.label}</span>
                  ))}
                </div>
              ))}
              {/* then each account's OWN wider network */}
              <div style={{ fontSize: 10, color: '#667', textTransform: 'uppercase', letterSpacing: 1, margin: '14px 0 8px' }}>Each account's connections</div>
              {rel.accounts?.map((a: any, i: number) => (
                <div key={'ac' + i} style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 8, padding: 10, marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: a.connections?.length ? 8 : 0 }}>
                    <span style={{ minWidth: 30, textAlign: 'center', fontWeight: 800, fontFamily: 'monospace', color: scoreCol(a.network_score) }}>{a.network_score}/10</span>
                    <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{a.login}</span>
                    <span style={{ fontSize: 12, color: '#e0e0e0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 10, color: '#8a93a3' }}>{a.n_connections} linked{a.top_reason ? ' · ' + a.top_reason : ''}</span>
                  </div>
                  {a.connections?.slice(0, 6).map((cn: any, j: number) => (
                    <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 6px', fontSize: 11, borderTop: '1px solid #2c333e' }}>
                      <span style={{ color: cn.in_this_case ? '#ff6b6b' : '#c4ccd8' }}>{cn.in_this_case ? '★ ' : ''}{(cn.name || '—').slice(0, 22)}</span>
                      <span style={{ marginLeft: 'auto', display: 'flex', gap: 3, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        {(cn.reasons || []).slice(0, 2).map((r: any, k: number) => (
                          <span key={k} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: '#0a1a3a', color: '#7fb0ff' }}>{r.label}</span>
                        ))}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </Section>
            );
          })()}

          {(net == null || net?.nodes?.length > 1 || links.length > 0) && (
            <Section title="Network graph">
              {net == null
                ? <div style={{ fontSize: 12, color: '#667', padding: 10 }}>Loading connections…</div>
                : <NetworkGraph net={net} caseLogins={row.all_logins || [row.login_a]} />}
              {(net?.edges || []).filter((e: any) => e.reason !== 'abuse').length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 10, color: '#667', marginBottom: 6 }}>Shared links (how we know they're connected):</div>
                  {(net.edges).filter((e: any) => e.reason !== 'abuse').slice(0, 10).map((e: any, i: number) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: '#2c333e', borderRadius: 8, marginBottom: 5, fontSize: 11, border: '1px solid #4f596b' }}>
                      <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{e.a}</span>
                      <span style={{ color: '#556' }}>↔</span>
                      <span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{e.b}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 9, padding: '2px 8px', borderRadius: 4, fontWeight: 700, background: (EDGE_COLOR[e.reason] || '#445') + '22', color: EDGE_COLOR[e.reason] || '#99a' }}>
                        {REASON_LABEL[e.reason] || e.reason}</span>
                      {e.value && <span style={{ fontSize: 10, color: '#778', fontFamily: 'monospace', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.value}</span>}
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}

          {d?.recommendation && (
            <div style={{ background: 'rgba(255,170,0,0.08)', border: '1px solid rgba(255,170,0,0.3)', borderRadius: 8, padding: '10px 12px', fontSize: 13, color: '#ffaa00', fontWeight: 600 }}>💡 {d.recommendation}</div>
          )}
        </div>

        <div style={{ padding: '12px 20px', borderTop: '1px solid #373f4d', display: 'flex', gap: 8, flexShrink: 0 }}>
          <button disabled={busy} onClick={() => act('freeze')} style={{ flex: 1, padding: 11, background: '#ff4d4d', border: 'none', borderRadius: 8, color: '#000', fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit' }}>🔒 Freeze</button>
          <button disabled={busy} onClick={() => act('hold_wd')} style={{ flex: 1, padding: 11, background: '#ffaa00', border: 'none', borderRadius: 8, color: '#000', fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit' }}>⏸ Hold W/D</button>
          <button disabled={busy} onClick={() => act('clear')} style={{ flex: 1, padding: 11, background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#9aa', cursor: 'pointer', fontFamily: 'inherit' }}>✓ Not abuse</button>
        </div>
      </div>
    </div>
  );
}

// ── table row (one finding) ──────────────────────────────────────────────────────
function CaseRow({ c, onClick }: any) {
  const sev = SEV[c.severity] || SEV.medium;
  const tm = typeMeta(c.abuse_type);
  const al = c.all_logins || [c.login_a];
  return (
    <tr onClick={onClick} style={{ ...CT.row(), cursor: 'pointer', borderLeft: `3px solid ${sev.c}` }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
      <td style={{ ...CT.td, color: '#667', fontFamily: 'monospace', borderLeft: `3px solid ${sev.c}` }}>#{c.id}</td>
      <td style={{ ...CT.td, color: '#8a93a3' }}>{fmtDT(c.created_at)}</td>
      <td style={CT.td}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 15 }}>{tm.icon}</span>
          <span style={{ fontWeight: 600, color: '#e6e9ef' }}>{tm.label}</span>
          {c.hot && <HotBadge />}
        </span>
      </td>
      <td style={CT.td}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          {al.slice(0, 2).map((l: any, i: number) => <span key={i} style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{l}</span>)}
          {al.length > 2 && <span style={{ color: '#667', fontSize: 11 }}>+{al.length - 2}</span>}
        </span>
      </td>
      <td style={{ ...CT.td, color: '#9aa3b2' }}>{c.symbol || '—'}</td>
      <td style={CT.td}>
        <span style={{ fontSize: 10.5, fontWeight: 800, padding: '2px 9px', borderRadius: 99, background: sev.bg, color: sev.c }}>{sev.dot} {String(c.severity).toUpperCase()}</span>
      </td>
      <td style={{ ...CT.td, textAlign: 'right', fontWeight: 700, color: c.exposure > 0 ? '#ff7a7a' : '#667' }}>{c.exposure > 0 ? money(c.exposure) : '—'}</td>
      <td style={{ ...CT.td, width: 90 }}><ScoreBar v={c.risk_score || 0} c={sev.c} /></td>
    </tr>
  );
}

// ── main ───────────────────────────────────────────────────────────────────────────
export default function AbuseDetection() {
  const [tab, setTab] = useState<'cases' | 'hedge'>('cases');
  const [counts, setCounts] = useState<any>({ types: [], total: 0, exposure: 0, hot: 0, critical: 0 });
  const [filter, setFilter] = useState('');       // '', 'hot', or an abuse_type
  const [sevFilter, setSevFilter] = useState('');
  const [search, setSearch] = useState('');
  const [cases, setCases] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [open, setOpen] = useState<any>(null);

  const loadCounts = useCallback(() => { apiGet('/abuse/type-counts').then(setCounts).catch(() => {}); }, []);
  const loadCases = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ page: '1', page_size: '200' });
      if (filter === 'hot') p.set('hot', '1');
      else if (filter) p.set('abuse_type', filter);
      if (sevFilter) p.set('severity', sevFilter);
      if (search) p.set('search', search);
      const d = await apiGet(`/abuse/cases?${p}`);
      setCases(d.cases || []); setTotal(d.total || 0);
    } catch { /* */ } finally { setLoading(false); }
  }, [filter, sevFilter, search]);

  useEffect(() => { loadCounts(); }, [loadCounts]);
  useEffect(() => { loadCases(); }, [loadCases]);

  const runDetection = async () => {
    setRunning(true);
    try { await apiPost('/abuse/run-detection', {});
      setTimeout(() => { loadCounts(); loadCases(); setRunning(false); }, 6000);
    } catch { setRunning(false); }
  };

  const COLS = ['#', 'Catching time', 'Type', 'Accounts', 'Symbol', 'Severity', 'Possible broker loss', 'Risk'];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, background: '#20252f' }}>
      {/* top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid #373f4d', flexShrink: 0 }}>
        <button onClick={() => setTab('cases')} style={tabBtn(tab === 'cases', '#00e5a0')}>🛡 Abuse Cases</button>
        <button onClick={() => setTab('hedge')} style={tabBtn(tab === 'hedge', '#00aaff')}>🔀 Hedge Traders</button>
        {tab === 'cases' && (<>
          <div style={{ marginLeft: 10, display: 'flex', gap: 18 }}>
            <Kpi label="Open cases" value={counts.total} c="#e6e9ef" />
            <Kpi label="🔥 Hot" value={counts.hot} c="#ff5d6c" />
            <Kpi label="Critical" value={counts.critical} c="#ff4d4d" />
            <Kpi label="Possible broker loss" value={money(counts.exposure)} c="#ffaa00" />
          </div>
          <button onClick={runDetection} disabled={running} style={{ marginLeft: 'auto', padding: '7px 16px', borderRadius: 8, border: '1px solid #2a7', background: running ? '#4f596b' : 'rgba(0,229,160,0.12)', color: running ? '#667' : '#00e5a0', cursor: running ? 'default' : 'pointer', fontWeight: 700, fontSize: 12, fontFamily: 'inherit' }}>
            {running ? '⏳ Scanning…' : '⚡ Run Detection'}</button>
        </>)}
      </div>

      {tab === 'hedge' ? (
        <div style={{ flex: 1, overflow: 'auto', minHeight: 0, padding: 16 }}><HedgeTraders /></div>
      ) : (<>
        {/* filter chips: ALL default + Hot + each type */}
        <div style={{ display: 'flex', gap: 6, padding: '8px 16px', borderBottom: '1px solid #373f4d', flexShrink: 0, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip active={!filter} onClick={() => setFilter('')} label={`All · ${counts.total}`} c="#00e5a0" />
          {counts.hot > 0 && <Chip active={filter === 'hot'} onClick={() => setFilter(filter === 'hot' ? '' : 'hot')} label={`🔥 Hot · ${counts.hot}`} c="#ff5d6c" />}
          {Object.keys(TYPES).map(t => {
            const ct = counts.types.find((x: any) => x.abuse_type === t);
            if (!ct) return null;
            return <Chip key={t} active={filter === t} onClick={() => setFilter(filter === t ? '' : t)}
              label={`${typeMeta(t).icon} ${typeMeta(t).short} · ${ct.total}`} c="#00aaff" badge={ct.critical} />;
          })}
          <span style={{ width: 1, height: 18, background: '#4f596b', margin: '0 4px' }} />
          {['critical', 'high', 'medium'].map(s => (
            <Chip key={s} active={sevFilter === s} onClick={() => setSevFilter(sevFilter === s ? '' : s)} label={`${SEV[s].dot} ${s}`} c={SEV[s].c} />
          ))}
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="login / symbol…"
            style={{ marginLeft: 'auto', padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12, width: 160, outline: 'none' }} />
        </div>

        {/* clean table — one row per case */}
        <div style={CT.scroll}>
          {loading ? <div style={{ padding: 40, textAlign: 'center', color: '#556' }}>Loading…</div>
            : cases.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: '#556' }}>No cases. Click “Run Detection”.</div>
            : <table style={CT.table}>
                <thead>
                  <tr style={CT.theadTr}>
                    {COLS.map((h, i) => (
                      <th key={h} style={CT.th(false, i === 6 ? 'right' : 'left')}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cases.map(c => <CaseRow key={c.id} c={c} onClick={() => setOpen(c)} />)}
                </tbody>
              </table>}
          {total > cases.length && <div style={{ padding: 14, textAlign: 'center', color: '#556', fontSize: 11 }}>Showing top {cases.length} of {total} — narrow with the tabs/filters above</div>}
        </div>
      </>)}

      {open && <CaseDrawer row={open} onClose={() => setOpen(null)} onAction={() => { loadCounts(); loadCases(); }} />}
    </div>
  );
}

function tabBtn(active: boolean, c: string): React.CSSProperties {
  return { padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', border: `1px solid ${active ? c : '#626d80'}`, background: active ? c + '1a' : 'transparent', color: active ? c : '#889', fontFamily: 'inherit' };
}
function Kpi({ label, value, c }: any) {
  return (<div><div style={{ fontSize: 9, color: '#556', textTransform: 'uppercase' }}>{label}</div>
    <div style={{ fontSize: 16, fontWeight: 800, color: c }}>{(value ?? 0).toLocaleString?.() ?? value}</div></div>);
}
function Chip({ active, onClick, label, c, badge }: any) {
  return (
    <button onClick={onClick} style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11, border: `1px solid ${active ? c : '#2a2f3a'}`, background: active ? c + '1a' : 'transparent', color: active ? c : '#889', cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
      {label}{badge ? <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 800, color: '#ff4d4d' }}>🔴{badge}</span> : null}
    </button>
  );
}
