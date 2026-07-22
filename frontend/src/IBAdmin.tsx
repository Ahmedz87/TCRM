import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost } from './api';
import NetworkBadge from './NetworkBadge';
import IBTradesTab from './IBTradesTab';
import IBPortal from './IBPortal';
import { useIsTeamLead } from './OwnDataToggle';
import { CT, Pager } from './crmTable';

const PERIODS = [
  { key: 'today',        label: 'Today' },
  { key: 'yesterday',    label: 'Yesterday' },
  { key: 'last_7_days',  label: 'Last 7 days' },
  { key: 'this_week',    label: 'This week' },
  { key: 'last_week',    label: 'Last week' },
  { key: 'last_30_days', label: 'Last 30 days' },
  { key: 'this_month',   label: 'This month' },
  { key: 'last_month',   label: 'Last month' },
  { key: 'this_year',    label: 'This year' },
  { key: 'last_year',    label: 'Last year' },
  { key: 'all_time',     label: 'All time' },
  { key: 'custom',       label: 'Custom' },
];

const levelColor = (l: number) =>l >= 9 ? '#ff4d4d' : l >= 7 ? '#ffaa00' : '#00e5a0';
// IB-5..IB-10 → Bronze..Prime IB (matches backend TIER_NAMES; desk sheet Jul 13 2026)
const TIER_NAMES: Record<number, string>= { 5: 'Bronze', 6: 'Silver', 7: 'Golden', 8: 'Diamond', 9: 'Legendary', 10: 'Prime IB' };
const fmtUSD = (n: number) =>'$' + Math.round(n).toLocaleString('en-GB');
const GOLD_RATE: any = { 5: '$5', 6: '$6', 7: '$7', 8: '$8', 9: '$9', 10: '$10' };  // XAUUSD/major $ per lot BY LEVEL — ladder linearised Jul 9 2026 (was L6=$7/L7=$7.50); keep in sync with commission_rules

// Shorten long official country names for the table (United Arab Emirates -> UAE, etc.)
const COUNTRY_SHORT: Record<string, string> = {
  'United Arab Emirates': 'UAE', 'Syrian Arab Republic': 'Syria', 'Saudi Arabia': 'KSA',
  'United Kingdom': 'UK', 'United States': 'USA', 'United States of America': 'USA',
  'Russian Federation': 'Russia', 'Iran, Islamic Republic of': 'Iran', 'Republic of Korea': 'S. Korea',
  'Democratic Republic of the Congo': 'DR Congo', 'Türkiye': 'Turkey', 'Bosnia and Herzegovina': 'Bosnia',
  'Palestinian Territory': 'Palestine', 'Palestine, State of': 'Palestine',
};
const shortCountry = (c?: string) => (c ? (COUNTRY_SHORT[c] || c) : c);

// IB list column show/hide (mirrors the Clients page). Sub-IBs + Own balance hidden by default.
// NOTE: no 'Clients' column by design (desk rule, Jul 16 2026). A raw client count credited an IB
// for every account that merely sits under their agent code — including customers who first
// deposited under a DIFFERENT IB (one IB showed 138 clients, only 9 of whom he actually
// introduced). It is not an IB performance factor: IBs are PAID on trading (Volume/Commission)
// and PROMOTED on FTD + NDA, all of which are columns here.
const IB_ALL_COLS = ['IB Name', 'Phone', 'Country', 'Sales agent', 'Level', 'IB since',
  'FTD', 'New Clients', 'Accounts', 'Sub-IBs', 'Volume (lots)', 'Commission', 'Payoff', 'Net comm.',
  'Own balance', 'Status', 'Action'];
const IB_COLS_LOCKED = ['IB Name', 'Action'];
// Hidden unless the user ticks them in the ▦ Columns menu. Keeps the default view to what an IB
// is actually judged on (FTD/NDA -> promotion, Volume/Commission -> pay).
const IB_COLS_HIDE_DEFAULT = ['Sub-IBs', 'Own balance', 'Accounts', 'Payoff'];

const fmtNum = (n: number) =>n.toLocaleString('en-GB');
// name-click popup button (mirrors the Loyalty page menu)
const menuBtn: React.CSSProperties = { display: 'block', width: '100%', textAlign: 'left', padding: '9px 10px', background: 'none', border: 'none', color: '#e8e8e8', fontSize: 12.5, cursor: 'pointer', borderRadius: 6 };

const IB_STATUS: Record<string,{label:string;col:string;bg:string}>= {
  elite:          { label: 'Elite',          col: '#b794ff', bg: '#241a3a' },
  active:         { label: 'Active',         col: '#00e5a0', bg: '#0e3a2a' },
  low:            { label: 'Low',            col: '#ffaa00', bg: '#3a2a0e' },
  inactive:       { label: 'Inactive',       col: '#ff8800', bg: '#3a1e0e' },
  super_inactive: { label: 'Super-inactive', col: '#ff4d4d', bg: '#3a0e0e' },
  pending:        { label: '…',              col: '#888',    bg: '#373f4d' },
};
// mirror of backend ib_status_for — trading_clients are loaded lazily, so the status
// pill is recomputed client-side once the lazy /status-breakdown call lands.
function ibStatusFor(tc: number, lowMin: number, activeMin: number, eliteMin: number = 25): string {
  if (tc >= eliteMin)  return 'elite';
  if (tc >= activeMin) return 'active';
  if (tc >= lowMin)    return 'low';
  if (tc >= 1)         return 'inactive';
  return 'super_inactive';
}
// phone shown as a compact badge with last-4 (matches leads/clients pages)
function PhoneBadge({ phone }: { phone: string }) {
  if (!phone) return <span style={{ color: '#626d80' }}>—</span>;
  const last4 = String(phone).replace(/\D/g, '').slice(-4);
  return (
    <span title={phone} style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'2px 8px', borderRadius:6, border:'1px solid #626d80', background:'#373f4d', fontSize:11, color:'#888' }}>
      <span style={{ color:'#ff2d78' }}></span>···{last4}
    </span>
  );
}

// Match the Clients-page table look: dark header bar (#373f4d) with bold light text,
// thin row separators, consistent 12px body font.
const thStyle: React.CSSProperties = {
  padding: '9px 10px', textAlign: 'left', color: '#aeb8c8', fontWeight: 600,
  fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.4px',
  borderBottom: '1px solid #4f596b', whiteSpace: 'nowrap', cursor: 'pointer',
  background: '#333b49', position: 'sticky', top: 0, zIndex: 5,
};
const tdStyle: React.CSSProperties = {
  padding: '8px 10px', borderBottom: '1px solid rgba(79,89,107,0.45)', verticalAlign: 'middle',
  fontSize: 12, color: '#e0e0e0',
};

// ─── IB PROFILE PAGE ────────────────────────────────────────────────────────
function IBProfile({ ibId, onBack, canChangeLevel }: { ibId: number; onBack: () =>void; canChangeLevel: boolean }) {
  const [ib, setIb]         = useState<any>(null);
  const [tab, setTab]       = useState('clients');
  const [ops, setOps]       = useState<any>(null);   // payout operations (lazy)
  const [promos, setPromos] = useState<any>(null);   // level-promotion history (lazy)
  const [refInfo, setRefInfo] = useState<any>(null); // IB referral link (#196)
  const [refCopied, setRefCopied] = useState(false);
  const [period, setPeriod] = useState('this_month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]     = useState('');
  const [fCountry, setFCountry] = useState('');
  const [fCity, setFCity]       = useState('');
  const [loading, setLoading]   = useState(true);
  const [paying, setPaying]     = useState(false);

  const load = useCallback(async () =>{
    setLoading(true);
    try {
      const params = new URLSearchParams({ period });
      if (period === 'custom' && dateFrom && dateTo) {
        params.set('date_from', dateFrom);
        params.set('date_to', dateTo);
      }
      if (fCountry) params.set('country', fCountry);
      if (fCity)    params.set('city', fCity);
      const data = await apiGet(`/ibs/${ibId}?${params}`);
      setIb(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [ibId, period, dateFrom, dateTo, fCountry, fCity]);

  useEffect(() =>{ load(); }, [load]);
  useEffect(() =>{
    if (tab === 'operations' && !ops) {
      apiGet(`/ibs/${ibId}/operations`).then(setOps).catch(() =>setOps({ operations: [], summary: {} }));
    }
    if (tab === 'promotions' && !promos) {
      apiGet(`/ibs/${ibId}/promotions`).then(setPromos).catch(() =>setPromos({ promotions: [] }));
    }
    if (tab === 'promotions' && !refInfo) {
      apiGet(`/ibs/${ibId}/ref`).then(setRefInfo).catch(() => setRefInfo({}));   // #196 IB link
    }
  }, [tab, ops, promos, refInfo, ibId]);

  const handlePay = async () =>{
    if (!ib || !window.confirm(`Pay ${fmtUSD(ib.unpaid_commission)} to ${ib.name}?`)) return;
    setPaying(true);
    try {
      await apiPost('/ibs/pay-commission', { ib_id: ibId });
      await load();
    } catch (e) { alert('Payment failed'); }
    setPaying(false);
  };

  const handlePromote = async () =>{
    if (!ib) return;
    if (!canChangeLevel) { alert('Only Zainab can change an IB level.'); return; }
    const newLevel = window.prompt(`Current level: ${ib.ib_level}\nEnter new level (5-10):`, String(ib.ib_level));
    if (!newLevel) return;
    try {
      await apiPost('/ibs/promote', { ib_id: ibId, new_level: parseInt(newLevel) });
      await load();
    } catch (e) { alert('Promotion failed'); }
  };

  if (loading) return <div style={{ color: '#555', padding: 40, textAlign: 'center' }}>Loading...</div>;
  if (!ib) return <div style={{ color: '#555', padding: 40, textAlign: 'center' }}>IB not found</div>;

  // Ticket 190 #3 — client rows are one-per-ACCOUNT (backend), so counting rows overstates the
  // client total. Count UNIQUE people (by customer_no) for the "Clients" figure; the raw row count
  // is the number of trading ACCOUNTS, shown separately so the two aren't confused.
  const _clientRows = ib.clients || [];
  const uniqClients = new Set(_clientRows.map((c: any) => c.customer_no || c.account_number || c.login)).size;

  const tabs = ['clients', 'leads', 'trades', 'operations', 'promotions'];
  const tabLabels: any = {
    clients: `Clients (${uniqClients || ib.total_clients || 0})`,
    leads: `Leads (${(ib.clients || []).filter((c: any) => !(c.total_dep > 0)).length})`,
    trades: 'Trades',
    operations: `💸 Payouts${ib.total_payoff ? ` (${fmtUSD(ib.total_payoff)})` : ''}`,
    promotions: `🎖 Level history${promos?.promotions?.length ? ` (${promos.promotions.length})` : ''}`,
  };

  return (
    <div style={{ height:'100%', overflowY:'auto', padding:'0 4px 24px 0' }}>
      <style>{`.ib-cli-row:hover { background: rgba(0,170,255,0.06) !important; }`}</style>
      {/* ── IDENTITY BAND — one compact card: name row + meta line + actions ── */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: '12px 16px', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={onBack} title="Back to IB list"
            style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(0,229,160,0.1)', border: '1px solid #00e5a0', color: '#00e5a0', cursor: 'pointer', fontSize: 15, fontWeight: 700, flexShrink: 0, lineHeight: 1 }}>←</button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 16.5, fontWeight: 700, color: '#ffffff' }}>{ib.name}</span>
              {ib.ext_ib_id != null && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#1a2440', color: '#7fb0ff', fontWeight: 700 }}>IB {ib.ext_ib_id}</span>}
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${levelColor(ib.ib_level)}22`, color: levelColor(ib.ib_level), fontWeight: 600, border: `1px solid ${levelColor(ib.ib_level)}55` }}>{ib.tier || ''} · IB-{ib.ib_level} · {GOLD_RATE[ib.ib_level] || '$'+ib.ib_level}/lot gold</span>
              {ib.is_sub_ib && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#3a2a0e', color: '#ffaa00', fontWeight: 600 }}>Sub-IB</span>}
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0e3a2a', color: '#00e5a0', fontWeight: 600 }}>● Active</span>
            </div>
            {/* everything about the IB on ONE meta line */}
            <div style={{ marginTop: 5, fontSize: 11.5, color: '#aab4c4', display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'wrap', whiteSpace: 'nowrap' }}>
              {(() =>{
                const accts = (ib.accounts && ib.accounts.length ? ib.accounts : [{ account: ib.agent_id, platform: 'MT5' }]);
                const sep = <span style={{ color: '#4a5261', margin: '0 8px' }}>|</span>;
                const parts: any[] = [
                  <span key="em" style={{ color: '#d5dbe5' }}>{ib.email || '—'}</span>,
                  <span key="ph">{ib.phone || '—'}</span>,
                  <span key="loc">{[ib.country, ib.city].filter(Boolean).join(', ') || '—'}</span>,
                  ...accts.map((a: any, j: number) =>(
                    <span key={'a'+j}><span style={{ fontSize: 9, color: '#8a93a3', border: '1px solid #4a5261', borderRadius: 4, padding: '0 4px', marginRight: 4 }}>{a.platform || 'MT'}</span>
                    <span style={{ fontFamily: 'ui-monospace, monospace', color: '#7fd1ff' }}>#{a.account}</span></span>
                  )),
                  <span key="since">IB since <b style={{ color: '#d5dbe5' }}>{ib.ib_creation_date ? String(ib.ib_creation_date).slice(0, 10) : '—'}</b></span>,
                  ...(ib.master_ib ? [<span key="master">Master <b style={{ color: '#7fb0ff' }}>{ib.master_ib.name}</b></span>] : []),
                ];
                return parts.map((p, j) =>(<span key={j} style={{ display: 'inline-flex', alignItems: 'center' }}>{j > 0 && sep}{p}</span>));
              })()}
            </div>
          </div>
          {/* actions — one horizontal row, small */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
            <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
              style={{ padding: '7px 14px', background: ib.unpaid_commission >0 ? '#00e5a0' : '#373f4d', color: ib.unpaid_commission >0 ? '#04231a' : '#666', border: 'none', borderRadius: 8, fontSize: 12, cursor: ib.unpaid_commission >0 ? 'pointer' : 'default', fontWeight: 700, whiteSpace: 'nowrap' }}>
              {paying ? 'Paying…' : `Pay ${fmtUSD(ib.unpaid_commission)}`}
            </button>
            {canChangeLevel && (
              <button onClick={handlePromote} title="Promote level"
                style={{ padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#c4ccd8', fontSize: 12, cursor: 'pointer', fontWeight: 600, whiteSpace: 'nowrap' }}>⭑ Promote</button>
            )}
            <button title="Suspend this IB"
              style={{ padding: '7px 12px', background: 'transparent', border: '1px solid #ff4d4d', borderRadius: 8, color: '#ff4d4d', fontSize: 12, cursor: 'pointer', fontWeight: 600 }}>Suspend</button>
          </div>
        </div>
      </div>

      {/* ── STATS BAND — period chips + ONE slim stat strip ── */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: '8px 14px 10px', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          {PERIODS.map(p =>(
            <button key={p.key} onClick={() =>setPeriod(p.key)}
              style={{ padding: '3px 10px', borderRadius: 99, fontSize: 10.5, cursor: 'pointer', border: 'none',
                background: period === p.key ? '#00e5a0' : 'transparent', color: period === p.key ? '#04231a' : '#aab4c4',
                fontWeight: period === p.key ? 700 : 500, fontFamily: 'inherit' }}>
              {p.label}
            </button>
          ))}
          {period === 'custom' && (
            <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', marginLeft: 4 }}>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e =>setDateFrom(e.target.value)}
                style={{ padding: '2px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 10.5 }} />
              <span style={{ color: '#666' }}>—</span>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e =>setDateTo(e.target.value)}
                style={{ padding: '2px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 10.5 }} />
            </span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 10, color: '#7c8798' }}>{ib.period?.from} — {ib.period?.to}</span>
        </div>
        {/* one-row stat strip: thin dividers, no boxes */}
        <div style={{ display: 'flex', flexWrap: 'wrap', marginTop: 8, borderTop: '1px solid #3a4250' }}>
          {(() =>{
            // Commission / Payoff / Net follow the SELECTED PERIOD (desk request Jul 2026);
            // small amounts show cents so live commission doesn't round to a misleading $0
            const money = (n: number) => (n !== 0 && Math.abs(n) < 100) ? '$' + n.toFixed(2) : fmtUSD(n);
            const pComm = ib.period?.commission || 0;
            const pPay = ib.period?.payoff || 0;
            const pNet = pComm - pPay;
            return [
            { val: fmtNum(ib.total_clients || 0),                        lbl: 'Clients',      col: '#e8ecf2' },
            { val: fmtNum(ib.period?.new_clients || 0),                  lbl: 'New',          col: '#e8ecf2' },
            { val: fmtNum(ib.period?.active_clients || 0),               lbl: 'Active',       col: '#00e5a0' },
            { val: fmtNum(ib.period?.ftd ?? ib.funnel?.ftd ?? 0),        lbl: 'FTD (period)', col: '#00aaff' },
            { val: fmtNum(ib.period?.nda || 0) + (ib.period?.ftd ? ` · ${Math.round(100*(ib.period.nda||0)/ib.period.ftd)}%` : ''), lbl: 'New Clients', col: '#ffd166' },
            { val: money(ib.period?.deposits || 0),                      lbl: 'Deposits',     col: '#00e5a0' },
            { val: money(ib.period?.withdrawals || 0),                   lbl: 'Withdrawals',  col: '#ff8a8a' },
            { val: money(pComm),                                         lbl: 'Commission',   col: '#ffaa00' },
            { val: money(pPay),                                          lbl: 'Payoff',       col: '#ff8a8a' },
            { val: money(pNet),                                          lbl: 'Net',          col: pNet < 0 ? '#ff4d4d' : '#00e5a0' },
          ]; })().map((k, i) =>(
            <div key={i} style={{ flex: '1 1 0', minWidth: 86, padding: '8px 12px 2px', borderLeft: i ? '1px solid #3a4250' : 'none' }}>
              <div style={{ fontSize: 9, color: '#8a95a7', textTransform: 'uppercase', letterSpacing: '.5px', fontWeight: 600, whiteSpace: 'nowrap' }}>{k.lbl}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: k.col, marginTop: 1, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{k.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: '#373f4d', borderRadius: 10, padding: 4, marginBottom: 12 }}>
        {tabs.map(t =>(
          <button key={t} onClick={() =>setTab(t)}
            style={{ padding: '7px 14px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: tab === t ? '1px solid #7a8699' : 'none', background: tab === t ? '#2c333e' : 'transparent', color: tab === t ? '#ffffff' : '#c4ccd8', fontWeight: tab === t ? 600 : 400, fontFamily: 'inherit' }}>
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {/* TRADES TAB */}
      {tab === 'trades' && (
        <IBTradesTab endpoint={`/ibs/${ib.id}/trades`} period={period} dateFrom={dateFrom} dateTo={dateTo} />
      )}

      {/* PAYOUTS / OPERATIONS TAB */}
      {tab === 'operations' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 10, padding: '12px 14px', borderBottom: '1px solid #4f596b', flexWrap: 'wrap' }}>
            {[['Total paid out', ops?.summary?.paid_out, '#ff4d4d'], ['Withdrawn', ops?.summary?.withdrawn, '#ff8800'], ['Transferred', ops?.summary?.transferred, '#00aaff'], ['Net commission', (ib.total_commission || 0) - (ib.total_payoff || 0), '#00e5a0']].map(([l, v, c]: any, i) =>(
              <div key={i} style={{ background: '#373f4d', borderRadius: 8, padding: '8px 14px', minWidth: 120 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: c }}>{fmtUSD(v || 0)}</div>
                <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>{l}</div>
              </div>
            ))}
            <div style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 11, color: '#888' }}>{(ops?.operations || []).length} operations · IB payouts (May 2023 →)</div>
          </div>
          <div style={{ overflowX: 'auto', maxHeight: 520, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead><tr>{['Date', 'Type', 'Amount', 'Method', 'To account', 'Status', 'Note'].map(hh =><th key={hh} style={{ ...thStyle }}>{hh}</th>)}</tr></thead>
              <tbody>
                {!ops ? <tr><td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 30 }}>Loading…</td></tr>
                  : (ops.operations || []).map((o: any, i: number) =>{
                    const st = o.status === 'Approved' ? '#00e5a0' : o.status === 'Declined' ? '#ff4d4d' : '#ffaa00';
                    const tyC = o.request_type?.includes('Withdrawal') ? '#ff8800' : '#00aaff';
                    return (
                      <tr key={i}>
                        <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.op_date ? String(o.op_date).slice(0, 10) : '—'}</td>
                        <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${tyC}22`, color: tyC }}>{o.request_type?.replace(' Wallet', '').replace('Wallet ', '')}</span></td>
                        <td style={{ ...tdStyle, fontWeight: 600 }}>{fmtUSD(o.amount)}</td>
                        <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.payment_type || '—'}</td>
                        <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11, fontFamily: 'monospace' }}>{o.to_account || '—'}</td>
                        <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${st}22`, color: st }}>{o.status}</span></td>
                        <td style={{ ...tdStyle, color: '#666', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={o.note}>{o.note || ''}</td>
                      </tr>
                    );
                  })}
                {ops && (ops.operations || []).length === 0 && <tr><td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 30 }}>No payout operations</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PROMOTIONS / LEVEL HISTORY TAB */}
      {tab === 'promotions' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '12px 14px', borderBottom: '1px solid #4f596b', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e0e0e0' }}>🎖 Level history</div>
            <div style={{ fontSize: 11, color: '#888' }}>current level <b style={{ color: '#ffd166' }}>IB-{ib.ib_level ?? '—'}</b></div>
            {/* IB referral link (#196) — open + copy */}
            {refInfo?.link && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <a href={refInfo.link} target="_blank" rel="noopener noreferrer"
                   style={{ fontSize: 11.5, fontWeight: 700, padding: '4px 10px', borderRadius: 7, background: 'rgba(56,189,248,0.12)', border: '1px solid rgba(56,189,248,0.4)', color: '#38bdf8', textDecoration: 'none' }}
                   title={refInfo.link}>🔗 IB link</a>
                <button onClick={() => { navigator.clipboard?.writeText(refInfo.link); setRefCopied(true); setTimeout(() => setRefCopied(false), 1500); }}
                   style={{ fontSize: 11, padding: '4px 9px', borderRadius: 7, background: '#373f4d', border: '1px solid #4f596b', color: refCopied ? '#00e5a0' : '#cdd4de', cursor: 'pointer' }}>
                  {refCopied ? '✓ Copied' : '⧉ Copy'}
                </button>
              </div>
            )}
            <div style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>promotions ↑ & demotions ↓ detected from the broker Commission Report (per-lot rate changes)</div>
          </div>
          <div style={{ padding: '16px 18px' }}>
            {!promos ? <div style={{ color: '#555', padding: 20 }}>Loading…</div>
              : (promos.promotions || []).length === 0
                ? <div style={{ color: '#666', padding: 20, fontSize: 13 }}>No level changes detected in the report period. This IB's level has been stable.</div>
                : (
                  <div style={{ position: 'relative', paddingLeft: 22 }}>
                    <div style={{ position: 'absolute', left: 6, top: 4, bottom: 4, width: 2, background: '#4f596b' }} />
                    {(promos.promotions || []).map((p: any, i: number) => {
                      const demo = p.direction === 'demotion';
                      const col = demo ? '#ff4d4d' : '#00e5a0';
                      const delta = p.to_level - p.from_level;
                      return (
                      <div key={i} style={{ position: 'relative', marginBottom: 18 }}>
                        <div style={{ position: 'absolute', left: -22, top: 2, width: 12, height: 12, borderRadius: 99, background: col, border: '2px solid #2c333e' }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 12, color: '#9aa3b3', fontFamily: 'monospace' }}>{p.date}</span>
                          <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 99, background: '#8892a022', color: '#9aa3b3' }}>IB-{p.from_level}</span>
                          <span style={{ color: col, fontWeight: 700 }}>{demo ? '↓' : '→'}</span>
                          <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 99, background: `${col}22`, color: col, fontWeight: 600 }}>IB-{p.to_level}</span>
                          <span style={{ fontSize: 11, color: col }}>{demo ? `demoted ${delta}` : `promoted +${delta}`}</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{p.note}</div>
                      </div>
                      );
                    })}
                  </div>
                )}
          </div>
        </div>
      )}

      {/* CLIENTS TAB */}
      {tab === 'clients' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display:'flex', gap:8, padding:'10px 12px', borderBottom:'1px solid #4f596b', alignItems:'center' }}>
            <span style={{ fontSize:11, color:'#9aa3b3' }}>Filter:</span>
            <input value={fCountry} onChange={e=>setFCountry(e.target.value)} placeholder="Country..."
              style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11, width:140, outline:'none' }} />
            <input value={fCity} onChange={e=>setFCity(e.target.value)} placeholder="City..."
              style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11, width:140, outline:'none' }} />
            {(fCountry||fCity) && <span onClick={()=>{setFCountry('');setFCity('');}} style={{ fontSize:11, color:'#ff4d4d', cursor:'pointer' }}>Clear ✕</span>}
            <span style={{ fontSize:11, color:'#9aa3b3', marginLeft:'auto' }}>{uniqClients} clients · {(ib.clients||[]).length} accounts</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1050 }}>
              <thead>
                <tr>
                  {([['Client','left'],['Account','left'],['Address','left'],['Sales agent','left'],['Network','center'],
                     ['Volume','right'],['Commission','right'],['Net deposit','right'],['Abuse','left'],['Start trade','left'],['Last activity','left']] as [string,string][]).map(([h,al]) =>(
                    <th key={h} style={{ ...thStyle, textAlign: al as any }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.clients || []).map((c: any, i: number) =>{
                  const ns = c.network_score || 0;
                  const nsCol = ns >= 7 ? '#ff4d4d' : ns >= 4 ? '#ffaa00' : '#8a93a3';
                  const netDep = (c.total_dep || 0) - (c.total_with || 0);
                  const num: React.CSSProperties = { ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
                  const goClient = (e: any) => { e.stopPropagation();
                    window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'clients', search: c.name || String(c.login), openProfile: c.login } })); };
                  const goAccount = (e: any) => { e.stopPropagation();
                    window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'accounts', login: c.account_number || c.login } })); };
                  return (
                  <tr key={i} className="ib-cli-row" style={{ background: i % 2 ? 'rgba(255,255,255,0.015)' : 'transparent' }}>
                    <td style={tdStyle}>
                      <div onClick={goClient} className="hover-underline" title="Open client page"
                        style={{ fontWeight: 600, color: '#4ea1ff', cursor: 'pointer' }}>{c.name}</div>
                      <div style={{ fontSize: 10, color: '#7c8798' }}>{c.customer_no || `#${c.login}`}</div>
                    </td>
                    <td style={tdStyle}>
                      <span onClick={goAccount} className="hover-underline" title="Open trading account"
                        style={{ fontFamily: 'ui-monospace, monospace', color: '#7fd1ff', fontSize: 12, cursor: 'pointer' }}>{c.account_number || c.login || '—'}</span>
                      {c.accounts > 1 && <span title={`${c.accounts} accounts merged (same phone & platform)`}
                        style={{ marginLeft: 5, fontSize: 9, padding: '1px 6px', borderRadius: 99, background: '#1a2440', color: '#7fb0ff', fontWeight: 700 }}>×{c.accounts}</span>}
                    </td>
                    <td style={{ ...tdStyle, fontSize: 11.5, whiteSpace: 'nowrap' }}>
                      <span onClick={(e) => { e.stopPropagation(); if (c.country) { setFCountry(c.country); } }}
                        className={c.country ? 'hover-underline' : ''} title="Filter by country"
                        style={{ color: '#c4ccd8', cursor: c.country ? 'pointer' : 'default' }}>{c.country || '—'}</span>
                      {c.city ? <span onClick={(e) => { e.stopPropagation(); setFCity(c.city); }}
                        className="hover-underline" title="Filter by city"
                        style={{ color: '#7c8798', cursor: 'pointer' }}> · {c.city}</span> : ''}
                    </td>
                    <td style={{ ...tdStyle, fontSize: 11.5, color: c.sales_agent ? '#c4ccd8' : '#5a6472', whiteSpace: 'nowrap' }}>{c.sales_agent || '—'}</td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <NetworkBadge score={ns} login={c.login} />
                    </td>
                    <td style={{ ...num, color: (c.volume || 0) > 0 ? '#c4ccd8' : '#5a6472' }}>
                      {(c.volume || 0) > 0 ? ((c.volume < 10 ? c.volume.toFixed(2) : fmtNum(Math.round(c.volume)))) : '—'}{(c.volume || 0) > 0 && <span style={{ color: '#7c8798', fontSize: 10 }}> lots</span>}
                    </td>
                    <td style={{ ...num, color: c.commission > 0 ? '#00e5a0' : '#5a6472', fontWeight: c.commission > 0 ? 600 : 400 }}>
                      {c.commission > 0 ? (c.commission < 100 ? '$' + c.commission.toFixed(2) : fmtUSD(c.commission)) : '—'}
                    </td>
                    <td style={{ ...num, color: netDep > 0 ? '#00e5a0' : netDep < 0 ? '#ff8a8a' : '#5a6472', fontWeight: netDep !== 0 ? 600 : 400 }}
                      title={`Deposits ${fmtUSD(c.total_dep || 0)} − Withdrawals ${fmtUSD(c.total_with || 0)}`}>
                      {netDep !== 0 ? fmtUSD(netDep) : '—'}
                    </td>
                    <td style={tdStyle}>{c.abuse_flag ? (() =>{ const col:any={critical:'#ff4d4d',high:'#ff8800',medium:'#ffaa00'}; const cc=col[c.abuse_severity]||'#ff4d4d'; return <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: `${cc}22`, color: cc, border:`1px solid ${cc}66`, fontWeight:700, whiteSpace:'nowrap' }}>{c.abuse_hot?'🔥 ':''}{c.abuse_flag}</span>; })() : <span style={{ color: '#4a5261' }}>—</span>}</td>
                    <td style={{ ...tdStyle, color: '#8a93a3', fontSize: 11, whiteSpace: 'nowrap' }}>{c.first_trade || '—'}</td>
                    <td style={{ ...tdStyle, color: '#8a93a3', fontSize: 11, whiteSpace: 'nowrap' }}>{c.last_activity || '—'}</td>
                  </tr>
                  );
                })}
                {(ib.clients || []).length === 0 && (
                  <tr><td colSpan={11} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No clients match</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* LEADS TAB */}
      {tab === 'leads' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
              <thead>
                <tr>
                  {['Name', 'Email', 'Phone', 'Country', 'Registered', 'KYC', 'Status'].map(h =>(
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* LEADS = registered but NOT deposited. Anyone who deposited is a client and
                    lives in the Clients tab only (desk request Jul 2026). */}
                {(ib.clients || []).filter((c: any) => !(c.total_dep > 0)).map((c: any, i: number) =>(
                  <tr key={i}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{c.name}</div></td>
                    {/* Ticket 190 #4 — IB leads: show full email + phone (copyable) so the team can reach them */}
                    <td style={{ ...tdStyle, color: '#9aa3b3', userSelect: 'text' }}>{c.email ? <a href={`mailto:${c.email}`} style={{ color: '#4d9fff', textDecoration: 'none' }}>{c.email}</a> : '—'}</td>
                    <td style={{ ...tdStyle, color: '#d5dbe5', fontFamily: 'monospace', userSelect: 'text', whiteSpace: 'nowrap' }}>{c.phone ? <a href={`tel:${c.phone}`} style={{ color: '#d5dbe5', textDecoration: 'none' }}>{c.phone}</a> : '—'}</td>
                    <td style={{ ...tdStyle, color: '#9aa3b3' }}>{c.country}</td>
                    <td style={{ ...tdStyle, color: '#9aa3b3' }}>{c.reg_date}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0e3a2a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00e5a0' : '#ffaa00' }}>{c.kyc}</span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0a1a3a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00aaff' : '#ffaa00' }}>
                        {c.kyc === 'verified' ? 'Verified lead' : 'Lead'}
                      </span>
                    </td>
                  </tr>
                ))}
                {(ib.clients || []).filter((c: any) => !(c.total_dep > 0)).length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No leads yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* COMMISSION TAB */}
      {tab === 'commission' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>Commission summary</div>
              {(() =>{
                const rows: any[] = [
                  { label: 'Total earned (all time)', val: fmtUSD(ib.total_commission), col: '#00e5a0' },
                ];
                if ((ib.commission_excel || 0) >0)
                  rows.push({ label: '· Plugit report (2023–Jul 2026)', val: fmtUSD(ib.commission_excel), col: '#7fd1ff', sm: true });
                if ((ib.commission_computed || 0) >0)
                  rows.push({ label: '· computed (pre-2023)', val: fmtUSD(ib.commission_computed), col: '#7fd1ff', sm: true });
                rows.push(
                  { label: 'Total payoff (withdrawn)', val: fmtUSD(ib.total_payoff || 0), col: '#ff4d4d' },
                  { label: 'Net (commission − payoff)', val: fmtUSD((ib.total_commission||0)-(ib.total_payoff||0)), col: ((ib.total_commission||0)-(ib.total_payoff||0)) < 0 ? '#ff4d4d' : '#00e5a0' },
                  { label: 'Unpaid balance', val: fmtUSD(ib.unpaid_commission), col: '#ffaa00' },
                );
                return rows.map((r, i) =>(
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: r.sm ? '3px 0 3px 10px' : '7px 0', borderBottom: (!r.sm && i < rows.length - 1) ? '1px solid #373f4d' : 'none' }}>
                    <span style={{ color: r.sm ? '#5a6472' : '#666', fontSize: r.sm ? 11 : 13 }}>{r.label}</span>
                    <span style={{ color: r.col, fontWeight: 600, fontSize: r.sm ? 11 : 13 }}>{r.val}</span>
                  </div>
                ));
              })()}
              <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
                style={{ width: '100%', marginTop: 12, padding: 8, background: ib.unpaid_commission >0 ? '#00e5a0' : '#373f4d', color: ib.unpaid_commission >0 ? '#000' : '#555', border: 'none', borderRadius: 8, fontSize: 13, cursor: ib.unpaid_commission >0 ? 'pointer' : 'default', fontWeight: 500 }}>
                {paying ? 'Processing...' : `Pay ${fmtUSD(ib.unpaid_commission)}`}
              </button>
            </div>
            <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>Period volume</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#00aaff' }}>{fmtNum(Math.round(ib.period?.volume || 0))}</div>
              <div style={{ fontSize: 11, color: '#555', marginTop: 4 }}>lots traded by clients</div>
              <div style={{ marginTop: 16, fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 8 }}>Active clients this period</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#00e5a0' }}>{ib.period?.active_clients || 0}</div>
            </div>
          </div>

          {/* Commission detail table */}
          <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
                <thead>
                  <tr>
                    {['Date', 'Client', 'Symbol', 'Volume', 'Pts/lot', 'Native', 'FX rate', 'USD', 'Type', 'Status'].map(h =>(
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(ib.commissions || []).map((c: any, i: number) =>(
                    <tr key={i}>
                      <td style={{ ...tdStyle, color: '#666' }}>{c.trade_date}</td>
                      <td style={tdStyle}><div style={{ fontWeight: 500 }}>{c.client_name}</div><div style={{ fontSize: 10, color: '#555' }}>#{c.client_login}</div></td>
                      <td style={{ ...tdStyle, color: '#00aaff' }}>{c.symbol}</td>
                      <td style={tdStyle}>{c.volume?.toFixed(2)}</td>
                      <td style={{ ...tdStyle, color: '#ffaa00' }}>{c.pts_per_lot}</td>
                      <td style={tdStyle}>{c.commission_native?.toFixed(2)} {c.quote_currency}</td>
                      <td style={{ ...tdStyle, color: '#555' }}>{c.fx_rate?.toFixed(4)}</td>
                      <td style={{ ...tdStyle, color: '#00e5a0', fontWeight: 600 }}>${c.commission_usd?.toFixed(2)}</td>
                      <td style={tdStyle}>
                        <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.commission_type === 'direct' ? '#0e3a2a' : '#0a1a3a', color: c.commission_type === 'direct' ? '#00e5a0' : '#00aaff' }}>
                          {c.commission_type === 'direct' ? 'Direct' : 'Override 10%'}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.status === 'paid' ? '#373f4d' : '#3a2a0e', color: c.status === 'paid' ? '#555' : '#ffaa00' }}>
                          {c.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {(ib.commissions || []).length === 0 && (
                    <tr><td colSpan={10} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No commission records for this period</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* SUB-IBs TAB */}
      {tab === 'sub_ibs' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
              <thead>
                <tr>
                  {['IB Name', 'Level', 'Clients', 'Volume (lots)', 'Their commission', 'Your override (10%)', 'Unpaid', 'Status'].map(h =>(
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.sub_ibs || []).map((s: any, i: number) =>(
                  <tr key={i}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{s.name}</div><div style={{ fontSize: 10, color: '#00aaff' }}>{s.ib_code}</div></td>
                    <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: `${levelColor(s.ib_level)}22`, color: levelColor(s.ib_level) }}>L{s.ib_level}</span></td>
                    <td style={tdStyle}>{s.total_clients}</td>
                    <td style={{ ...tdStyle, color: '#00aaff' }}>{fmtNum(Math.round(s.total_volume))}</td>
                    <td style={{ ...tdStyle, color: '#00e5a0' }}>{fmtUSD(s.total_commission)}</td>
                    <td style={{ ...tdStyle, color: '#00aaff', fontWeight: 600 }}>{fmtUSD(s.total_commission * 0.1)}</td>
                    <td style={{ ...tdStyle, color: s.unpaid_commission >0 ? '#ffaa00' : '#555' }}>{s.unpaid_commission >0 ? fmtUSD(s.unpaid_commission) : '—'}</td>
                    <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: s.status === 'active' ? '#0e3a2a' : '#373f4d', color: s.status === 'active' ? '#00e5a0' : '#555' }}>{s.status}</span></td>
                  </tr>
                ))}
                {(ib.sub_ibs || []).length === 0 && (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No sub-IBs yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* REFERRAL LINKS TAB */}
      {tab === 'referral_links' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px' }}>Referral links & campaigns</div>
            <button style={{ padding: '5px 12px', background: '#00e5a0', color: '#000', border: 'none', borderRadius: 8, fontSize: 11, cursor: 'pointer', fontWeight: 500 }}>+ New link</button>
          </div>
          {(ib.referral_links || []).length === 0 ? (
            <div style={{ textAlign: 'center', color: '#555', padding: 40 }}>No referral links yet</div>
          ) : (ib.referral_links || []).map((l: any, i: number) =>(
            <div key={i} style={{ borderBottom: '1px solid #373f4d', padding: '12px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 500 }}>{l.name}</span>
                <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: l.status === 'active' ? '#0e3a2a' : '#3a2a0e', color: l.status === 'active' ? '#00e5a0' : '#ffaa00' }}>{l.status}</span>
                <div style={{ flex: 1 }} />
                <span style={{ color: '#555', fontSize: 11 }}>Clicks: <span style={{ color: '#00aaff' }}>{l.clicks?.toLocaleString('en-GB')}</span></span>
              </div>
              <div style={{ color: '#00aaff', fontFamily: 'monospace', fontSize: 11, marginTop: 4 }}>{l.url}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── IB LIST PAGE ────────────────────────────────────────────────────────────
// "Plugit-only" tab — IBs present in the Plugit export but NOT in the CRM.
function PlugitOnly() {
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() =>{
    setLoading(true);
    apiGet(`/ibs/plugit-only?page=${page}&page_size=50&search=${encodeURIComponent(search)}`)
      .then((d: any) =>{ setRows(d.rows || []); setTotal(d.total || 0); })
      .catch(() =>setRows([])).finally(() =>setLoading(false));
  }, [page, search]);
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>🔌 From Plugit only <span style={{ fontSize: 12, color: '#888', fontWeight: 400 }}>· in the Plugit export but not in the CRM ({total.toLocaleString('en-GB')})</span></div>
        <input value={search} onChange={e =>{ setSearch(e.target.value); setPage(1); }} placeholder="Search name, email, code…"
          style={{ marginLeft: 'auto', padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 240, outline: 'none' }} />
      </div>
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', maxHeight: '70vh' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead><tr>{['IB Code', 'Name', 'Email', 'Markup (pips)', 'Level'].map(h =><th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={5} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>Loading…</td></tr>
                : rows.map((r, i) =>(
                  <tr key={i} className="ibp-row">
                    <td style={{ ...tdStyle, color: '#00aaff', fontFamily: 'monospace' }}>{r.code}</td>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{r.name || '—'}</td>
                    <td style={{ ...tdStyle, color: '#9aa3b3' }}>{r.email || '—'}</td>
                    <td style={{ ...tdStyle, color: '#e0e0e0' }}>{r.pips != null ? `${r.pips} pips` : '—'}</td>
                    <td style={tdStyle}>{r.level ? <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 7, background: `${levelColor(r.level)}18`, color: levelColor(r.level), border: `1px solid ${levelColor(r.level)}66` }}>IB-{r.level} · {r.tier}</span>: '—'}</td>
                  </tr>
                ))}
              {!loading && rows.length === 0 && <tr><td colSpan={5} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>None</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: '10px 12px', borderTop: '1px solid #4f596b', alignItems: 'center', fontSize: 12, color: '#888' }}>
          <button disabled={page <= 1} onClick={() =>setPage(p =>p - 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page <= 1 ? '#555' : '#888', cursor: page <= 1 ? 'default' : 'pointer' }}>← Prev</button>
          <span>Page {page} · {total.toLocaleString('en-GB')} total</span>
          <button disabled={rows.length < 50} onClick={() =>setPage(p =>p + 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: rows.length < 50 ? '#555' : '#888', cursor: rows.length < 50 ? 'default' : 'pointer' }}>Next →</button>
        </div>
      </div>
    </div>
  );
}

// Withdrawals page — ALL IB payouts (withdrawals + int/ext transfers). IB rows are colour-tagged.
function IBWithdrawals({ onOpenIB }: { onOpenIB: (id: number) =>void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [totals, setTotals] = useState<any>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [fType, setFType] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  useEffect(() =>{
    setLoading(true);
    const p = new URLSearchParams({ page: String(page), page_size: '50' });
    if (fType) p.set('request_type', fType);
    if (fStatus) p.set('status', fStatus);
    if (search) p.set('search', search);
    apiGet(`/ibs/operations?${p}`).then((d: any) =>{ setRows(d.rows || []); setTotals(d.totals || {}); setTotal(d.total || 0); })
      .catch(() =>setRows([])).finally(() =>setLoading(false));
  }, [page, fType, fStatus, search, refresh]);
  // Desk approves/declines a pending IB payout. apiPost resolves even on HTTP errors, so we
  // check the response body for `ok`/`detail` rather than relying on a rejection.
  const act = async (o: any, action: 'approve' | 'decline') =>{
    if (busyId) return;
    if (action === 'approve' && !window.confirm(`Approve ${o.request_type?.replace(' Wallet','')} of ${fmtUSD(o.amount)} for ${o.name || 'this IB'}?\nThe amount will be deducted from their commission wallet.`)) return;
    let reason: string | null = null;
    if (action === 'decline') { reason = window.prompt('Reason for declining (optional):', '') ; }
    setBusyId(o.id);
    try {
      const r = await apiPost(`/ibs/operations/${o.id}/action`, { action, reason: reason || undefined });
      if (!r || r.ok !== true) { alert(r?.detail || 'Could not process the request'); }
      setRefresh(x =>x + 1);
    } catch { alert('Network error — please retry'); }
    finally { setBusyId(null); }
  };
  const chip = (k: string, l: string, cur: string, set: (v: string) =>void) =>(
    <button onClick={() =>{ set(cur === k ? '' : k); setPage(1); }}
      style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${cur === k ? '#00e5a0' : '#626d80'}`, background: cur === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: cur === k ? '#00e5a0' : '#888', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap' }}>{l}</button>
  );
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>💸 IB Withdrawals & Transfers</div>
        <span style={{ fontSize: 11, color: '#ff8800', border: '1px solid #ff880066', borderRadius: 6, padding: '2px 8px' }}>All rows are IB payouts</span>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#9aa3b3' }}>Approved out: <b style={{ color: '#ff4d4d' }}>{fmtUSD(totals.approved_amount || 0)}</b>{totals.pending ? <>· <b style={{ color: '#ffaa00' }}>{totals.pending} pending approval</b></>: ''}</div>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 10.5, color: '#555', textTransform: 'uppercase' }}>Type:</span>
        {chip('Wallet Withdrawal', 'Withdrawals', fType, setFType)}
        {chip('Internal Wallet Transfer', 'Internal transfers', fType, setFType)}
        {chip('External Wallet Transfer', 'External transfers', fType, setFType)}
        <span style={{ fontSize: 10.5, color: '#555', textTransform: 'uppercase', marginLeft: 8 }}>Status:</span>
        {chip('Pending', 'Pending', fStatus, setFStatus)}
        {chip('Approved', 'Approved', fStatus, setFStatus)}
        {chip('Declined', 'Declined', fStatus, setFStatus)}
        <input value={search} onChange={e =>{ setSearch(e.target.value); setPage(1); }} placeholder="Search name / email / account…"
          style={{ marginLeft: 'auto', padding: '5px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 230, outline: 'none' }} />
      </div>
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', maxHeight: '68vh', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 950 }}>
            <thead><tr>{['IB', 'IB ID', 'Date', 'Type', 'Amount', 'Method', 'To account', 'Status', 'Actions'].map(h =><th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>Loading…</td></tr>
                : rows.map((o, i) =>{
                  const st = o.status === 'Approved' ? '#00e5a0' : o.status === 'Declined' ? '#ff4d4d' : '#ffaa00';
                  const isTransfer = o.request_type?.includes('Transfer');
                  return (
                    // IB-origin rows tinted pink so they're recognisable as coming from IBs; pending transfers amber
                    <tr key={i} style={{ background: o.status === 'Pending' ? 'rgba(255,170,0,0.08)' : 'rgba(255,45,120,0.05)', cursor: o.ib_id ? 'pointer' : 'default' }}
                      onClick={() =>o.ib_id && onOpenIB(o.ib_id)}
                      onMouseEnter={e =>(e.currentTarget.style.background = 'rgba(255,45,120,0.12)')}
                      onMouseLeave={e =>(e.currentTarget.style.background = o.status === 'Pending' ? 'rgba(255,170,0,0.08)' : 'rgba(255,45,120,0.05)')}>
                      <td style={{ ...tdStyle, color: '#4ea1ff', fontWeight: 500 }}>{o.name || '—'}</td>
                      <td style={{ ...tdStyle, color: '#7fb0ff', fontFamily: 'monospace', fontSize: 11 }}>{o.ext_ib_id || '—'}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.op_date ? String(o.op_date).slice(0, 10) : '—'}</td>
                      <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: isTransfer ? 'rgba(0,170,255,0.16)' : 'rgba(255,136,0,0.16)', color: isTransfer ? '#00aaff' : '#ff8800' }}>{o.request_type?.replace(' Wallet', '')}</span></td>
                      <td style={{ ...tdStyle, fontWeight: 600, color: '#ff2d78' }}>{fmtUSD(o.amount)}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.payment_type || '—'}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11, fontFamily: 'monospace' }}>{o.to_account || '—'}</td>
                      <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${st}22`, color: st }}>{o.status}{o.status === 'Pending' && isTransfer ? ' · needs approval' : ''}</span></td>
                      <td style={tdStyle} onClick={e =>e.stopPropagation()}>
                        {o.status === 'Pending' ? (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button disabled={busyId === o.id} onClick={() =>act(o, 'approve')}
                              style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid #00e5a055', background: 'rgba(0,229,160,0.12)', color: '#00e5a0', cursor: busyId === o.id ? 'default' : 'pointer', fontSize: 11, opacity: busyId === o.id ? 0.5 : 1 }}>{busyId === o.id ? '…' : 'Approve'}</button>
                            <button disabled={busyId === o.id} onClick={() =>act(o, 'decline')}
                              style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid #ff4d4d55', background: 'rgba(255,77,77,0.1)', color: '#ff4d4d', cursor: busyId === o.id ? 'default' : 'pointer', fontSize: 11, opacity: busyId === o.id ? 0.5 : 1 }}>Decline</button>
                          </div>
                        ) : <span style={{ fontSize: 10.5, color: '#5a6472' }}>—</span>}
                      </td>
                    </tr>
                  );
                })}
              {!loading && rows.length === 0 && <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>No operations</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: '10px 12px', borderTop: '1px solid #4f596b', alignItems: 'center', fontSize: 12, color: '#888' }}>
          <button disabled={page <= 1} onClick={() =>setPage(p =>p - 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page <= 1 ? '#555' : '#888', cursor: page <= 1 ? 'default' : 'pointer' }}>← Prev</button>
          <span>Page {page} · {total.toLocaleString('en-GB')} total</span>
          <button disabled={rows.length < 50} onClick={() =>setPage(p =>p + 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: rows.length < 50 ? '#555' : '#888', cursor: rows.length < 50 ? 'default' : 'pointer' }}>Next →</button>
        </div>
      </div>
    </div>
  );
}

export default function IBAdmin({ user }: any) {
  // Only Zainab may change an IB's level (admin kept as a failsafe). Everyone else
  // can SEE promote/demote in the action menu but can't execute it.
  const canChangeLevel =
    ['zainabw@tnfx.co', 'zainabwmh@tnfx.co'].includes((user?.email || '').toLowerCase())
    || (user?.full_name || '').toLowerCase().includes('zainab')
    || user?.role === 'admin';
  // Role gate for the "⚙ Status rules" button: admin / super_admin / director only. Role
  // comes from localStorage.userRole (how the app stores it) with the user prop as a fallback.
  // (A specific extra user 'Salim' was requested but no such account exists yet — gate by role.)
  const userRole = (localStorage.getItem('userRole') || user?.role || '').toLowerCase();
  const canEditStatusRules = ['admin', 'super_admin', 'director'].includes(userRole);
  // Roles that can see ALL IBs (mirror backend rbac.ALL_ACCESS_ROLES). Seeds the 3-state
  // toggle's "All data" state immediately; the backend `all_access` flag is authoritative.
  const ALL_ACCESS_ROLES = ['super_admin', 'admin', 'director', 'backoffice', 'validation', 'customer_care', 'vps', 'marketing'];
  const isTeamLead = useIsTeamLead('ibs');
  const [allAccess, setAllAccess] = useState<boolean>(ALL_ACCESS_ROLES.includes(userRole));
  const [ibs, setIbs]         = useState<any[]>([]);
  const [kpis, setKpis]       = useState<any>({});
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sort, setSort]       = useState('volume');   // IBs are paid on trading, so rank by it
  // column visibility (persisted) + client-side sort for the period columns (IB since / FTD / NDA)
  const [visCols, setVisCols] = useState<Record<string, boolean>>(() => {
    try { const s = JSON.parse(localStorage.getItem('ib_cols_v3') || 'null'); if (s && typeof s === 'object') return s; } catch {}
    const d: Record<string, boolean> = {}; IB_ALL_COLS.forEach(c => d[c] = !IB_COLS_HIDE_DEFAULT.includes(c)); return d;
  });
  const [colsOpen, setColsOpen] = useState(false);
  const V = (h: string) => IB_COLS_LOCKED.includes(h) || visCols[h] !== false;
  const setColVis = (n: Record<string, boolean>) => { setVisCols(n); try { localStorage.setItem('ib_cols_v3', JSON.stringify(n)); } catch {} };
  // Direction for the active sort column (▲▼). All sortable columns — including IB since /
  // FTD / NDA — now sort SERVER-SIDE across every IB (not just the loaded page).
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');
  const clickSort = (key: string) => {
    if (sort === key) setDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSort(key); setDir(key === 'name' ? 'asc' : 'desc'); }
    setPage(1);
  };
  const [search, setSearch]   = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');   // search actually sent (debounced)
  const [period, setPeriod]   = useState('all_time');
  // 3-state visibility cycle: team (default) -> own -> all (all only if the user has all-access).
  const [scopeMode, setScopeMode] = useState<'team' | 'own' | 'all'>('own');   // default = MY data
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]   = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedIB, setSelectedIB] = useState<number | null>(null);
  const [portalIB, setPortalIB] = useState<number | null>(null);   // "View IB portal" ->live IB Portal as this IB
  const [mainView, setMainView] = useState<'list' | 'trades' | 'plugit' | 'withdrawals'>('list');
  // clicking an IB name opens a small menu: view their IB portal OR open their client page
  const [nameMenu, setNameMenu] = useState<any>(null);   // { ib, x, y }
  const openNameMenu = (ib: any, e: any) =>{
    e.stopPropagation();
    setNameMenu({ ib, x: Math.min(e.clientX, window.innerWidth - 250), y: e.clientY });
  };
  // "Go to client page" — the IB's OWN account is clients.login = ib.agent_id, so open
  // that client profile (Dashboard's navigate->clients handler fetches /clients/{login}).
  const goToClient = (ib: any) =>{
    setNameMenu(null);
    try {
      window.dispatchEvent(new CustomEvent('navigate', {
        detail: { page: 'clients', search: ib.name || String(ib.agent_id || ''), openProfile: ib.agent_id || undefined }
      }));
    } catch {}
  };
  // close the name menu on any outside click / escape
  useEffect(() =>{
    if (!nameMenu) return;
    const close = () =>setNameMenu(null);
    const esc = (ev: any) =>{ if (ev.key === 'Escape') setNameMenu(null); };
    window.addEventListener('click', close);
    window.addEventListener('keydown', esc);
    return () =>{ window.removeEventListener('click', close); window.removeEventListener('keydown', esc); };
  }, [nameMenu]);
  const [actionIB, setActionIB] = useState<any>(null);
  const [actStep, setActStep] = useState('menu');
  const [actDays, setActDays] = useState(0);
  const [actHours, setActHours] = useState(2);
  const [actTarget, setActTarget] = useState(0);
  const doIbAction = async (body: any) =>{
    if (!actionIB) return;
    try { await apiPost(`/ibs/${actionIB.id}/action`, body); setActionIB(null); setActStep('menu'); load(); }
    catch { alert('Action failed'); }
  };
  const [showCfg, setShowCfg] = useState(false);
  const [cfgLow, setCfgLow] = useState(3);
  const [cfgActive, setCfgActive] = useState(10);
  const [cfgElite, setCfgElite] = useState(25);
  // Level is read-only in the list now; level changes are Zainab-only via the Action menu.
  // click-to-filter on the list columns
  const [fCountry, setFCountry] = useState('');
  const [fCity, setFCity]       = useState('');
  const [fLevel, setFLevel]     = useState(0);
  const [fPlugit, setFPlugit]   = useState('');   // ''|synced|no_plugit_update
  const [fAgent, setFAgent]     = useState<{ id: number; name: string } | null>(null);
  useEffect(() =>{ if (kpis.low_min) setCfgLow(kpis.low_min); if (kpis.active_min) setCfgActive(kpis.active_min); if (kpis.elite_min) setCfgElite(kpis.elite_min); }, [kpis.low_min, kpis.active_min, kpis.elite_min]);
  const saveCfg = async () =>{
    try { await apiPost('/ibs/settings/status-thresholds', { low_min: cfgLow, active_min: cfgActive, elite_min: cfgElite }); setShowCfg(false); load(); }
    catch { alert('Save failed'); }
  };
  // Add IB (ticket #12)
  const [addOpen, setAddOpen] = useState(false);
  const [addF, setAddF] = useState<any>({ ib_level: 5 });
  const [addBusy, setAddBusy] = useState(false);
  const [addErr, setAddErr] = useState('');
  const createIB = async () =>{
    if (!String(addF.agent_id || '').trim()) { setAddErr("Enter the IB's trading account login"); return; }
    setAddBusy(true); setAddErr('');
    try {
      const r: any = await apiPost('/ibs', addF);
      if (r && r.detail) { setAddErr(r.detail); }
      else {
        setAddOpen(false); setAddF({ ib_level: 5 }); load();
        const linked = r?.linked_clients ?? 0;
        alert(
          `IB created.\n` +
          `Linked ${linked} existing referred client${linked === 1 ? '' : 's'} to this IB.\n\n` +
          `Note: setting this IB up as an agent on the MT server is a separate, ` +
          `gated action that needs approval — it was NOT done automatically.`
        );
      }
    } catch (e: any) { setAddErr(e?.message || 'Could not create IB'); }
    finally { setAddBusy(false); }
  };

  // debounce the search box so we only query once the user pauses — and so a slower
  // earlier keystroke's response can't land last and clobber the filtered list (ticket #34)
  useEffect(() =>{
    const t = setTimeout(() =>{ setDebouncedSearch(search.trim()); setPage(1); }, 300);
    return () =>clearTimeout(t);
  }, [search]);

  const reqSeq = useRef(0);
  const load = useCallback(async () =>{
    const myReq = ++reqSeq.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, direction: dir, search: debouncedSearch, period });
      if (period === 'custom' && dateFrom && dateTo) {
        params.set('date_from', dateFrom);
        params.set('date_to', dateTo);
      }
      if (fCountry) params.set('country', fCountry);
      if (fCity)    params.set('city', fCity);
      if (fLevel)   params.set('ib_level', String(fLevel));
      if (fPlugit)  params.set('plugit', fPlugit);
      if (fAgent)   params.set('sales_agent_id', String(fAgent.id));
      if (scopeMode === 'own')      params.set('own', '1');
      else if (scopeMode === 'all') params.set('scope', 'all');
      const data = await apiGet(`/ibs?${params}`);
      if (myReq !== reqSeq.current) return;   // a newer request started — ignore this stale response
      setIbs(data.ibs || []);
      setTotal(data.total || 0);
      setKpis({ ...(data.kpis || {}), ...(data.thresholds || {}) });
      // backend is the authority on whether this user may see ALL IBs (drives the "All data" state)
      if (typeof data.all_access === 'boolean') setAllAccess(data.all_access);
      // Per-row trading_clients/status AND the active/low/inactive tier tiles all need a
      // heavy all-IB deals scan (~10s cold for all_time), so the backend serves them
      // separately — fetch lazily and merge so the list never waits on it. Rows show a
      // "…" status pill and the tiles show "…" until this lands.
      const bdParams = new URLSearchParams({ period });
      if (period === 'custom' && dateFrom && dateTo) { bdParams.set('date_from', dateFrom); bdParams.set('date_to', dateTo); }
      // thread the SAME scope so the tier tiles match the (scoped) list + main KPIs
      if (scopeMode === 'own')      bdParams.set('own', '1');
      else if (scopeMode === 'all') bdParams.set('scope', 'all');
      const pageAgents = (data.ibs || []).map((x: any) =>x.agent_id).filter(Boolean);
      if (pageAgents.length) bdParams.set('agents', pageAgents.join(','));
      apiGet(`/ibs/status-breakdown?${bdParams}`).then((bd: any) =>{
        if (myReq !== reqSeq.current) return;
        const lowMin = bd.low_min ?? 3, activeMin = bd.active_min ?? 10, eliteMin = bd.elite_min ?? 25;
        const tmap = bd.trading || {}, ftdMap = bd.ftd || {}, ndaMap = bd.nda || {};
        const accMap = bd.accounts || {}, perMap = bd.persons || {};
        setIbs((prev: any[]) =>prev.map(row =>{
          const k = String(row.agent_id);
          const tc = tmap[k];
          // accounts_live/persons_live = live counts over ALL the person's IB agent accounts —
          // the same scope the IB profile uses (the stored active_clients was stale + narrower).
          const base = { ...row, ftd: ftdMap[k] || 0, nda: ndaMap[k] || 0, nda_loaded: true,
                         accounts_live: accMap[k], persons_live: perMap[k] };
          if (tc === undefined) return { ...base, trading_clients: 0, status: ibStatusFor(0, lowMin, activeMin, eliteMin) };
          return { ...base, trading_clients: tc, status: ibStatusFor(tc, lowMin, activeMin, eliteMin) };
        }));
        setKpis((prev: any) =>({ ...prev,
          elite_ibs: bd.elite_ibs, active_ibs: bd.active_ibs, low_ibs: bd.low_ibs,
          inactive_ibs: bd.inactive_ibs, super_inactive_ibs: bd.super_inactive_ibs }));
      }).catch(() =>{});
    } catch (e) { console.error(e); }
    if (myReq === reqSeq.current) setLoading(false);
  }, [page, pageSize, sort, dir, debouncedSearch, period, dateFrom, dateTo, fCountry, fCity, fLevel, fPlugit, fAgent, scopeMode]);

  useEffect(() =>{ load(); }, [load]);

  // another page (clients/leads/transactions) clicked an IB name ->focus it here
  useEffect(() =>{
    const h = (e:any) =>{
      const id = e.detail?.ibId; const n = e.detail?.ib;
      if (id) { setSelectedIB(Number(id)); }          // open the specific IB profile directly
      else if (n) { setSearch(String(n)); setPage(1); }
    };
    window.addEventListener('ib_focus', h);
    return () =>window.removeEventListener('ib_focus', h);
  }, []);

  if (selectedIB !== null) {
    return <IBProfile ibId={selectedIB} onBack={() =>setSelectedIB(null)} canChangeLevel={canChangeLevel} />;
  }
  // "View IB portal" — render the real IB Portal (client-facing) as this IB
  if (portalIB) {
    return <IBPortal ibId={portalIB} onBack={() =>setPortalIB(null)} />;
  }

  const viewToggle = (
    <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
      {([['list', '🤝 IB List'], ['trades', '📊 All Trades'], ['withdrawals', '💸 Withdrawals']] as [string, string][]).map(([k, l]) =>(
        <button key={k} onClick={() =>setMainView(k as any)}
          style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${mainView === k ? '#00e5a0' : '#626d80'}`,
            background: mainView === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: mainView === k ? '#00e5a0' : '#c4ccd8',
            cursor: 'pointer', fontSize: 12.5, fontWeight: 600, fontFamily: 'inherit' }}>{l}</button>
      ))}
    </div>
  );

  const periodBar = (
    <div style={{ display: 'flex', gap: 4, marginBottom: 10, overflowX: 'auto', alignItems: 'center', flexWrap: 'wrap' }}>
      {[['all_time', 'All'], ['today', 'Today'], ['yesterday', 'Yesterday'], ['last_7_days', 'Last 7d'], ['this_week', 'This week'], ['last_week', 'Last week'], ['last_30_days', 'Last 30d'], ['this_month', 'This month'], ['last_month', 'Last month'], ['this_year', 'This year'], ['last_year', 'Last year'], ['custom', 'Custom']].map(([k, l]) =>(
        <button key={k} onClick={() =>setPeriod(k)}
          style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${period === k ? '#00e5a0' : '#626d80'}`, background: period === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: period === k ? '#00e5a0' : '#c4ccd8', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap', fontFamily: 'inherit' }}>{l}</button>
      ))}
      {period === 'custom' && (
        <span style={{ display: 'flex', gap: 6 }}>
          <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e =>setDateFrom(e.target.value)} style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
          <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e =>setDateTo(e.target.value)} style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
        </span>
      )}
    </div>
  );

  if (mainView === 'trades') {
    return (
      <div style={{ height: '100%', overflowY: 'auto', padding: '0 4px 24px 0' }}>
        {viewToggle}
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>All IB Trades</div>
        {periodBar}
        <IBTradesTab endpoint="/ibs/0/trades" period={period} dateFrom={dateFrom} dateTo={dateTo} />
      </div>
    );
  }

  if (mainView === 'withdrawals') {
    return (
      <div style={{ height: '100%', overflowY: 'auto', padding: '0 4px 24px 0' }}>
        {viewToggle}
        <IBWithdrawals onOpenIB={(id: number) =>setSelectedIB(id)} />
      </div>
    );
  }

  if (mainView === 'plugit') {
    return (
      <div style={{ height: '100%', overflowY: 'auto', padding: '0 4px 24px 0' }}>
        {viewToggle}
        <PlugitOnly />
      </div>
    );
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '0 4px 24px 0' }}>
      {viewToggle}

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginRight: 8 }}>IB System</div>
        <input
          value={search}
          onChange={e =>{ setSearch(e.target.value); setPage(1); }}
          placeholder="Search IB name, phone, code..."
          style={{ padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 240, outline: 'none' }}
        />
        <div style={{ display:'flex', gap:4 }}>
          {[{key:'volume',label:'Volume'},{key:'nda',label:'Most new clients'},{key:'commission',label:'Commission'},{key:'new',label:'Newest'},{key:'deposit',label:'Deposits'}].map(s=>(
            <button key={s.key} onClick={()=>{setSort(s.key);setPage(1);}}
              style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${sort===s.key?'#00e5a0':'#626d80'}`,background:sort===s.key?'rgba(0,229,160,0.1)':'transparent',color:sort===s.key?'#00e5a0':'#c4ccd8',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
              {s.label}
            </button>
          ))}
        </div>
        {/* ONE 3-state visibility button: My team -> My own data -> All data (all-access only). */}
        {(isTeamLead || allAccess) && (() => {
          const LABELS: Record<string, string> = { team: '👥 My team', own: '👤 My own data', all: '🌐 All data' };
          // cycle order; "all" is only reachable when the user actually has all-access (never
          // grants new access — the backend gates it too). Otherwise it toggles team <-> own.
          const nextMode = scopeMode === 'team' ? 'own'
            : scopeMode === 'own' ? (allAccess ? 'all' : 'team') : 'team';
          return (
            <button onClick={() =>{ setScopeMode(nextMode as any); setPage(1); }}
              title="Click to switch visibility: My team → My own data → All data"
              style={{ padding: '6px 13px', fontSize: 12, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                border: '1px solid var(--border,#4f596b)', borderRadius: 9,
                background: 'var(--bg-input,#373f4d)', color: 'var(--accent,#00e5a0)' }}>
              {LABELS[scopeMode]}
            </button>
          );
        })()}
        <div style={{ flex: 1 }} />
        <span style={{ color: '#555', fontSize: 11 }}>{total.toLocaleString('en-GB')} IBs</span>
        {/* Status rules — admin / super_admin / director only (role from localStorage.userRole) */}
        {canEditStatusRules && (
        <div style={{ position: 'relative' }}>
          <button onClick={() =>setShowCfg(v =>!v)} title="Define IB status rules"
            style={{ padding: '6px 14px', border: '1px solid #626d80', borderRadius: 8, background: '#373f4d', color: '#e0e5ec', fontSize: 12, cursor: 'pointer' }}>⚙ Status rules</button>
          {showCfg && (
            <div style={{ position: 'absolute', right: 0, top: '115%', zIndex: 60, background: '#2c333e', border: '1px solid #626d80', borderRadius: 10, padding: 14, width: 280, boxShadow: '0 8px 28px rgba(0,0,0,0.6)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>IB status definition</div>
              <div style={{ fontSize: 10, color: '#666', marginBottom: 10 }}>Based on how many clients traded in the selected period.</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: '#ffaa00', width: 60 }}>Low ≥</span>
                <input type="number" min={1} value={cfgLow} onChange={e =>setCfgLow(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: 60, padding: '4px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                <span style={{ fontSize: 10, color: '#555' }}>trading clients</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: '#00e5a0', width: 60 }}>Active ≥</span>
                <input type="number" min={1} value={cfgActive} onChange={e =>setCfgActive(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: 60, padding: '4px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                <span style={{ fontSize: 10, color: '#555' }}>trading clients</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 11, color: '#b794ff', width: 60 }}>Elite ≥</span>
                <input type="number" min={1} value={cfgElite} onChange={e =>setCfgElite(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: 60, padding: '4px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                <span style={{ fontSize: 10, color: '#555' }}>trading clients</span>
              </div>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 10 }}>Super-inactive = 0 trading · Inactive = 1 to Low−1 · Elite = top band</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={saveCfg} style={{ flex: 1, padding: '6px 0', background: '#00e5a0', border: 'none', borderRadius: 7, color: '#000', fontWeight: 600, fontSize: 12, cursor: 'pointer' }}>Save</button>
                <button onClick={() =>setShowCfg(false)} style={{ padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#888', fontSize: 12, cursor: 'pointer' }}>Cancel</button>
              </div>
            </div>
          )}
        </div>
        )}
        <div style={{ position: 'relative' }}>
          <button onClick={() => setColsOpen(v => !v)} title="Show / hide columns"
            style={{ width: 34, height: 34, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${colsOpen ? '#00e5a0' : '#626d80'}`, background: colsOpen ? 'rgba(0,229,160,0.1)' : 'transparent', color: colsOpen ? '#00e5a0' : '#888', fontSize: 15, cursor: 'pointer' }}>⚙</button>
          {colsOpen && (
            <div style={{ position: 'absolute', right: 0, top: '115%', zIndex: 60, background: '#2c333e', border: '1px solid #626d80', borderRadius: 10, padding: 8, width: 210, boxShadow: '0 8px 28px rgba(0,0,0,0.6)', maxHeight: '70vh', overflowY: 'auto' }}>
              {IB_ALL_COLS.filter(h => !IB_COLS_LOCKED.includes(h)).map(h => (
                <label key={h} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, cursor: 'pointer', fontSize: 12, color: '#d6dbe3' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#373f4d')} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <input type="checkbox" checked={V(h)} onChange={e => setColVis({ ...visCols, [h]: e.target.checked })} />
                  {h}
                </label>
              ))}
              <div style={{ borderTop: '1px solid #4f596b', marginTop: 6, paddingTop: 6, textAlign: 'right' }}>
                <span onClick={() => { try { localStorage.removeItem('ib_cols_v3'); } catch {}; const d: Record<string, boolean> = {}; IB_ALL_COLS.forEach(c => d[c] = !IB_COLS_HIDE_DEFAULT.includes(c)); setVisCols(d); }}
                  style={{ fontSize: 11, color: '#00aaff', cursor: 'pointer' }}>Reset to default</span>
              </div>
            </div>
          )}
        </div>
        <button style={{ padding: '6px 14px', border: '1px solid #626d80', borderRadius: 8, background: '#373f4d', color: '#e0e5ec', fontSize: 12, cursor: 'pointer' }}>Export</button>
        <button onClick={() =>{ setAddF({ ib_level: 5 }); setAddErr(''); setAddOpen(true); }} style={{ padding: '6px 14px', border: 'none', borderRadius: 8, background: '#00e5a0', color: '#000', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>+ Add IB</button>
      </div>

      {/* Active filter chips (click-to-filter from the table) */}
      {(fCountry || fCity || fLevel || fAgent) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: '#667' }}>Filters:</span>
          {([
            fAgent   ? ['Sales agent', fAgent.name, () =>setFAgent(null)] : null,
            fCountry ? ['Country', fCountry, () =>setFCountry('')] : null,
            fCity    ? ['City', fCity, () =>setFCity('')] : null,
            fLevel   ? ['Level', `L${fLevel}`, () =>setFLevel(0)] : null,
          ].filter(Boolean) as [string, string, () =>void][]).map(([lbl, val, clear], i) =>(
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, padding: '3px 10px', borderRadius: 99, background: 'rgba(0,170,255,0.12)', color: '#00aaff', border: '1px solid rgba(0,170,255,0.3)' }}>
              <span style={{ color: '#667' }}>{lbl}:</span>{val}
              <span onClick={() =>{ clear(); setPage(1); }} style={{ cursor: 'pointer', color: '#88a', fontWeight: 700 }}>✕</span>
            </span>
          ))}
          <button onClick={() =>{ setFCountry(''); setFCity(''); setFLevel(0); setFAgent(null); setPage(1); }}
            style={{ fontSize: 11, color: '#888', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit' }}>Clear all</button>
        </div>
      )}

      {/* ── FILTERS + STATS BAND: period box · plugit box · one slim stat strip ── */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: '8px 14px 10px', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {/* period segmented control — one neat rounded box */}
          <div style={{ display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 2,
            background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border,#4f596b)', borderRadius: 10, padding: 3 }}>
            {PERIODS.map(p =>(
              <button key={p.key} onClick={() =>setPeriod(p.key)}
                style={{ padding: '3px 10px', borderRadius: 8, fontSize: 10.5, cursor: 'pointer', border: 'none',
                  background: period === p.key ? 'var(--bg-card,#2c333e)' : 'transparent',
                  color: period === p.key ? 'var(--accent,#00e5a0)' : '#aab4c4',
                  fontWeight: period === p.key ? 700 : 500, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
                {p.label}
              </button>
            ))}
          </div>
          {period === 'custom' && (
            <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e =>setDateFrom(e.target.value)}
                style={{ padding: '2px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 10.5 }} />
              <span style={{ color: '#666' }}>—</span>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e =>setDateTo(e.target.value)}
                style={{ padding: '2px 6px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 10.5 }} />
            </span>
          )}
          {/* divider between the two control boxes */}
          <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border,#4f596b)', margin: '2px 0' }} />
          {/* plugit segmented control — a SEPARATE adjacent rounded box */}
          <div style={{ display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 2,
            background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border,#4f596b)', borderRadius: 10, padding: 3 }}>
            <span style={{ fontSize: 9.5, color: '#8a95a7', textTransform: 'uppercase', letterSpacing: '.5px', margin: '0 4px' }}>Plugit</span>
            {[['','All'],['synced','✓ Synced'],['no_plugit_update','⚠ No update'],['plugit_only','🔌 Only'],['null','🈳 Null']].map(([k,l]) =>(
              <button key={k} onClick={() =>{ setFPlugit(k); setPage(1); }}
                style={{ padding: '3px 10px', borderRadius: 8, fontSize: 10.5, cursor: 'pointer', border: 'none',
                  background: fPlugit === k ? 'var(--bg-card,#2c333e)' : 'transparent',
                  color: fPlugit === k ? '#ffaa00' : '#aab4c4',
                  fontWeight: fPlugit === k ? 700 : 500, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{l}</button>
            ))}
          </div>
        </div>
        {/* one-row stat strip */}
        <div style={{ display: 'flex', flexWrap: 'wrap', marginTop: 8, borderTop: '1px solid #3a4250' }}>
          {[
            { val: fmtNum(kpis.total_ibs || 0),                                              lbl: 'Total IBs',      col: '#e8ecf2' },
            { val: kpis.elite_ibs == null          ? '…' : fmtNum(kpis.elite_ibs),           lbl: `Elite ≥${kpis.elite_min||25}`,  col: '#b794ff' },
            { val: kpis.active_ibs == null         ? '…' : fmtNum(kpis.active_ibs),          lbl: `Active ≥${kpis.active_min||10}`, col: '#00e5a0' },
            { val: kpis.low_ibs == null            ? '…' : fmtNum(kpis.low_ibs),             lbl: `Low ≥${kpis.low_min||3}`,       col: '#ffaa00' },
            { val: kpis.inactive_ibs == null       ? '…' : fmtNum(kpis.inactive_ibs),        lbl: 'Inactive',       col: '#ff8800' },
            { val: kpis.super_inactive_ibs == null ? '…' : fmtNum(kpis.super_inactive_ibs),  lbl: 'Super-inactive', col: '#ff8a8a' },
            // no 'Clients' tile — see IB_ALL_COLS: a client count is not an IB performance factor
            // (it credited IBs for accounts they never introduced). Pay = volume/commission, promo = FTD/NDA.
            { val: fmtNum(Math.round(kpis.total_volume || 0)),                               lbl: 'Volume (lots)',  col: '#00aaff' },
            { val: fmtUSD(kpis.total_commission || 0),                                       lbl: 'Commission',     col: '#ffaa00' },
            { val: fmtUSD(kpis.total_payoff || 0),                                           lbl: 'Payoff',         col: '#ff8a8a' },
            { val: fmtUSD((kpis.total_commission || 0) - (kpis.total_payoff || 0)),          lbl: 'Net',            col: ((kpis.total_commission||0)-(kpis.total_payoff||0)) < 0 ? '#ff4d4d' : '#00e5a0' },
          ].map((k, i) =>(
            <div key={i} style={{ flex: '1 1 0', minWidth: 86, padding: '8px 12px 2px', borderLeft: i ? '1px solid #3a4250' : 'none' }}>
              <div style={{ fontSize: 9, color: '#8a95a7', textTransform: 'uppercase', letterSpacing: '.5px', fontWeight: 600, whiteSpace: 'nowrap' }}>{k.lbl}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: k.col, marginTop: 1, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{k.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* IB Table — borderless full-bleed on the page bg, exactly like the Leads/Clients list tables */}
      <div>
        <div style={{ ...CT.scroll, overflowY: 'visible', flex: 'unset', minHeight: 'unset' }}>
          <table style={{ ...CT.table, minWidth: 1000 }}>
            <thead>
              <tr style={CT.theadTr}>
                {([
                  ['IB Name', 'name', 'left'], ['Phone', '', 'left'], ['Country', '', 'left'],
                  ['Sales agent', '', 'left'], ['Level', '', 'left'], ['IB since', 'ib_since', 'left'],
                  ['FTD', 'ftd', 'right'], ['New Clients', 'nda', 'right'],
                  ['Accounts', '', 'right'], ['Sub-IBs', '', 'left'],
                  ['Volume (lots)', 'volume', 'right'], ['Commission', 'commission', 'right'],
                  ['Payoff', 'payoff', 'right'], ['Net comm.', 'net', 'right'],
                  ['Own balance', '', 'right'], ['Status', '', 'left'], ['Action', '', 'left'],
                ] as [string, string, 'left' | 'right'][]).filter(([h]) => V(h)).map(([h, key, align]) => {
                  const active = !!key && sort === key;
                  return (
                    <th key={h} onClick={() => { if (key) clickSort(key); }}
                      style={{ ...CT.th(active, align), cursor: key ? 'pointer' : 'default' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {h}
                        {!!key && (
                          <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1, fontSize: 8, opacity: active ? 1 : 0.3 }}>
                            <span style={{ color: active && dir === 'asc' ? 'var(--accent,#00e5a0)' : 'inherit' }}>▲</span>
                            <span style={{ color: active && dir === 'desc' ? 'var(--accent,#00e5a0)' : 'inherit' }}>▼</span>
                          </span>
                        )}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={18} style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading...</td></tr>
              ) : ibs.map((ib, i) => (
                <tr key={i} onClick={() =>setSelectedIB(ib.id)} style={{ ...CT.row(), cursor: 'pointer' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#373f4d')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  {V('IB Name') && (
                  <td style={{ ...CT.td, paddingLeft: 16 }}>
                    <div onClick={(e) =>openNameMenu(ib, e)} title="View IB portal or open client page"
                      style={{ fontWeight: 500, color: '#4ea1ff', cursor: 'pointer', display: 'inline-block', textDecoration: 'underline', textDecorationStyle: 'dotted' }}>
                      {ib.name || '—'}
                    </div>
                    <div style={{ fontSize: 11, color: '#aab4c4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}
                      title={ib.email || 'no email on record'}>{ib.email || '—'}</div>
                  </td>)}
                  {V('Phone') && (<td style={CT.td}><PhoneBadge phone={ib.phone} /></td>)}
                  {V('Country') && (
                  <td style={CT.td}>
                    <div style={{ fontSize: 12, cursor: ib.country ? 'pointer' : 'default' }} className={ib.country ? 'hover-underline' : ''}
                      onClick={(e) =>{ if (!ib.country) return; e.stopPropagation(); setFCountry(ib.country); setPage(1); }} title={ib.country || 'Filter by country'}>{shortCountry(ib.country) || '—'}</div>
                    <div style={{ fontSize: 10, color: '#555', cursor: ib.city ? 'pointer' : 'default' }}
                      onClick={(e) =>{ if (!ib.city) return; e.stopPropagation(); setFCity(ib.city); setPage(1); }} title="Filter by city">{ib.city}</div>
                  </td>)}
                  {V('Sales agent') && (
                  <td style={{ ...CT.td, fontSize: 11 }}>
                    {ib.sales_agent
                      ? <span onClick={(e) =>{
                            e.stopPropagation();
                            if (fAgent && fAgent.id === ib.sales_agent_id) {
                              window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'sales_agents', agentId: ib.sales_agent_id } }));
                            } else if (ib.sales_agent_id) { setFAgent({ id: ib.sales_agent_id, name: ib.sales_agent }); setPage(1); }
                          }}
                          title={fAgent && fAgent.id === ib.sales_agent_id ? 'Open Sales Agent page' : 'Filter by this sales agent (click again to open page)'}
                          style={{ color: '#00aaff', cursor: 'pointer' }} className="hover-underline">{ib.sales_agent}</span>
                      : <span style={{ color: '#444' }}>—</span>}
                  </td>)}
                  {/* Level — read-only badge; level changes are Zainab-only via the Action menu. Clicking filters. */}
                  {V('Level') && (
                  <td style={CT.td} onClick={e =>e.stopPropagation()}>
                    <span onClick={() =>{ setFLevel(ib.ib_level); setPage(1); }} title="Filter the list by this level"
                      className="hover-underline"
                      style={{ fontSize: 11, padding: '3px 9px', borderRadius: 7, cursor: 'pointer', whiteSpace: 'nowrap',
                        background: `${levelColor(ib.ib_level)}18`, color: levelColor(ib.ib_level), border: `1px solid ${levelColor(ib.ib_level)}66` }}>
                      IB-{ib.ib_level} · {TIER_NAMES[ib.ib_level]}
                    </span>
                  </td>)}
                  {V('IB since') && (<td style={{ ...CT.td, fontSize: 11, color: '#9aa3b3', whiteSpace: 'nowrap' }}>{ib.ib_creation_date ? String(ib.ib_creation_date).slice(0, 10) : '—'}</td>)}
                  {V('FTD') && (
                  <td style={{ ...CT.td, textAlign: 'right', color: ib.ftd ? '#00aaff' : '#5a6472' }}
                    title="First-Time-Deposit accounts (unique customers) in the selected period">
                    {ib.nda_loaded ? (ib.ftd || '—') : '…'}</td>)}
                  {V('New Clients') && (
                  <td style={{ ...CT.td, textAlign: 'right' }}
                    title="New Clients = genuinely-new clients (no relation to any existing TNFX client) who have traded 1.0+ lot on Gold or FX. IB promotions are scored on New Clients, not raw first-deposits.">
                    {ib.nda_loaded
                      ? (ib.ftd
                          ? <span><b style={{ color: '#ffd166' }}>{ib.nda}</b><span style={{ fontSize: 10, color: '#889', marginLeft: 3 }}>{Math.round(100 * ib.nda / ib.ftd)}%</span></span>
                          : <span style={{ color: '#5a6472' }}>—</span>)
                      : '…'}</td>)}
                  {V('Accounts') && (
                  <td style={{ ...CT.td, textAlign: 'right', color: '#666' }}
                    title={ib.accounts_live != null ? `${ib.accounts_live} referred trading accounts (${ib.persons_live} people)` : ''}>
                    {ib.accounts_live != null ? fmtNum(ib.accounts_live) : '…'}
                  </td>)}
                  {V('Sub-IBs') && (
                  <td style={CT.td}>
                    {ib.sub_ib_count >0
                      ? <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff' }}>{ib.sub_ib_count} sub-IBs</span>
                      : <span style={{ color: '#626d80' }}>—</span>}
                  </td>)}
                  {V('Volume (lots)') && (<td style={{ ...CT.td, textAlign: 'right', color: (ib.total_volume || 0) > 0 ? '#00aaff' : '#5a6472' }}>{(ib.total_volume || 0) > 0 ? fmtNum(Math.round(ib.total_volume)) : '—'}</td>)}
                  {V('Commission') && (<td style={{ ...CT.td, textAlign: 'right', color: (ib.total_commission || 0) > 0 ? '#00e5a0' : '#5a6472', fontWeight: (ib.total_commission || 0) > 0 ? 600 : 400 }}>{(ib.total_commission || 0) > 0 ? fmtUSD(ib.total_commission) : '—'}</td>)}
                  {V('Payoff') && (
                  <td style={{ ...CT.td, textAlign: 'right', color: (ib.total_payoff || 0) >0 ? '#ff4d4d' : '#555', fontWeight: (ib.total_payoff || 0) >0 ? 600 : 400 }}
                    title="Total the IB has already withdrawn / transferred (from the Operation Log)">
                    {(ib.total_payoff || 0) >0 ? fmtUSD(ib.total_payoff) : '—'}
                  </td>)}
                  {V('Net comm.') && (
                  <td style={{ ...CT.td, textAlign: 'right', fontWeight: 600, color: (ib.net_commission ?? ((ib.total_commission||0)-(ib.total_payoff||0))) < 0 ? '#ff4d4d' : '#00e5a0' }}
                    title="Commission − Payoff (what's left after payouts)">
                    {fmtUSD(ib.net_commission ?? ((ib.total_commission||0)-(ib.total_payoff||0)))}
                  </td>)}
                  {V('Own balance') && (<td style={{ ...CT.td, textAlign: 'right', color: (ib.balance || 0) > 0 ? '#e0e0e0' : '#5a6472' }}>{(ib.balance || 0) > 0 ? fmtUSD(ib.balance) : '—'}</td>)}
                  {V('Status') && (
                  <td style={CT.td}>
                    {(() =>{ const s = IB_STATUS[ib.status] || IB_STATUS.pending;
                      const title = ib.status == null ? 'Loading trading activity…' : `${ib.trading_clients||0} client(s) traded this period`;
                      return <span title={title} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: s.bg, color: s.col, fontWeight: 500 }}>{s.label}</span>; })()}
                  </td>)}
                  {V('Action') && (
                  <td style={CT.td} onClick={e =>e.stopPropagation()}>
                    <button onClick={() =>{ setActionIB(ib); setActStep('menu'); }}
                      style={{ padding: '4px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#888', cursor: 'pointer', fontSize: 11 }}>
                      Action ▾
                    </button>
                  </td>)}
                </tr>
              ))}
              {!loading && ibs.length === 0 && (
                <tr><td colSpan={18} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No IBs found</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <Pager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize}
          count={ibs.length} total={total} label="IBs" />
      </div>

      {/* Action modal — call outcome (like the client page) + management */}
      {addOpen && (
        <div style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,0.65)' }} onClick={()=>setAddOpen(false)}>
          <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:22, width:360, maxHeight:'88vh', overflowY:'auto' }} onClick={e=>e.stopPropagation()}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
              <span style={{ fontSize:16, fontWeight:700, color:'#fff' }}>Add IB</span>
              <button onClick={()=>setAddOpen(false)} style={{ background:'none', border:'none', color:'#888', fontSize:18, cursor:'pointer' }}>✕</button>
            </div>
            <div style={{ fontSize:11.5, color:'#888', marginBottom:14 }}>Enter the IB's trading account login. Name & contact auto-fill from that account if it exists.</div>
            {[['agent_id','Trading account login *','e.g. 537715'],['name','Name','(auto from account)'],['email','Email',''],['phone','Phone',''],['country','Country',''],['city','City','']].map(([k,label,ph]:any)=>(
              <div key={k} style={{ marginBottom:10 }}>
                <label style={{ fontSize:11, color:'#8a93a3', fontWeight:600, display:'block', marginBottom:4 }}>{label}</label>
                <input value={addF[k]||''} onChange={e=>setAddF((p:any)=>({...p,[k]:e.target.value}))} placeholder={ph}
                  style={{ width:'100%', padding:'9px 11px', borderRadius:8, background:'#373f4d', border:'1px solid #4f596b', color:'#e8edf2', fontSize:13, outline:'none', boxSizing:'border-box' }} />
              </div>
            ))}
            <div style={{ marginBottom:10 }}>
              <label style={{ fontSize:11, color:'#8a93a3', fontWeight:600, display:'block', marginBottom:4 }}>IB level (5–10)</label>
              <select value={addF.ib_level||5} onChange={e=>setAddF((p:any)=>({...p,ib_level:parseInt(e.target.value)}))}
                style={{ width:'100%', padding:'9px 11px', borderRadius:8, background:'#373f4d', border:'1px solid #4f596b', color:'#e8edf2', fontSize:13 }}>
                {[5,6,7,8,9,10].map(n=><option key={n} value={n}>Level {n}</option>)}
              </select>
            </div>
            <div style={{ fontSize:11, color:'#7e8a99', background:'#23303a', border:'1px solid #335', borderRadius:8, padding:'8px 10px', marginBottom:10, lineHeight:1.4 }}>
              On create, this IB's existing referred clients (clients whose agent = this login) are linked automatically.
              MT-server agent setup is a gated action and needs separate approval — it is not done here.
            </div>
            {addErr && <div style={{ color:'#ff7a7a', fontSize:12.5, marginBottom:10 }}>{addErr}</div>}
            <button onClick={createIB} disabled={addBusy} style={{ width:'100%', padding:'11px', borderRadius:9, background:'#00e5a0', color:'#000', border:'none', fontWeight:700, fontSize:14, cursor:'pointer', opacity:addBusy?0.6:1 }}>{addBusy?'Creating…':'Create IB'}</button>
          </div>
        </div>
      )}

      {actionIB && (
        <div style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,0.65)' }} onClick={()=>{setActionIB(null);setActStep('menu');}}>
          <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:22, width:330, maxHeight:'88vh', overflowY:'auto' }} onClick={e=>e.stopPropagation()}>
            <div style={{ fontSize:13, fontWeight:500, marginBottom:3 }}>{actionIB.name}</div>
            <div style={{ fontSize:11, color:'#555', marginBottom:16 }}>{actStep==='menu'?'Select outcome':actStep==='call_later'?'Call Later':'Set target'}</div>
            {actStep==='menu' && <>
              {[
                {key:'connected_done', icon:'✓', label:'Connected & Done', sub:'Resurfaces in 14 days', color:'#00e5a0'},
                {key:'no_answer',      icon:'✗', label:'No Answer',         sub:'Resurfaces in 2 hours', color:'#ffaa00'},
                {key:'call_later',     icon:'⏰', label:'Call Later',         sub:'Set custom follow-up',  color:'#0066ff'},
                {key:'not_interested', icon:'⊘', label:'Not Interested',     sub:'Pass to manager / hide',color:'#ff4d4d'},
              ].map(a=>(
                <div key={a.key} onClick={()=>{ if(a.key==='call_later'){ setActStep('call_later'); } else { doIbAction({action:a.key}); } }}
                  style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid #4f596b' }}
                  onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')} onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                  <div style={{ width:30, height:30, borderRadius:8, background:`${a.color}22`, color:a.color, display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>{a.icon}</div>
                  <div><div style={{ fontSize:13, fontWeight:500, color:a.color }}>{a.label}</div><div style={{ fontSize:11, color:'#555' }}>{a.sub}</div></div>
                </div>
              ))}
              <div style={{ height:1, background:'#4f596b', margin:'12px 0' }} />
              <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:'.5px', marginBottom:8 }}>Manage IB</div>
              {[
                {icon:'', label:`Promote +1 (now IB-${actionIB.ib_level})`, color:'#00e5a0', fn:()=>canChangeLevel ? doIbAction({action:'promote'}) : alert('Only Zainab can change an IB level.')},
                {icon:'', label:'Demote −1 level', color:'#ffaa00', fn:()=>canChangeLevel ? doIbAction({action:'demote'}) : alert('Only Zainab can change an IB level.')},
                {icon:'', label:`Pay commission ${fmtUSD(actionIB.unpaid_commission||0)}`, color:'#00aaff', fn:async()=>{ if(window.confirm(`Pay ${fmtUSD(actionIB.unpaid_commission||0)} to ${actionIB.name}?`)){ try{ await apiPost('/ibs/pay-commission',{ib_id:actionIB.id}); }catch{} setActionIB(null); load(); } }},
                {icon:'', label:'Set target', color:'#9966ff', fn:()=>setActStep('target')},
              ].map(a=>(
                <div key={a.label} onClick={a.fn} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid #4f596b' }}
                  onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')} onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                  <div style={{ width:26, height:26, borderRadius:7, background:`${a.color}22`, color:a.color, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13 }}>{a.icon}</div>
                  <div style={{ fontSize:12, color:a.color }}>{a.label}</div>
                </div>
              ))}
            </>}
            {actStep==='call_later' && <>
              <div onClick={()=>setActStep('menu')} style={{ cursor:'pointer', color:'#888', fontSize:12, marginBottom:12 }}>← Back</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:12 }}>
                <div><div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Days</div>
                  <input type="number" value={actDays} min={0} onChange={e=>setActDays(parseInt(e.target.value)||0)} style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, boxSizing:'border-box' }} /></div>
                <div><div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Hours</div>
                  <input type="number" value={actHours} min={0} max={23} onChange={e=>setActHours(parseInt(e.target.value)||0)} style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, boxSizing:'border-box' }} /></div>
              </div>
              <button onClick={()=>doIbAction({action:'call_later', days:actDays, hours:actHours})} style={{ width:'100%', padding:10, background:'#0066ff', border:'none', borderRadius:8, color:'#fff', fontWeight:600, fontSize:13, cursor:'pointer' }}>Schedule follow-up</button>
            </>}
            {actStep==='target' && <>
              <div onClick={()=>setActStep('menu')} style={{ cursor:'pointer', color:'#888', fontSize:12, marginBottom:12 }}>← Back</div>
              <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>Target (clients / deposits)</div>
              <input type="number" value={actTarget} min={0} onChange={e=>setActTarget(parseInt(e.target.value)||0)} style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, boxSizing:'border-box' }} />
              <button onClick={()=>doIbAction({action:'set_target', target:actTarget})} style={{ width:'100%', marginTop:12, padding:10, background:'#9966ff', border:'none', borderRadius:8, color:'#fff', fontWeight:600, fontSize:13, cursor:'pointer' }}>Set target</button>
            </>}
          </div>
        </div>
      )}

      {/* Name-click menu: view the IB portal OR open their client page (mirrors Loyalty) */}
      {nameMenu && (
        <div onClick={(e) =>e.stopPropagation()} style={{ position: 'fixed', top: nameMenu.y, left: nameMenu.x, zIndex: 200,
          background: '#222831', border: '1px solid #4f596b', borderRadius: 10, padding: 6, minWidth: 220, boxShadow: '0 8px 28px rgba(0,0,0,0.5)' }}>
          <div style={{ padding: '4px 10px 8px', fontSize: 11.5, color: '#9aa3b2', borderBottom: '1px solid #373f4d', marginBottom: 4 }}>
            {nameMenu.ib.name || ('IB #' + nameMenu.ib.id)} {nameMenu.ib.ib_code && <span style={{ color: '#666' }}>· {nameMenu.ib.ib_code}</span>}
          </div>
          <button onClick={() =>{ setSelectedIB(nameMenu.ib.id); setNameMenu(null); }} style={menuBtn}>📊 IB profile (admin)</button>
          <button onClick={() =>{ setPortalIB(nameMenu.ib.id); setNameMenu(null); }} style={menuBtn}>🌐 View IB portal</button>
        </div>
      )}
    </div>
  );
}
