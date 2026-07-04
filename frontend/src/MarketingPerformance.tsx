import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const fmt = (n: number) => (n || 0).toLocaleString();
const usd = (n: number) => '$' + Math.round(n || 0).toLocaleString();
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });
const input: React.CSSProperties = { padding: '8px 10px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };

const PERIODS = [
  ['all_time', 'All time'], ['today', 'Today'], ['yesterday', 'Yesterday'],
  ['last_7_days', 'Last 7d'], ['last_30_days', 'Last 30d'], ['this_month', 'This month'],
  ['last_month', 'Last month'], ['this_year', 'This year'], ['last_year', 'Last year'],
] as const;

type Tab = 'closedloop' | 'acquisition' | 'campaigns' | 'value' | 'sales' | 'quality';
const TABS: { key: Tab; label: string }[] = [
  { key: 'closedloop', label: '🏆 Closed-loop ROI' },
  { key: 'acquisition', label: '🌐 Acquisition channels' },
  { key: 'campaigns', label: '📊 Campaign performance' },
  { key: 'value', label: '💎 Customer value' },
  { key: 'sales', label: '📞 Sales activity' },
  { key: 'quality', label: '🧹 Data quality' },
];

// ───────────────────────── Acquisition channels (clients.source — real, TradeSoft-backfilled) ─────────────
const SRC_META: Record<string, { label: string; color: string; icon: string }> = {
  google: { label: 'Google', color: '#4285f4', icon: '🔍' },
  facebook: { label: 'Facebook', color: '#1877f2', icon: '📘' },
  instagram: { label: 'Instagram', color: '#e1306c', icon: '📸' },
  affiliate: { label: 'Affiliate / IB', color: '#00e5a0', icon: '🤝' },
  direct: { label: 'Direct', color: '#ffaa00', icon: '🌐' },
  other: { label: 'Other', color: '#8a93a5', icon: '•' },
};
function srcMeta(s: string) {
  return SRC_META[(s || '').toLowerCase()] || { label: s || '—', color: '#8a93a5', icon: '•' };
}
function Acquisition() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { apiGet('/marketing/client-sources').then(setData).catch(() => {}); }, []);
  if (!data) return <div style={{ color: '#888' }}>Loading acquisition channels…</div>;
  const rows = (data.sources || []) as any[];
  const totC = rows.reduce((a, r) => a + r.clients, 0) || 1;
  const totR = rows.reduce((a, r) => a + r.revenue, 0);
  const totD = rows.reduce((a, r) => a + r.depositors, 0);
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ ...card, background: '#10233a', border: '1px solid #1f4c7a' }}>
        <div style={{ ...cap, color: '#79b8ff' }}>🌐 Where your customers actually came from</div>
        <div style={{ fontSize: 12, color: '#8a93a5' }}>
          Real acquisition source per client (backfilled from the TradeSoft registration source on my.tnfx.co).
          Revenue = lifetime deposits. Clients with no recorded channel show as “(unknown)”.
        </div>
      </div>
      <div style={card}>
        <div style={cap}>Channel breakdown · {fmt(totC)} clients · {fmt(totD)} depositors · {usd(totR)} deposits</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 620 }}>
            <thead><tr style={{ color: '#8a93a5', textAlign: 'right' }}>
              <th style={{ padding: 8, textAlign: 'left' }}>Channel</th>
              <th style={{ padding: 8 }}>Clients</th><th style={{ padding: 8 }}>Share</th>
              <th style={{ padding: 8 }}>Depositors</th><th style={{ padding: 8 }}>Dep %</th>
              <th style={{ padding: 8 }}>Revenue</th><th style={{ padding: 8 }}>$/client</th>
            </tr></thead>
            <tbody>{rows.map((r, i) => {
              const m = srcMeta(r.source);
              const depRate = r.clients ? Math.round((r.depositors / r.clients) * 100) : 0;
              const perC = r.clients ? r.revenue / r.clients : 0;
              return (
                <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4', textAlign: 'right' }}>
                  <td style={{ padding: 8, textAlign: 'left', color: '#e6e9ef', fontWeight: 600 }}>
                    <span style={{ color: m.color }}>{m.icon}</span> {m.label}
                  </td>
                  <td style={{ padding: 8 }}>{fmt(r.clients)}</td>
                  <td style={{ padding: 8, color: '#79b8ff' }}>{Math.round((r.clients / totC) * 100)}%</td>
                  <td style={{ padding: 8 }}>{fmt(r.depositors)}</td>
                  <td style={{ padding: 8, color: '#79b8ff' }}>{depRate}%</td>
                  <td style={{ padding: 8, color: '#00e5a0', fontWeight: 700 }}>{usd(r.revenue)}</td>
                  <td style={{ padding: 8, color: perC >= 50 ? '#00e5a0' : '#ffaa00' }}>{usd(perC)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────── shared closed-loop table (original /performance) ─────────────
function ROITable({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div style={card}>
      <div style={cap}>{title}</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 640 }}>
          <thead><tr style={{ color: '#8a93a5', textAlign: 'right' }}>
            <th style={{ padding: 8, textAlign: 'left' }}>Name</th>
            <th style={{ padding: 8 }}>Leads</th><th style={{ padding: 8 }}>Registered</th>
            <th style={{ padding: 8 }}>Reg %</th><th style={{ padding: 8 }}>Depositors</th>
            <th style={{ padding: 8 }}>Dep %</th><th style={{ padding: 8 }}>Revenue</th>
            <th style={{ padding: 8 }}>$/lead</th>
          </tr></thead>
          <tbody>{(rows || []).map((r, i) => (
            <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4', textAlign: 'right' }}>
              <td style={{ padding: 8, textAlign: 'left', color: '#e6e9ef' }}>{r.name}</td>
              <td style={{ padding: 8 }}>{fmt(r.leads)}</td>
              <td style={{ padding: 8 }}>{fmt(r.registered)}</td>
              <td style={{ padding: 8, color: '#79b8ff' }}>{r.reg_rate}%</td>
              <td style={{ padding: 8 }}>{fmt(r.depositors)}</td>
              <td style={{ padding: 8, color: '#79b8ff' }}>{r.dep_rate}%</td>
              <td style={{ padding: 8, color: '#00e5a0', fontWeight: 700 }}>{usd(r.revenue)}</td>
              <td style={{ padding: 8, color: r.rev_per_lead >= 5 ? '#00e5a0' : '#ffaa00' }}>${r.rev_per_lead}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ClosedLoop() {
  const [data, setData] = useState<any>(null);
  const [capi, setCapi] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState('');
  useEffect(() => {
    apiGet('/marketing/performance').then(setData).catch(() => {});
    apiGet('/meta/deposits/stats').then(setCapi).catch(() => {});
  }, []);
  const sync = async () => {
    setSyncing(true); setSyncMsg('');
    try {
      const r = await apiPost('/meta/deposits/sync', {});
      setSyncMsg(`Sent ${r.sent} deposit conversions to Meta${r.failed ? `, ${r.failed} failed` : ''}.`);
      apiGet('/meta/deposits/stats').then(setCapi).catch(() => {});
    } catch { setSyncMsg('Sync failed'); }
    setSyncing(false);
  };
  if (!data) return <div style={{ color: '#888' }}>Loading performance…</div>;
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ ...card, background: '#10233a', border: '1px solid #1f4c7a' }}>
        <div style={{ ...cap, color: '#79b8ff' }}>📈 Meta CAPI — deposit-value optimization</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ fontSize: 13, color: '#cfd6e4' }}>
            Send your real depositors back to Meta as <b>value conversions</b> so its algorithm finds more depositors.
            <div style={{ fontSize: 12, color: '#8a93a5', marginTop: 4 }}>
              {capi ? <>Eligible: <b style={{ color: '#00e5a0' }}>{fmt(capi.eligible)}</b> depositors worth <b style={{ color: '#00e5a0' }}>{usd(capi.eligible_value)}</b> · already sent: {fmt(capi.already_sent)} · dataset {capi.dataset_id}</> : '…'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {syncMsg && <span style={{ fontSize: 12, color: '#00e5a0' }}>{syncMsg}</span>}
            <button onClick={sync} disabled={syncing || !capi?.configured} style={btn('#79b8ff', '#06192e')}>{syncing ? 'Sending…' : '↗ Send deposit conversions'}</button>
          </div>
        </div>
      </div>
      <ROITable title="🏆 By campaign — who actually produces depositors & revenue" rows={data.by_campaign} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <ROITable title="By channel" rows={data.by_channel} />
        <ROITable title="By country" rows={data.by_country} />
      </div>
      <div style={{ fontSize: 12, color: '#8a93a5' }}>{data.note}</div>
    </div>
  );
}

// ───────────────────────── period bar ─────────────────────────
function PeriodBar({ period, setPeriod, extra }: { period: string; setPeriod: (p: string) => void; extra?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
      <select value={period} onChange={e => setPeriod(e.target.value)} style={input}>
        {PERIODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      {extra}
    </div>
  );
}

// ───────────────────────── Campaign performance ─────────────────────────
function CampaignPerf() {
  const [period, setPeriod] = useState('all_time');
  const [dimension, setDimension] = useState('campaign');
  const [sort, setSort] = useState('funded');
  const [data, setData] = useState<any>(null);
  const load = useCallback(() => {
    setData(null);
    apiGet(`/marketing/campaign-performance?period=${period}&dimension=${dimension}&sort=${sort}`).then(setData).catch(() => {});
  }, [period, dimension, sort]);
  useEffect(() => { load(); }, [load]);
  const t = data?.totals;
  const Th = ({ k, children, l }: any) => (
    <th style={{ padding: 8, textAlign: l ? 'left' : 'right', cursor: 'pointer', color: sort === k ? '#00e5a0' : '#8a93a5' }} onClick={() => setSort(k)}>{children}{sort === k ? ' ▾' : ''}</th>
  );
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <PeriodBar period={period} setPeriod={setPeriod} extra={
        <select value={dimension} onChange={e => setDimension(e.target.value)} style={input}>
          <option value="campaign">By campaign</option>
          <option value="source">By source (FB/IG)</option>
          <option value="country">By country</option>
        </select>
      } />
      {t && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12 }}>
          {[['Leads', fmt(t.leads), '#e6e9ef'], ['Matched', fmt(t.matched), '#79b8ff'], ['Funded', fmt(t.funded), '#00e5a0'], ['Conv %', t.fund_rate + '%', '#79b8ff'], ['Deposits', usd(t.deposits), '#00e5a0'], ['$/lead', '$' + t.rev_per_lead, '#ffaa00']].map(([lab, val, c]: any, i) => (
            <div key={i} style={{ ...card, padding: 12 }}>
              <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase' }}>{lab}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: c }}>{val}</div>
            </div>
          ))}
        </div>
      )}
      <div style={card}>
        <div style={cap}>{dimension === 'campaign' ? 'Per campaign' : dimension === 'source' ? 'Per source' : 'Per country'} — lead → matched → funded → revenue</div>
        {!data ? <div style={{ color: '#888' }}>Loading…</div> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 720 }}>
              <thead><tr><Th k="name" l>Name</Th><Th k="leads">Leads</Th><Th k="matched">Matched</Th><Th k="funded">Funded</Th><Th k="conv">Conv %</Th><th style={{ padding: 8, textAlign: 'right', color: '#8a93a5' }}>Funded/matched</th><Th k="deposits">Deposits</Th><Th k="rev_per_lead">$/lead</Th><th style={{ padding: 8, textAlign: 'right', color: '#8a93a5' }}>Avg dep</th></tr></thead>
              <tbody>{data.rows.map((r: any, i: number) => (
                <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4', textAlign: 'right' }}>
                  <td style={{ padding: 8, textAlign: 'left', color: '#e6e9ef' }}>{r.name}</td>
                  <td style={{ padding: 8 }}>{fmt(r.leads)}</td>
                  <td style={{ padding: 8 }}>{fmt(r.matched)}</td>
                  <td style={{ padding: 8, color: '#00e5a0' }}>{fmt(r.funded)}</td>
                  <td style={{ padding: 8, color: '#79b8ff' }}>{r.fund_rate}%</td>
                  <td style={{ padding: 8 }}>{r.fund_of_matched}%</td>
                  <td style={{ padding: 8, color: '#00e5a0', fontWeight: 700 }}>{usd(r.deposits)}</td>
                  <td style={{ padding: 8, color: r.rev_per_lead >= 5 ? '#00e5a0' : '#ffaa00' }}>${r.rev_per_lead}</td>
                  <td style={{ padding: 8 }}>{usd(r.avg_deposit)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </div>
      {data && <div style={{ fontSize: 12, color: '#8a93a5' }}>{data.note}</div>}
    </div>
  );
}

// ───────────────────────── Customer value / retention ─────────────────────────
function CustomerValue() {
  const [period, setPeriod] = useState('all_time');
  const [data, setData] = useState<any>(null);
  useEffect(() => { setData(null); apiGet(`/marketing/customer-value?period=${period}`).then(setData).catch(() => {}); }, [period]);
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <PeriodBar period={period} setPeriod={setPeriod} />
      <div style={card}>
        <div style={cap}>💎 Customer value & retention per campaign — CLV = Σ deposits of acquired clients</div>
        {!data ? <div style={{ color: '#888' }}>Loading…</div> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 760 }}>
              <thead><tr style={{ color: '#8a93a5', textAlign: 'right' }}>
                <th style={{ padding: 8, textAlign: 'left' }}>Campaign</th>
                <th style={{ padding: 8 }}>Funded clients</th><th style={{ padding: 8 }}>Total CLV</th>
                <th style={{ padding: 8 }}>Avg CLV</th><th style={{ padding: 8 }}>Deposits</th>
                <th style={{ padding: 8 }}>Repeat depositors</th><th style={{ padding: 8 }}>Repeat %</th>
                <th style={{ padding: 8 }}>First dep</th><th style={{ padding: 8 }}>Last dep</th>
              </tr></thead>
              <tbody>{data.rows.map((r: any, i: number) => (
                <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4', textAlign: 'right' }}>
                  <td style={{ padding: 8, textAlign: 'left', color: '#e6e9ef' }}>{r.campaign}</td>
                  <td style={{ padding: 8 }}>{fmt(r.funded_clients)}</td>
                  <td style={{ padding: 8, color: '#00e5a0', fontWeight: 700 }}>{usd(r.clv)}</td>
                  <td style={{ padding: 8, color: '#00e5a0' }}>{usd(r.avg_clv)}</td>
                  <td style={{ padding: 8 }}>{fmt(r.deposits)}</td>
                  <td style={{ padding: 8 }}>{fmt(r.repeat_depositors)}</td>
                  <td style={{ padding: 8, color: '#79b8ff' }}>{r.repeat_rate}%</td>
                  <td style={{ padding: 8, fontSize: 12 }}>{r.first_deposit || '—'}</td>
                  <td style={{ padding: 8, fontSize: 12 }}>{r.last_deposit || '—'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </div>
      {data && <div style={{ fontSize: 12, color: '#8a93a5' }}>{data.note}</div>}
    </div>
  );
}

// ───────────────────────── Sales activity (Power Dialer) ─────────────────────────
function SalesActivity() {
  const [period, setPeriod] = useState('all_time');
  const [data, setData] = useState<any>(null);
  useEffect(() => { setData(null); apiGet(`/marketing/sales-activity?period=${period}`).then(setData).catch(() => {}); }, [period]);
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <PeriodBar period={period} setPeriod={setPeriod} />
      {!data ? <div style={{ color: '#888' }}>Loading…</div> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12 }}>
            {[['Calls', fmt(data.calls), '#e6e9ef'], ['Connected', fmt(data.connected), '#00e5a0'], ['No answer', fmt(data.no_answer), '#ffaa00'], ['Connect rate', data.connect_rate + '%', '#79b8ff']].map(([lab, val, c]: any, i) => (
              <div key={i} style={{ ...card, padding: 14 }}>
                <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase' }}>{lab}</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: c }}>{val}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={card}>
              <div style={cap}>By outcome</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <tbody>{(data.by_outcome || []).map((o: any, i: number) => (
                  <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4' }}>
                    <td style={{ padding: 7 }}>{o.outcome}</td>
                    <td style={{ padding: 7, textAlign: 'right' }}>{fmt(o.count)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
            <div style={card}>
              <div style={cap}>By agent</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <tbody>{(data.by_agent || []).map((a: any, i: number) => (
                  <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4' }}>
                    <td style={{ padding: 7 }}>{a.agent}</td>
                    <td style={{ padding: 7, textAlign: 'right' }}>{fmt(a.calls)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </div>
          <div style={{ fontSize: 12, color: '#8a93a5' }}>Source: Power Dialer call logs. Outcomes captured by the dialer; connected = answered/interested/callback.</div>
        </>
      )}
    </div>
  );
}

// ───────────────────────── Data quality ─────────────────────────
function DataQuality() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { apiGet('/marketing/data-quality').then(setData).catch(() => {}); }, []);
  if (!data) return <div style={{ color: '#888' }}>Loading…</div>;
  const SampleTable = ({ title, rows, cols }: { title: string; rows: any[]; cols: [string, string][] }) => (
    <div style={card}>
      <div style={cap}>{title}</div>
      {(!rows || !rows.length) ? <div style={{ color: '#5d6675', fontSize: 13 }}>None 🎉</div> : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr style={{ color: '#8a93a5' }}>{cols.map(([, l], i) => <th key={i} style={{ padding: 7, textAlign: 'left' }}>{l}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4' }}>
              {cols.map(([k], j) => <td key={j} style={{ padding: 7 }}>{String(r[k] ?? '—')}</td>)}
            </tr>))}</tbody>
        </table>
      )}
    </div>
  );
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div style={{ ...card, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase' }}>Lead data-quality score</div>
          <div style={{ fontSize: 30, fontWeight: 800, color: data.quality_score >= 90 ? '#00e5a0' : data.quality_score >= 75 ? '#ffaa00' : '#ff6b6b' }}>{data.quality_score}%</div>
        </div>
        <div style={{ fontSize: 13, color: '#8a93a5' }}>Across <b style={{ color: '#e6e9ef' }}>{fmt(data.total_leads)}</b> leads</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 12 }}>
        {data.metrics.map((m: any, i: number) => (
          <div key={i} style={{ ...card, padding: 14 }}>
            <div style={{ fontSize: 11, color: '#8a93a5' }}>{m.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: m.count ? '#ffaa00' : '#00e5a0' }}>{fmt(m.count)}<span style={{ fontSize: 12, color: '#8a93a5', fontWeight: 400 }}> · {m.pct}%</span></div>
            {m.groups != null && <div style={{ fontSize: 11, color: '#5d6675' }}>{fmt(m.groups)} groups</div>}
          </div>
        ))}
      </div>
      <SampleTable title="Duplicate phone (sample)" rows={data.samples.dup_phone} cols={[['phone', 'Phone'], ['n', 'Count'], ['example', 'Example name']]} />
      <SampleTable title="Duplicate email (sample)" rows={data.samples.dup_email} cols={[['email', 'Email'], ['n', 'Count'], ['example', 'Example name']]} />
      <SampleTable title="Invalid phone (<8 digits, sample)" rows={data.samples.invalid_phone} cols={[['id', 'Lead ID'], ['full_name', 'Name'], ['phone', 'Phone']]} />
    </div>
  );
}

// ───────────────────────── shell with tabs ─────────────────────────
export default function MarketingPerformance() {
  const [tab, setTab] = useState<Tab>('closedloop');
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderBottom: '1px solid #373f4d', paddingBottom: 4 }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '8px 14px', background: tab === t.key ? '#00e5a01a' : 'transparent',
            border: 'none', borderBottom: tab === t.key ? '2px solid #00e5a0' : '2px solid transparent',
            color: tab === t.key ? '#00e5a0' : '#8a93a5', fontSize: 13, fontWeight: 700, cursor: 'pointer',
          }}>{t.label}</button>
        ))}
      </div>
      {tab === 'closedloop' && <ClosedLoop />}
      {tab === 'acquisition' && <Acquisition />}
      {tab === 'campaigns' && <CampaignPerf />}
      {tab === 'value' && <CustomerValue />}
      {tab === 'sales' && <SalesActivity />}
      {tab === 'quality' && <DataQuality />}
    </div>
  );
}
