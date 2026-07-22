import React, { useState, useEffect, useCallback } from 'react';
import { apiGet } from './api';
import { CT } from './crmTable';

// ── Performance / KPI report (ticket #45) ─────────────────────────────────────
// Company KPIs for the selected period vs the previous comparable period, with a
// per-method withdrawal breakdown, deposits-by-type cards, and a CSV export.

const PERIODS: [string, string][] = [
  ['today', 'Today'],
  ['this_week', 'This week'],
  ['this_month', 'This month'],
  ['last_month', 'Last month'],
  ['this_year', 'This year'],
  ['last_year', 'Last year'],
  ['all_time', 'All time'],
];

const fmtUSD = (n: number) =>
  (n < 0 ? '-$' : '$') + Math.abs(Math.round(n || 0)).toLocaleString('en-GB');
const fmtNum = (n: number) => (n || 0).toLocaleString('en-GB');

// KPI display config. `money`=format as $; `inverse`=a RISE is BAD (red), e.g. withdrawals.
const KPI_DEFS: { key: string; label: string; money?: boolean; inverse?: boolean }[] = [
  { key: 'deposits', label: 'Deposits', money: true },
  { key: 'withdrawals', label: 'Withdrawals', money: true, inverse: true },
  { key: 'net', label: 'Net deposit', money: true },
  { key: 'new_clients', label: 'New clients (first deposit)' },
  { key: 'active_traders', label: 'Active traders (depositing)' },
  { key: 'ib_commission', label: 'IB commission', money: true, inverse: true },
  { key: 'markup_revenue', label: 'Markup revenue', money: true },
  { key: 'total_clients', label: 'Total clients' },
];

const card: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)',
  border: '1px solid var(--border,#373f4d)',
  borderRadius: 12,
  padding: 16,
};

function pctColor(pct: number | null, inverse?: boolean) {
  if (pct === null || pct === 0) return '#8a93a3';
  const good = inverse ? pct < 0 : pct > 0;
  return good ? '#37d67a' : '#ff5c6c';
}
function pctLabel(pct: number | null) {
  if (pct === null) return '—';
  const s = pct > 0 ? '+' : '';
  return `${s}${pct}%`;
}

// Small current-vs-previous mini bar (two stacked bars normalised to the larger one).
function MiniBars({ current, previous, color }: { current: number; previous: number | null; color: string }) {
  const max = Math.max(Math.abs(current || 0), Math.abs(previous || 0), 1);
  const w = (v: number | null) => `${Math.max(2, (Math.abs(v || 0) / max) * 100)}%`;
  const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, fontSize: 9, color: '#8a93a3' };
  const track: React.CSSProperties = { flex: 1, height: 6, background: '#1f242d', borderRadius: 3, overflow: 'hidden' };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 8 }}>
      <div style={rowStyle}>
        <span style={{ width: 26 }}>now</span>
        <div style={track}><div style={{ width: w(current), height: '100%', background: color }} /></div>
      </div>
      <div style={rowStyle}>
        <span style={{ width: 26 }}>prev</span>
        <div style={track}><div style={{ width: w(previous), height: '100%', background: '#4a5160' }} /></div>
      </div>
    </div>
  );
}

function KpiCard({ def, kpi }: { def: typeof KPI_DEFS[0]; kpi: any }) {
  if (!kpi) return null;
  const fmt = def.money ? fmtUSD : fmtNum;
  const col = pctColor(kpi.pct_change, def.inverse);
  return (
    <div style={card}>
      <div style={{ fontSize: 10, color: '#8a93a3', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        {def.label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#e6e9ef' }}>{fmt(kpi.current)}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: col }}>{pctLabel(kpi.pct_change)}</span>
        <span style={{ fontSize: 10, color: '#8a93a3' }}>
          vs prev {kpi.previous === null || kpi.previous === undefined ? '—' : fmt(kpi.previous)}
        </span>
      </div>
      <MiniBars current={kpi.current} previous={kpi.previous} color={col === '#8a93a3' ? '#5b9dff' : col} />
    </div>
  );
}

// click-to-sort helper for the breakdown tables
function sortRows(rows: any[], key: string, dir: string) {
  const m = dir === 'asc' ? 1 : -1;
  return [...(rows || [])].sort((a, b) => key === 'method'
    ? m * String(a.method || '').localeCompare(String(b.method || ''))
    : m * ((a[key] || 0) - (b[key] || 0)));
}

export default function ReportsKpi() {
  const [period, setPeriod] = useState('this_month');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [wSort, setWSort] = useState({ k: 'value', dir: 'desc' });   // withdrawals-by-method sort

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/reports/kpi?period=${period}`)
      .then((d: any) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const downloadCsv = () => {
    if (!data) return;
    const lines: string[] = [];
    const esc = (v: any) => {
      const s = String(v ?? '');
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    lines.push(`Performance Report,period=${data.period?.key},${data.period?.from} to ${data.period?.to}`);
    lines.push('');
    lines.push('KPI,Current,Previous,% Change');
    KPI_DEFS.forEach((d) => {
      const k = data.kpis?.[d.key];
      if (!k) return;
      lines.push([esc(d.label), esc(k.current), esc(k.previous), esc(k.pct_change)].join(','));
    });
    // counts
    ['deposit_count', 'withdrawal_count'].forEach((key) => {
      const k = data.kpis?.[key];
      if (k) lines.push([esc(key), esc(k.current), esc(k.previous), esc(k.pct_change)].join(','));
    });
    lines.push('');
    lines.push('Withdrawals by method,Count,Value');
    (data.withdrawals_by_method || []).forEach((r: any) =>
      lines.push([esc(r.method), esc(r.count), esc(r.value)].join(',')));
    lines.push('');
    lines.push('Deposits by type,Count,Value');
    (data.deposits_by_type || []).forEach((r: any) =>
      lines.push([esc(r.method), esc(r.count), esc(r.value)].join(',')));

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `performance_report_${data.period?.key}_${data.period?.from}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const kpis = data?.kpis || {};

  return (
    <div style={{ padding: 16, color: '#e6e9ef', height: '100%', overflow: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>📊 Performance Report</h2>
        <div style={{ flex: 1 }} />
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          style={{
            background: 'var(--bg-card,#2c333e)', color: '#e6e9ef',
            border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '8px 12px', fontSize: 13,
          }}
        >
          {PERIODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <button
          onClick={downloadCsv}
          disabled={!data}
          style={{
            background: '#2d6cdf', color: '#fff', border: 'none', borderRadius: 8,
            padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: data ? 'pointer' : 'not-allowed',
          }}
        >
          ⬇ Download CSV
        </button>
      </div>

      {data?.period && (
        <div style={{ fontSize: 12, color: '#8a93a3', marginBottom: 14 }}>
          {data.period.from} → {data.period.to}
          {data.previous_period
            ? ` · compared to ${data.previous_period.from} → ${data.previous_period.to}`
            : ' · no comparison period (all-time)'}
        </div>
      )}

      {loading && <div style={{ color: '#8a93a3', padding: 20 }}>Loading…</div>}

      {!loading && data && (
        <>
          {/* KPI cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginBottom: 22 }}>
            {KPI_DEFS.map((d) => <KpiCard key={d.key} def={d} kpi={kpis[d.key]} />)}
          </div>

          {/* Breakdowns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
            {/* Withdrawals by method */}
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Withdrawals by method</div>
              <div style={CT.scroll}>
                <table style={CT.table}>
                  <thead>
                    <tr style={CT.theadTr}>
                      {([['method', 'Method', 'left'], ['count', 'Count', 'right'], ['value', 'Value', 'right']] as const).map(([k, label, al]) => (
                        <th key={k} onClick={() => setWSort(s => s.k === k ? { k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { k, dir: 'desc' })}
                          style={{ ...CT.th(wSort.k === k, al), cursor: 'pointer' }}>
                          {label}{wSort.k === k ? (wSort.dir === 'asc' ? ' ↑' : ' ↓') : ' ⇅'}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(data.withdrawals_by_method || []).length === 0 && (
                      <tr><td colSpan={3} style={{ ...CT.td, color: '#8a93a3' }}>No withdrawals in period</td></tr>
                    )}
                    {sortRows(data.withdrawals_by_method || [], wSort.k, wSort.dir).map((r: any) => (
                      <tr key={r.method} style={CT.row()}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                        <td style={CT.td}>{r.method}</td>
                        <td style={{ ...CT.td, textAlign: 'right' }}>{fmtNum(r.count)}</td>
                        <td style={{ ...CT.td, textAlign: 'right', color: '#ff8a93' }}>{fmtUSD(r.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Deposits by type */}
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Deposits by type</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
                {(data.deposits_by_type || []).length === 0 && (
                  <div style={{ color: '#8a93a3', fontSize: 12 }}>No deposits in period</div>
                )}
                {(data.deposits_by_type || []).map((r: any) => (
                  <div key={r.method} style={{ background: 'var(--bg-card2,#262c36)', border: '1px solid var(--border,#373f4d)', borderRadius: 9, padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#8a93a3', marginBottom: 4 }}>{r.method}</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#37d67a' }}>{fmtUSD(r.value)}</div>
                    <div style={{ fontSize: 10, color: '#8a93a3', marginTop: 2 }}>{fmtNum(r.count)} txns</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
