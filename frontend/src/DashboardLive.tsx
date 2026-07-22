/**
 * DashboardLive.tsx — the live, role-aware front page.
 *
 * Backend: GET /dashboard/live?period=  (dashboard_router.py) — returns everything
 * in ONE payload, cached server-side, so we can poll cheaply.
 *
 * What each desk sees (the backend decides the role from users.role + team_type):
 *   RETENTION → live markup feed: every closing trade credits markup commission now.
 *   SALES     → live leads (last 10 + how long they've waited), won/lost on FTD
 *               (won = called BEFORE the deposit → $10; lost = deposited first),
 *               and the KYC queue.
 *   ADMIN     → both.
 *
 * Live = poll every REFRESH_MS with a pulse + "updated Xs ago". Tables use the
 * shared CT design so they match Clients/Leads. KPI numbers carry .kpi-num so the
 * light theme renders them black (App.tsx).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from './api';
import { CT } from './crmTable';

const REFRESH_MS = 10000;

const PERIODS: Array<[string, string]> = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['this_week', 'This week'], ['last_week', 'Last week'],
  ['this_month', 'This month'], ['last_month', 'Last month'], ['this_year', 'This year'], ['last_year', 'Last year'],
];

type Live = {
  role: 'leads' | 'retention' | 'admin';
  agent_id: number | null;
  kpis: {
    commission: number; clients: number; active_clients: number; leads: number; nda: number; won: number; lost: number;
    new_clients: number; new_leads: number;   // acquired in the selected period (admin headline tiles)
    markup: number; paid_to_ib: number; net: number; retention_pct: number;   // retention money
    converted: number; calls: number; leads_received: number;      // retention funnel
  };
  profit?: {
    net_deposit_profit: number; markup_profit: number; credit_lost: number;
    sales_commission: number; ib_commission: number;
    expenses: { tech: number; wages: number; marketing: number; office: number; other: number; total: number };
  };
  markup_rows: Array<{ time: string; client: string; login: number; symbol: string; lots: number; markup: number; commission: number; paid_to_ib: number; net: number }>;
  recent_leads: Array<{ id: number; name: string; source: string; campaign: string; country: string; created_at: string; age_minutes: number }>;
  won_lost: Array<{ login: number; name: string; first_deposit_at: string; called_at: string | null; status: 'won' | 'lost'; bonus: number }>;
  kyc_leads: Array<{ id: number; name: string; kyc_status: string; submitted_at: string | null }>;
  flows?: { deposits: number; withdrawals: number; net: number };
  ranking?: Array<{ agent_id: number; name: string; deposits: number; new_clients: number }>;
  trends?: Array<{ date: string; deposits: number; withdrawals: number }>;
  compare?: Record<string, { current: number; previous: number; pct: number }>;
  to_call?: Array<{ login: number; name: string; balance: number; deposits: number; call_score: number; trades: number; first_deposit_at: string | null; last_trade_at: string | null; reason: string }>;
};

const money = (n: number) => '$' + (n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = (n: number) => (n || 0).toLocaleString('en-GB');
const hhmm = (t: string) => { try { return new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); } catch { return '—'; } };
const dt = (t: string | null) => { if (!t) return '—'; try { const d = new Date(t); return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); } catch { return '—'; } };
const age = (m: number) => (m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${Math.floor(m / 1440)}d`);

const SRC: Record<string, { icon: string; c: string }> = {
  facebook: { icon: 'f', c: '#4d9fff' }, instagram: { icon: '◎', c: '#ff8ac8' },
  google: { icon: 'G', c: '#ffbf47' }, tradesoft: { icon: '⇄', c: '#00e5a0' },
};

/** Count-up number — animates when the live value changes, so a new commission is felt. */
function Counter({ value, fmt, style, className }: { value: number; fmt: (n: number) => string; style?: React.CSSProperties; className?: string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value) return;
    const t0 = performance.now(), dur = 700;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);           // easeOutCubic
      setShown(start + (value - start) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className={className} style={style}>{fmt(shown)}</span>;
}

function Pulse({ on }: { on: boolean }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: 8, height: 8 }}>
      <span style={{
        position: 'absolute', inset: 0, borderRadius: '50%', background: '#00e5a0',
        opacity: on ? 0.75 : 0, animation: on ? 'crmPing 1.8s cubic-bezier(0,0,.2,1) infinite' : 'none',
      }} />
      <span style={{ position: 'relative', width: 8, height: 8, borderRadius: '50%', background: on ? '#00e5a0' : '#626d80' }} />
    </span>
  );
}

/** Hero tile. `hero` = the big money one. `info` = a ⓘ with a hover tooltip explaining the number. */
function Tile({ label, value, fmt, hero, accent, sub, info }: {
  label: string; value: number; fmt: (n: number) => string;
  hero?: boolean; accent?: string; sub?: string; info?: string;
}) {
  const c = accent || '#00e5a0';
  return (
    <div style={{
      position: 'relative', overflow: 'hidden',
      background: hero
        ? `linear-gradient(135deg, ${c}1f 0%, var(--bg-card,#2c333e) 62%)`
        : 'var(--bg-card,#2c333e)',
      border: `1px solid ${hero ? c + '55' : 'var(--border,#4f596b)'}`,
      borderRadius: 14, padding: hero ? '16px 18px' : '13px 15px',
      gridColumn: hero ? 'span 2' : undefined,
    }}>
      {hero && <div style={{ position: 'absolute', right: -28, top: -28, width: 110, height: 110, borderRadius: '50%', background: c, opacity: 0.10 }} />}
      <div style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
        {label}
        {info && <span title={info} style={{ cursor: 'help', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 14, height: 14, borderRadius: '50%', border: `1px solid ${c}`, color: c, fontSize: 9, fontWeight: 700, fontStyle: 'italic', flexShrink: 0 }}>i</span>}
      </div>
      {/* .kpi-num → the light theme forces these black (App.tsx); dark keeps the accent */}
      <Counter className="kpi-num" value={value} fmt={fmt} style={{
        display: 'block', marginTop: 5, fontWeight: 800, lineHeight: 1.05,
        fontSize: hero ? 34 : 23, color: c,
      }} />
      {sub && <div style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function Panel({ title, note, count, children }: { title: string; note?: string; count?: number; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)',
      borderRadius: 14, display: 'flex', flexDirection: 'column', minHeight: 0, maxHeight: 560, overflow: 'hidden',
    }}>
      <div style={{ padding: '11px 14px', borderBottom: '1px solid var(--border,#4f596b)', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text,#e6e9ef)' }}>{title}</span>
        {count != null && <span style={{ fontSize: 10.5, fontWeight: 700, color: '#00e5a0', background: 'rgba(0,229,160,0.12)', border: '1px solid rgba(0,229,160,0.35)', borderRadius: 999, padding: '1px 8px' }}>{count}</span>}
        {note && <span style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', marginLeft: 'auto' }}>{note}</span>}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>{children}</div>
    </div>
  );
}

/** Deposits vs withdrawals vs net — the money-flow bar (proportional split + count-up figures). */
function FlowBar({ flows }: { flows?: { deposits: number; withdrawals: number; net: number } }) {
  const dep = flows?.deposits || 0, wd = flows?.withdrawals || 0, net = dep - wd;
  const tot = Math.max(1, dep + wd);
  const depPct = (dep / tot) * 100, wdPct = (wd / tot) * 100;
  const cell = (label: string, val: number, c: string, arrow: string): React.ReactNode => (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 700 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ color: c, fontSize: 15 }}>{arrow}</span>
        <Counter className="kpi-num" value={val} fmt={money} style={{ fontWeight: 800, fontSize: 21, color: c }} />
      </div>
    </div>
  );
  return (
    <div style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 14, padding: '13px 16px' }}>
      <div style={{ display: 'flex', gap: 18, marginBottom: 10 }}>
        {cell('Deposits', dep, '#00e5a0', '↑')}
        {cell('Withdrawals', wd, '#ff5d6c', '↓')}
        {cell('Net deposit', net, net >= 0 ? '#00aaff' : '#ff5d6c', net >= 0 ? '=' : '=')}
      </div>
      {/* proportional deposits vs withdrawals bar */}
      <div style={{ display: 'flex', height: 10, borderRadius: 6, overflow: 'hidden', background: 'var(--bg-input,#373f4d)' }}>
        <div style={{ width: `${depPct}%`, background: 'linear-gradient(90deg,#00e5a0,#00c88a)', transition: 'width .6s ease' }} />
        <div style={{ width: `${wdPct}%`, background: 'linear-gradient(90deg,#ff7a86,#ff5d6c)', transition: 'width .6s ease' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--text2,#8a93a3)' }}>
        <span>{depPct.toFixed(0)}% in</span><span>{wdPct.toFixed(0)}% out</span>
      </div>
    </div>
  );
}

/** Period-vs-previous comparison KPIs (admin) — brings back the old dashboard's compare row.
 *  Each metric shows the current value + % change against the SAME-LENGTH prior window, with the
 *  arrow coloured by whether the move is favourable (deposits/net/new clients up = good; withdrawals
 *  and IB-commission cost up = red). Replaces the money-flow bar on the admin desk. */
function CompareBar({ cmp }: { cmp?: Live['compare'] }) {
  const items: Array<{ key: string; label: string; fmt: (n: number) => string; goodUp: boolean }> = [
    { key: 'deposits', label: 'Deposits', fmt: money, goodUp: true },
    { key: 'withdrawals', label: 'Withdrawals', fmt: money, goodUp: false },
    { key: 'net', label: 'Net deposit', fmt: money, goodUp: true },
    { key: 'new_clients', label: 'New clients', fmt: num, goodUp: true },
    { key: 'ib_commission', label: 'IB commission', fmt: money, goodUp: false },
  ];
  return (
    <div style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 14, padding: '12px 16px' }}>
      <div style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 700, marginBottom: 11 }}>
        This period vs previous&nbsp;
        <span style={{ textTransform: 'none', letterSpacing: 0, opacity: 0.7, fontWeight: 600 }}>· same-length prior window</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${items.length},1fr)`, gap: 14 }}>
        {items.map(it => {
          const m = cmp?.[it.key] || { current: 0, previous: 0, pct: 0 };
          const flat = Math.abs(m.pct) < 0.05;
          const up = m.pct >= 0;
          const good = up === it.goodUp;
          const col = flat ? 'var(--text2,#8a93a3)' : good ? '#00e5a0' : '#ff5d6c';
          return (
            <div key={it.key} style={{ minWidth: 0 }}>
              <div style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 700 }}>{it.label}</div>
              <Counter className="kpi-num" value={m.current} fmt={it.fmt} style={{ fontWeight: 800, fontSize: 20, color: 'var(--text,#e8ecf3)' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3, flexWrap: 'wrap' }}>
                <span style={{ color: col, fontSize: 12, fontWeight: 800 }}>{flat ? '—' : up ? '▲' : '▼'} {Math.abs(m.pct).toFixed(1)}%</span>
                <span style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)' }}>vs {it.fmt(m.previous)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const Empty = ({ cols, children }: { cols: number; children: React.ReactNode }) => (
  <tr><td colSpan={cols} style={{ padding: 34, textAlign: 'center', color: 'var(--text2,#8a93a3)', whiteSpace: 'normal' }}>{children}</td></tr>
);

/* ── the four live tables (module-scope so the role layout below stays readable) ── */
function MarkupFeed({ rows, flash, title = '⚡ Live commission feed', showIb = true }:
  { rows: Live['markup_rows']; flash: Set<string>; title?: string; showIb?: boolean }) {
  return (
    <Panel title={title} count={rows.length} note="every closing trade credits commission instantly">
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>Time</th><th style={CT.th()}>Client</th><th style={CT.th()}>Symbol</th>
          <th style={CT.th(false, 'right')}>Lots</th><th style={CT.th(false, 'right')}>Markup</th>
          {showIb && <th style={CT.th(false, 'right')}>Paid to IB</th>}
          <th style={CT.th(false, 'right')}>Net comm.</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={showIb ? 7 : 6}>No closing trades in this period yet — this feed fills as clients close.</Empty>
            : rows.map((m, i) => {
              const key = `${m.login}|${m.time}`;
              return (
                <tr key={i} style={{ ...CT.row(), animation: flash.has(key) ? 'crmFlash 2s ease-out' : undefined }}>
                  <td style={{ ...CT.td, color: 'var(--text2,#8a93a3)' }}>{hhmm(m.time)}</td>
                  <td style={CT.td}>{m.client}<span style={{ color: '#556', fontSize: 10 }}> #{m.login}</span></td>
                  <td style={{ ...CT.td, fontFamily: 'monospace', color: '#4d9fff' }}>{m.symbol}</td>
                  <td style={{ ...CT.td, textAlign: 'right' }}>{m.lots}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: 'var(--text2,#8a93a3)' }}>{money(m.markup)}</td>
                  {showIb && <td style={{ ...CT.td, textAlign: 'right', color: '#ffaa00' }}>{money(m.paid_to_ib)}</td>}
                  <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>+{money(m.net)}</td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </Panel>
  );
}

const CALL_REASON: Record<string, { label: string; c: string; bg: string }> = {
  activate:  { label: 'D1 · activate', c: '#00e5a0', bg: 'rgba(0,229,160,0.12)' },
  're-engage': { label: 'Re-engage', c: '#ffaa00', bg: 'rgba(255,170,0,0.12)' },
  'follow-up': { label: 'Follow-up', c: '#4d9fff', bg: 'rgba(77,159,255,0.12)' },
};

/** RETENTION action list: which of my clients to call, and why. */
function ToCall({ rows }: { rows: NonNullable<Live['to_call']> }) {
  return (
    <Panel title="📞 Clients to call" count={rows.length} note="funded & not trading first, then by call priority">
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>Client</th><th style={CT.th()}>Why</th>
          <th style={CT.th(false, 'right')}>Balance</th><th style={CT.th(false, 'right')}>Deposited</th><th style={CT.th(false, 'right')}>Score</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={5}>No clients need a call right now.</Empty>
            : rows.map(c => {
              const r = CALL_REASON[c.reason] || CALL_REASON['follow-up'];
              return (
                <tr key={c.login} style={CT.row()}>
                  <td style={CT.td}>{c.name}<span style={{ color: '#556', fontSize: 10 }}> #{c.login}</span></td>
                  <td style={CT.td}>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999, color: r.c, background: r.bg, border: `1px solid ${r.c}55` }}>{r.label}</span>
                  </td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 600 }}>{money(c.balance)}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: 'var(--text2,#8a93a3)' }}>{money(c.deposits)}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: c.call_score >= 60 ? '#ff5d6c' : c.call_score >= 30 ? '#ffaa00' : 'var(--text2,#8a93a3)', fontWeight: 700 }}>{c.call_score || '—'}</td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </Panel>
  );
}

function RankingTable({ rows }: { rows: NonNullable<Live['ranking']> }) {
  return (
    <Panel title="🏆 Sales ranking" count={rows.length} note="top agents by deposits this period">
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>#</th><th style={CT.th()}>Agent</th>
          <th style={CT.th(false, 'right')}>New clients</th><th style={CT.th(false, 'right')}>Deposits</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={4}>No agent deposits in this period.</Empty>
            : rows.map((a, i) => (
              <tr key={a.agent_id} style={CT.row()}>
                <td style={{ ...CT.td, color: i < 3 ? '#ffbf47' : 'var(--text2,#8a93a3)', fontWeight: i < 3 ? 800 : 400 }}>{i + 1}</td>
                <td style={CT.td}>{a.name}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff' }}>{num(a.new_clients)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{money(a.deposits)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </Panel>
  );
}

/** Compact SVG chart: two-series area (deposits vs withdrawals) or single net line. */
function TrendChart({ title, data, mode }: { title: string; data: NonNullable<Live['trends']>; mode: 'dw' | 'net' }) {
  const W = 520, H = 150, pad = 6;
  const pts = data.length ? data : [{ date: '', deposits: 0, withdrawals: 0 }];
  const series = mode === 'dw'
    ? [{ key: 'deposits', c: '#00e5a0' }, { key: 'withdrawals', c: '#ff5d6c' }]
    : [{ key: 'net', c: '#00aaff' }];
  const vals: number[] = [0];
  pts.forEach((p: any) => (mode === 'dw' ? [p.deposits, p.withdrawals] : [p.deposits - p.withdrawals]).forEach(v => vals.push(v)));
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0);
  const x = (i: number) => pad + (i / Math.max(1, pts.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - min) / (max - min || 1)) * (H - 2 * pad);
  const line = (key: string) => pts.map((p: any, i: number) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(mode === 'net' ? p.deposits - p.withdrawals : p[key]).toFixed(1)}`).join(' ');
  const fmtK = (v: number) => (Math.abs(v) >= 1000 ? '$' + (v / 1000).toFixed(0) + 'K' : '$' + Math.round(v));
  return (
    <div style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 14, padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text,#e6e9ef)' }}>{title}</span>
        <span style={{ fontSize: 10.5, color: 'var(--text2,#8a93a3)', marginLeft: 'auto' }}>{fmtK(min)} … {fmtK(max)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 150, display: 'block' }} preserveAspectRatio="none">
        <line x1={pad} y1={y(0)} x2={W - pad} y2={y(0)} stroke="var(--border,#4f596b)" strokeWidth="1" strokeDasharray="3 3" />
        {series.map(s => <path key={s.key} d={line(s.key)} fill="none" stroke={s.c} strokeWidth="2" strokeLinejoin="round" />)}
      </svg>
      <div style={{ display: 'flex', gap: 14, marginTop: 4, fontSize: 10.5 }}>
        {mode === 'dw'
          ? <><span style={{ color: '#00e5a0' }}>● Deposits</span><span style={{ color: '#ff5d6c' }}>● Withdrawals</span></>
          : <span style={{ color: '#00aaff' }}>● Net deposit</span>}
      </div>
    </div>
  );
}

function LeadsFeed({ rows }: { rows: Live['recent_leads'] }) {
  return (
    <Panel title="🎯 Live leads" count={rows.length} note="last 10 registered · call the freshest first">
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>Lead</th><th style={CT.th()}>Arrived from</th><th style={CT.th()}>Country</th><th style={CT.th(false, 'right')}>Waiting</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={4}>No new leads in this period.</Empty>
            : rows.map(l => {
              const s = SRC[(l.source || '').toLowerCase()] || { icon: '•', c: '#8a93a3' };
              const hot = l.age_minutes <= 30;
              return (
                <tr key={l.id} style={CT.row()}>
                  <td style={CT.td}>{l.name || 'Unknown'}</td>
                  <td style={CT.td}>
                    <span style={{ color: s.c, fontWeight: 700, marginRight: 5 }}>{s.icon}</span>
                    <span style={{ color: s.c }}>{l.source || '—'}</span>
                    {l.campaign && <span style={{ color: '#667', fontSize: 10 }}> · {l.campaign}</span>}
                  </td>
                  <td style={{ ...CT.td, color: 'var(--text2,#8a93a3)' }}>{l.country || '—'}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: hot ? '#00e5a0' : '#ffaa00', fontWeight: 700 }}>{hot && '🔥 '}{age(l.age_minutes)}</td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </Panel>
  );
}

function WonLostFeed({ rows }: { rows: Live['won_lost'] }) {
  return (
    <Panel title="🏆 Became clients — won / lost" note="won = you called before the deposit">
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>Client</th><th style={CT.th()}>Called</th><th style={CT.th()}>Deposited</th><th style={CT.th(false, 'right')}>Result</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={4}>No conversions in this period.</Empty>
            : rows.map(w => (
              <tr key={w.login} style={CT.row()}>
                <td style={CT.td}>{w.name}<span style={{ color: '#556', fontSize: 10 }}> #{w.login}</span></td>
                <td style={{ ...CT.td, color: w.called_at ? '#00e5a0' : '#ff5d6c' }}>{dt(w.called_at)}</td>
                <td style={{ ...CT.td, color: 'var(--text2,#8a93a3)' }}>{dt(w.first_deposit_at)}</td>
                <td style={{ ...CT.td, textAlign: 'right' }}>
                  {w.status === 'won'
                    ? <span style={{ color: '#00e5a0', fontWeight: 800 }}>WON +{money(w.bonus)}</span>
                    : <span style={{ color: '#ff5d6c', fontWeight: 800 }}>LOST</span>}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </Panel>
  );
}

function KycQueue({ rows }: { rows: Live['kyc_leads'] }) {
  return (
    <Panel title="🪪 KYC queue" count={rows.length}>
      <table style={CT.table}>
        <thead><tr style={CT.theadTr}>
          <th style={CT.th()}>Name</th><th style={CT.th()}>Submitted</th><th style={CT.th(false, 'right')}>Status</th>
        </tr></thead>
        <tbody>
          {!rows.length ? <Empty cols={3}>Nothing waiting on KYC.</Empty>
            : rows.map(x => {
              const ok = /appro|verif/i.test(x.kyc_status || '');
              return (
                <tr key={x.id} style={CT.row()}>
                  <td style={CT.td}>{x.name}</td>
                  <td style={{ ...CT.td, color: 'var(--text2,#8a93a3)' }}>{dt(x.submitted_at)}</td>
                  <td style={{ ...CT.td, textAlign: 'right' }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                      color: ok ? '#00e5a0' : '#ffaa00',
                      background: ok ? 'rgba(0,229,160,0.12)' : 'rgba(255,170,0,0.12)',
                      border: `1px solid ${ok ? '#00e5a055' : '#ffaa0055'}`,
                    }}>{(x.kyc_status || '—').toUpperCase()}</span>
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </Panel>
  );
}

export default function DashboardLive({ user }: { user?: any }) {
  const [period, setPeriod] = useState('this_month');   // default landing = this month
  const [d, setD] = useState<Live | null>(null);
  const [err, setErr] = useState('');
  const [ago, setAgo] = useState(0);
  const seen = useRef<Set<string>>(new Set());
  const [flash, setFlash] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    apiGet(`/dashboard/live?period=${period}`)
      .then((r: any) => {
        if (!r || !r.kpis) { setErr('The live endpoint is not deployed yet — restart the backend to enable it.'); return; }
        setErr('');
        // flash rows we haven't seen before (a trade that just closed / a new lead)
        const fresh = new Set<string>();
        (r.markup_rows || []).forEach((m: any) => {
          const k = `${m.login}|${m.time}`;
          if (seen.current.size && !seen.current.has(k)) fresh.add(k);
        });
        (r.markup_rows || []).forEach((m: any) => seen.current.add(`${m.login}|${m.time}`));
        setFlash(fresh);
        if (fresh.size) setTimeout(() => setFlash(new Set()), 2000);
        setD(r); setAgo(0);
      })
      .catch(() => setErr('Could not reach the live endpoint.'));
  }, [period]);

  useEffect(() => { seen.current = new Set(); load(); }, [load]);
  useEffect(() => { const t = setInterval(load, REFRESH_MS); return () => clearInterval(t); }, [load]);
  useEffect(() => { const t = setInterval(() => setAgo(a => a + 1), 1000); return () => clearInterval(t); }, []);

  const role = d?.role || 'admin';
  const isLeads = role === 'leads';
  const isRet = role === 'retention';
  const k = d?.kpis;

  const roleLabel = isLeads ? 'Leads desk' : isRet ? 'Retention desk' : 'Full CRM';

  return (
    // natural flow — the page scrolls (Dashboard content area is overflow:auto); no fit-to-screen
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 16 }}>
      <style>{`@keyframes crmPing{75%,100%{transform:scale(2.6);opacity:0}}
        @keyframes crmFlash{0%{background:rgba(0,229,160,.30)}100%{background:transparent}}`}</style>

      {/* ── header ───────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Pulse on={!err} />
        <span style={{ fontSize: 15, fontWeight: 800, color: 'var(--text,#e6e9ef)' }}>
          {user?.full_name ? `${String(user.full_name).split(' ')[0]}'s desk` : 'Live'}
        </span>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: '#00e5a0', background: 'rgba(0,229,160,0.12)', border: '1px solid rgba(0,229,160,0.35)', borderRadius: 999, padding: '2px 9px' }}>
          {roleLabel}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text2,#8a93a3)' }}>
          {err ? '—' : `updated ${ago}s ago · live every ${REFRESH_MS / 1000}s`}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {PERIODS.map(([kk, lbl]) => (
            <button key={kk} onClick={() => setPeriod(kk)} style={{
              padding: '5px 12px', borderRadius: 8, fontSize: 11.5, cursor: 'pointer',
              border: `1px solid ${period === kk ? '#00e5a0' : 'var(--border2,#626d80)'}`,
              background: period === kk ? 'rgba(0,229,160,0.10)' : 'transparent',
              color: period === kk ? '#00e5a0' : 'var(--text2,#8a93a3)',
            }}>{lbl}</button>
          ))}
        </div>
      </div>

      {err && (
        <div style={{ background: 'rgba(255,170,0,0.08)', border: '1px solid #ffaa0055', color: '#ffaa00', borderRadius: 10, padding: '9px 13px', fontSize: 12 }}>
          ⚠ {err}
        </div>
      )}

      {/* ── KPI strip (role-specific) ─────────────────────────── */}
      {isLeads && (
        // LEADS desk (more leads than clients): lead-focused — NO clients
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 10 }}>
          <Tile hero label="My leads" value={k?.leads || 0} fmt={num} accent="#9966ff" sub="active leads in your book" />
          <Tile label="Leads received" value={k?.leads_received || 0} fmt={num} accent="#4d9fff" sub="this period" />
          <Tile label="Leads converted" value={k?.converted || 0} fmt={num} accent="#00aaff" />
          <Tile label="Total calls" value={k?.calls || 0} fmt={num} accent="#00e5a0" />
          <Tile label="Won" value={k?.won || 0} fmt={num} accent="#00e5a0" sub="called before deposit" />
          <Tile label="Lost" value={k?.lost || 0} fmt={num} accent="#ff5d6c" sub="deposited before call" />
        </div>
      )}
      {isRet && (
        // RETENTION desk (more clients than leads): client + commission focused — NO leads
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10 }}>
          <Tile hero label="My commission" value={k?.commission || 0} fmt={money} accent="#00e5a0"
            sub={`net markup × ${k?.retention_pct ?? 15}%`}
            info={`Commission = net markup × ${k?.retention_pct ?? 15}%. Net markup = total markup you earned − IB commission, with credit-funded trades excluded. Change the rate in settings and this follows.`} />
          <Tile label="My clients" value={k?.clients || 0} fmt={num} accent="#00aaff" />
          <Tile label="Active clients" value={k?.active_clients || 0} fmt={num} accent="#4d9fff"
            info="Clients who deposited, withdrew, transferred, or traded in this period." />
          <Tile label="Paid to IB" value={k?.paid_to_ib || 0} fmt={money} accent="#ffaa00" sub="on your book" />
          <Tile label="Net markup" value={k?.net || 0} fmt={money} accent="#00e5a0" sub="markup − paid to IB"
            info="Total markup earned − IB commission (credit-funded trades excluded)." />
        </div>
      )}
      {role === 'admin' && (
        // ADMIN cares about COMPANY PROFIT. Two hero KPIs: RED = risky (client money that can still
        // be withdrawn), GREEN = safe (genuinely-earned markup). Both net off sales + IB commission.
        // 7-col grid: the two heroes span 2 each (slightly narrower than before) so Active/Clients/Leads fit.
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 10 }}>
          <Tile hero label="Net-deposit profit" value={d?.profit?.net_deposit_profit || 0} fmt={money} accent="#ff5d6c"
            sub="net deposit − commissions − expenses · RISKY"
            info={`RISKY profit = net deposit (deposits − withdrawals) − sales commission ($${Math.round(d?.profit?.sales_commission || 0).toLocaleString()}) − IB commission ($${Math.round(d?.profit?.ib_commission || 0).toLocaleString()}) − expenses ($${Math.round(d?.profit?.expenses?.total || 0).toLocaleString()}). Red because it counts client money that can still be withdrawn.`} />
          <Tile hero label="Markup profit" value={d?.profit?.markup_profit || 0} fmt={money} accent="#00e5a0"
            sub="markup − commissions − expenses − credit lost · SAFE"
            info={`SAFE profit = gross markup − sales commission ($${Math.round(d?.profit?.sales_commission || 0).toLocaleString()}) − IB commission ($${Math.round(d?.profit?.ib_commission || 0).toLocaleString()}) − expenses ($${Math.round(d?.profit?.expenses?.total || 0).toLocaleString()}) − credit lost ($${Math.round(d?.profit?.credit_lost || 0).toLocaleString()}). Green because markup is genuinely earned spread revenue.`} />
          <Tile label="Active clients" value={k?.active_clients || 0} fmt={num} accent="#4d9fff"
            info="Clients who deposited, withdrew, transferred, or traded in this period (not just funded)." />
          <Tile label="New clients" value={k?.new_clients || 0} fmt={num} accent="#00aaff" sub="acquired this period"
            info="Distinct people whose first-ever deposit landed inside the selected period — genuinely new depositing clients, not the lifetime total." />
          <Tile label="New leads" value={k?.new_leads || 0} fmt={num} accent="#9966ff" sub="received this period"
            info="Leads received (created) inside the selected period, not the lifetime total." />
        </div>
      )}

      {/* ── money-flow bar (retention) · period-vs-previous compare (admin, replaces the bar) ── */}
      {isRet && <FlowBar flows={d?.flows} />}
      {role === 'admin' && <CompareBar cmp={d?.compare} />}

      {/* ── ADMIN: two charts (deposits vs withdrawals · net) ─── */}
      {role === 'admin' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <TrendChart title="Deposits vs withdrawals" data={d?.trends || []} mode="dw" />
          <TrendChart title="Net deposit" data={d?.trends || []} mode="net" />
        </div>
      )}

      {/* ── live tables (role-specific) — natural height, page scrolls ──────── */}
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr', alignItems: 'start' }}>
        {role === 'admin' && <>
          <MarkupFeed rows={d?.markup_rows || []} flash={flash} />
          <RankingTable rows={d?.ranking || []} />
        </>}
        {isRet && <>
          <MarkupFeed rows={d?.markup_rows || []} flash={flash} title="⚡ Live commission feed" />
          <ToCall rows={d?.to_call || []} />
        </>}
        {isLeads && <>
          <LeadsFeed rows={d?.recent_leads || []} />
          <WonLostFeed rows={d?.won_lost || []} />
          <div style={{ gridColumn: '1 / -1', minHeight: 0 }}><KycQueue rows={d?.kyc_leads || []} /></div>
        </>}
        {/* #244 — TEAM LEADERS (non-admin) get their team's ranking, scoped server-side */}
        {role !== 'admin' && (d?.ranking || []).length > 0 && (
          <div style={{ gridColumn: '1 / -1', minHeight: 0 }}><RankingTable rows={d?.ranking || []} /></div>
        )}
      </div>
    </div>
  );
}
