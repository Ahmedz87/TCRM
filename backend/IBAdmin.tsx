import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';

const PERIODS = [
  { key: 'this_week',   label: 'This week' },
  { key: 'last_week',   label: 'Last week' },
  { key: 'this_month',  label: 'This month' },
  { key: 'last_month',  label: 'Last month' },
  { key: 'this_year',   label: 'This year' },
  { key: 'last_year',   label: 'Last year' },
  { key: 'custom',      label: 'Custom' },
];

const levelColor = (l: number) => l >= 9 ? '#ff4d4d' : l >= 7 ? '#ffaa00' : '#00e5a0';
const fmtUSD = (n: number) => '$' + Math.round(n).toLocaleString();
const fmtNum = (n: number) => n.toLocaleString();

const thStyle: React.CSSProperties = {
  padding: '9px 10px', textAlign: 'left', color: '#555', fontWeight: 500,
  fontSize: 11, borderBottom: '1px solid #1a1d24', whiteSpace: 'nowrap', cursor: 'pointer',
};
const tdStyle: React.CSSProperties = {
  padding: '9px 10px', borderBottom: '1px solid #111318', verticalAlign: 'middle',
};

// ─── IB PROFILE PAGE ────────────────────────────────────────────────────────
function IBProfile({ ibId, onBack }: { ibId: number; onBack: () => void }) {
  const [ib, setIb]         = useState<any>(null);
  const [tab, setTab]       = useState('clients');
  const [period, setPeriod] = useState('this_month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]     = useState('');
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
      const data = await apiGet(`/ibs/${ibId}?${params}`);
      setIb(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [ibId, period, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

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
    const newLevel = window.prompt(`Current level: ${ib.ib_level}\nEnter new level (5-10):`, String(ib.ib_level));
    if (!newLevel) return;
    try {
      await apiPost('/ibs/promote', { ib_id: ibId, new_level: parseInt(newLevel) });
      await load();
    } catch (e) { alert('Promotion failed'); }
  };

  if (loading) return <div style={{ color: '#555', padding: 40, textAlign: 'center' }}>Loading...</div>;
  if (!ib) return <div style={{ color: '#555', padding: 40, textAlign: 'center' }}>IB not found</div>;

  const tabs = ['clients', 'leads', 'commission', 'sub_ibs', 'referral_links'];
  const tabLabels: any = {
    clients: `Clients (${ib.total_clients || 0})`,
    leads: 'Leads',
    commission: 'Commission',
    sub_ibs: `Sub-IBs (${ib.funnel?.sub_ibs || 0})`,
    referral_links: 'Referral links',
  };

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0 }}>
      {/* Back */}
      <button onClick={onBack} style={{ background: 'transparent', border: '1px solid #333', borderRadius: 8, color: '#888', padding: '6px 14px', cursor: 'pointer', fontSize: 12, marginBottom: 14 }}>
        ← Back to IB list
      </button>

      {/* Header */}
      <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, padding: 16, marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
          <div style={{ width: 50, height: 50, borderRadius: '50%', background: '#0e3a2a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 600, color: '#00e5a0', flexShrink: 0 }}>
            {(ib.name || '?').substring(0, 2).toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 17, fontWeight: 600 }}>{ib.name}</span>
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff' }}>{ib.ib_code}</span>
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${levelColor(ib.ib_level)}22`, color: levelColor(ib.ib_level) }}>L{ib.ib_level} · {ib.ib_level}pts/lot</span>
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0e3a2a', color: '#00e5a0' }}>Active</span>
            </div>
            <div style={{ color: '#666', marginTop: 4 }}>{ib.phone} &nbsp;·&nbsp; {ib.country}{ib.city ? `, ${ib.city}` : ''}</div>
            <div style={{ color: '#666', marginTop: 2 }}>Group: <span style={{ color: '#e0e0e0' }}>{ib.group_name}</span> &nbsp;·&nbsp; Account: <span style={{ color: '#00e5a0' }}>#{ib.agent_id}</span> &nbsp;·&nbsp; Balance: <span style={{ color: '#00e5a0' }}>{fmtUSD(ib.balance)}</span></div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
            <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
              style={{ padding: '6px 14px', background: ib.unpaid_commission > 0 ? '#00e5a0' : '#1a1d24', color: ib.unpaid_commission > 0 ? '#000' : '#555', border: 'none', borderRadius: 8, fontSize: 12, cursor: ib.unpaid_commission > 0 ? 'pointer' : 'default', fontWeight: 500 }}>
              {paying ? 'Paying...' : `Pay ${fmtUSD(ib.unpaid_commission)}`}
            </button>
            <button onClick={handlePromote} style={{ padding: '5px 12px', background: '#1a1d24', border: '1px solid #333', borderRadius: 8, color: '#888', fontSize: 12, cursor: 'pointer' }}>
              Promote level
            </button>
            <button style={{ padding: '5px 12px', background: '#3a0e0e', border: '1px solid #ff4d4d', borderRadius: 8, color: '#ff4d4d', fontSize: 12, cursor: 'pointer' }}>
              Suspend
            </button>
          </div>
        </div>

        {/* Period selector */}
        <div style={{ display: 'flex', gap: 4, background: '#1a1d24', borderRadius: 10, padding: 4, marginTop: 14, flexWrap: 'wrap' }}>
          {PERIODS.map(p => (
            <button key={p.key} onClick={() => setPeriod(p.key)}
              style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11, cursor: 'pointer', border: period === p.key ? '1px solid #333' : 'none', background: period === p.key ? '#111318' : 'transparent', color: period === p.key ? '#e0e0e0' : '#555', fontWeight: period === p.key ? 500 : 400, fontFamily: 'inherit' }}>
              {p.label}
            </button>
          ))}
          {period === 'custom' && (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 4px' }}>
              <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                style={{ padding: '3px 8px', background: '#111318', border: '1px solid #333', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
              <span style={{ color: '#555' }}>—</span>
              <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                style={{ padding: '3px 8px', background: '#111318', border: '1px solid #333', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
            </div>
          )}
        </div>

        {/* Funnel KPIs */}
        <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginTop: 14, marginBottom: 8 }}>Referral funnel</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 14 }}>
          {[
            { val: fmtNum(ib.funnel?.clicks || 0),         lbl: 'Total clicks',      col: '#00aaff',  sub: 'Referral link clicks' },
            { val: fmtNum(ib.funnel?.leads || 0),           lbl: 'Total leads',       col: '#e0e0e0',  sub: 'Registered accounts' },
            { val: fmtNum(ib.funnel?.verified_leads || 0),  lbl: 'Verified leads',    col: '#ffaa00',  sub: 'KYC completed' },
            { val: fmtNum(ib.funnel?.ftd || 0),             lbl: 'Active clients',    col: '#00e5a0',  sub: 'Made a deposit (FTD)' },
            { val: fmtNum(ib.funnel?.sub_ibs || 0),         lbl: 'Sub-IBs',           col: '#e0e0e0',  sub: 'Under this IB' },
          ].map((k, i) => (
            <div key={i} style={{ background: '#1a1d24', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 18, fontWeight: 600, color: k.col }}>{k.val}</div>
              <div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{k.lbl}</div>
              <div style={{ fontSize: 10, color: '#00e5a0', marginTop: 2 }}>{k.sub}</div>
            </div>
          ))}
        </div>

        {/* Trading KPIs */}
        <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 8 }}>Trading & commission ({ib.period?.from} — {ib.period?.to})</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8 }}>
          {[
            { val: fmtNum(ib.total_clients || 0),             lbl: 'Total accounts',      col: '#00aaff' },
            { val: fmtNum(Math.round(ib.period?.volume || 0)),lbl: 'Volume (lots)',        col: '#00aaff' },
            { val: fmtUSD(ib.total_commission || 0),           lbl: 'Total commission',    col: '#00e5a0' },
            { val: fmtUSD(ib.unpaid_commission || 0),          lbl: 'Unpaid',              col: '#ffaa00' },
            { val: fmtUSD(ib.paid_commission || 0),            lbl: 'Paid',                col: '#555'    },
          ].map((k, i) => (
            <div key={i} style={{ background: '#1a1d24', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 18, fontWeight: 600, color: k.col }}>{k.val}</div>
              <div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{k.lbl}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: '#1a1d24', borderRadius: 10, padding: 4, marginBottom: 12 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '7px 14px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: tab === t ? '1px solid #333' : 'none', background: tab === t ? '#111318' : 'transparent', color: tab === t ? '#e0e0e0' : '#666', fontWeight: tab === t ? 500 : 400, fontFamily: 'inherit' }}>
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {/* CLIENTS TAB */}
      {tab === 'clients' && (
        <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
              <thead>
                <tr>
                  {['Client', 'Phone', 'Country', 'Balance', 'Total dep.', 'Total with.', 'KYC', 'Reg date'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(ib.clients || []).map((c: any, i: number) => (
                  <tr key={i} style={{ cursor: 'pointer' }}>
                    <td style={tdStyle}><div style={{ fontWeight: 500 }}>{c.name}</div><div style={{ fontSize: 10, color: '#555' }}>#{c.login}</div></td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.phone}</td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.country}</td>
                    <td style={{ ...tdStyle, color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(c.balance)}</td>
                    <td style={{ ...tdStyle, color: '#00e5a0' }}>{fmtUSD(c.total_dep)}</td>
                    <td style={{ ...tdStyle, color: '#ff4d4d' }}>{fmtUSD(c.total_with)}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0e3a2a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00e5a0' : '#ffaa00' }}>{c.kyc}</span>
                    </td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.reg_date}</td>
                  </tr>
                ))}
                {(ib.clients || []).length === 0 && (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No clients yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* LEADS TAB */}
      {tab === 'leads' && (
        <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, overflow: 'hidden' }}>
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
                    <td style={{ ...tdStyle, color: '#666' }}>{c.phone}</td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.country}</td>
                    <td style={{ ...tdStyle, color: '#666' }}>{c.reg_date}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.kyc === 'verified' ? '#0e3a2a' : '#3a2a0e', color: c.kyc === 'verified' ? '#00e5a0' : '#ffaa00' }}>{c.kyc}</span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.total_dep > 0 ? '#0e3a2a' : '#1a1d24', color: c.total_dep > 0 ? '#00e5a0' : '#555' }}>
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
            <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>Commission summary</div>
              {[
                { label: 'Total earned (all time)', val: fmtUSD(ib.total_commission), col: '#00e5a0' },
                { label: 'Unpaid balance', val: fmtUSD(ib.unpaid_commission), col: '#ffaa00' },
                { label: 'Paid out', val: fmtUSD(ib.paid_commission), col: '#555' },
                { label: `Period (${ib.period?.from} — ${ib.period?.to})`, val: fmtUSD(ib.period?.commission || 0), col: '#00aaff' },
              ].map((r, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: i < 3 ? '1px solid #1a1d24' : 'none' }}>
                  <span style={{ color: '#666' }}>{r.label}</span>
                  <span style={{ color: r.col, fontWeight: 600 }}>{r.val}</span>
                </div>
              ))}
              <button onClick={handlePay} disabled={paying || ib.unpaid_commission <= 0}
                style={{ width: '100%', marginTop: 12, padding: 8, background: ib.unpaid_commission > 0 ? '#00e5a0' : '#1a1d24', color: ib.unpaid_commission > 0 ? '#000' : '#555', border: 'none', borderRadius: 8, fontSize: 13, cursor: ib.unpaid_commission > 0 ? 'pointer' : 'default', fontWeight: 500 }}>
                {paying ? 'Processing...' : `Pay ${fmtUSD(ib.unpaid_commission)}`}
              </button>
            </div>
            <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>Period volume</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#00aaff' }}>{fmtNum(Math.round(ib.period?.volume || 0))}</div>
              <div style={{ fontSize: 11, color: '#555', marginTop: 4 }}>lots traded by clients</div>
              <div style={{ marginTop: 16, fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 8 }}>Active clients this period</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#00e5a0' }}>{ib.period?.active_clients || 0}</div>
            </div>
          </div>

          {/* Commission detail table */}
          <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, overflow: 'hidden' }}>
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
                        <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: c.status === 'paid' ? '#1a1d24' : '#3a2a0e', color: c.status === 'paid' ? '#555' : '#ffaa00' }}>
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
        <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, overflow: 'hidden' }}>
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
                    <td style={tdStyle}><span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: s.status === 'active' ? '#0e3a2a' : '#1a1d24', color: s.status === 'active' ? '#00e5a0' : '#555' }}>{s.status}</span></td>
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
        <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', letterSpacing: '.5px' }}>Referral links & campaigns</div>
            <button style={{ padding: '5px 12px', background: '#00e5a0', color: '#000', border: 'none', borderRadius: 8, fontSize: 11, cursor: 'pointer', fontWeight: 500 }}>+ New link</button>
          </div>
          {(ib.referral_links || []).length === 0 ? (
            <div style={{ textAlign: 'center', color: '#555', padding: 40 }}>No referral links yet</div>
          ) : (ib.referral_links || []).map((l: any, i: number) => (
            <div key={i} style={{ borderBottom: '1px solid #1a1d24', padding: '12px 0' }}>
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
export default function IBAdmin() {
  const [ibs, setIbs]         = useState<any[]>([]);
  const [kpis, setKpis]       = useState<any>({});
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sort, setSort]       = useState('clients');
  const [search, setSearch]   = useState('');
  const [period, setPeriod]   = useState('all_time');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]   = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedIB, setSelectedIB] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, search, period });
      if (period === 'custom' && dateFrom && dateTo) {
        params.set('date_from', dateFrom);
        params.set('date_to', dateTo);
      }
      const data = await apiGet(`/ibs?${params}`);
      setIbs(data.ibs || []);
      setTotal(data.total || 0);
      setKpis(data.kpis || {});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [page, pageSize, sort, search, period, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    apiGet(`/dashboard/kpis?period=${period}`)
      .then((d:any) => setKpis((prev:any) => ({...prev, ...d}))).catch(()=>{});
  }, [period]);

  if (selectedIB !== null) {
    return <IBProfile ibId={selectedIB} onBack={() => setSelectedIB(null)} />;
  }

  return (
    <div>
      {/* Period selector */}
      <div style={{ display:'flex', gap:4, marginBottom:8, overflowX:'auto' }}>
        {[['all_time','All time'],['today','Today'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l]) => (
          <button key={k} onClick={() => setPeriod(k)}
            style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${period===k?'#00e5a0':'#333'}`, background:period===k?'rgba(0,229,160,0.1)':'transparent', color:period===k?'#00e5a0':'#555', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
            {l}
          </button>
        ))}
      </div>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginRight: 8 }}>IB System</div>
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search IB name, phone, code..."
          style={{ padding: '7px 12px', background: '#1a1d24', border: '1px solid #333', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 240, outline: 'none' }}
        />
        <div style={{ flex: 1 }} />
        <span style={{ color: '#555', fontSize: 11 }}>{total.toLocaleString()} IBs</span>
        <button style={{ padding: '6px 14px', border: '1px solid #333', borderRadius: 8, background: '#1a1d24', color: '#888', fontSize: 12, cursor: 'pointer' }}>Export</button>
        <button style={{ padding: '6px 14px', border: 'none', borderRadius: 8, background: '#00e5a0', color: '#000', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>+ Add IB</button>
      </div>

      {/* Period selector */}
      <div style={{ display: 'flex', gap: 4, background: '#1a1d24', borderRadius: 10, padding: 4, marginBottom: 14, flexWrap: 'wrap' }}>
        {PERIODS.map(p => (
          <button key={p.key} onClick={() => setPeriod(p.key)}
            style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11, cursor: 'pointer', border: period === p.key ? '1px solid #333' : 'none', background: period === p.key ? '#111318' : 'transparent', color: period === p.key ? '#e0e0e0' : '#555', fontWeight: period === p.key ? 500 : 400, fontFamily: 'inherit' }}>
            {p.label}
          </button>
        ))}
        {period === 'custom' && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ padding: '3px 8px', background: '#111318', border: '1px solid #333', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
            <span style={{ color: '#555' }}>—</span>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ padding: '3px 8px', background: '#111318', border: '1px solid #333', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
          </div>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 8, marginBottom: 14 }}>
        {[
          { val: fmtNum(kpis.total_ibs || 0),             lbl: 'Total IBs',             col: '#e0e0e0' },
          { val: fmtNum(kpis.total_clients || 0),          lbl: 'Total clients',          col: '#00e5a0' },
          { val: fmtNum(Math.round(kpis.period_volume||0)),lbl: 'Total lots',             col: '#00aaff' },
          { val: fmtUSD(kpis.period_commission || 0),      lbl: 'Commission (period)',    col: '#00e5a0' },
          { val: fmtUSD(kpis.total_unpaid || 0),           lbl: 'Unpaid commission',      col: '#ffaa00' },
          { val: fmtNum(kpis.total_sub_ibs || 0),          lbl: 'Sub-IBs',                col: '#e0e0e0' },
        ].map((k, i) => (
          <div key={i} style={{ background: '#111318', border: '1px solid #222', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 18, fontWeight: 600, color: k.col }}>{k.val}</div>
            <div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{k.lbl}</div>
          </div>
        ))}
      </div>

      {/* IB Table */}
      <div style={{ background: '#111318', border: '1px solid #222', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1000 }}>
            <thead>
              <tr>
                {[
                  ['IB Name', 'name'], ['Phone', ''], ['Country', ''], ['Level', ''],
                  ['Clients ↕', 'clients'], ['Accounts', ''], ['Sub-IBs', ''],
                  ['Volume (lots) ↕', 'volume'], ['Commission ↕', 'commission'],
                  ['Unpaid ↕', 'unpaid'], ['Own balance', ''], ['Status', ''], ['Action', ''],
                ].map(([h, s]) => (
                  <th key={h as string} style={thStyle} onClick={() => s && setSort(s as string)}>
                    {h}{sort === s ? ' ↑' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={13} style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading...</td></tr>
              ) : ibs.map((ib, i) => (
                <tr key={i} onClick={() => setSelectedIB(ib.id)} style={{ cursor: 'pointer' }}>
                  <td style={{ ...tdStyle, paddingLeft: 16 }}>
                    <div style={{ fontWeight: 500 }}>{ib.name}</div>
                    <div style={{ fontSize: 10, color: '#00aaff' }}>{ib.ib_code}</div>
                  </td>
                  <td style={{ ...tdStyle, color: '#666' }}>{ib.phone}</td>
                  <td style={tdStyle}>
                    <div style={{ fontSize: 12 }}>{ib.country}</div>
                    <div style={{ fontSize: 10, color: '#555' }}>{ib.city}</div>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${levelColor(ib.ib_level)}22`, color: levelColor(ib.ib_level) }}>
                      L{ib.ib_level} · {ib.ib_level}pts
                    </span>
                  </td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{ib.total_clients}</td>
                  <td style={{ ...tdStyle, color: '#666' }}>{ib.active_clients}</td>
                  <td style={tdStyle}>
                    {ib.sub_ib_count > 0
                      ? <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff' }}>{ib.sub_ib_count} sub-IBs</span>
                      : <span style={{ color: '#333' }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: '#00aaff' }}>{fmtNum(Math.round(ib.period_volume || 0))}</td>
                  <td style={{ ...tdStyle, color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(ib.period_commission || 0)}</td>
                  <td style={{ ...tdStyle, color: ib.unpaid_commission > 0 ? '#ffaa00' : '#555', fontWeight: ib.unpaid_commission > 0 ? 600 : 400 }}>
                    {ib.unpaid_commission > 0 ? fmtUSD(ib.unpaid_commission) : '—'}
                  </td>
                  <td style={{ ...tdStyle, color: '#e0e0e0' }}>{fmtUSD(ib.balance)}</td>
                  <td style={tdStyle}>
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: ib.status === 'active' ? '#0e3a2a' : '#1a1d24', color: ib.status === 'active' ? '#00e5a0' : '#555' }}>
                      {ib.status}
                    </span>
                  </td>
                  <td style={tdStyle} onClick={e => e.stopPropagation()}>
                    <button onClick={() => setSelectedIB(ib.id)}
                      style={{ padding: '4px 10px', background: '#1a1d24', border: '1px solid #333', borderRadius: 6, color: '#666', cursor: 'pointer', fontSize: 11 }}>
                      View ▾
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && ibs.length === 0 && (
                <tr><td colSpan={13} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No IBs found</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid #1a1d24' }}>
          <span style={{ color: '#555', fontSize: 11 }}>Page {page} · {total.toLocaleString()} IBs</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
              style={{ padding: '3px 6px', background: '#1a1d24', border: '1px solid #333', borderRadius: 5, color: '#888', fontSize: 11 }}>
              {[20, 50, 100].map(s => <option key={s} value={s}>{s}/page</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              style={{ padding: '4px 10px', background: '#1a1d24', border: '1px solid #333', borderRadius: 6, color: page === 1 ? '#333' : '#888', cursor: page === 1 ? 'default' : 'pointer', fontSize: 12 }}>← Prev</button>
            <button onClick={() => setPage(p => p + 1)} disabled={ibs.length < pageSize}
              style={{ padding: '4px 10px', background: '#1a1d24', border: '1px solid #333', borderRadius: 6, color: ibs.length < pageSize ? '#333' : '#888', cursor: ibs.length < pageSize ? 'default' : 'pointer', fontSize: 12 }}>Next →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
