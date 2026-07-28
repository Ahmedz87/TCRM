import React, { useState, useEffect, useRef, Suspense } from 'react';
import { createPortal } from 'react-dom';
import { apiGet } from './api';
import { useT } from './adminI18n';
import { lazyWithReload, ChunkErrorBoundary } from './lazyWithReload';
import tnfxLogo from './assets/tnfx-logo.png';
import tnfxMark from './assets/tnfx-mark.png';

// ── Code-splitting: each page is lazily loaded so its JS is only fetched when
//    the section is first opened, keeping the initial bundle small. The default
//    "dashboard" landing view stays in the main chunk for fast first paint.
import DashboardLive from './DashboardLive';   // the front page — eager, it's the landing view
import MarginWatch from './MarginWatch';        // #210 — floating draggable margin-watch widget

const GlobalSearch = lazyWithReload(() => import('./GlobalSearch'));
const Clients = lazyWithReload(() => import('./Clients'));
const Leads = lazyWithReload(() => import('./Leads'));
const Training = lazyWithReload(() => import('./Training'));
const TradingAccounts = lazyWithReload(() => import('./TradingAccounts'));
const IBPortal = lazyWithReload(() => import('./IBPortal'));
const IBAdmin = lazyWithReload(() => import('./IBAdmin'));
const SalesAgents = lazyWithReload(() => import('./SalesAgents'));
const CallQA = lazyWithReload(() => import('./CallQA'));
const AMLReview = lazyWithReload(() => import('./AMLReview'));
const MarkupSettings = lazyWithReload(() => import('./MarkupSettings'));
const Transactions = lazyWithReload(() => import('./Transactions'));
const ScoreSettings = lazyWithReload(() => import('./ScoreSettings'));
const LeadsSettings = lazyWithReload(() => import('./LeadsSettings'));
const PaymentSettings = lazyWithReload(() => import('./PaymentSettings'));
const PaymentCards = lazyWithReload(() => import('./PaymentCards'));
const BonusSettings = lazyWithReload(() => import('./BonusSettings'));
const ArchiveSettings = lazyWithReload(() => import('./ArchiveSettings'));
const TicketsPage = lazyWithReload(() => import('./Tickets'));
const AccountTypes = lazyWithReload(() => import('./AccountTypes'));
const UserManagement = lazyWithReload(() => import('./UserManagement'));
const NetworkPage = lazyWithReload(() => import('./NetworkPage'));
const AbuseDetection = lazyWithReload(() => import('./AbuseDetection'));
const Retention = lazyWithReload(() => import('./Retention'));
const CopyTradingAdmin = lazyWithReload(() => import('./CopyTradingAdmin'));
const CommissionProfiles = lazyWithReload(() => import('./CommissionProfiles'));
const ChallengeSettings = lazyWithReload(() => import('./ChallengeSettings'));
const NegBalance = lazyWithReload(() => import('./NegBalance'));
const Loyalty = lazyWithReload(() => import('./Loyalty'));
const MyLoyalty = lazyWithReload(() => import('./MyLoyalty'));
const ReportsKpi = lazyWithReload(() => import('./ReportsKpi'));
const MonthlyReport = lazyWithReload(() => import('./MonthlyReport'));
const Finance = lazyWithReload(() => import('./Finance'));
const Marketing = lazyWithReload(() => import('./Marketing'));
const KycReview = lazyWithReload(() => import('./KycReview'));
const Hedging = lazyWithReload(() => import('./Hedging'));

const menuSections = [
  {
    title: 'Main',
    items: [
      { icon: '📊', label: 'Dashboard',        key: 'dashboard' },
      { icon: '🎯', label: 'Leads',             key: 'leads' },
      { icon: '🪪', label: 'KYC',               key: 'kyc' },
      { icon: '👥', label: 'Clients',           key: 'clients' },
      { icon: '📣', label: 'Marketing',         key: 'marketing' },
      { icon: '🛟', label: 'Retention Engine',  key: 'retention' },
      { icon: '📈', label: 'Trading accounts',  key: 'accounts' },
      { icon: '💳', label: 'Transactions',      key: 'transactions' },
      { icon: '🛡️', label: 'Neg. Balance',       key: 'neg_balance' },
      { icon: '📊', label: 'Performance Report', key: 'reports' },
      { icon: '📅', label: 'Monthly Report',     key: 'monthly_report' },
      { icon: '💰', label: 'Finance Management', key: 'finance' },
      { icon: '🚨', label: 'Abuse Detection',   key: 'abuse' },
      { icon: '📕', label: 'Hedging',           key: 'hedging' },
      { icon: '⚖️', label: 'AML Screening',      key: 'aml' },
      { icon: '🎧', label: 'Call QA',           key: 'call_qa' },
      { icon: '🎓', label: 'Training',          key: 'training' },
      { icon: '🪞', label: 'Copy Trading',      key: 'copy_admin' },
      { icon: '🎁', label: 'Loyalty', key: 'loyalty' },
      { icon: '🕸️', label: 'Network / Risk',    key: 'network' },
      { icon: '🎫', label: 'Tickets',           key: 'tickets' },
    ]
  },
  {
    title: 'IB System',
    items: [
      { icon: '🤝', label: 'IB Admin',          key: 'ib_admin' },
      { icon: '🧑‍💼', label: 'Sales Agents',      key: 'sales_agents' },
      { icon: '💰', label: 'Commission Profiles', key: 'ib_profiles' },
      { icon: '🏆', label: 'IB Challenges',     key: 'ib_challenges' },
    ]
  },
  {
    title: 'Settings',
    hub: true, hubKey: 'settings', hubIcon: '⚙️',
    items: [
      { icon: '🎯', label: 'Priority score',    key: 'settings_score',         desc: 'Lead-priority scoring weights & call cycle' },
      { icon: '🧭', label: 'Leads assignment',  key: 'settings_leads',         desc: 'Rules that route leads to sales agents' },
      { icon: '👤', label: 'Users & roles',     key: 'settings_users',         desc: 'Staff accounts, roles & permissions' },
      { icon: '💳', label: 'Payment methods',   key: 'settings_payments',      desc: 'Deposit / withdrawal gateways' },
      { icon: '🪪', label: 'Payment cards',     key: 'settings_payment_cards', desc: 'Qi/Zain/Fastpay/Sham cards + anti-fraud series' },
      { icon: '🗂', label: 'Account types',     key: 'settings_account_types', desc: 'Trading account groups & leverage' },
      { icon: '💹', label: 'Markups',           key: 'settings_markups',       desc: 'Spread markups & commission revenue' },
      { icon: '🎁', label: 'Bonus settings',    key: 'settings_bonuses',       desc: 'Welcome / deposit / special bonuses' },
      { icon: '🗄', label: 'Archive',           key: 'settings_archive',       desc: 'Archived clients & leads — auto re-capture on re-engagement' },
    ]
  },
];
// Flatten for backward compat
const menuItems = menuSections.flatMap(s => s.items);

// Hedging section — visible ONLY to these staff emails (case-insensitive), even for admins.
const HEDGING_EMAILS = ['abbask@tnfx.co', 'ahmedz@tnfx.co'];

const PERIODS = [
  { key: 'today',        label: 'Today' },
  { key: 'yesterday',    label: 'Yesterday' },
  { key: 'last_7d',      label: 'Last 7 days' },
  { key: 'this_week',    label: 'This week' },
  { key: 'this_month',   label: 'This month' },
  { key: 'last_month',   label: 'Last month' },
  { key: 'last_3m',      label: 'Last 3 months' },
  { key: 'this_year',    label: 'This year' },
  { key: 'last_year',    label: 'Last year' },
  { key: 'all_time',     label: 'All time' },
];

// Demo data for Top agents (until real per-agent deposits are wired)
const DEMO_LEADERBOARD = [
  { agent_id: 1, name: 'Rand Awad',        deposits: 184200, new_clients: 23 },
  { agent_id: 2, name: 'Hammam Alkfari',   deposits: 156800, new_clients: 19 },
  { agent_id: 3, name: 'Aileen Yousif',    deposits: 142500, new_clients: 21 },
  { agent_id: 4, name: 'Sarah Ali',        deposits: 119300, new_clients: 14 },
  { agent_id: 5, name: 'Ahmad Alshamaa',   deposits: 98600,  new_clients: 12 },
  { agent_id: 6, name: 'Nur Abdulhalem',   deposits: 84100,  new_clients: 11 },
  { agent_id: 7, name: 'Ritta Alzeer',     deposits: 72400,  new_clients: 9 },
  { agent_id: 8, name: 'Hiba Hasan',       deposits: 61200,  new_clients: 8 },
];

// ── Interactive line/area chart with hover tooltip ─────────────────────────────
function LineChart({ data, series, label, height = 170 }: any) {
  // series: [{ key, color, name }]
  const [hover, setHover] = React.useState<number | null>(null);
  const rows = (data || []);
  const n = rows.length;
  const fmtMoney = (v: number) => {
    const a = Math.abs(v);
    const s = v < 0 ? '-' : '';
    return a >= 1e6 ? s+'$'+(a/1e6).toFixed(2)+'M' : a >= 1e3 ? s+'$'+(a/1e3).toFixed(1)+'K' : s+'$'+Math.round(a);
  };

  // domain across all series (include 0 so net can go negative)
  let allVals: number[] = [0];
  rows.forEach((r: any) => series.forEach((s: any) => allVals.push(r[s.key] || 0)));
  const maxV = Math.max(...allVals);
  const minV = Math.min(...allVals);
  const range = (maxV - minV) || 1;

  const W = 1000, H = height, padT = 14, padB = 24, padL = 6, padR = 6;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const x = (i: number) => padL + (n <= 1 ? plotW/2 : (i/(n-1))*plotW);
  const y = (v: number) => padT + (1 - (v - minV)/range) * plotH;
  const zeroY = y(0);

  const pathFor = (key: string) => rows.map((r: any, i: number) =>
    `${i===0?'M':'L'}${x(i).toFixed(1)},${y(r[key]||0).toFixed(1)}`).join(' ');
  const areaFor = (key: string) => n === 0 ? '' :
    `M${x(0).toFixed(1)},${zeroY.toFixed(1)} ` +
    rows.map((r: any, i: number) => `L${x(i).toFixed(1)},${y(r[key]||0).toFixed(1)}`).join(' ') +
    ` L${x(n-1).toFixed(1)},${zeroY.toFixed(1)} Z`;

  const totals = series.map((s: any) => rows.reduce((a: number, r: any) => a + (r[s.key]||0), 0));

  return (
    <div style={{ width:'100%' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10, flexWrap:'wrap', gap:8 }}>
        <span style={{ fontSize:12, color:'var(--text2,#888)', fontWeight:500 }}>{label}</span>
        <div style={{ display:'flex', gap:14 }}>
          {series.map((s: any, i: number) => (
            <span key={s.key} style={{ display:'flex', alignItems:'center', gap:5, fontSize:11 }}>
              <span style={{ width:9, height:9, borderRadius:2, background:s.color }}></span>
              <span style={{ color:'var(--text3,#888)' }}>{s.name}</span>
              <span style={{ color:s.color, fontWeight:600 }}>{fmtMoney(totals[i])}</span>
            </span>
          ))}
        </div>
      </div>

      <div style={{ position:'relative' }} onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width:'100%', height }}>
          <defs>
            {series.map((s: any) => (
              <linearGradient key={s.key} id={`grad-${label.replace(/\s/g,'')}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.35" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          {/* gridlines */}
          {[0,0.5,1].map(g => {
            const gy = padT + g*plotH;
            return <line key={g} x1={padL} y1={gy} x2={W-padR} y2={gy} stroke="var(--border,#4f596b)" strokeWidth="1" strokeDasharray="4 4" />;
          })}
          {/* zero line if negatives exist */}
          {minV < 0 && <line x1={padL} y1={zeroY} x2={W-padR} y2={zeroY} stroke="#666" strokeWidth="1" />}
          {/* areas + lines */}
          {series.map((s: any) => (
            <g key={s.key}>
              <path d={areaFor(s.key)} fill={`url(#grad-${label.replace(/\s/g,'')}-${s.key})`} />
              <path d={pathFor(s.key)} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </g>
          ))}
          {/* hover marker */}
          {hover !== null && (
            <line x1={x(hover)} y1={padT} x2={x(hover)} y2={padT+plotH} stroke="#fff" strokeWidth="1" strokeDasharray="3 3" opacity="0.4" vectorEffect="non-scaling-stroke" />
          )}
          {hover !== null && series.map((s: any) => (
            <circle key={s.key} cx={x(hover)} cy={y(rows[hover]?.[s.key]||0)} r="3.5" fill={s.color} stroke="#000" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>

        {/* invisible hover columns */}
        <div style={{ position:'absolute', inset:0, display:'flex' }}>
          {rows.map((_: any, i: number) => (
            <div key={i} style={{ flex:1, cursor:'crosshair' }} onMouseEnter={() => setHover(i)} />
          ))}
        </div>

        {/* tooltip */}
        {hover !== null && rows[hover] && (
          <div style={{ position:'absolute', top:0, left:`${(hover/Math.max(n-1,1))*100}%`,
                        transform:`translateX(${hover > n/2 ? '-105%' : '5%'})`,
                        background:'#000', border:'1px solid #626d80', borderRadius:7, padding:'7px 10px', pointerEvents:'none', zIndex:5, whiteSpace:'nowrap' }}>
            <div style={{ fontSize:10, color:'var(--text3,#888)', marginBottom:3 }}>{rows[hover].date}</div>
            {series.map((s: any) => (
              <div key={s.key} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12 }}>
                <span style={{ width:8, height:8, borderRadius:2, background:s.color }}></span>
                <span style={{ color:'var(--text2,#aaa)' }}>{s.name}:</span>
                <span style={{ color:s.color, fontWeight:600 }}>{fmtMoney(rows[hover][s.key]||0)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:'var(--text3,#555)', marginTop:6 }}>
        <span>{rows[0]?.date || ''}</span>
        {n > 2 && <span>{rows[Math.floor(n/2)]?.date || ''}</span>}
        <span>{rows[n-1]?.date || ''}</span>
      </div>
    </div>
  );
}

// Mock KPI data per period
const KPI_DATA: any = {
  today:      { clients:12,  deposits:84200,  withdrawals:12000, pending_w:3,  no_deposit:8,  sales_comm:1240,  ib_comm:820,  new_leads:14, active_traders:203 },
  this_week:  { clients:48,  deposits:312000, withdrawals:54000, pending_w:7,  no_deposit:24, sales_comm:4800,  ib_comm:3200, new_leads:67, active_traders:498 },
  this_month: { clients:142, deposits:940000, withdrawals:180000,pending_w:12, no_deposit:58, sales_comm:14200, ib_comm:9400, new_leads:210, active_traders:1203 },
  last_month: { clients:118, deposits:820000, withdrawals:155000,pending_w:9,  no_deposit:44, sales_comm:12100, ib_comm:8200, new_leads:188, active_traders:1089 },
  this_year:  { clients:821, deposits:5400000,withdrawals:980000,pending_w:12, no_deposit:210,sales_comm:84000, ib_comm:54000,new_leads:1240, active_traders:1203 },
  last_year:  { clients:624, deposits:4100000,withdrawals:720000,pending_w:0,  no_deposit:0,  sales_comm:62000, ib_comm:41000,new_leads:980, active_traders:980 },
};

// Sales-specific mock (subset)
const SALES_KPI: any = {
  today:      { clients:3,  deposits:12000, withdrawals:2000, pending_w:1, no_deposit:2, sales_comm:320,  ib_comm:180,  new_leads:4, active_traders:28 },
  this_week:  { clients:9,  deposits:44000, withdrawals:8000, pending_w:2, no_deposit:6, sales_comm:1100, ib_comm:620,  new_leads:14, active_traders:62 },
  this_month: { clients:24, deposits:140000,withdrawals:28000,pending_w:3, no_deposit:11,sales_comm:3200, ib_comm:1800, new_leads:38, active_traders:142 },
  last_month: { clients:19, deposits:118000,withdrawals:22000,pending_w:2, no_deposit:8, sales_comm:2800, ib_comm:1400, new_leads:31, active_traders:118 },
  this_year:  { clients:112,deposits:820000,withdrawals:140000,pending_w:3,no_deposit:11,sales_comm:18000,ib_comm:9800, new_leads:210, active_traders:142 },
  last_year:  { clients:88, deposits:640000,withdrawals:110000,pending_w:0,no_deposit:0, sales_comm:14200,ib_comm:7600, new_leads:168, active_traders:112 },
};

const TARGET = 20000; // monthly sales target

function fmt(n: number) {
  if (n >= 1000000) return '$' + (n/1000000).toFixed(1) + 'M';
  if (n >= 1000)    return '$' + (n/1000).toFixed(1) + 'K';
  return '$' + n.toLocaleString('en-GB');
}


const NOTIF_ICON: Record<string, string> = {
  lead: '🎯', client: '👤', money_request: '💰', ticket: '🎫', abuse: '⚠️', call_qa: '📞',
};
function timeAgo(d: string, t: (en: string) => string): string {
  const s = Math.max(0, (Date.now() - new Date(d).getTime()) / 1000);
  if (s < 90) return t('just now');
  if (s < 3600) return Math.round(s / 60) + ' ' + t('min ago');
  if (s < 86400) return Math.round(s / 3600) + ' ' + t('h ago');
  return Math.round(s / 86400) + ' ' + t('d ago');
}

function NotificationBell() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number }>({ left: 0, top: 0 });
  const bellRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<any>({ unread: 0, notifications: [] });
  const load = () => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || '/api') + '/notifications', {
      headers: { Authorization: 'Bearer ' + token }
    }).then(r => r.json()).then(d => setData(
      d && Array.isArray(d.notifications) ? d : { unread: 0, notifications: [] }
    )).catch(() => {});
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  const markRead = (id: number) => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || '/api') + '/notifications/' + id + '/read', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    }).then(() => load());
  };
  const markAll = () => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || '/api') + '/notifications/read-all', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    }).then(() => load());
  };
  const toggle = () => {
    const r = bellRef.current?.getBoundingClientRect();
    if (r) {
      // the bell sits at the BOTTOM-LEFT of the sidebar; opening downward runs off-screen.
      // Open upward whenever the bell is in the lower half of the viewport, and keep the
      // 320-wide panel fully on-screen horizontally.
      const openUp = r.top > window.innerHeight / 2;
      setPos({
        left: Math.min(Math.max(8, r.left), window.innerWidth - 332),
        top: openUp ? undefined : r.bottom + 8,
        bottom: openUp ? Math.max(8, window.innerHeight - r.top + 8) : undefined,
      });
    }
    setOpen(o => !o);
  };
  return (
    <div ref={bellRef} style={{ position: 'relative' }}>
      <div onClick={toggle} style={{ cursor: 'pointer', fontSize: 18, position: 'relative' }} title={t('Notifications')}>
        🔔
        {data.unread > 0 && (
          <span style={{ position: 'absolute', top: -6, right: -8, background: '#ff4d4d', color: '#fff', borderRadius: 99, fontSize: 9, fontWeight: 700, padding: '1px 5px', minWidth: 14, textAlign: 'center' }}>
            {data.unread > 99 ? '99+' : data.unread}
          </span>
        )}
      </div>
      {open && createPortal(
        <>
        <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 2147483646 }} />
        <div style={{ position: 'fixed', left: pos.left, top: pos.top, bottom: pos.bottom, width: 320, maxHeight: '70vh', overflowY: 'auto', background: '#373f4d', border: '1px solid #626d80', borderRadius: 12, zIndex: 2147483647, boxShadow: '0 8px 30px rgba(0,0,0,0.5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderBottom: '1px solid #626d80' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>{t('Notifications')}</span>
            {data.unread > 0 && <span onClick={markAll} style={{ fontSize: 11, color: '#00aaff', cursor: 'pointer' }}>{t('Mark all read')}</span>}
          </div>
          {data.notifications.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#555', fontSize: 12 }}>{t('No notifications')}</div>
          ) : data.notifications.map((n: any) => (
            <div key={n.id} onClick={() => { markRead(n.id); if (n.link) window.dispatchEvent(new CustomEvent('navigate', { detail: { page: n.link.replace('/', '') } })); setOpen(false); }}
              style={{ padding: '11px 14px', borderBottom: '1px solid #4f596b', cursor: 'pointer', background: n.is_read ? 'transparent' : 'rgba(0,170,255,0.07)', display: 'flex', gap: 10 }}>
              <div style={{ fontSize: 16, lineHeight: 1.2 }}>{NOTIF_ICON[n.type] || '🔔'}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: n.is_read ? '#aaa' : '#fff', marginBottom: 3, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.title}</span>
                  {!n.is_read && <span style={{ width: 7, height: 7, borderRadius: 99, background: '#00aaff', flexShrink: 0, marginTop: 3 }} />}
                </div>
                <div style={{ fontSize: 11, color: '#98a2b3', lineHeight: 1.4 }}>{n.message}</div>
                <div style={{ fontSize: 9.5, color: '#5b6575', marginTop: 4 }}>{timeAgo(n.created_at, t)}</div>
              </div>
            </div>
          ))}
        </div>
        </>, document.body
      )}
    </div>
  );
}

export default function Dashboard({ user, onLogout, lang, onLangChange, theme, onThemeChange }: any) {
  const t = useT();
  // remember the open page across a browser refresh (ticket #4)
  // Per-TAB view state (sessionStorage, not localStorage) so multiple tabs are independent and a
  // refresh returns to the SAME place. A ?page=/?client=/?lead= URL (right-click → open in new tab)
  // wins on first load; then the address bar is cleaned back to my1.tnfx.co (see the effect below).
  const [active, setActiveRaw] = useState<string>(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      if (p.get('page'))   return p.get('page') as string;
      if (p.get('client')) return 'clients';
      if (p.get('lead'))   return 'leads';
      return sessionStorage.getItem('crm_active_page') || 'dashboard';
    } catch { return 'dashboard'; }
  });
  const setActive = (k: string) => {
    try { sessionStorage.setItem('crm_active_page', k); } catch {}
    setActiveRaw(k);
    // #275: push a history entry so the browser BACK button steps back through in-app sections
    // instead of leaving the CRM. URL stays clean (pathname only). Guard against duplicate pushes.
    try { if ((window.history.state || {}).crmActive !== k) window.history.pushState({ crmActive: k }, '', window.location.pathname); } catch {}
  };
  const [salesAgentFocus, setSalesAgentFocus] = useState<number | undefined>(undefined);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // default to a bounded period so the home page loads instantly; "All time" scans the
  // full 2M-row transactions table (~30s) and is now a deliberate click, not the default.
  const [period, setPeriod] = useState('this_month');
  const [kpiData, setKpiData] = useState<any>(null);
  const [cmpGran, setCmpGran] = useState<'week' | 'month' | 'year'>('month');   // comparison (ticket #15)
  const [cmpData, setCmpData] = useState<any>(null);
  const [kpiLoading, setKpiLoading] = useState(false);
  const isAr = lang === 'ar';

  const role = user?.role || 'sales_agent';
  const isAdmin   = ['super_admin','admin','director'].includes(role);
  const isSales   = role === 'sales_agent';
  // Only back-office (+admins) may action transactions; everyone else is read-only.
  const isBackoffice = ['super_admin','admin','backoffice'].includes(role);
  // The Ticket Centre is open to EVERY staff user (desk decision Jul 2026): anyone can submit a
  // ticket to the developer and track their own; admins see and answer all. The backend scopes
  // non-admins to their own tickets, so no client-side allowlist is needed.
  const canTicket = !!user;
  // Menu access per role. Admins/director see everything; other departments are limited.
  let allowedKeys: string[] | null;
  if (isAdmin) {
    allowedKeys = null;                                   // super_admin / admin / director
  } else if (role === 'customer_care') {
    allowedKeys = ['dashboard', 'leads', 'clients', 'accounts', 'transactions'];      // read-only
  } else if (role === 'validation') {
    allowedKeys = ['dashboard', 'network', 'leads', 'clients', 'aml'];                  // + KYC (in client profile) + AML review
  } else if (role === 'backoffice') {
    allowedKeys = ['dashboard', 'transactions', 'accounts', 'abuse', 'aml', 'network', 'retention', 'settings_payment_cards'];
  } else if (role === 'vps') {
    allowedKeys = ['dashboard'];
  } else if (role === 'marketing') {
    allowedKeys = ['dashboard', 'marketing', 'leads', 'clients'];                       // Marketing + Leads + Clients
  } else if (role === 'training') {
    allowedKeys = ['dashboard', 'training'];                                            // Training department
  } else {
    // sales_agent / sales_manager / retention.
    // call_qa: every agent sees the Call QA page — the BACKEND limits sales_agent role to their
    // OWN calls only (call_qa_router._own_filter by users.extension). sales_agents: they see the
    // commission page too, but the figures render blurred + board-review notice (SalesAgents.tsx).
    // training: sales/retention flag leads for training and see their OWN submissions.
    allowedKeys = ['dashboard', 'leads', 'clients', 'accounts', 'transactions', 'ib_admin', 'loyalty', 'call_qa', 'sales_agents', 'training'];
    // the retention team gets the Retention Engine
    if (role === 'retention') allowedKeys = [...allowedKeys, 'retention'];
  }
  // Per-user nav OVERRIDE ("small admin" — e.g. granted exactly Leads/Clients/Sales Agents). When a
  // user has nav_keys set, it replaces the role-based menu (data access still comes from their role).
  const navOverride = String(user?.nav_keys || '').split(',').map((s: string) => s.trim()).filter(Boolean);
  if (navOverride.length) allowedKeys = ['dashboard', ...navOverride];
  // Performance Report: ADMINS / DIRECTORS ONLY (desk decision Jul 2026 — hidden from everyone
  // else, including sales managers who previously had it). Admins have allowedKeys=null, so
  // canSee('reports') lets them in; every non-admin role's explicit list omits 'reports'.
  // Section-restricted team leader / manager (requirement #2): hide the data pages they can't
  // see. scope_sections empty = all allowed; scope_mode 'none' = hide every data page.
  const _secs: string[] = Array.isArray((user as any)?.scope_sections) ? (user as any).scope_sections : [];
  const _secKey: Record<string, string> = { clients: 'clients', leads: 'leads', ibs: 'ib_admin', calls: 'call_qa' };
  if (allowedKeys && (user as any)?.scope_mode === 'none') {
    const dataPages = ['clients', 'leads', 'ib_admin', 'call_qa', 'accounts', 'transactions', 'sales_agents', 'retention', 'loyalty'];
    allowedKeys = allowedKeys.filter((k: string) => !dataPages.includes(k));
  } else if (allowedKeys && _secs.length) {
    allowedKeys = allowedKeys.filter((k: string) => {
      const sec = Object.keys(_secKey).find(s => _secKey[s] === k);
      return !sec || _secs.includes(sec);   // keep non-section pages; keep allowed sections only
    });
  }
  // Ticket Centre: open to everyone. For non-admins (explicit allowedKeys list) add 'tickets';
  // admins (allowedKeys=null) get it via canSee() below.
  if (allowedKeys && canTicket && !allowedKeys.includes('tickets')) allowedKeys = [...allowedKeys, 'tickets'];
  if (allowedKeys) allowedKeys = allowedKeys.filter((k: string) => k !== 'tickets' || canTicket);

  // ACCESS GUARD — the sidebar filter alone was NOT enough: the dashboard "Quick actions" /
  // "All modules" buttons and the localStorage-restored last page could open ANY section for
  // any role. canSee() is the single source of truth; anything not allowed bounces to home.
  const canSee = (k: string): boolean => {
    if (k === 'search') return true;          // global search — available to every staff user
    if (k === 'tickets') return canTicket;    // hard allowlist — overrides the admin "see all"
    if (k === 'hedging') return HEDGING_EMAILS.includes(String(user?.email || '').trim().toLowerCase());  // email allowlist — overrides admin "see all"
    if (!allowedKeys || k === 'dashboard') return true;
    if (allowedKeys.includes(k)) return true;
    const hub = menuSections.find(s => (s as any).hub) as any;
    if (hub && k === hub.hubKey) return hub.items.some((i: any) => allowedKeys!.includes(i.key));
    return false;
  };
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => { if (!canSee(active)) setActive('dashboard'); }, [active, role, user]);  // eslint-disable-line react-hooks/exhaustive-deps

  const [trends, setTrends] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [funnel, setFunnel] = useState<any>(null);

  useEffect(() => {
    const handler = (e: any) => {
      const { page, search, openProfile, login, ib, ibId, agentId } = e.detail || {};
      if (page === 'sales_agents') {
        setSalesAgentFocus(agentId || undefined);
        setActive('sales_agents');
      } else if (page === 'clients') {
        setActive('clients');
        if (search) {
          // small delay to let Clients component mount
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('clients_search', {detail:{search, openProfile}}));
          }, 100);
        }
      } else if (page === 'leads') {
        setActive('leads');
        if (search) {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('leads_search', { detail: { search } }));
          }, 120);
        }
      } else if (page === 'network') {
        setActive('network');
        if (login) {
          // let NetworkPage mount, then focus the account's network
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('network_focus', {detail:{login}}));
          }, 150);
        }
      } else if (page === 'ib_admin') {
        setActive('ib_admin');
        if (ib || ibId) {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('ib_focus', {detail:{ib, ibId}}));
          }, 150);
        }
      } else if (page === 'accounts') {
        setActive('accounts');
        if (login) {
          // let TradingAccounts mount, then search for that login
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('accounts_focus', {detail:{login}}));
          }, 150);
        }
      } else if (page) {
        // generic fallback (notification bell links: leads / transactions / abuse / tickets…);
        // an unknown key is reset to 'dashboard' by the canSee guard above.
        setActive(page);
      }
    };
    window.addEventListener('navigate', handler);
    return () => window.removeEventListener('navigate', handler);
  }, []);

  // Deep-link support (right-click → "Open in new tab"): a URL like ?page=<key>, ?client=<login>
  // or ?lead=<id> opens that view on load — so ANY page or profile can live in its own tab. We
  // record the target in sessionStorage (per-tab); the Clients/Leads pages reopen the profile on
  // mount, so a refresh returns to the SAME place. Then we CLEAN the address bar back to
  // my1.tnfx.co (no query string shown), and each tab stays independent.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const client = p.get('client'), lead = p.get('lead'), page = p.get('page');
    try {
      if (client)      { sessionStorage.setItem('crm_open_client', client); setActive('clients'); }
      else if (lead)   { sessionStorage.setItem('crm_open_lead', lead);     setActive('leads'); }
      else if (page)   { setActive(page); }
    } catch {}
    if ((client || lead || page) && window.location.search) {
      // seed crmActive so the browser Back button (#275) has a defined target from a deep link
      try { window.history.replaceState({ crmActive: (page || (client ? 'clients' : 'leads')) }, '', window.location.pathname); } catch {}
    }
  }, []);  // once, on mount

  // #275: browser BACK walks back through in-app sections. setActive() pushes an entry per nav;
  // here we seed the initial entry (for a plain load with no deep link) and restore the section
  // on popstate. Uses setActiveRaw (not setActive) so a back-navigation doesn't push a new entry.
  useEffect(() => {
    try { if (!(window.history.state || {}).crmActive) window.history.replaceState({ crmActive: active }, '', window.location.pathname); } catch {}
    const onPop = (e: PopStateEvent) => {
      const k = (e.state || {}).crmActive;
      if (k) { try { sessionStorage.setItem('crm_active_page', k); } catch {} setActiveRaw(k); }
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setKpiLoading(true);
    apiGet(`/dashboard/kpis?period=${period}`)
      .then(data => setKpiData(data))
      .catch(() => {})
      .finally(() => setKpiLoading(false));
    apiGet(`/dashboard/trends?period=${period}`)
      .then((d: any) => setTrends(d?.series || []))
      .catch(() => setTrends([]));
    if (!isSales) {
      apiGet(`/dashboard/leaderboard?period=${period}`)
        .then((d: any) => setLeaderboard(d?.leaderboard || []))
        .catch(() => setLeaderboard([]));
      apiGet(`/dashboard/funnel?period=${period}`)
        .then((d: any) => setFunnel(d))
        .catch(() => setFunnel(null));
    }
  }, [period, isSales]);

  // refetch the comparison when the week/month/year toggle changes (ticket #15)
  useEffect(() => {
    apiGet(`/dashboard/compare?granularity=${cmpGran}`)
      .then((d: any) => setCmpData(d))
      .catch(() => setCmpData(null));
  }, [cmpGran]);

  // Map API response to template fields
  const mappedKpiData = kpiData ? {
    clients:        kpiData.clients || 0,
    deposits:       kpiData.deposits || 0,
    withdrawals:    kpiData.withdrawals || 0,
    pending_w:      kpiData.pending_w || 0,
    no_deposit:     kpiData.no_deposit_14d || 0,
    active_traders: kpiData.active_traders || 0,
    new_leads:      kpiData.new_clients || 0,
    sales_comm:     kpiData.sales_comm || 0,
    ib_comm:        kpiData.ib_comm || 0,
    new_clients:    kpiData.new_clients || 0,
  } : null;
  const ZERO_KPI = { clients:0, deposits:0, withdrawals:0, pending_w:0, no_deposit:0, active_traders:0, new_leads:0, sales_comm:0, ib_comm:0, new_clients:0 };
  const kpi = mappedKpiData || ZERO_KPI;
  const commPct = Math.min(100, Math.round((kpi.sales_comm / TARGET) * 100));

  return (
    <div style={{ display:'flex', height:'100vh', overflow:'hidden', background:'var(--bg-main,#20252f)', color:'var(--text,#fff)', fontFamily:'sans-serif', direction: isAr?'rtl':'ltr' }}>

      {/* pinned ticket button removed — manual ticket creation disabled (tickets are created via assistant chat / WhatsApp only) */}
      {/* <TicketButton /> */}

      {/* Sidebar — .keep-dark: stays dark even in light theme */}
      <div className="keep-dark kd-side" style={{ width: sidebarOpen?220:60, flexShrink:0, background:'var(--bg-card,#2c333e)', borderRight:'1px solid var(--border,#4f596b)', color:'var(--text,#fff)', display:'flex', flexDirection:'column', transition:'width 0.25s', overflow:'hidden', position:'relative', zIndex:6 }}>
        <div style={{ padding:'16px 14px', borderBottom:'1px solid var(--border,#4f596b)', display:'flex', alignItems:'center', gap:10 }}>
          {sidebarOpen
            ? <img src={tnfxLogo} alt="TNFX" style={{ height:28, width:'auto', display:'block' }} />
            : <img src={tnfxMark} alt="TNFX" style={{ width:32, height:32, flexShrink:0, display:'block' }} />}
          {sidebarOpen && <div style={{ fontSize:10, color:'#fff', letterSpacing:1, fontWeight:600 }}>{isAr?'نظام CRM':'CRM'}</div>}
        </div>
        <div style={{ flex:1, overflowY:'auto', padding:'8px 6px' }}>
          {menuSections.map(section => {
            const ak = allowedKeys;
            // canSee() is the source of truth (handles the hard 'tickets' allowlist even for admins
            // where ak is null); intersect the role list with it so restricted keys never show.
            const items = (ak ? section.items.filter(i => ak.includes(i.key)) : section.items).filter(i => canSee(i.key));
            if (!items.length) return null;
            // Hub section (e.g. Settings): one clickable item that opens a hub page of subpages
            if ((section as any).hub) {
              const hk = (section as any).hubKey;
              const onHub = active === hk || items.some(i => i.key === active);
              return (
                <div key={section.title} onClick={() => setActive(hk)} title={t(section.title)}
                  style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 10px', borderRadius:8, cursor:'pointer', marginBottom:2, marginTop:8, background: onHub?'rgba(248,80,10,0.10)':'transparent', color: onHub?'#FF6A1A':'#fff', borderLeft: onHub?'3px solid #F8500A':'3px solid transparent', fontSize:12 }}>
                  <span style={{ fontSize:14, width:18, textAlign:'center', flexShrink:0 }}>{(section as any).hubIcon}</span>
                  {sidebarOpen && <span>{t(section.title)}</span>}
                </div>
              );
            }
            return (
            <div key={section.title}>
              {sidebarOpen && (
                <div style={{ padding: '6px 10px 2px', fontSize: 10, color: '#fff', textTransform: 'uppercase', letterSpacing: '.5px', fontWeight: 500, marginTop: 8 }}>
                  {t(section.title)}
                </div>
              )}
              {items.map(item => (
                <a key={item.key} href={`?page=${item.key}`}
                   onClick={(e) => { if (e.ctrlKey||e.metaKey||e.shiftKey||(e as any).button===1) return; e.preventDefault(); setActive(item.key); }}
                   title={`${t(item.label)} — ${t('right-click to open in a new tab')}`}
                   style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 10px', borderRadius:8, cursor:'pointer', marginBottom:2, textDecoration:'none', background: active===item.key?'rgba(248,80,10,0.10)':'transparent', color: active===item.key?'#FF6A1A':'#fff', borderLeft: active===item.key?'3px solid #F8500A':'3px solid transparent', fontSize:12 }}>
                  <span style={{ fontSize:14, width:18, textAlign:'center', flexShrink:0 }}>{item.icon}</span>
                  {sidebarOpen && <span>{t(item.label)}</span>}
                </a>
              ))}
            </div>
            );
          })}
        </div>
        {sidebarOpen && (
          <div style={{ padding:'12px 14px', borderTop:'1px solid var(--border,#4f596b)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ width:32, height:32, borderRadius:8, flexShrink:0, background:'linear-gradient(135deg,#0066ff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700 }}>{user?.full_name?.[0]}</div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, fontWeight:500, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{user?.full_name}</div>
                <div style={{ fontSize:10, color:'#fff' }}>{user?.role}</div>
              </div>
              <NotificationBell />
              <div onClick={onLogout} style={{ cursor:'pointer', color:'#fff', fontSize:16 }} title={t('Logout')}>⇥</div>
            </div>
          </div>
        )}
      </div>

      {/* Main */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', height:'100%', minHeight:0 }}>

        {/* Topbar — .keep-dark: stays dark even in light theme */}
        <div className="keep-dark kd-top" style={{ height:52, display:'flex', alignItems:'center', padding:'0 16px', background:'var(--bg-card,#2c333e)', borderBottom:'1px solid var(--border,#4f596b)', color:'var(--text,#fff)', gap:12, flexShrink:0, position:'relative', zIndex:5 }}>
          <div onClick={() => setSidebarOpen(!sidebarOpen)} style={{ cursor:'pointer', color:'#fff', fontSize:20, padding:4 }}>☰</div>
          <div style={{ fontSize:14, fontWeight:500 }}>{active==='settings' ? t('Settings') : t(menuItems.find(m=>m.key===active)?.label || '')}</div>
          <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:10 }}>
            {/* Global search — available on every page; opens the /search view */}
            <div onClick={() => setActive('search')} title={isAr?'بحث شامل':'Search everything'}
              style={{ display:'flex', alignItems:'center', justifyContent:'center', width:30, height:30, borderRadius:'50%',
                cursor:'pointer', border:`1px solid ${active==='search'?'#00e5a0':'var(--border2,#626d80)'}`,
                background: active==='search'?'rgba(0,229,160,0.12)':'var(--bg-input,#373f4d)', fontSize:14,
                color: active==='search'?'#00e5a0':'#fff', flexShrink:0 }}>
              🔍
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:6, background:'rgba(0,229,160,0.1)', color:'#00e5a0', padding:'4px 10px', borderRadius:99, fontSize:11 }}>
              <div style={{ width:6, height:6, borderRadius:'50%', background:'#00e5a0' }}></div>
              {isAr?'متصل':'Live'}
            </div>
            <button onClick={() => onLangChange(isAr?'en':'ar')} style={{ background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'#fff', padding:'5px 10px', cursor:'pointer', fontSize:11 }}>
              {isAr?'EN':'عربي'}
            </button>
            <div style={{ position:'relative' }}>
              <div onClick={onThemeChange} title={theme==='dark'?t('Switch to Light'):t('Switch to Dark')}
                style={{ display:'flex', alignItems:'center', gap:7, cursor:'pointer', padding:'5px 10px', borderRadius:8, border:'1px solid var(--border2,#626d80)', background:'var(--bg-input,#373f4d)' }}>
                <span style={{ fontSize:15 }}>{theme==='dark'?'🌙':'☀️'}</span>
                <div style={{ width:34, height:18, borderRadius:9, background: theme==='dark'?'#444':'#00a572', position:'relative', transition:'background 0.2s', flexShrink:0 }}>
                  <div style={{ position:'absolute', top:2, left: theme==='dark'?2:16, width:14, height:14, borderRadius:'50%', background:'#fff', transition:'left 0.2s', boxShadow:'0 1px 3px rgba(0,0,0,0.3)' }}></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex:1, overflow: ['clients','accounts','transactions','ib_admin','sales_agents','ib','settings_score','settings_users','network','abuse','reports','monthly_report','finance','leads','kyc','call_qa'].includes(active) ? 'hidden' : 'auto', padding: ['clients','accounts','transactions','ib_admin','sales_agents','ib','reports','monthly_report','finance','call_qa','leads'].includes(active) ? 0 : 16, display:'flex', flexDirection:'column', height:'100%', minHeight:0 }}>

          {/* Everyone (incl. sales/retention) sees the role-scoped dashboard — it shows "my" numbers via isSales */}
          {active === 'dashboard' && <DashboardLive user={user} />}

          <ChunkErrorBoundary><Suspense fallback={<div style={{padding:40,color:'#8a93a3'}}>{t('Loading…')}</div>}>
          {active === 'search'         && <GlobalSearch />}
          {active === 'leads'          && <Leads />}
          {active === 'training'       && <Training />}
          {active === 'kyc'            && <KycReview />}
          {active === 'marketing'      && <Marketing />}
          {active === 'clients'        && <Clients lang={lang} />}
          {active === 'retention'      && <Retention />}
          {active === 'accounts'       && <TradingAccounts lang={lang} />}
          {active === 'ib'             && <IBPortal lang={lang} />}
          {active === 'ib_admin'       && <IBAdmin user={user} />}
          {active === 'sales_agents'   && <SalesAgents focusAgentId={salesAgentFocus} />}
          {active === 'call_qa'        && <CallQA />}
          {active === 'ib_profiles'    && <CommissionProfiles />}
          {active === 'ib_challenges'  && <ChallengeSettings />}
          {active === 'transactions'   && <Transactions readOnly={!isBackoffice} lang={lang} />}
          {active === 'settings' && (() => {
            const sec = menuSections.find(s => (s as any).hub) as any;
            const ak = allowedKeys;
            const items = ak ? sec.items.filter((i: any) => ak.includes(i.key)) : sec.items;
            return (
              <div style={{ maxWidth: 920 }}>
                <h2 style={{ color: 'var(--text,#e6e9ef)', margin: '4px 0 4px', fontSize: 22 }}>⚙️ {t('Settings')}</h2>
                <p style={{ color: '#8a93a5', fontSize: 13, marginTop: 0, marginBottom: 20 }}>{t('Choose a section to configure.')}</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 14 }}>
                  {items.map((it: any) => (
                    <a key={it.key} href={`?page=${it.key}`}
                      onClick={(e) => { if (e.ctrlKey||e.metaKey||e.shiftKey||(e as any).button===1) return; e.preventDefault(); setActive(it.key); }}
                      title={`${t(it.label)} — ${t('right-click to open in a new tab')}`}
                      style={{ display: 'block', textDecoration: 'none', background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18, cursor: 'pointer', transition: 'border-color .15s, transform .15s' }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = '#00e5a0'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border,#4f596b)'; e.currentTarget.style.transform = 'none'; }}>
                      <div style={{ fontSize: 26, marginBottom: 10 }}>{it.icon}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text,#e6e9ef)', marginBottom: 4 }}>{t(it.label)}</div>
                      <div style={{ fontSize: 12, color: '#8a93a5', lineHeight: 1.4 }}>{it.desc ? t(it.desc) : ''}</div>
                    </a>
                  ))}
                </div>
              </div>
            );
          })()}
          {String(active).startsWith('settings_') && (
            <div onClick={() => setActive('settings')} style={{ cursor: 'pointer', color: '#00e5a0', fontSize: 13, marginBottom: 12, display: 'inline-flex', alignItems: 'center', gap: 6 }}>‹ {t('Back to Settings')}</div>
          )}
          {active === 'settings_score' && <ScoreSettings />}
          {active === 'settings_leads' && <LeadsSettings />}
          {active === 'settings_users' && <UserManagement />}
          {active === 'settings_payments' && <PaymentSettings />}
          {active === 'settings_payment_cards' && <PaymentCards />}
          {active === 'settings_account_types' && <AccountTypes />}
          {active === 'settings_markups'      && <MarkupSettings />}
          {active === 'settings_bonuses'      && <BonusSettings />}
          {active === 'settings_archive'      && <ArchiveSettings />}
          {active === 'tickets'   && canTicket && <TicketsPage />}
          {active === 'network'        && <NetworkPage />}
          {active === 'reports'        && <ReportsKpi />}
          {active === 'monthly_report' && <MonthlyReport />}
          {active === 'finance'        && <Finance />}
          {active === 'abuse'          && <AbuseDetection />}
          {active === 'hedging'        && <Hedging />}
          {active === 'aml'            && <AMLReview />}
          {active === 'copy_admin'     && <CopyTradingAdmin />}
          {active === 'loyalty'        && <Loyalty />}
          {active === 'my_loyalty'     && <MyLoyalty />}
          {active === 'neg_balance'    && <NegBalance />}
          </Suspense></ChunkErrorBoundary>

          {!(['abuse', 'accounts', 'call_qa', 'hedging', 'clients', 'copy_admin', 'dashboard', 'finance', 'ib', 'ib_admin', 'ib_challenges', 'ib_profiles', 'kyc', 'leads', 'loyalty', 'marketing', 'monthly_report', 'my_loyalty', 'neg_balance', 'network', 'reports', 'retention', 'sales_agents', 'settings', 'settings_account_types', 'settings_archive', 'settings_bonuses', 'settings_leads', 'settings_markups', 'settings_payment_cards', 'settings_payments', 'settings_score', 'settings_users', 'tickets', 'transactions'] as string[]).includes(active) && (
            <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'60vh', flexDirection:'column', gap:16 }}>
              <div style={{ fontSize:48 }}>{menuItems.find(m=>m.key===active)?.icon}</div>
              <div style={{ fontSize:20, fontWeight:500 }}>{t(menuItems.find(m=>m.key===active)?.label || '')}</div>
              <div style={{ fontSize:13, color:'var(--text3,#555)' }}>{t('This module is being built — coming next!')}</div>
            </div>
          )}

        </div>
      </div>

      {/* #210: floating draggable margin-watch widget — sticks on every page */}
      <MarginWatch />
    </div>
  );
}

