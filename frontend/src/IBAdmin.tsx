import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost } from './api';
import IBTradesTab from './IBTradesTab';
import IBPortal from './IBPortal';
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

const levelColor = (l: number) => l >= 9 ? '#ff4d4d' : l >= 7 ? '#ffaa00' : '#00e5a0';
// IB-5..IB-10 → Bronze..Master (matches backend TIER_NAMES)
const TIER_NAMES: Record<number, string> = { 5: 'Bronze', 6: 'Silver', 7: 'Gold', 8: 'Diamond', 9: 'Elite', 10: 'Master' };
const fmtUSD = (n: number) => '$' + Math.round(n).toLocaleString();
const fmtNum = (n: number) => n.toLocaleString();
// name-click popup button (mirrors the Loyalty page menu)
const menuBtn: React.CSSProperties = { display: 'block', width: '100%', textAlign: 'left', padding: '9px 10px', background: 'none', border: 'none', color: '#e8e8e8', fontSize: 12.5, cursor: 'pointer', borderRadius: 6 };

const IB_STATUS: Record<string,{label:string;col:string;bg:string}> = {
  active:         { label: 'Active',         col: '#00e5a0', bg: '#0e3a2a' },
  low:            { label: 'Low',            col: '#ffaa00', bg: '#3a2a0e' },
  inactive:       { label: 'Inactive',       col: '#ff8800', bg: '#3a1e0e' },
  super_inactive: { label: 'Super-inactive', col: '#ff4d4d', bg: '#3a0e0e' },
  pending:        { label: '…',              col: '#888',    bg: '#373f4d' },
};
// mirror of backend ib_status_for — trading_clients are loaded lazily, so the status
// pill is recomputed client-side once the lazy /status-breakdown call lands.
function ibStatusFor(tc: number, lowMin: number, activeMin: number): string {
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
      <span style={{ color:'#ff2d78' }}>📞</span>···{last4}
    </span>
  );
}

// Match the Clients-page table look: dark header bar (#373f4d) with bold light text,
// thin row separators, consistent 12px body font.
const thStyle: React.CSSProperties = {
  padding: '9px 8px', textAlign: 'left', color: '#cfd6e0', fontWeight: 600,
  fontSize: 11, borderBottom: '1px solid #4f596b', whiteSpace: 'nowrap', cursor: 'pointer',
  background: '#373f4d', position: 'sticky', top: 0, zIndex: 5,
};
const tdStyle: React.CSSProperties = {
  padding: '9px 8px', borderBottom: '1px solid #373f4d', verticalAlign: 'middle',
  fontSize: 12, color: '#e0e0e0',
};

// ─── IB PROFILE PAGE ────────────────────────────────────────────────────────
function IBProfile({ ibId, onBack, canChangeLevel }: { ibId: number; onBack: () => void; canChangeLevel: boolean }) {
  const [ib, setIb]         = useState<any>(null);
  const [tab, setTab]       = useState('clients');
  const [ops, setOps]       = useState<any>(null);   // payout operations (lazy)
  const [promos, setPromos] = useState<any>(null);   // level-promotion history (lazy)
  const [period, setPeriod] = useState('this_month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]     = useState('');
  const [fCountry, setFCountry] = useState('');
  const [fCity, setFCity]       = useState('');
  const [loading, setLoading]   = useState(true);
  const [paying, setPaying]     = useState(false);

  const load = useCallback(async () => {
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

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (tab === 'operations' && !ops) {
      apiGet(`/ibs/${ibId}/operations`).then(setOps).catch(() => setOps({ operations: [], summary: {} }));
    }
    if (tab === 'promotions' && !promos) {
      apiGet(`/ibs/${ibId}/promotions`).then(setPromos).catch(() => setPromos({ promotions: [] }));
    }
  }, [tab, ops, promos, ibId]);

  const handlePay = async () => {
    if (!ib || !window.confirm(`Pay ${fmtUSD(ib.unpaid_commission)} to ${ib.name}?`)) return;
    setPaying(true);
    try {
      await apiPost('/ibs/pay-commission', { ib_id: ibId });
      await load();
    } catch (e) { alert('Payment failed'); }
    setPaying(false);
  };

  const handlePromote = async () => {
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

  const tabs = ['clients', 'leads', 'trades', 'operations', 'promotions'];
  const tabLabels: any = {
    clients: `Clients (${ib.total_clients || 0})`,
    leads: `Leads (${ib.funnel?.leads || 0})`,
    trades: 'Trades',
    operations: `💸 Payouts${ib.total_payoff ? ` (${fmtUSD(ib.total_payoff)})` : ''}`,
    promotions: `🎖 Promotions${promos?.promotions?.length ? ` (${promos.promotions.length})` : ''}`,
  };

  return (
    <div style={{ height:'100%', overflowY:'auto', padding:'0 4px 24px 0' }}>
      {/* Back — sticky so it's always visible */}
      <button onClick={onBack} style={{ alignSelf:'flex-start', background: 'rgba(0,229,160,0.1)', border: '1px solid #00e5a0', borderRadius: 8, color: '#00e5a0', padding: '7px 16px', cursor: 'pointer', fontSize: 12, fontWeight: 600, marginBottom: 12, flexShrink: 0 }}>
        ← Back to IB list
      </button>

      {/* Header */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16, marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
          <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#0e3a2a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, color: '#00e5a0', flexShrink: 0 }}>
            {(ib.name || '?').substring(0, 2).toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{ib.name}</span>
              {ib.ext_ib_id != null && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#1a2440', color: '#7fb0ff', fontWeight: 600 }}>IB ID {ib.ext_ib_id}</span>}
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${levelColor(ib.ib_level)}22`, color: levelColor(ib.ib_level) }}>{ib.tier || ''} · IB-{ib.ib_level} · {ib.ib_level}pts/lot</span>
              {ib.is_sub_ib && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#3a2a0e', color: '#ffaa00' }}>Sub-IB</span>}
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0e3a2a', color: '#00e5a0' }}>Active</span>
            </div>
            <div style={{ color: '#cfd6e0', marginTop: 4, display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
              <span><span style={{ color: '#ff2d78' }}>✉</span> {ib.email || '—'}</span>
              {ib.email_verified && <span style={{ fontSize: 10, fontWeight:700, padding: '2px 8px', borderRadius: 99, background: 'rgba(0,229,160,0.14)', color: '#00e5a0' }}>✓ Email verified</span>}
              {ib.phone_verified && <span style={{ fontSize: 10, fontWeight:700, padding: '2px 8px', borderRadius: 99, background: 'rgba(0,229,160,0.14)', color: '#00e5a0' }}>✓ Phone verified</span>}
              {ib.kyc === 'verified' && <span style={{ fontSize: 10, fontWeight:700, padding: '2px 8px', borderRadius: 99, background: 'rgba(0,229,160,0.14)', color: '#00e5a0' }}>✓ KYC</span>}
            </div>
            <div style={{ color: '#666', marginTop: 2 }}>{ib.phone} &nbsp;·&nbsp; {ib.country}{ib.city ? `, ${ib.city}` : ''}</div>
            <div style={{ color: '#666', marginTop: 2 }}>
              Accounts: {(ib.accounts && ib.accounts.length ? ib.accounts : [{ account: ib.agent_id, platform: 'MT5' }]).map((a: any, i: number) => (
                <span key={i}><span style={{ fontSize: 9, color: '#8a93a3', border: '1px solid #4f596b', borderRadius: 4, padding: '0 4px', marginRight: 3 }}>{a.platform}</span><span style={{ color: '#00e5a0' }}>#{a.account}</span>{i < ib.accounts.length - 1 ? <span style={{ color: '#444' }}> &nbsp; </span> : ''}</span>
              ))}
              &nbsp;·&nbsp; Balance: <span style={{ color: '#00e5a0' }}>{fmtUSD(ib.balance)}</span>
            </div>
            <div style={{ color: '#666', marginTop: 2 }}>
              {ib.ib_creation_date && <>IB since: <span style={{ color: '#cfd6e0' }}>{String(ib.ib_creation_date).slice(0, 10)}</span></>}
              {ib.master_ib && <> &nbsp;·&nbsp; Master IB: <span style={{ color: '#7fb0ff' }}>{ib.master_ib.name} (#{ib.master_ib.agent_id})</span></>}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
            <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
              style={{ padding: '6px 14px', background: ib.unpaid_commission > 0 ? '#00e5a0' : '#373f4d', color: ib.unpaid_commission > 0 ? '#000' : '#555', border: 'none', borderRadius: 8, fontSize: 12, cursor: ib.unpaid_commission > 0 ? 'pointer' : 'default', fontWeight: 500 }}>
              {paying ? 'Paying...' : `Pay ${fmtUSD(ib.unpaid_commission)}`}
            </button>
            {canChangeLevel && (
              <button onClick={handlePromote} style={{ padding: '5px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', fontSize: 12, cursor: 'pointer' }}>
                Promote level
              </button>
            )}
            <button style={{ padding: '5px 12px', background: '#3a0e0e', border: '1px solid #ff4d4d', borderRadius: 8, color: '#ff4d4d', fontSize: 12, cursor: 'pointer' }}>
              Suspend
            </button>
          </div>
        </div>

        {/* Period selector */}
        <div style={{ display: 'flex', gap: 4, background: '#373f4d', borderRadius: 10, padding: 4, marginTop: 14, flexWrap: 'wrap' }}>
          {PERIODS.map(p => (
            <button key={p.key} onClick={() => setPeriod(p.key)}
              style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11, cursor: 'pointer', border: period === p.key ? '1px solid #626d80' : 'none', background: period === p.key ? '#2c333e' : 'transparent', color: period === p.key ? '#e0e0e0' : '#555', fontWeight: period === p.key ? 500 : 400, fontFamily: 'inherit' }}>
              {p.label}
            </button>
          ))}
          {period === 'custom' && (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 4px' }}>
              <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
              <span style={{ color: '#555' }}>—</span>
              <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
            </div>
          )}
        </div>

        {/* KPIs — all driven by the selected period */}
        <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginTop: 14, marginBottom: 8 }}>
          KPIs · {ib.period?.from} — {ib.period?.to}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
          {[
            { val: fmtNum(ib.total_clients || 0),                       lbl: 'Total clients',  col: '#00aaff', sub: 'All time' },
            { val: fmtNum(ib.period?.new_clients || 0),                 lbl: 'New clients',    col: '#00e5a0', sub: 'This period' },
            { val: fmtNum(ib.period?.active_clients || 0),              lbl: 'Active clients', col: '#00e5a0', sub: 'Traded / deposited' },
            { val: fmtNum(ib.funnel?.ftd || 0),                         lbl: 'Funded (FTD)',   col: '#00aaff', sub: 'All time' },
            { val: fmtUSD(ib.period?.deposits || 0),                    lbl: 'Deposits',       col: '#00e5a0', sub: 'This period' },
            { val: fmtUSD(ib.period?.withdrawals || 0),                 lbl: 'Withdrawals',    col: '#ff4d4d', sub: 'This period' },
            { val: fmtNum(Math.round(ib.period?.volume || 0)) + ' lots',lbl: 'Volume',         col: '#00aaff', sub: 'This period' },
            { val: fmtUSD(ib.period?.commission || 0),                  lbl: 'Commission',     col: '#ffaa00', sub: `${ib.ib_level} pts/lot · total ${fmtUSD(ib.total_commission||0)}` },
            { val: fmtUSD(ib.total_payoff || 0),                        lbl: 'Total payoff',   col: '#ff4d4d', sub: 'withdrawn / transferred' },
            { val: fmtUSD((ib.total_commission||0) - (ib.total_payoff||0)), lbl: 'Net commission', col: '#00e5a0', sub: 'commission − payoff' },
          ].map((k, i) => (
            <div key={i} style={{ background: '#373f4d', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: k.col }}>{k.val}</div>
              <div style={{ fontSize: 10, color: '#888', marginTop: 3 }}>{k.lbl}</div>
              <div style={{ fontSize: 9, color: '#666', marginTop: 2 }}>{k.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: '#373f4d', borderRadius: 10, padding: 4, marginBottom: 12 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '7px 14px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: tab === t ? '1px solid #626d80' : 'none', background: tab === t ? '#2c333e' : 'transparent', color: tab === t ? '#e0e0e0' : '#666', fontWeight: tab === t ? 500 : 400, fontFamily: 'inherit' }}>
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
            {[['Total paid out', ops?.summary?.paid_out, '#ff4d4d'], ['Withdrawn', ops?.summary?.withdrawn, '#ff8800'], ['Transferred', ops?.summary?.transferred, '#00aaff'], ['Net commission', (ib.total_commission || 0) - (ib.total_payoff || 0), '#00e5a0']].map(([l, v, c]: any, i) => (
              <div key={i} style={{ background: '#373f4d', borderRadius: 8, padding: '8px 14px', minWidth: 120 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: c }}>{fmtUSD(v || 0)}</div>
                <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>{l}</div>
              </div>
            ))}
            <div style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 11, color: '#888' }}>{(ops?.operations || []).length} operations · IB payouts (May 2023 →)</div>
          </div>
          <div style={{ overflowX: 'auto', maxHeight: 520, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead><tr>{['Date', 'Type', 'Amount', 'Method', 'To account', 'Status', 'Note'].map(hh => <th key={hh} style={{ ...thStyle }}>{hh}</th>)}</tr></thead>
              <tbody>
                {!ops ? <tr><td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 30 }}>Loading…</td></tr>
                  : (ops.operations || []).map((o: any, i: number) => {
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
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e0e0e0' }}>🎖 Level promotion history</div>
            <div style={{ fontSize: 11, color: '#888' }}>current level <b style={{ color: '#ffd166' }}>IB-{ib.ib_level ?? '—'}</b></div>
            <div style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>detected from the broker Commission Report (per-lot rate step-ups)</div>
          </div>
          <div style={{ padding: '16px 18px' }}>
            {!promos ? <div style={{ color: '#555', padding: 20 }}>Loading…</div>
              : (promos.promotions || []).length === 0
                ? <div style={{ color: '#666', padding: 20, fontSize: 13 }}>No promotions detected in the report period. This IB's level has been stable.</div>
                : (
                  <div style={{ position: 'relative', paddingLeft: 22 }}>
                    <div style={{ position: 'absolute', left: 6, top: 4, bottom: 4, width: 2, background: '#4f596b' }} />
                    {(promos.promotions || []).map((p: any, i: number) => (
                      <div key={i} style={{ position: 'relative', marginBottom: 18 }}>
                        <div style={{ position: 'absolute', left: -22, top: 2, width: 12, height: 12, borderRadius: 99, background: '#ffd166', border: '2px solid #2c333e' }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 12, color: '#9aa3b3', fontFamily: 'monospace' }}>{p.date}</span>
                          <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 99, background: '#8892a022', color: '#9aa3b3' }}>IB-{p.from_level}</span>
                          <span style={{ color: '#ffd166', fontWeight: 700 }}>→</span>
                          <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 99, background: '#00e5a022', color: '#00e5a0', fontWeight: 600 }}>IB-{p.to_level}</span>
                          <span style={{ fontSize: 11, color: '#ffd166' }}>promoted +{p.to_level - p.from_level}</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{p.note}</div>
                      </div>
                    ))}
                  </div>
                )}
          </div>
        </div>
      )}

      {/* CLIENTS TAB */}
      {tab === 'clients' && (
        <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display:'flex', gap:8, padding:'10px 12px', borderBottom:'1px solid #4f596b', alignItems:'center' }}>
            <span style={{ fontSize:11, color:'#555' }}>Filter:</span>
            <input value={fCountry} onChange={e=>setFCountry(e.target.value)} placeholder="Country..."
              style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11, width:140, outline:'none' }} />
            <input value={fCity} onChange={e=>setFCity(e.target.value)} placeholder="City..."
              style={{ padding:'5px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11, width:140, outline:'none' }} />
            {(fCountry||fCity) && <span onClick={()=>{setFCountry('');setFCity('');}} style={{ fontSize:11, color:'#ff4d4d', cursor:'pointer' }}>Clear ✕</span>}
            <span style={{ fontSize:11, color:'#555', marginLeft:'auto' }}>{(ib.clients||[]).length} shown</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
              <thead>
                <tr>
                  {['Client', 'Account #', 'Phone', 'Country / City', 'Sales agent', 'Campaign', 'Network', 'Volume', 'Commission', 'Total dep.', 'Total with.', 'Abuse', 'Start trade', 'KYC'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.clients || []).map((c: any, i: number) => {
                  const ns = c.network_score || 0;
                  const nsCol = ns >= 7 ? '#ff4d4d' : ns >= 4 ? '#ffaa00' : '#00e5a0';
                  return (
                  <tr key={i} style={{ cursor: 'pointer' }}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{c.name}</div><div style={{ fontSize: 10, color: '#555' }}>#{c.login}</div></td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', color: '#cfd6e0' }}>{c.account_number || c.login || '—'}</td>
                    <td style={tdStyle}><PhoneBadge phone={c.phone} /></td>
                    <td style={{ ...tdStyle, color: '#888', fontSize: 11 }}>{c.country || '—'}{c.city ? <span style={{ color: '#555' }}> · {c.city}</span> : ''}</td>
                    <td style={{ ...tdStyle, fontSize: 11, color: c.sales_agent ? '#cfd6e0' : '#444' }} title={c.sales_agent || ''}>{c.sales_agent || '—'}</td>
                    <td style={{ ...tdStyle, color: '#888', fontSize: 11, maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.campaign || ''}>{c.campaign || '—'}</td>
                    <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, border: `1px solid ${nsCol}`, color: nsCol, fontWeight: 600 }}>{ns}/10</span></td>
                    <td style={{ ...tdStyle, color: '#00aaff' }}>{fmtNum(Math.round(c.volume || 0))} lots</td>
                    <td style={{ ...tdStyle, color: c.commission > 0 ? '#00e5a0' : '#666', fontWeight: c.commission > 0 ? 600 : 400 }} title="Commission this client earned the IB (all-time)">{c.commission > 0 ? fmtUSD(c.commission) : '—'}</td>
                    <td style={{ ...tdStyle, color: '#00e5a0' }}>{fmtUSD(c.total_dep)}</td>
                    <td style={{ ...tdStyle, color: '#ff4d4d' }}>{fmtUSD(c.total_with)}</td>
                    <td style={tdStyle}>{c.abuse_flag ? (() => { const col:any={critical:'#ff4d4d',high:'#ff8800',medium:'#ffaa00'}; const cc=col[c.abuse_severity]||'#ff4d4d'; return <span title="In an open abuse case" style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: `${cc}22`, color: cc, border:`1px solid ${cc}66`, fontWeight:700, whiteSpace:'nowrap' }}>{c.abuse_hot?'🔥 ':'⛔ '}{c.abuse_flag}</span>; })() : <span style={{ color: '#626d80' }}>—</span>}</td>
                    <td style={{ ...tdStyle, color: '#666', fontSize: 11 }}>{c.first_trade || '—'}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0e3a2a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00e5a0' : '#ffaa00' }}>{c.kyc}</span>
                    </td>
                  </tr>
                  );
                })}
                {(ib.clients || []).length === 0 && (
                  <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No clients match</td></tr>
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
                  {['Name', 'Phone', 'Country', 'Registered', 'KYC', 'Deposited', 'Status'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.clients || []).map((c: any, i: number) => (
                  <tr key={i}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{c.name}</div></td>
                    <td style={{ ...tdStyle, color: '#666' }} title={c.phone||''}>{c.phone ? '···'+String(c.phone).replace(/\D/g,'').slice(-4) : '—'}</td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.country}</td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.reg_date}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0e3a2a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00e5a0' : '#ffaa00' }}>{c.kyc}</span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.total_dep > 0 ? '#0e3a2a' : '#373f4d', color: c.total_dep > 0 ? '#00e5a0' : '#555' }}>
                        {c.total_dep > 0 ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.total_dep > 0 ? '#0e3a2a' : c.kyc === 'verified' ? '#0a1a3a' : '#3a2a0e', color: c.total_dep > 0 ? '#00e5a0' : c.kyc === 'verified' ? '#00aaff' : '#ffaa00' }}>
                        {c.total_dep > 0 ? 'Client' : c.kyc === 'verified' ? 'Verified lead' : 'Lead'}
                      </span>
                    </td>
                  </tr>
                ))}
                {(ib.clients || []).length === 0 && (
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
              {[
                { label: 'Total earned (all time)', val: fmtUSD(ib.total_commission), col: '#00e5a0' },
                { label: 'Unpaid balance', val: fmtUSD(ib.unpaid_commission), col: '#ffaa00' },
                { label: 'Paid out', val: fmtUSD(ib.paid_commission), col: '#555' },
                { label: `Period (${ib.period?.from} — ${ib.period?.to})`, val: fmtUSD(ib.period?.commission || 0), col: '#00aaff' },
              ].map((r, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: i < 3 ? '1px solid #373f4d' : 'none' }}>
                  <span style={{ color: '#666' }}>{r.label}</span>
                  <span style={{ color: r.col, fontWeight: 600 }}>{r.val}</span>
                </div>
              ))}
              <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
                style={{ width: '100%', marginTop: 12, padding: 8, background: ib.unpaid_commission > 0 ? '#00e5a0' : '#373f4d', color: ib.unpaid_commission > 0 ? '#000' : '#555', border: 'none', borderRadius: 8, fontSize: 13, cursor: ib.unpaid_commission > 0 ? 'pointer' : 'default', fontWeight: 500 }}>
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
                    {['Date', 'Client', 'Symbol', 'Volume', 'Pts/lot', 'Native', 'FX rate', 'USD', 'Type', 'Status'].map(h => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(ib.commissions || []).map((c: any, i: number) => (
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
                  {['IB Name', 'Level', 'Clients', 'Volume (lots)', 'Their commission', 'Your override (10%)', 'Unpaid', 'Status'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.sub_ibs || []).map((s: any, i: number) => (
                  <tr key={i}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{s.name}</div><div style={{ fontSize: 10, color: '#00aaff' }}>{s.ib_code}</div></td>
                    <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: `${levelColor(s.ib_level)}22`, color: levelColor(s.ib_level) }}>L{s.ib_level}</span></td>
                    <td style={tdStyle}>{s.total_clients}</td>
                    <td style={{ ...tdStyle, color: '#00aaff' }}>{fmtNum(Math.round(s.total_volume))}</td>
                    <td style={{ ...tdStyle, color: '#00e5a0' }}>{fmtUSD(s.total_commission)}</td>
                    <td style={{ ...tdStyle, color: '#00aaff', fontWeight: 600 }}>{fmtUSD(s.total_commission * 0.1)}</td>
                    <td style={{ ...tdStyle, color: s.unpaid_commission > 0 ? '#ffaa00' : '#555' }}>{s.unpaid_commission > 0 ? fmtUSD(s.unpaid_commission) : '—'}</td>
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
          ) : (ib.referral_links || []).map((l: any, i: number) => (
            <div key={i} style={{ borderBottom: '1px solid #373f4d', padding: '12px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 500 }}>{l.name}</span>
                <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: l.status === 'active' ? '#0e3a2a' : '#3a2a0e', color: l.status === 'active' ? '#00e5a0' : '#ffaa00' }}>{l.status}</span>
                <div style={{ flex: 1 }} />
                <span style={{ color: '#555', fontSize: 11 }}>Clicks: <span style={{ color: '#00aaff' }}>{l.clicks?.toLocaleString()}</span></span>
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
  useEffect(() => {
    setLoading(true);
    apiGet(`/ibs/plugit-only?page=${page}&page_size=50&search=${encodeURIComponent(search)}`)
      .then((d: any) => { setRows(d.rows || []); setTotal(d.total || 0); })
      .catch(() => setRows([])).finally(() => setLoading(false));
  }, [page, search]);
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>🔌 From Plugit only <span style={{ fontSize: 12, color: '#888', fontWeight: 400 }}>· in the Plugit export but not in the CRM ({total.toLocaleString()})</span></div>
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search name, email, code…"
          style={{ marginLeft: 'auto', padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 240, outline: 'none' }} />
      </div>
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', maxHeight: '70vh' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead><tr>{['IB Code', 'Name', 'Email', 'Markup (pips)', 'Level'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={5} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>Loading…</td></tr>
                : rows.map((r, i) => (
                  <tr key={i} className="ibp-row">
                    <td style={{ ...tdStyle, color: '#00aaff', fontFamily: 'monospace' }}>{r.code}</td>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{r.name || '—'}</td>
                    <td style={{ ...tdStyle, color: '#9aa3b3' }}>{r.email || '—'}</td>
                    <td style={{ ...tdStyle, color: '#e0e0e0' }}>{r.pips != null ? `${r.pips} pips` : '—'}</td>
                    <td style={tdStyle}>{r.level ? <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 7, background: `${levelColor(r.level)}18`, color: levelColor(r.level), border: `1px solid ${levelColor(r.level)}66` }}>IB-{r.level} · {r.tier}</span> : '—'}</td>
                  </tr>
                ))}
              {!loading && rows.length === 0 && <tr><td colSpan={5} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>None</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: '10px 12px', borderTop: '1px solid #4f596b', alignItems: 'center', fontSize: 12, color: '#888' }}>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page <= 1 ? '#555' : '#888', cursor: page <= 1 ? 'default' : 'pointer' }}>← Prev</button>
          <span>Page {page} · {total.toLocaleString()} total</span>
          <button disabled={rows.length < 50} onClick={() => setPage(p => p + 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: rows.length < 50 ? '#555' : '#888', cursor: rows.length < 50 ? 'default' : 'pointer' }}>Next →</button>
        </div>
      </div>
    </div>
  );
}

// Withdrawals page — ALL IB payouts (withdrawals + int/ext transfers). IB rows are colour-tagged.
function IBWithdrawals({ onOpenIB }: { onOpenIB: (id: number) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [totals, setTotals] = useState<any>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [fType, setFType] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ page: String(page), page_size: '50' });
    if (fType) p.set('request_type', fType);
    if (fStatus) p.set('status', fStatus);
    if (search) p.set('search', search);
    apiGet(`/ibs/operations?${p}`).then((d: any) => { setRows(d.rows || []); setTotals(d.totals || {}); setTotal(d.total || 0); })
      .catch(() => setRows([])).finally(() => setLoading(false));
  }, [page, fType, fStatus, search]);
  const chip = (k: string, l: string, cur: string, set: (v: string) => void) => (
    <button onClick={() => { set(cur === k ? '' : k); setPage(1); }}
      style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${cur === k ? '#00e5a0' : '#626d80'}`, background: cur === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: cur === k ? '#00e5a0' : '#888', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap' }}>{l}</button>
  );
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>💸 IB Withdrawals & Transfers</div>
        <span style={{ fontSize: 11, color: '#ff8800', border: '1px solid #ff880066', borderRadius: 6, padding: '2px 8px' }}>All rows are IB payouts</span>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#9aa3b3' }}>Approved out: <b style={{ color: '#ff4d4d' }}>{fmtUSD(totals.approved_amount || 0)}</b>{totals.pending ? <> · <b style={{ color: '#ffaa00' }}>{totals.pending} pending approval</b></> : ''}</div>
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
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search name / email / account…"
          style={{ marginLeft: 'auto', padding: '5px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 230, outline: 'none' }} />
      </div>
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', maxHeight: '68vh', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 950 }}>
            <thead><tr>{['IB', 'IB ID', 'Date', 'Type', 'Amount', 'Method', 'To account', 'Status'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={8} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>Loading…</td></tr>
                : rows.map((o, i) => {
                  const st = o.status === 'Approved' ? '#00e5a0' : o.status === 'Declined' ? '#ff4d4d' : '#ffaa00';
                  const isTransfer = o.request_type?.includes('Transfer');
                  return (
                    // IB-origin rows tinted pink so they're recognisable as coming from IBs; pending transfers amber
                    <tr key={i} style={{ background: o.status === 'Pending' ? 'rgba(255,170,0,0.08)' : 'rgba(255,45,120,0.05)', cursor: o.ib_id ? 'pointer' : 'default' }}
                      onClick={() => o.ib_id && onOpenIB(o.ib_id)}
                      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,45,120,0.12)')}
                      onMouseLeave={e => (e.currentTarget.style.background = o.status === 'Pending' ? 'rgba(255,170,0,0.08)' : 'rgba(255,45,120,0.05)')}>
                      <td style={{ ...tdStyle, color: '#4ea1ff', fontWeight: 500 }}>{o.name || '—'}</td>
                      <td style={{ ...tdStyle, color: '#7fb0ff', fontFamily: 'monospace', fontSize: 11 }}>{o.ext_ib_id || '—'}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.op_date ? String(o.op_date).slice(0, 10) : '—'}</td>
                      <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: isTransfer ? 'rgba(0,170,255,0.16)' : 'rgba(255,136,0,0.16)', color: isTransfer ? '#00aaff' : '#ff8800' }}>{o.request_type?.replace(' Wallet', '')}</span></td>
                      <td style={{ ...tdStyle, fontWeight: 600, color: '#ff2d78' }}>{fmtUSD(o.amount)}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11 }}>{o.payment_type || '—'}</td>
                      <td style={{ ...tdStyle, color: '#9aa3b3', fontSize: 11, fontFamily: 'monospace' }}>{o.to_account || '—'}</td>
                      <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${st}22`, color: st }}>{o.status}{o.status === 'Pending' && isTransfer ? ' · needs approval' : ''}</span></td>
                    </tr>
                  );
                })}
              {!loading && rows.length === 0 && <tr><td colSpan={8} style={{ ...tdStyle, textAlign: 'center', color: '#555', padding: 40 }}>No operations</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 8, padding: '10px 12px', borderTop: '1px solid #4f596b', alignItems: 'center', fontSize: 12, color: '#888' }}>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: page <= 1 ? '#555' : '#888', cursor: page <= 1 ? 'default' : 'pointer' }}>← Prev</button>
          <span>Page {page} · {total.toLocaleString()} total</span>
          <button disabled={rows.length < 50} onClick={() => setPage(p => p + 1)} style={{ padding: '4px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: rows.length < 50 ? '#555' : '#888', cursor: rows.length < 50 ? 'default' : 'pointer' }}>Next →</button>
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
  const [ibs, setIbs]         = useState<any[]>([]);
  const [kpis, setKpis]       = useState<any>({});
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sort, setSort]       = useState('clients');
  const [search, setSearch]   = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');   // search actually sent (debounced)
  const [period, setPeriod]   = useState('all_time');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]   = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedIB, setSelectedIB] = useState<number | null>(null);
  const [portalIB, setPortalIB] = useState<number | null>(null);   // "View IB portal" -> live IB Portal as this IB
  const [mainView, setMainView] = useState<'list' | 'trades' | 'plugit' | 'withdrawals'>('list');
  // clicking an IB name opens a small menu: view their IB portal OR open their client page
  const [nameMenu, setNameMenu] = useState<any>(null);   // { ib, x, y }
  const openNameMenu = (ib: any, e: any) => {
    e.stopPropagation();
    setNameMenu({ ib, x: Math.min(e.clientX, window.innerWidth - 250), y: e.clientY });
  };
  // "Go to client page" — the IB's OWN account is clients.login = ib.agent_id, so open
  // that client profile (Dashboard's navigate->clients handler fetches /clients/{login}).
  const goToClient = (ib: any) => {
    setNameMenu(null);
    try {
      window.dispatchEvent(new CustomEvent('navigate', {
        detail: { page: 'clients', search: ib.name || String(ib.agent_id || ''), openProfile: ib.agent_id || undefined }
      }));
    } catch {}
  };
  // close the name menu on any outside click / escape
  useEffect(() => {
    if (!nameMenu) return;
    const close = () => setNameMenu(null);
    const esc = (ev: any) => { if (ev.key === 'Escape') setNameMenu(null); };
    window.addEventListener('click', close);
    window.addEventListener('keydown', esc);
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', esc); };
  }, [nameMenu]);
  const [actionIB, setActionIB] = useState<any>(null);
  const [actStep, setActStep] = useState('menu');
  const [actDays, setActDays] = useState(0);
  const [actHours, setActHours] = useState(2);
  const [actTarget, setActTarget] = useState(0);
  const doIbAction = async (body: any) => {
    if (!actionIB) return;
    try { await apiPost(`/ibs/${actionIB.id}/action`, body); setActionIB(null); setActStep('menu'); load(); }
    catch { alert('Action failed'); }
  };
  const [showCfg, setShowCfg] = useState(false);
  const [cfgLow, setCfgLow] = useState(3);
  const [cfgActive, setCfgActive] = useState(5);
  // Level is read-only in the list now; level changes are Zainab-only via the Action menu.
  // click-to-filter on the list columns
  const [fCountry, setFCountry] = useState('');
  const [fCity, setFCity]       = useState('');
  const [fLevel, setFLevel]     = useState(0);
  const [fPlugit, setFPlugit]   = useState('');   // ''|synced|no_plugit_update
  const [fAgent, setFAgent]     = useState<{ id: number; name: string } | null>(null);
  useEffect(() => { if (kpis.low_min) setCfgLow(kpis.low_min); if (kpis.active_min) setCfgActive(kpis.active_min); }, [kpis.low_min, kpis.active_min]);
  const saveCfg = async () => {
    try { await apiPost('/ibs/settings/status-thresholds', { low_min: cfgLow, active_min: cfgActive }); setShowCfg(false); load(); }
    catch { alert('Save failed'); }
  };
  // Add IB (ticket #12)
  const [addOpen, setAddOpen] = useState(false);
  const [addF, setAddF] = useState<any>({ ib_level: 5 });
  const [addBusy, setAddBusy] = useState(false);
  const [addErr, setAddErr] = useState('');
  const createIB = async () => {
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
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search.trim()); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const reqSeq = useRef(0);
  const load = useCallback(async () => {
    const myReq = ++reqSeq.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, search: debouncedSearch, period });
      if (period === 'custom' && dateFrom && dateTo) {
        params.set('date_from', dateFrom);
        params.set('date_to', dateTo);
      }
      if (fCountry) params.set('country', fCountry);
      if (fCity)    params.set('city', fCity);
      if (fLevel)   params.set('ib_level', String(fLevel));
      if (fPlugit)  params.set('plugit', fPlugit);
      if (fAgent)   params.set('sales_agent_id', String(fAgent.id));
      const data = await apiGet(`/ibs?${params}`);
      if (myReq !== reqSeq.current) return;   // a newer request started — ignore this stale response
      setIbs(data.ibs || []);
      setTotal(data.total || 0);
      setKpis({ ...(data.kpis || {}), ...(data.thresholds || {}) });
      // Per-row trading_clients/status AND the active/low/inactive tier tiles all need a
      // heavy all-IB deals scan (~10s cold for all_time), so the backend serves them
      // separately — fetch lazily and merge so the list never waits on it. Rows show a
      // "…" status pill and the tiles show "…" until this lands.
      const bdParams = new URLSearchParams({ period });
      if (period === 'custom' && dateFrom && dateTo) { bdParams.set('date_from', dateFrom); bdParams.set('date_to', dateTo); }
      const pageAgents = (data.ibs || []).map((x: any) => x.agent_id).filter(Boolean);
      if (pageAgents.length) bdParams.set('agents', pageAgents.join(','));
      apiGet(`/ibs/status-breakdown?${bdParams}`).then((bd: any) => {
        if (myReq !== reqSeq.current) return;
        const lowMin = bd.low_min ?? 3, activeMin = bd.active_min ?? 5;
        const tmap = bd.trading || {};
        setIbs((prev: any[]) => prev.map(row => {
          const tc = tmap[String(row.agent_id)];
          if (tc === undefined) return { ...row, trading_clients: 0, status: ibStatusFor(0, lowMin, activeMin) };
          return { ...row, trading_clients: tc, status: ibStatusFor(tc, lowMin, activeMin) };
        }));
        setKpis((prev: any) => ({ ...prev,
          active_ibs: bd.active_ibs, low_ibs: bd.low_ibs,
          inactive_ibs: bd.inactive_ibs, super_inactive_ibs: bd.super_inactive_ibs }));
      }).catch(() => {});
    } catch (e) { console.error(e); }
    if (myReq === reqSeq.current) setLoading(false);
  }, [page, pageSize, sort, debouncedSearch, period, dateFrom, dateTo, fCountry, fCity, fLevel, fPlugit, fAgent]);

  useEffect(() => { load(); }, [load]);

  // another page (clients/leads/transactions) clicked an IB name -> focus it here
  useEffect(() => {
    const h = (e:any) => { const n = e.detail?.ib; if (n) { setSearch(String(n)); setPage(1); } };
    window.addEventListener('ib_focus', h);
    return () => window.removeEventListener('ib_focus', h);
  }, []);

  if (selectedIB !== null) {
    return <IBProfile ibId={selectedIB} onBack={() => setSelectedIB(null)} canChangeLevel={canChangeLevel} />;
  }
  // "View IB portal" — render the real IB Portal (client-facing) as this IB
  if (portalIB) {
    return <IBPortal ibId={portalIB} onBack={() => setPortalIB(null)} />;
  }

  const viewToggle = (
    <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
      {([['list', '🤝 IB List'], ['trades', '📊 All Trades'], ['withdrawals', '💸 Withdrawals']] as [string, string][]).map(([k, l]) => (
        <button key={k} onClick={() => setMainView(k as any)}
          style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${mainView === k ? '#00e5a0' : '#626d80'}`,
            background: mainView === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: mainView === k ? '#00e5a0' : '#888',
            cursor: 'pointer', fontSize: 12.5, fontWeight: 600, fontFamily: 'inherit' }}>{l}</button>
      ))}
    </div>
  );

  const periodBar = (
    <div style={{ display: 'flex', gap: 4, marginBottom: 10, overflowX: 'auto', alignItems: 'center', flexWrap: 'wrap' }}>
      {[['all_time', 'All'], ['today', 'Today'], ['yesterday', 'Yesterday'], ['last_7_days', 'Last 7d'], ['this_week', 'This week'], ['last_week', 'Last week'], ['last_30_days', 'Last 30d'], ['this_month', 'This month'], ['last_month', 'Last month'], ['this_year', 'This year'], ['last_year', 'Last year'], ['custom', 'Custom']].map(([k, l]) => (
        <button key={k} onClick={() => setPeriod(k)}
          style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${period === k ? '#00e5a0' : '#626d80'}`, background: period === k ? 'rgba(0,229,160,0.1)' : 'transparent', color: period === k ? '#00e5a0' : '#555', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap', fontFamily: 'inherit' }}>{l}</button>
      ))}
      {period === 'custom' && (
        <span style={{ display: 'flex', gap: 6 }}>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
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
        <IBWithdrawals onOpenIB={(id: number) => setSelectedIB(id)} />
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
      {/* Period selector */}
      <div style={{ display:'flex', gap:4, marginBottom:8, overflowX:'auto' }}>
        {[['all_time','All time'],['today','Today'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l]) => (
          <button key={k} onClick={() => setPeriod(k)}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${period===k?'#00e5a0':'#626d80'}`, background:period===k?'rgba(0,229,160,0.1)':'transparent', color:period===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
            {l}
          </button>
        ))}
      </div>
      {/* Plugit sync filter (tabs) */}
      <div style={{ display:'flex', gap:6, marginBottom:10, alignItems:'center', flexWrap:'wrap' }}>
        <span style={{ fontSize:10.5, color:'#555', textTransform:'uppercase', letterSpacing:'.5px' }}>Plugit:</span>
        {[['','All'],['synced','✓ Synced by Plugit'],['no_plugit_update','⚠ No Plugit update'],['plugit_only','🔌 Plugit only'],['null','🈳 Null (0 pt)']].map(([k,l]) => (
          <button key={k} onClick={() => { setFPlugit(k); setPage(1); }}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${fPlugit===k?'#ffaa00':'#626d80'}`, background:fPlugit===k?'rgba(255,170,0,0.12)':'transparent', color:fPlugit===k?'#ffaa00':'#888', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>{l}</button>
        ))}
      </div>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginRight: 8 }}>IB System</div>
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search IB name, phone, code..."
          style={{ padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 240, outline: 'none' }}
        />
        <div style={{ display:'flex', gap:4 }}>
          {[{key:'clients',label:'Most Clients'},{key:'volume',label:'Volume'},{key:'commission',label:'Commission'},{key:'new',label:'Newest'},{key:'deposit',label:'Deposits'}].map(s=>(
            <button key={s.key} onClick={()=>{setSort(s.key);setPage(1);}}
              style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${sort===s.key?'#00e5a0':'#626d80'}`,background:sort===s.key?'rgba(0,229,160,0.1)':'transparent',color:sort===s.key?'#00e5a0':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
              {s.label}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <span style={{ color: '#555', fontSize: 11 }}>{total.toLocaleString()} IBs</span>
        <div style={{ position: 'relative' }}>
          <button onClick={() => setShowCfg(v => !v)} title="Define IB status rules"
            style={{ padding: '6px 14px', border: '1px solid #626d80', borderRadius: 8, background: '#373f4d', color: '#888', fontSize: 12, cursor: 'pointer' }}>⚙ Status rules</button>
          {showCfg && (
            <div style={{ position: 'absolute', right: 0, top: '115%', zIndex: 60, background: '#2c333e', border: '1px solid #626d80', borderRadius: 10, padding: 14, width: 280, boxShadow: '0 8px 28px rgba(0,0,0,0.6)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>IB status definition</div>
              <div style={{ fontSize: 10, color: '#666', marginBottom: 10 }}>Based on how many clients traded in the selected period.</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: '#ffaa00', width: 60 }}>Low ≥</span>
                <input type="number" min={1} value={cfgLow} onChange={e => setCfgLow(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: 60, padding: '4px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                <span style={{ fontSize: 10, color: '#555' }}>trading clients</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 11, color: '#00e5a0', width: 60 }}>Active ≥</span>
                <input type="number" min={1} value={cfgActive} onChange={e => setCfgActive(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{ width: 60, padding: '4px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                <span style={{ fontSize: 10, color: '#555' }}>trading clients</span>
              </div>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 10 }}>Super-inactive = 0 trading · Inactive = 1 to Low−1</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={saveCfg} style={{ flex: 1, padding: '6px 0', background: '#00e5a0', border: 'none', borderRadius: 7, color: '#000', fontWeight: 600, fontSize: 12, cursor: 'pointer' }}>Save</button>
                <button onClick={() => setShowCfg(false)} style={{ padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#888', fontSize: 12, cursor: 'pointer' }}>Cancel</button>
              </div>
            </div>
          )}
        </div>
        <button style={{ padding: '6px 14px', border: '1px solid #626d80', borderRadius: 8, background: '#373f4d', color: '#888', fontSize: 12, cursor: 'pointer' }}>Export</button>
        <button onClick={() => { setAddF({ ib_level: 5 }); setAddErr(''); setAddOpen(true); }} style={{ padding: '6px 14px', border: 'none', borderRadius: 8, background: '#00e5a0', color: '#000', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>+ Add IB</button>
      </div>

      {/* Active filter chips (click-to-filter from the table) */}
      {(fCountry || fCity || fLevel || fAgent) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: '#667' }}>Filters:</span>
          {([
            fAgent   ? ['Sales agent', fAgent.name, () => setFAgent(null)] : null,
            fCountry ? ['Country', fCountry, () => setFCountry('')] : null,
            fCity    ? ['City', fCity, () => setFCity('')] : null,
            fLevel   ? ['Level', `L${fLevel}`, () => setFLevel(0)] : null,
          ].filter(Boolean) as [string, string, () => void][]).map(([lbl, val, clear], i) => (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, padding: '3px 10px', borderRadius: 99, background: 'rgba(0,170,255,0.12)', color: '#00aaff', border: '1px solid rgba(0,170,255,0.3)' }}>
              <span style={{ color: '#667' }}>{lbl}:</span> {val}
              <span onClick={() => { clear(); setPage(1); }} style={{ cursor: 'pointer', color: '#88a', fontWeight: 700 }}>✕</span>
            </span>
          ))}
          <button onClick={() => { setFCountry(''); setFCity(''); setFLevel(0); setFAgent(null); setPage(1); }}
            style={{ fontSize: 11, color: '#888', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit' }}>Clear all</button>
        </div>
      )}

      {/* Period selector */}
      <div style={{ display: 'flex', gap: 4, background: '#373f4d', borderRadius: 10, padding: 4, marginBottom: 14, flexWrap: 'wrap' }}>
        {PERIODS.map(p => (
          <button key={p.key} onClick={() => setPeriod(p.key)}
            style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11, cursor: 'pointer', border: period === p.key ? '1px solid #626d80' : 'none', background: period === p.key ? '#2c333e' : 'transparent', color: period === p.key ? '#e0e0e0' : '#555', fontWeight: period === p.key ? 500 : 400, fontFamily: 'inherit' }}>
            {p.label}
          </button>
        ))}
        {period === 'custom' && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
            <span style={{ color: '#555' }}>—</span>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ padding: '3px 8px', background: '#2c333e', border: '1px solid #626d80', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
          </div>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 8, marginBottom: 14 }}>
        {[
          { val: fmtNum(kpis.total_ibs || 0),              lbl: 'Total IBs',          col: '#e0e0e0', sub: '' },
          { val: kpis.active_ibs == null         ? '…' : fmtNum(kpis.active_ibs),         lbl: 'Active IBs',     col: '#00e5a0', sub: `≥${kpis.active_min||5} trading` },
          { val: kpis.low_ibs == null            ? '…' : fmtNum(kpis.low_ibs),            lbl: 'Low IBs',        col: '#ffaa00', sub: `≥${kpis.low_min||3} trading` },
          { val: kpis.inactive_ibs == null       ? '…' : fmtNum(kpis.inactive_ibs),       lbl: 'Inactive IBs',   col: '#ff8800', sub: '1–'+((kpis.low_min||3)-1)+' trading' },
          { val: kpis.super_inactive_ibs == null ? '…' : fmtNum(kpis.super_inactive_ibs), lbl: 'Super-inactive', col: '#ff4d4d', sub: '0 trading' },
          { val: fmtNum(kpis.total_clients || 0),          lbl: 'Total clients',      col: '#00aaff', sub: '' },
          { val: fmtUSD(kpis.total_commission || 0),       lbl: 'Total commission',   col: '#00e5a0', sub: fmtNum(Math.round(kpis.total_volume||0))+' lots' },
          { val: fmtUSD(kpis.total_payoff || 0),           lbl: 'Total payoff',       col: '#ff4d4d', sub: 'withdrawn / transferred' },
        ].map((k, i) => (
          <div key={i} style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 18, fontWeight: 600, color: k.col }}>{k.val}</div>
            <div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{k.lbl}</div>
            {k.sub && <div style={{ fontSize: 9, color: '#444', marginTop: 1 }}>{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* IB Table */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ ...CT.scroll, overflowY: 'visible', flex: 'unset', minHeight: 'unset' }}>
          <table style={{ ...CT.table, minWidth: 1000 }}>
            <thead>
              <tr style={CT.theadTr}>
                {([
                  ['IB Name', 'name', 'left'], ['Phone', '', 'left'], ['Country', '', 'left'], ['Sales agent', '', 'left'], ['Level', '', 'left'], ['IB since', '', 'left'],
                  ['Clients ↕', 'clients', 'right'], ['Accounts', '', 'right'], ['Sub-IBs', '', 'left'],
                  ['Volume (lots) ↕', 'volume', 'right'], ['Commission ↕', 'commission', 'right'],
                  ['Payoff ↕', 'payoff', 'right'], ['Net comm. ↕', 'net', 'right'],
                  ['Unpaid ↕', 'unpaid', 'right'], ['Own balance', '', 'right'], ['Status', '', 'left'], ['Action', '', 'left'],
                ] as [string, string, 'left' | 'right'][]).map(([h, s, align]) => (
                  <th key={h} style={{ ...CT.th(!!s && sort === s, align), cursor: s ? 'pointer' : 'default' }} onClick={() => s && setSort(s)}>
                    {h}{sort === s ? ' ↑' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={16} style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading...</td></tr>
              ) : ibs.map((ib, i) => (
                <tr key={i} onClick={() => setSelectedIB(ib.id)} style={{ ...CT.row(), cursor: 'pointer' }}>
                  <td style={{ ...CT.td, paddingLeft: 16 }}>
                    <div onClick={(e) => openNameMenu(ib, e)} title="View IB portal or open client page"
                      style={{ fontWeight: 500, color: '#4ea1ff', cursor: 'pointer', display: 'inline-block', textDecoration: 'underline', textDecorationStyle: 'dotted' }}>
                      {ib.name || '—'}
                    </div>
                    <div style={{ fontSize: 11, color: '#cfd6e0', display: 'flex', alignItems: 'center', gap: 5 }} title={ib.email || 'no email on record'}>
                      <span style={{ color: '#ff2d78' }}>✉</span>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 190 }}>{ib.email || '—'}</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#00aaff', display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>{ib.ib_code}
                      {ib.plugit_status === 'synced'
                        ? <span title={`Synced from Plugit — ${ib.markup_pips} pips`} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 99, background: 'rgba(0,229,160,0.14)', color: '#00e5a0', border: '1px solid rgba(0,229,160,0.4)' }}>✓ Plugit {ib.markup_pips != null ? `· ${ib.markup_pips}p` : ''}</span>
                        : ib.plugit_status === 'plugit_only'
                        ? <span title="From Plugit — not previously in My1" style={{ fontSize: 9, padding: '1px 6px', borderRadius: 99, background: 'rgba(0,170,255,0.14)', color: '#00aaff', border: '1px solid rgba(0,170,255,0.4)' }}>🔌 Plugit</span>
                        : ib.plugit_status === 'null'
                        ? <span title="Not eligible for commission (staff/scammer) — 0 pt/lot" style={{ fontSize: 9, padding: '1px 6px', borderRadius: 99, background: 'rgba(136,136,136,0.16)', color: '#9aa3b3', border: '1px solid #626d80' }}>🈳 Null · 0pt</span>
                        : ib.plugit_status === 'no_plugit_update'
                        ? <span title="In My1 but not in the Plugit export" style={{ fontSize: 9, padding: '1px 6px', borderRadius: 99, background: 'rgba(255,170,0,0.14)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.4)' }}>⚠ no Plugit</span>
                        : null}
                    </div>
                  </td>
                  <td style={CT.td}><PhoneBadge phone={ib.phone} /></td>
                  <td style={CT.td}>
                    <div style={{ fontSize: 12, cursor: ib.country ? 'pointer' : 'default' }} className={ib.country ? 'hover-underline' : ''}
                      onClick={(e) => { if (!ib.country) return; e.stopPropagation(); setFCountry(ib.country); setPage(1); }} title="Filter by country">{ib.country || '—'}</div>
                    <div style={{ fontSize: 10, color: '#555', cursor: ib.city ? 'pointer' : 'default' }}
                      onClick={(e) => { if (!ib.city) return; e.stopPropagation(); setFCity(ib.city); setPage(1); }} title="Filter by city">{ib.city}</div>
                  </td>
                  <td style={{ ...CT.td, fontSize: 11 }}>
                    {ib.sales_agent
                      ? <span onClick={(e) => {
                            e.stopPropagation();
                            if (fAgent && fAgent.id === ib.sales_agent_id) {
                              window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'sales_agents', agentId: ib.sales_agent_id } }));
                            } else if (ib.sales_agent_id) { setFAgent({ id: ib.sales_agent_id, name: ib.sales_agent }); setPage(1); }
                          }}
                          title={fAgent && fAgent.id === ib.sales_agent_id ? 'Open Sales Agent page' : 'Filter by this sales agent (click again to open page)'}
                          style={{ color: '#00aaff', cursor: 'pointer' }} className="hover-underline">{ib.sales_agent}</span>
                      : <span style={{ color: '#444' }}>—</span>}
                  </td>
                  {/* Level — read-only badge; level changes are Zainab-only via the Action menu.
                       Clicking filters the list by this level. */}
                  <td style={CT.td} onClick={e => e.stopPropagation()}>
                    <span onClick={() => { setFLevel(ib.ib_level); setPage(1); }} title="Filter the list by this level"
                      className="hover-underline"
                      style={{ fontSize: 11, padding: '3px 9px', borderRadius: 7, cursor: 'pointer', whiteSpace: 'nowrap',
                        background: `${levelColor(ib.ib_level)}18`, color: levelColor(ib.ib_level), border: `1px solid ${levelColor(ib.ib_level)}66` }}>
                      IB-{ib.ib_level} · {TIER_NAMES[ib.ib_level]}
                    </span>
                  </td>
                  <td style={{ ...CT.td, fontSize: 11, color: '#9aa3b3', whiteSpace: 'nowrap' }}>{ib.ib_creation_date ? String(ib.ib_creation_date).slice(0, 10) : '—'}</td>
                  <td style={{ ...CT.td, textAlign: 'right', fontWeight: 600 }}>{ib.total_clients}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#666' }}>{ib.active_clients}</td>
                  <td style={CT.td}>
                    {ib.sub_ib_count > 0
                      ? <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff' }}>{ib.sub_ib_count} sub-IBs</span>
                      : <span style={{ color: '#626d80' }}>—</span>}
                  </td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff' }}>{fmtNum(Math.round(ib.total_volume || 0))}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(ib.total_commission || 0)}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: (ib.total_payoff || 0) > 0 ? '#ff4d4d' : '#555', fontWeight: (ib.total_payoff || 0) > 0 ? 600 : 400 }}
                    title="Total the IB has already withdrawn / transferred (from the Operation Log)">
                    {(ib.total_payoff || 0) > 0 ? fmtUSD(ib.total_payoff) : '—'}
                  </td>
                  <td style={{ ...CT.td, textAlign: 'right', fontWeight: 600, color: (ib.net_commission ?? ((ib.total_commission||0)-(ib.total_payoff||0))) < 0 ? '#ff4d4d' : '#00e5a0' }}
                    title="Commission − Payoff (what's left after payouts)">
                    {fmtUSD(ib.net_commission ?? ((ib.total_commission||0)-(ib.total_payoff||0)))}
                  </td>
                  <td style={{ ...CT.td, textAlign: 'right', color: ib.unpaid_commission > 0 ? '#ffaa00' : '#555', fontWeight: ib.unpaid_commission > 0 ? 600 : 400 }}>
                    {ib.unpaid_commission > 0 ? fmtUSD(ib.unpaid_commission) : '—'}
                  </td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#e0e0e0' }}>{fmtUSD(ib.balance)}</td>
                  <td style={CT.td}>
                    {(() => { const s = IB_STATUS[ib.status] || IB_STATUS.pending;
                      const title = ib.status == null ? 'Loading trading activity…' : `${ib.trading_clients||0} client(s) traded this period`;
                      return <span title={title} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: s.bg, color: s.col, fontWeight: 500 }}>{s.label}</span>; })()}
                  </td>
                  <td style={CT.td} onClick={e => e.stopPropagation()}>
                    <button onClick={() => { setActionIB(ib); setActStep('menu'); }}
                      style={{ padding: '4px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#888', cursor: 'pointer', fontSize: 11 }}>
                      Action ▾
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && ibs.length === 0 && (
                <tr><td colSpan={14} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No IBs found</td></tr>
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
              <span style={{ fontSize:16, fontWeight:700, color:'#fff' }}>➕ Add IB</span>
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
                {icon:'⬆', label:`Promote +1 (now IB-${actionIB.ib_level})`, color:'#00e5a0', fn:()=> canChangeLevel ? doIbAction({action:'promote'}) : alert('Only Zainab can change an IB level.')},
                {icon:'⬇', label:'Demote −1 level', color:'#ffaa00', fn:()=> canChangeLevel ? doIbAction({action:'demote'}) : alert('Only Zainab can change an IB level.')},
                {icon:'💰', label:`Pay commission ${fmtUSD(actionIB.unpaid_commission||0)}`, color:'#00aaff', fn:async()=>{ if(window.confirm(`Pay ${fmtUSD(actionIB.unpaid_commission||0)} to ${actionIB.name}?`)){ try{ await apiPost('/ibs/pay-commission',{ib_id:actionIB.id}); }catch{} setActionIB(null); load(); } }},
                {icon:'🎯', label:'Set target', color:'#9966ff', fn:()=>setActStep('target')},
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
        <div onClick={(e) => e.stopPropagation()} style={{ position: 'fixed', top: nameMenu.y, left: nameMenu.x, zIndex: 200,
          background: '#222831', border: '1px solid #4f596b', borderRadius: 10, padding: 6, minWidth: 220, boxShadow: '0 8px 28px rgba(0,0,0,0.5)' }}>
          <div style={{ padding: '4px 10px 8px', fontSize: 11.5, color: '#9aa3b2', borderBottom: '1px solid #373f4d', marginBottom: 4 }}>
            {nameMenu.ib.name || ('IB #' + nameMenu.ib.id)} {nameMenu.ib.ib_code && <span style={{ color: '#666' }}>· {nameMenu.ib.ib_code}</span>}
          </div>
          <button onClick={() => { setPortalIB(nameMenu.ib.id); setNameMenu(null); }} style={menuBtn}>🌐 View IB portal</button>
          <button onClick={() => { setSelectedIB(nameMenu.ib.id); setNameMenu(null); }} style={menuBtn}>📊 IB profile (admin)</button>
          <button onClick={() => goToClient(nameMenu.ib)} disabled={!nameMenu.ib.agent_id}
            style={{ ...menuBtn, opacity: nameMenu.ib.agent_id ? 1 : 0.4, cursor: nameMenu.ib.agent_id ? 'pointer' : 'default' }}
            title={nameMenu.ib.agent_id ? '' : 'No own trading account linked'}>👤 Go to client page</button>
        </div>
      )}
    </div>
  );
}
