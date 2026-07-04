import React, { useState, useEffect, Suspense } from 'react';
import { apiGet } from './api';
import { lazyWithReload, ChunkErrorBoundary } from './lazyWithReload';
import tnfxLogo from './assets/tnfx-logo.png';
import tnfxMark from './assets/tnfx-mark.png';

// ── Code-splitting: each page is lazily loaded so its JS is only fetched when
//    the section is first opened, keeping the initial bundle small. The default
//    "dashboard" landing view stays in the main chunk for fast first paint.
const Clients = lazyWithReload(() => import('./Clients'));
const Leads = lazyWithReload(() => import('./Leads'));
const TradingAccounts = lazyWithReload(() => import('./TradingAccounts'));
const IBPortal = lazyWithReload(() => import('./IBPortal'));
const IBAdmin = lazyWithReload(() => import('./IBAdmin'));
const SalesAgents = lazyWithReload(() => import('./SalesAgents'));
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
const NegBalance = lazyWithReload(() => import('./NegBalance'));
const Loyalty = lazyWithReload(() => import('./Loyalty'));
const MyLoyalty = lazyWithReload(() => import('./MyLoyalty'));
const ReportsKpi = lazyWithReload(() => import('./ReportsKpi'));
const MonthlyReport = lazyWithReload(() => import('./MonthlyReport'));
const Finance = lazyWithReload(() => import('./Finance'));
const Marketing = lazyWithReload(() => import('./Marketing'));
const KycReview = lazyWithReload(() => import('./KycReview'));

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
  return '$' + n.toLocaleString();
}


function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>({ unread: 0, notifications: [] });
  const load = () => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || '/api') + '/notifications', {
      headers: { Authorization: 'Bearer ' + token }
    }).then(r => r.json()).then(setData).catch(() => {});
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
  return (
    <div style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', fontSize: 18, position: 'relative' }} title="Notifications">
        🔔
        {data.unread > 0 && (
          <span style={{ position: 'absolute', top: -6, right: -8, background: '#ff4d4d', color: '#fff', borderRadius: 99, fontSize: 9, fontWeight: 700, padding: '1px 5px', minWidth: 14, textAlign: 'center' }}>
            {data.unread}
          </span>
        )}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '140%', right: 0, width: 320, maxHeight: 420, overflowY: 'auto', background: '#373f4d', border: '1px solid #626d80', borderRadius: 12, zIndex: 9999, boxShadow: '0 8px 30px rgba(0,0,0,0.5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderBottom: '1px solid #626d80' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Notifications</span>
            {data.unread > 0 && <span onClick={markAll} style={{ fontSize: 11, color: '#00aaff', cursor: 'pointer' }}>Mark all read</span>}
          </div>
          {data.notifications.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#555', fontSize: 12 }}>No notifications</div>
          ) : data.notifications.map((n: any) => (
            <div key={n.id} onClick={() => { markRead(n.id); if (n.link) window.dispatchEvent(new CustomEvent('navigate', { detail: n.link.replace('/', '') })); setOpen(false); }}
              style={{ padding: '11px 14px', borderBottom: '1px solid #4f596b', cursor: 'pointer', background: n.is_read ? 'transparent' : 'rgba(255,77,77,0.06)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: n.is_read ? '#aaa' : '#ff4d4d', marginBottom: 3 }}>{n.title}</div>
              <div style={{ fontSize: 11, color: '#888', lineHeight: 1.4 }}>{n.message}</div>
              <div style={{ fontSize: 9, color: '#444', marginTop: 4 }}>{new Date(n.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard({ user, onLogout, lang, onLangChange, theme, onThemeChange }: any) {
  // remember the open page across a browser refresh (ticket #4)
  const [active, setActiveRaw] = useState<string>(() => {
    try { return localStorage.getItem('crm_active_page') || 'dashboard'; } catch { return 'dashboard'; }
  });
  const setActive = (k: string) => { try { localStorage.setItem('crm_active_page', k); } catch {} setActiveRaw(k); };
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
  const isManager = role === 'sales_manager';
  const isSales   = role === 'sales_agent';
  // Only back-office (+admins) may action transactions; everyone else is read-only.
  const isBackoffice = ['super_admin','admin','backoffice'].includes(role);
  // Menu access per role. Admins/director see everything; other departments are limited.
  let allowedKeys: string[] | null;
  if (isAdmin) {
    allowedKeys = null;                                   // super_admin / admin / director
  } else if (role === 'customer_care') {
    allowedKeys = ['dashboard', 'leads', 'clients', 'accounts', 'transactions'];      // read-only
  } else if (role === 'validation') {
    allowedKeys = ['dashboard', 'network', 'leads', 'clients'];                        // + KYC (in client profile)
  } else if (role === 'backoffice') {
    allowedKeys = ['dashboard', 'transactions', 'accounts', 'abuse', 'network', 'retention', 'settings_payment_cards'];
  } else if (role === 'vps') {
    allowedKeys = ['dashboard'];
  } else if (role === 'marketing') {
    allowedKeys = ['dashboard', 'marketing', 'leads', 'clients'];                       // Marketing + Leads + Clients
  } else {
    // sales_agent / sales_manager / retention
    allowedKeys = ['dashboard', 'leads', 'clients', 'accounts', 'transactions', 'ib_admin', 'loyalty'];
    // the retention team gets the Retention Engine
    if (role === 'retention') allowedKeys = [...allowedKeys, 'retention'];
  }
  // Per-user nav OVERRIDE ("small admin" — e.g. granted exactly Leads/Clients/Sales Agents). When a
  // user has nav_keys set, it replaces the role-based menu (data access still comes from their role).
  const navOverride = String(user?.nav_keys || '').split(',').map((s: string) => s.trim()).filter(Boolean);
  if (navOverride.length) allowedKeys = ['dashboard', ...navOverride];
  // Performance Report (ticket #45): admin/director see it (allowedKeys=null = all);
  // sales managers also get it explicitly (plain sales agents do NOT).
  if (allowedKeys && isManager && !allowedKeys.includes('reports')) allowedKeys = [...allowedKeys, 'reports'];
  // every staff member can see & raise tickets
  if (allowedKeys && !allowedKeys.includes('tickets')) allowedKeys = [...allowedKeys, 'tickets'];

  const [trends, setTrends] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [funnel, setFunnel] = useState<any>(null);

  useEffect(() => {
    const handler = (e: any) => {
      const { page, search, openProfile, login, ib, agentId } = e.detail || {};
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
        if (ib) {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('ib_focus', {detail:{ib}}));
          }, 150);
        }
      }
    };
    window.addEventListener('navigate', handler);
    return () => window.removeEventListener('navigate', handler);
  }, []);

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
        .then((d: any) => setLeaderboard(d?.leaderboard?.length ? d.leaderboard : DEMO_LEADERBOARD))
        .catch(() => setLeaderboard(DEMO_LEADERBOARD));
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

      {/* Sidebar */}
      <div style={{ width: sidebarOpen?220:60, flexShrink:0, background:'var(--bg-card,#2c333e)', borderRight:'1px solid var(--border,#4f596b)', display:'flex', flexDirection:'column', transition:'width 0.25s', overflow:'hidden' }}>
        <div style={{ padding:'16px 14px', borderBottom:'1px solid var(--border,#4f596b)', display:'flex', alignItems:'center', gap:10 }}>
          {sidebarOpen
            ? <img src={tnfxLogo} alt="TNFX" style={{ height:28, width:'auto', display:'block' }} />
            : <img src={tnfxMark} alt="TNFX" style={{ width:32, height:32, flexShrink:0, display:'block' }} />}
          {sidebarOpen && <div style={{ fontSize:10, color:'var(--text3,#888)', letterSpacing:1, fontWeight:600 }}>{isAr?'Ù†Ø¸Ø§Ù… CRM':'CRM'}</div>}
        </div>
        <div style={{ flex:1, overflowY:'auto', padding:'8px 6px' }}>
          {menuSections.map(section => {
            const ak = allowedKeys;
            const items = ak ? section.items.filter(i => ak.includes(i.key)) : section.items;
            if (!items.length) return null;
            // Hub section (e.g. Settings): one clickable item that opens a hub page of subpages
            if ((section as any).hub) {
              const hk = (section as any).hubKey;
              const onHub = active === hk || items.some(i => i.key === active);
              return (
                <div key={section.title} onClick={() => setActive(hk)} title={section.title}
                  style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 10px', borderRadius:8, cursor:'pointer', marginBottom:2, marginTop:8, background: onHub?'rgba(248,80,10,0.10)':'transparent', color: onHub?'#FF6A1A':'#888', borderLeft: onHub?'3px solid #F8500A':'3px solid transparent', fontSize:12 }}>
                  <span style={{ fontSize:14, width:18, textAlign:'center', flexShrink:0 }}>{(section as any).hubIcon}</span>
                  {sidebarOpen && <span>{section.title}</span>}
                </div>
              );
            }
            return (
            <div key={section.title}>
              {sidebarOpen && (
                <div style={{ padding: '6px 10px 2px', fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', fontWeight: 500, marginTop: 8 }}>
                  {section.title}
                </div>
              )}
              {items.map(item => (
                <div key={item.key} onClick={() => setActive(item.key)} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 10px', borderRadius:8, cursor:'pointer', marginBottom:2, background: active===item.key?'rgba(248,80,10,0.10)':'transparent', color: active===item.key?'#FF6A1A':'#888', borderLeft: active===item.key?'3px solid #F8500A':'3px solid transparent', fontSize:12 }}>
                  <span style={{ fontSize:14, width:18, textAlign:'center', flexShrink:0 }}>{item.icon}</span>
                  {sidebarOpen && <span>{item.label}</span>}
                </div>
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
                <div style={{ fontSize:10, color:'var(--text3,#555)' }}>{user?.role}</div>
              </div>
              <NotificationBell />
              <div onClick={onLogout} style={{ cursor:'pointer', color:'var(--text3,#555)', fontSize:16 }} title="Logout">⇥</div>
            </div>
          </div>
        )}
      </div>

      {/* Main */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', height:'100%', minHeight:0 }}>

        {/* Topbar */}
        <div style={{ height:52, display:'flex', alignItems:'center', padding:'0 16px', background:'var(--bg-card,#2c333e)', borderBottom:'1px solid var(--border,#4f596b)', gap:12, flexShrink:0 }}>
          <div onClick={() => setSidebarOpen(!sidebarOpen)} style={{ cursor:'pointer', color:'var(--text2,#888)', fontSize:20, padding:4 }}>☰</div>
          <div style={{ fontSize:14, fontWeight:500 }}>{active==='settings' ? 'Settings' : menuItems.find(m=>m.key===active)?.label}</div>
          <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:10 }}>
            <div style={{ display:'flex', alignItems:'center', gap:6, background:'rgba(0,229,160,0.1)', color:'#00e5a0', padding:'4px 10px', borderRadius:99, fontSize:11 }}>
              <div style={{ width:6, height:6, borderRadius:'50%', background:'#00e5a0' }}></div>
              {isAr?'Ù…ØªØµÙ„':'Live'}
            </div>
            <button onClick={() => onLangChange(isAr?'en':'ar')} style={{ background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text2,#888)', padding:'5px 10px', cursor:'pointer', fontSize:11 }}>
              {isAr?'EN':'Ø¹Ø±Ø¨ÙŠ'}
            </button>
            <div style={{ position:'relative' }}>
              <div onClick={onThemeChange} title={theme==='dark'?'Switch to Light':'Switch to Dark'}
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
        <div style={{ flex:1, overflow: ['clients','accounts','transactions','ib_admin','sales_agents','ib','settings_score','settings_users','network','abuse','reports','monthly_report','finance','leads','kyc'].includes(active) ? 'hidden' : 'auto', padding: ['clients','accounts','transactions','ib_admin','sales_agents','ib','reports','monthly_report','finance'].includes(active) ? 0 : 16, display:'flex', flexDirection:'column', height:'100%', minHeight:0 }}>

          {/* Everyone (incl. sales/retention) sees the role-scoped dashboard — it shows "my" numbers via isSales */}
          {active === 'dashboard' && (
            <div>

              {/* Period filter */}
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:16, flexWrap:'wrap' }}>
                <div style={{ fontSize:13, color:'var(--text3,#555)', marginRight:4 }}>Period:</div>
                {PERIODS.map(p => (
                  <button key={p.key} onClick={() => setPeriod(p.key)}
                    style={{ padding:'5px 14px', borderRadius:7, border:`1px solid ${period===p.key?'#00e5a0':'#626d80'}`, background: period===p.key?'rgba(0,229,160,0.1)':'transparent', color: period===p.key?'#00e5a0':'#888', cursor:'pointer', fontSize:12 }}>
                    {p.label}
                  </button>
                ))}
                {isSales && <span style={{ fontSize:11, color:'var(--text3,#555)', marginLeft:8 }}>Showing your data only</span>}
                {isManager && <span style={{ fontSize:11, color:'var(--text3,#555)', marginLeft:8 }}>Showing your team data</span>}
                {isAdmin && <span style={{ fontSize:11, color:'var(--text3,#555)', marginLeft:8 }}>Showing entire CRM</span>}
              </div>

              {/* Whole-year totals (1 Jan – 31 Dec) — ticket #14 */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:12 }}>
                <div style={{ background:'linear-gradient(135deg,#10331f,#1b2129)', border:'1px solid #1f7a4d', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#7fd6a8', marginBottom:6, fontWeight:600 }}>📅 {kpiData?.year_label||''} deposits (1 Jan – 31 Dec)</div>
                  <div style={{ fontSize:24, fontWeight:600, color:'#00e5a0' }}>{fmt(kpiData?.year_deposits||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Full year to date</div>
                </div>
                <div style={{ background:'linear-gradient(135deg,#331717,#1b2129)', border:'1px solid #7a3a3a', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#e6a3a3', marginBottom:6, fontWeight:600 }}>📅 {kpiData?.year_label||''} withdrawals (1 Jan – 31 Dec)</div>
                  <div style={{ fontSize:24, fontWeight:600, color:'#ff8888' }}>{fmt(kpiData?.year_withdrawals||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Full year to date</div>
                </div>
                <div style={{ background:'linear-gradient(135deg,#102a33,#1b2129)', border:'1px solid #1f5f7a', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#8fcfe6', marginBottom:6, fontWeight:600 }}>📅 {kpiData?.year_label||''} net (deposits − withdrawals)</div>
                  <div style={{ fontSize:24, fontWeight:600, color:(kpiData?.year_net||0)>=0?'#00aaff':'#ff8888' }}>{fmt(kpiData?.year_net||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Full year to date</div>
                </div>
              </div>

              {/* Equity snapshot at this point in time — ticket #21/#22/#23 */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:12 }}>
                <div style={{ background:'linear-gradient(135deg,#1a2440,#1b2129)', border:'1px solid #3956a0', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#9db4ee', marginBottom:6, fontWeight:600 }}>💼 Total equity (now)</div>
                  <div style={{ fontSize:24, fontWeight:600, color:'#7da6ff' }}>{fmt(kpiData?.total_equity||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Snapshot across all accounts</div>
                </div>
                <div style={{ background:'linear-gradient(135deg,#15301f,#1b2129)', border:'1px solid #2f7a55', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#86d7ab', marginBottom:6, fontWeight:600 }}>💵 Equity — bonus excluded</div>
                  <div style={{ fontSize:24, fontWeight:600, color:'#34d399' }}>{fmt(kpiData?.equity_ex_bonus||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Real client money (equity − bonus)</div>
                </div>
                <div style={{ background:'linear-gradient(135deg,#2e2410,#1b2129)', border:'1px solid #8a6a2a', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'#e3c887', marginBottom:6, fontWeight:600 }}>🎁 Bonus inside equity</div>
                  <div style={{ fontSize:24, fontWeight:600, color:'#E8B84B' }}>{fmt(kpiData?.bonus_in_equity||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Credit/bonus carried on accounts</div>
                </div>
              </div>

              {/* KPI grid — 8 KPIs, fixed 4 columns = 2 rows */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:16 }}>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>{isSales?'My clients':'Total clients'}</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#00e5a0' }}>{kpi.clients.toLocaleString()}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>+{kpi.new_clients||kpi.new_leads||0} new this period</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>Total deposits</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#00e5a0' }}>{fmt(kpi.deposits)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>{isSales?'My clients':'All clients'}</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>Total withdrawals</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#ff8888' }}>{fmt(kpi.withdrawals)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Net: {fmt(kpi.deposits - kpi.withdrawals)}</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>Pending withdrawals</div>
                  <div style={{ fontSize:22, fontWeight:500, color: kpi.pending_w > 5 ? '#ff4d4d' : '#ffaa00' }}>{kpi.pending_w}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Awaiting approval</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>No deposit 14+ days</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#ff4d4d' }}>{kpi.no_deposit}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Need follow-up</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>Active traders</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#0066ff' }}>{kpi.active_traders.toLocaleString()}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>Traded this period</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>New leads</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#9966ff' }}>{kpi.new_leads}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>This period</div>
                </div>

                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginBottom:6 }}>Total balance</div>
                  <div style={{ fontSize:22, fontWeight:500, color:'#00aaff' }}>{fmt(kpiData?.total_balance||0)}</div>
                  <div style={{ fontSize:11, color:'var(--text3,#555)', marginTop:2 }}>{isSales?'My clients':'All clients'}</div>
                </div>

              </div>

              {/* Comparison: week / month / year — current vs previous (ticket #15) */}
              <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16, marginBottom:16 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14, flexWrap:'wrap', gap:8 }}>
                  <div style={{ fontSize:14, fontWeight:600 }}>📊 Comparison
                    {cmpData && <span style={{ fontSize:12, color:'var(--text3,#888)', fontWeight:400, marginLeft:8 }}>{cmpData.current_label} vs {cmpData.previous_label}</span>}
                  </div>
                  <div style={{ display:'flex', gap:6 }}>
                    {(['week','month','year'] as const).map(g => (
                      <button key={g} onClick={() => setCmpGran(g)} style={{ padding:'5px 14px', borderRadius:7, border:`1px solid ${cmpGran===g?'#00e5a0':'#626d80'}`, background:cmpGran===g?'rgba(0,229,160,0.10)':'transparent', color:cmpGran===g?'#00e5a0':'#888', cursor:'pointer', fontSize:12, fontFamily:'inherit', textTransform:'capitalize' }}>{g}</button>
                    ))}
                  </div>
                </div>
                {!cmpData ? <div style={{ color:'var(--text3,#555)', fontSize:13, padding:'10px 0' }}>Loading comparison…</div> : (
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:10 }}>
                    {([['deposits','Deposits',true],['withdrawals','Withdrawals',true],['net','Net',true],['new_clients','New clients',false],['active_traders','Active traders',false]] as const).map(([key,label,money]) => {
                      const m = cmpData.metrics[key] || { current:0, previous:0, pct:0 };
                      const up = m.pct >= 0;
                      const good = key==='withdrawals' ? !up : up;   // more withdrawals = bad
                      const col = m.pct===0 ? '#888' : good ? '#00e5a0' : '#ff6b6b';
                      const cur = money ? fmt(m.current) : (m.current||0).toLocaleString();
                      const prev = money ? fmt(m.previous) : (m.previous||0).toLocaleString();
                      const maxv = Math.max(Math.abs(m.current), Math.abs(m.previous), 1);
                      return (
                        <div key={key} style={{ background:'var(--bg-main,#20252f)', border:'1px solid var(--border,#3a4250)', borderRadius:9, padding:'11px 12px' }}>
                          <div style={{ fontSize:10.5, color:'var(--text3,#888)', marginBottom:6 }}>{label}</div>
                          <div style={{ fontSize:18, fontWeight:600, color:'#e8edf2' }}>{cur}</div>
                          <div style={{ fontSize:11, color:col, fontWeight:600, marginTop:2 }}>{up?'▲':'▼'} {Math.abs(m.pct)}%</div>
                          {/* mini current-vs-previous bars */}
                          <div style={{ marginTop:8, display:'flex', flexDirection:'column', gap:3 }}>
                            <div style={{ height:5, borderRadius:3, background:'#00aaff', width:`${Math.round(Math.abs(m.current)/maxv*100)}%`, minWidth:2 }} title={`Now: ${cur}`} />
                            <div style={{ height:5, borderRadius:3, background:'#5a6470', width:`${Math.round(Math.abs(m.previous)/maxv*100)}%`, minWidth:2 }} title={`Prev: ${prev}`} />
                          </div>
                          <div style={{ fontSize:9.5, color:'var(--text3,#667)', marginTop:5 }}>prev {prev}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Deposits vs Withdrawals (combined) + Net deposit charts */}
              <div style={{ display:'grid', gridTemplateColumns:'1.4fr 1fr', gap:12, marginBottom:16 }}>
                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                  <LineChart
                    data={trends}
                    label="Deposits vs Withdrawals"
                    series={[
                      { key:'deposits',    color:'#00e5a0', name:'Deposits' },
                      { key:'withdrawals', color:'#ff5d6c', name:'Withdrawals' },
                    ]}
                  />
                </div>
                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                  <LineChart
                    data={(trends||[]).map((d:any)=>({ date:d.date, net:(d.deposits||0)-(d.withdrawals||0) }))}
                    label="Net deposit"
                    series={[{ key:'net', color:'#0a84ff', name:'Net' }]}
                  />
                </div>
              </div>

              {/* Leaderboard + Funnel (managers & admins) */}
              {!isSales && (
                <div style={{ display:'grid', gridTemplateColumns: funnel ? '2fr 1fr' : '1fr', gap:12, marginBottom:16 }}>
                  <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                    <div style={{ fontSize:13, fontWeight:600, marginBottom:12 }}>{isManager?'Team leaderboard':'Top agents'}</div>
                    {leaderboard.length === 0 && <div style={{ fontSize:12, color:'var(--text3,#555)' }}>No data for this period.</div>}
                    {leaderboard.map((a:any, i:number) => {
                      const maxDep = Math.max(1, ...leaderboard.map((x:any)=>x.deposits));
                      return (
                        <div key={a.agent_id} style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
                          <div style={{ width:18, fontSize:11, color:'var(--text3,#555)' }}>{i+1}</div>
                          <div style={{ flex:1, minWidth:0 }}>
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                              <span style={{ fontSize:12, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{a.name}</span>
                              <span style={{ fontSize:12, color:'#00e5a0', fontWeight:500 }}>{fmt(a.deposits)}</span>
                            </div>
                            <div style={{ height:4, background:'var(--bg-input,#373f4d)', borderRadius:2, overflow:'hidden' }}>
                              <div style={{ height:'100%', width:`${(a.deposits/maxDep)*100}%`, background:'linear-gradient(90deg,#00e5a0,#0066ff)' }}></div>
                            </div>
                          </div>
                          <div style={{ width:54, textAlign:'right', fontSize:10, color:'var(--text3,#555)' }}>{a.new_clients} new</div>
                        </div>
                      );
                    })}
                  </div>

                  {funnel && (
                    <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                      <div style={{ fontSize:13, fontWeight:600, marginBottom:12 }}>Conversion funnel</div>
                      {[
                        { label:'Leads', value: funnel.total_leads, color:'#9966ff' },
                        { label:'Contacted', value: funnel.contacted, color:'#0066ff' },
                        { label:'Converted', value: funnel.converted, color:'#00e5a0' },
                      ].map((s:any) => {
                        const pct = funnel.total_leads ? (s.value/funnel.total_leads)*100 : 0;
                        return (
                          <div key={s.label} style={{ marginBottom:10 }}>
                            <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:3 }}>
                              <span>{s.label}</span><span style={{ fontWeight:500 }}>{s.value.toLocaleString()}</span>
                            </div>
                            <div style={{ height:6, background:'var(--bg-input,#373f4d)', borderRadius:3, overflow:'hidden' }}>
                              <div style={{ height:'100%', width:`${pct}%`, background:s.color }}></div>
                            </div>
                          </div>
                        );
                      })}
                      <div style={{ marginTop:12, paddingTop:12, borderTop:'1px solid var(--border,#4f596b)', textAlign:'center' }}>
                        <div style={{ fontSize:24, fontWeight:600, color:'#00e5a0' }}>{funnel.conversion_rate}%</div>
                        <div style={{ fontSize:11, color:'var(--text3,#555)' }}>conversion rate</div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Commission KPIs */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(300px,1fr))', gap:12, marginBottom:16 }}>

                {/* Sales commission */}
                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                    <div>
                      <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:4 }}>{isSales?'My commission':'Sales commission'}</div>
                      <div style={{ fontSize:26, fontWeight:500, color:'#00e5a0' }}>{fmt(kpi.sales_comm)}</div>
                    </div>
                    {isSales && (
                      <div style={{ textAlign:'right' }}>
                        <div style={{ fontSize:11, color:'var(--text3,#555)' }}>Target: {fmt(TARGET)}</div>
                        <div style={{ fontSize:13, fontWeight:500, color: commPct >= 80 ? '#00e5a0' : '#ffaa00', marginTop:2 }}>{commPct}% achieved</div>
                      </div>
                    )}
                  </div>
                  {isSales && (
                    <div>
                      <div style={{ height:6, background:'var(--bg-input,#373f4d)', borderRadius:3, overflow:'hidden', marginBottom:6 }}>
                        <div style={{ height:'100%', borderRadius:3, background: commPct >= 80 ? '#00e5a0' : '#ffaa00', width:`${commPct}%`, transition:'width 0.5s' }}></div>
                      </div>
                      <div style={{ fontSize:11, color:'var(--text3,#555)' }}>
                        {commPct >= 80 ? '✓ Commission eligibility reached' : `Need ${fmt(TARGET - kpi.sales_comm)} more to reach 80% threshold`}
                      </div>
                    </div>
                  )}
                  {!isSales && (
                    <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, marginTop:8 }}>
                      {[{label:'Paid',val:fmt(kpi.sales_comm*0.8),color:'#00e5a0'},{label:'Pending',val:fmt(kpi.sales_comm*0.2),color:'#ffaa00'},{label:'Agents',val:'12',color:'var(--text2,#888)'}].map((s,i)=>(
                        <div key={i} style={{ background:'var(--bg-input,#373f4d)', borderRadius:8, padding:'8px 10px', textAlign:'center' }}>
                          <div style={{ fontSize:13, fontWeight:500, color:s.color }}>{s.val}</div>
                          <div style={{ fontSize:10, color:'var(--text3,#555)', marginTop:2 }}>{s.label}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* IB commission */}
                <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                    <div>
                      <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:4 }}>{isSales?'My IBs commission':'IB commission'}</div>
                      <div style={{ fontSize:26, fontWeight:500, color:'#ff8c00' }}>{fmt(kpi.ib_comm)}</div>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ fontSize:11, color:'var(--text3,#555)' }}>Active IBs</div>
                      <div style={{ fontSize:13, fontWeight:500, color:'var(--text2,#888)', marginTop:2 }}>{isSales?'3':isManager?'8':'24'}</div>
                    </div>
                  </div>
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8 }}>
                    {[
                      {label:'IB-001',val:fmt(kpi.ib_comm*0.45),color:'#ff8c00'},
                      {label:'IB-002',val:fmt(kpi.ib_comm*0.32),color:'#ff8c00'},
                      {label:'Others',val:fmt(kpi.ib_comm*0.23),color:'var(--text3,#555)'},
                    ].map((s,i) => (
                      <div key={i} style={{ background:'var(--bg-input,#373f4d)', borderRadius:8, padding:'8px 10px', textAlign:'center' }}>
                        <div style={{ fontSize:12, fontWeight:500, color:s.color }}>{s.val}</div>
                        <div style={{ fontSize:10, color:'var(--text3,#555)', marginTop:2 }}>{s.label}</div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>

              {/* Sales target progress (sales agent only) */}
              {isSales && (
                <div style={{ background:'var(--bg-card,#2c333e)', border:`1px solid ${commPct>=80?'rgba(0,229,160,0.3)':'#4f596b'}`, borderRadius:10, padding:16, marginBottom:16 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:10 }}>
                    <div style={{ fontSize:13, fontWeight:500 }}>Monthly target progress</div>
                    <div style={{ fontSize:13, color: commPct>=80?'#00e5a0':'#ffaa00', fontWeight:500 }}>{commPct}% → {commPct>=80?'Commission unlocked ✓':'Commission pending'}</div>
                  </div>
                  <div style={{ height:8, background:'var(--bg-input,#373f4d)', borderRadius:4, overflow:'hidden', marginBottom:8 }}>
                    <div style={{ height:'100%', borderRadius:4, background:`linear-gradient(90deg,${commPct>=80?'#00e5a0':'#ffaa00'},${commPct>=100?'#00e5a0':'#0066ff'})`, width:`${commPct}%`, transition:'width 0.5s' }}></div>
                  </div>
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8 }}>
                    {[{pct:25,label:'25%'},{pct:50,label:'50%'},{pct:80,label:'80% → Commission'},{pct:100,label:'100% → Full pay'}].map((t,i) => (
                      <div key={i} style={{ textAlign:'center', padding:'6px 8px', borderRadius:7, background: commPct>=t.pct?'rgba(0,229,160,0.08)':'#373f4d', border:`1px solid ${commPct>=t.pct?'rgba(0,229,160,0.3)':'#626d80'}` }}>
                        <div style={{ fontSize:12, fontWeight:500, color: commPct>=t.pct?'#00e5a0':'#555' }}>{t.label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Quick actions */}
              <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16, marginBottom:16 }}>
                <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:12, textTransform:'uppercase', letterSpacing:1 }}>Quick actions</div>
                <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                  {[
                    { label:'Clients', icon:'👥', color:'#00e5a0', key:'clients' },
                    { label:'Finance', icon:'💰', color:'#0066ff', key:'finance' },
                    { label:'KYC queue', icon:'🛡️', color:'#ffaa00', key:'compliance' },
                    { label:'Reports', icon:'📊', color:'#9966ff', key:'reports' },
                  ].map((a,i) => (
                    <button key={i} onClick={() => setActive(a.key)} style={{ display:'flex', alignItems:'center', gap:6, padding:'8px 14px', borderRadius:8, border:`1px solid ${a.color}33`, background:`${a.color}11`, color:a.color, cursor:'pointer', fontSize:12, fontWeight:500 }}>
                      {a.icon} {a.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* All modules grid */}
              <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:10, padding:16 }}>
                <div style={{ fontSize:12, color:'var(--text3,#555)', marginBottom:12, textTransform:'uppercase', letterSpacing:1 }}>All modules</div>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))', gap:8 }}>
                  {menuItems.slice(1).map((m,i) => (
                    <div key={i} onClick={() => setActive(m.key)} style={{ padding:'10px 12px', borderRadius:8, border:'1px solid var(--border,#4f596b)', cursor:'pointer', display:'flex', alignItems:'center', gap:8 }}
                      onMouseEnter={e => (e.currentTarget.style.borderColor='#00e5a0')}
                      onMouseLeave={e => (e.currentTarget.style.borderColor='#4f596b')}>
                      <span>{m.icon}</span>
                      <span style={{ fontSize:12, color:'var(--text2,#888)' }}>{m.label}</span>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}

          <ChunkErrorBoundary><Suspense fallback={<div style={{padding:40,color:'#8a93a3'}}>Loading…</div>}>
          {active === 'leads'          && <Leads />}
          {active === 'kyc'            && <KycReview />}
          {active === 'marketing'      && <Marketing />}
          {active === 'clients'        && <Clients lang={lang} />}
          {active === 'retention'      && <Retention />}
          {active === 'accounts'       && <TradingAccounts lang={lang} />}
          {active === 'ib'             && <IBPortal lang={lang} />}
          {active === 'ib_admin'       && <IBAdmin user={user} />}
          {active === 'sales_agents'   && <SalesAgents focusAgentId={salesAgentFocus} />}
          {active === 'ib_profiles'    && <CommissionProfiles />}
          {active === 'transactions'   && <Transactions readOnly={!isBackoffice} />}
          {active === 'settings' && (() => {
            const sec = menuSections.find(s => (s as any).hub) as any;
            const ak = allowedKeys;
            const items = ak ? sec.items.filter((i: any) => ak.includes(i.key)) : sec.items;
            return (
              <div style={{ maxWidth: 920 }}>
                <h2 style={{ color: 'var(--text,#e6e9ef)', margin: '4px 0 4px', fontSize: 22 }}>⚙️ Settings</h2>
                <p style={{ color: '#8a93a5', fontSize: 13, marginTop: 0, marginBottom: 20 }}>Choose a section to configure.</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 14 }}>
                  {items.map((it: any) => (
                    <div key={it.key} onClick={() => setActive(it.key)}
                      style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18, cursor: 'pointer', transition: 'border-color .15s, transform .15s' }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = '#00e5a0'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border,#4f596b)'; e.currentTarget.style.transform = 'none'; }}>
                      <div style={{ fontSize: 26, marginBottom: 10 }}>{it.icon}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text,#e6e9ef)', marginBottom: 4 }}>{it.label}</div>
                      <div style={{ fontSize: 12, color: '#8a93a5', lineHeight: 1.4 }}>{it.desc || ''}</div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}
          {String(active).startsWith('settings_') && (
            <div onClick={() => setActive('settings')} style={{ cursor: 'pointer', color: '#00e5a0', fontSize: 13, marginBottom: 12, display: 'inline-flex', alignItems: 'center', gap: 6 }}>‹ Back to Settings</div>
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
          {active === 'tickets'               && <TicketsPage />}
          {active === 'network'        && <NetworkPage />}
          {active === 'reports'        && <ReportsKpi />}
          {active === 'monthly_report' && <MonthlyReport />}
          {active === 'finance'        && <Finance />}
          {active === 'abuse'          && <AbuseDetection />}
          {active === 'copy_admin'     && <CopyTradingAdmin />}
          {active === 'loyalty'        && <Loyalty />}
          {active === 'my_loyalty'     && <MyLoyalty />}
          {active === 'neg_balance'    && <NegBalance />}
          </Suspense></ChunkErrorBoundary>

          {active !== 'dashboard' && active !== 'clients' && active !== 'accounts' && active !== 'ib' && active !== 'ib_admin' && active !== 'sales_agents' && active !== 'ib_profiles' && active !== 'transactions' && active !== 'settings_score' && active !== 'settings_users' && active !== 'network' && active !== 'abuse' && active !== 'reports' && active !== 'monthly_report' && active !== 'finance' && active !== 'leads' && active !== 'loyalty' && active !== 'my_loyalty' && active !== 'neg_balance' && active !== 'settings_payments' && active !== 'settings_payment_cards' && active !== 'settings_account_types' && active !== 'settings_markups' && active !== 'settings_bonuses' && active !== 'tickets' && active !== 'copy_admin' && active !== 'retention' && (
            <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'60vh', flexDirection:'column', gap:16 }}>
              <div style={{ fontSize:48 }}>{menuItems.find(m=>m.key===active)?.icon}</div>
              <div style={{ fontSize:20, fontWeight:500 }}>{menuItems.find(m=>m.key===active)?.label}</div>
              <div style={{ fontSize:13, color:'var(--text3,#555)' }}>This module is being built — coming next!</div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

